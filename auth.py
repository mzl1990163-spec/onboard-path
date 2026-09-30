import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Cookie, Depends, HTTPException, Request, Response
from ldap3 import ALL, NONE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy.orm import Session

import models
from database import get_db


SESSION_COOKIE = "onboard_admin_session"
SESSION_HOURS = int(os.getenv("ADMIN_SESSION_HOURS", "12"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def _fernet() -> Fernet:
    secret = os.getenv("APP_SECRET_KEY", "change-this-onboardpath-secret")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt((value or "").encode("utf-8")).decode("ascii") if value else ""


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        raise HTTPException(status_code=500, detail="认证源密钥不可用，请检查 APP_SECRET_KEY")


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 位")
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations)
        )
        return secrets.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def create_session(db: Session, user: models.AdminUser, response: Response) -> None:
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.utcnow() + timedelta(hours=SESSION_HOURS)
    db.add(models.AdminSession(token_hash=token_hash, user_id=user.id, expires_at=expires_at))
    user.last_login_at = datetime.utcnow()
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session(db: Session, response: Response, raw_token: Optional[str]) -> None:
    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        db.query(models.AdminSession).filter(models.AdminSession.token_hash == token_hash).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


def find_session_user(db: Session, raw_token: Optional[str]) -> Optional[models.AdminUser]:
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session = db.query(models.AdminSession).filter(models.AdminSession.token_hash == token_hash).first()
    if not session:
        return None
    if session.expires_at <= datetime.utcnow():
        db.delete(session)
        db.commit()
        return None
    if not session.user or not session.user.is_active:
        return None
    return session.user


def get_current_admin(
    db: Session = Depends(get_db),
    onboard_admin_session: Optional[str] = Cookie(default=None),
) -> models.AdminUser:
    user = find_session_user(db, onboard_admin_session)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录管理后台")
    return user


def get_optional_admin(
    db: Session = Depends(get_db),
    onboard_admin_session: Optional[str] = Cookie(default=None),
) -> Optional[models.AdminUser]:
    return find_session_user(db, onboard_admin_session)


def require_superadmin(user: models.AdminUser = Depends(get_current_admin)) -> models.AdminUser:
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="仅超级管理员可以执行此操作")
    return user


def can_manage_category(user: models.AdminUser, category_id: Optional[int]) -> bool:
    if user.role == "superadmin":
        return True
    if category_id is None:
        return False
    return category_id in {category.id for category in user.categories}


def _ldap_server(source: models.AuthSource) -> Server:
    host = source.host.strip()
    if host.startswith("ldap://"):
        host = host[7:]
    elif host.startswith("ldaps://"):
        host = host[8:]
    return Server(host, port=source.port, use_ssl=source.use_ssl, get_info=NONE, connect_timeout=8)


def _service_connection(source: models.AuthSource) -> Connection:
    server = _ldap_server(source)
    connection = Connection(
        server,
        user=source.bind_dn or None,
        password=decrypt_secret(source.bind_password_encrypted) or None,
        auto_bind=False,
        receive_timeout=8,
    )
    connection.open()
    if connection.closed:
        raise RuntimeError("无法连接 LDAP 服务器")
    if source.start_tls and not source.use_ssl and not connection.start_tls():
        raise RuntimeError("LDAP StartTLS 启动失败")
    if not connection.bind():
        raise RuntimeError("LDAP 查询账号验证失败")
    return connection


def lookup_ldap_user(source: models.AuthSource, username: str) -> dict:
    username = (username or "").strip()
    if not username:
        raise ValueError("用户名不能为空")
    connection = None
    try:
        connection = _service_connection(source)
        search_base = source.user_search_base or source.base_dn
        search_filter = (source.user_filter or "({attribute}={username})").replace(
            "{attribute}", source.username_attribute or "sAMAccountName"
        ).replace("{username}", escape_filter_chars(username))
        attributes = list({
            source.username_attribute or "sAMAccountName",
            source.display_name_attribute or "displayName",
            source.created_at_attribute or "whenCreated",
            "objectGUID",
            "entryUUID",
        })
        if not connection.search(search_base, search_filter, attributes=attributes, size_limit=2):
            return {}
        if len(connection.entries) != 1:
            return {}
        entry = connection.entries[0]

        def value_of(name: str):
            if not name or name not in entry.entry_attributes:
                return None
            value = entry[name].value
            return value

        external = value_of("objectGUID") or value_of("entryUUID") or entry.entry_dn
        return {
            "dn": entry.entry_dn,
            "username": str(value_of(source.username_attribute) or username),
            "display_name": str(value_of(source.display_name_attribute) or username),
            "created_at": value_of(source.created_at_attribute),
            "external_id": str(external),
        }
    except LDAPException as exc:
        raise RuntimeError(f"LDAP 查询失败：{exc.__class__.__name__}") from exc
    finally:
        if connection:
            connection.unbind()


def authenticate_ldap_user(source: models.AuthSource, username: str, password: str) -> dict:
    if not password:
        raise ValueError("请输入密码")
    user_info = lookup_ldap_user(source, username)
    if not user_info:
        return {}
    connection = None
    try:
        connection = Connection(
            _ldap_server(source), user=user_info["dn"], password=password,
            auto_bind=False, receive_timeout=8,
        )
        connection.open()
        if connection.closed:
            return {}
        if source.start_tls and not source.use_ssl and not connection.start_tls():
            return {}
        if not connection.bind():
            return {}
        return user_info
    except LDAPException:
        return {}
    finally:
        if connection:
            connection.unbind()


def test_ldap_source(source: models.AuthSource) -> None:
    connection = None
    try:
        connection = _service_connection(source)
    finally:
        if connection:
            connection.unbind()


def parse_ldap_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo is None else value.astimezone(timezone.utc).replace(tzinfo=None)
    text = str(value).strip()
    for pattern in ("%Y%m%d%H%M%S.%fZ", "%Y%m%d%H%M%SZ", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.replace(tzinfo=None) if parsed.tzinfo is None else parsed.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    return None

