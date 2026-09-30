import json
import os
import re
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import List, Literal, Optional
from uuid import uuid4

import bleach
from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

import models
from auth import (
    SESSION_COOKIE,
    authenticate_ldap_user,
    can_manage_category,
    clear_session,
    create_session,
    decrypt_secret,
    encrypt_secret,
    find_session_user,
    get_current_admin,
    hash_password,
    lookup_ldap_user,
    parse_ldap_datetime,
    require_superadmin,
    test_ldap_source,
    verify_password,
)
from database import SessionLocal, engine, get_db

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="OnboardPath")
app.mount("/static", StaticFiles(directory="static"), name="static")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
BACKGROUND_DIR = UPLOAD_DIR / "backgrounds"
BACKGROUND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def ensure_bootstrap_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(models.AdminUser).count() == 0:
            username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin").strip() or "admin"
            password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123!")
            db.add(models.AdminUser(
                username=username,
                display_name="超级管理员",
                auth_type="local",
                password_hash=hash_password(password),
                role="superadmin",
                is_active=True,
            ))
            db.commit()
    finally:
        db.close()


ensure_bootstrap_admin()

ALLOWED_TAGS = [
    "p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "blockquote", "code", "pre", "a",
    "img", "figure", "figcaption", "footer", "mark", "table", "thead", "tbody", "tr", "th", "td", "hr", "span", "div"
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "*": ["class"],
}


def clean_html(value: Optional[str]) -> str:
    return bleach.clean(
        value or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"], strip=True,
    )


def normalize_color(value: Optional[str], fallback: str) -> str:
    value = (value or "").strip()
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def normalize_opacity(value: int, fallback: int) -> int:
    try:
        return min(100, max(0, int(value)))
    except (TypeError, ValueError):
        return fallback


def clean_inline(value: object) -> str:
    return bleach.clean(
        str(value or ""),
        tags=["strong", "b", "em", "i", "u", "s", "a", "mark", "code", "br"],
        attributes={"a": ["href", "title", "target", "rel"]},
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def render_list_items(items: list) -> str:
    rendered = []
    for item in items or []:
        if isinstance(item, dict):
            content = clean_inline(item.get("content") or item.get("text"))
            children = item.get("items") or []
            nested = f"<ul>{render_list_items(children)}</ul>" if children else ""
            rendered.append(f"<li>{content}{nested}</li>")
        else:
            rendered.append(f"<li>{clean_inline(item)}</li>")
    return "".join(rendered)


def render_editor_json(raw: str) -> str:
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    parts = []
    for block in payload.get("blocks", []):
        block_type = block.get("type")
        data = block.get("data") or {}
        if block_type == "paragraph":
            parts.append(f"<p>{clean_inline(data.get('text'))}</p>")
        elif block_type == "header":
            level = int(data.get("level") or 2)
            level = min(max(level, 2), 4)
            parts.append(f"<h{level}>{clean_inline(data.get('text'))}</h{level}>")
        elif block_type == "list":
            tag = "ol" if data.get("style") == "ordered" else "ul"
            parts.append(f"<{tag}>{render_list_items(data.get('items') or [])}</{tag}>")
        elif block_type == "quote":
            caption = clean_inline(data.get("caption"))
            footer = f"<footer>{caption}</footer>" if caption else ""
            parts.append(f"<blockquote>{clean_inline(data.get('text'))}{footer}</blockquote>")
        elif block_type == "code":
            parts.append(f"<pre><code>{escape(str(data.get('code') or ''))}</code></pre>")
        elif block_type == "delimiter":
            parts.append("<hr>")
        elif block_type == "warning":
            parts.append(
                f"<div class=\"doc-warning\"><strong>{clean_inline(data.get('title'))}</strong>"
                f"<p>{clean_inline(data.get('message'))}</p></div>"
            )
        elif block_type == "table":
            rows = data.get("content") or []
            table_rows = []
            for row_index, row in enumerate(rows):
                cell_tag = "th" if data.get("withHeadings") and row_index == 0 else "td"
                cells = "".join(f"<{cell_tag}>{clean_inline(cell)}</{cell_tag}>" for cell in row)
                table_rows.append(f"<tr>{cells}</tr>")
            parts.append(f"<div class=\"doc-table-wrap\"><table>{''.join(table_rows)}</table></div>")
        elif block_type == "image":
            file_data = data.get("file") or {}
            url = str(file_data.get("url") or "")
            if url.startswith("/uploads/") or url.startswith("http://") or url.startswith("https://"):
                caption = clean_inline(data.get("caption"))
                caption_html = f"<figcaption>{caption}</figcaption>" if caption else ""
                parts.append(
                    f"<figure><img src=\"{escape(url, quote=True)}\" alt=\"{escape(bleach.clean(caption, tags=[], strip=True), quote=True)}\">"
                    f"{caption_html}</figure>"
                )
    return clean_html("".join(parts))


class VerifyReq(BaseModel):
    username: str
    position_id: int


class LocalPreviewReq(BaseModel):
    username: str
    password: str
    position_id: int


class AdminLoginReq(BaseModel):
    username: str
    password: str


class AuthSourceSchema(BaseModel):
    name: str
    is_enabled: bool = True
    is_employee_default: bool = False
    host: str
    port: int = 389
    use_ssl: bool = False
    start_tls: bool = False
    base_dn: str
    bind_dn: Optional[str] = ""
    bind_password: Optional[str] = ""
    user_search_base: Optional[str] = ""
    user_filter: Optional[str] = "(&(objectClass=user)(sAMAccountName={username}))"
    username_attribute: Optional[str] = "sAMAccountName"
    display_name_attribute: Optional[str] = "displayName"
    created_at_attribute: Optional[str] = "whenCreated"
    employee_valid_days: int = 14


class AdminUserCreateSchema(BaseModel):
    username: str
    display_name: Optional[str] = ""
    auth_type: Literal["local", "ldap"] = "local"
    password: Optional[str] = ""
    role: Literal["superadmin", "admin"] = "admin"
    is_active: bool = True
    auth_source_id: Optional[int] = None
    category_ids: List[int] = Field(default_factory=list)


class AdminUserUpdateSchema(BaseModel):
    display_name: Optional[str] = ""
    is_active: bool = True
    category_ids: List[int] = Field(default_factory=list)


class PasswordResetSchema(BaseModel):
    password: str


class ConfigSchema(BaseModel):
    login_bg_url: Optional[str] = ""
    login_bg_color: Optional[str] = "#0f172a"
    login_overlay_color: Optional[str] = "#0f172a"
    login_overlay_opacity: int = 65
    login_welcome_title: Optional[str] = "欢迎新同事加入！"
    login_welcome_subtitle: Optional[str] = "在开始办理入职配置前，请先登记您的基础个人信息"
    login_button_text: Optional[str] = "开启我的入职指南 ➔"
    header_bg_url: Optional[str] = ""
    header_bg_color: Optional[str] = "#0f172a"
    header_overlay_color: Optional[str] = "#0f172a"
    header_overlay_opacity: int = 72
    header_title_color: Optional[str] = "#ffffff"
    header_subtitle_color: Optional[str] = "#94a3b8"
    header_title: Optional[str] = "新员工入职落地指引"
    header_subtitle: Optional[str] = ""
    employee_expired_title: Optional[str] = "入职指引访问期已结束"
    employee_expired_message: Optional[str] = "您的新员工入职指引访问期限已结束。如有相关问题，请联系 IT 部门，或者前往钉钉服务台进行咨询。"
    employee_dingtalk_text: Optional[str] = "钉钉服务台"
    employee_dingtalk_url: Optional[str] = ""
    employee_not_found_message: Optional[str] = "未查询到员工信息，请确认姓名全拼或联系 IT 部门。"
    employee_service_error_message: Optional[str] = "认证服务暂时不可用，请稍后重试或联系 IT 部门。"


class CategorySchema(BaseModel):
    name: str
    sort_order: int = 0
    is_active: bool = True


class DepartmentSchema(BaseModel):
    name: str
    sort_order: int = 0
    is_active: bool = True


class PositionSchema(BaseModel):
    name: str
    department_id: int
    sort_order: int = 0
    is_active: bool = True


class DocSaveSchema(BaseModel):
    category_id: Optional[int] = None
    title: str
    content_html: Optional[str] = ""
    content_json: Optional[str] = ""
    dingtalk_url: Optional[str] = ""
    software_name: Optional[str] = ""
    software_sys: Optional[str] = "Windows/Mac"
    download_url: Optional[str] = ""
    extract_code: Optional[str] = ""
    visibility_type: Literal["all", "department", "position"] = "all"
    status: Literal["draft", "published"] = "published"
    sort_order: int = 0
    department_ids: List[int] = Field(default_factory=list)
    position_ids: List[int] = Field(default_factory=list)


@app.get("/")
def read_index():
    return FileResponse("static/index.html")


@app.get("/steps")
@app.get("/guide")
def read_guide():
    return FileResponse("static/guide.html")


@app.get("/admin")
def read_admin(
    onboard_admin_session: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if not find_session_user(db, onboard_admin_session):
        return RedirectResponse("/admin/login", status_code=302)
    return FileResponse("static/admin.html")


@app.get("/admin/login")
def read_admin_login(
    onboard_admin_session: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if find_session_user(db, onboard_admin_session):
        return RedirectResponse("/admin", status_code=302)
    return FileResponse("static/admin-login.html")


def serialize_admin_user(user: models.AdminUser) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "auth_type": user.auth_type,
        "auth_source_id": user.auth_source_id,
        "auth_source_name": user.auth_source.name if user.auth_source else "本地认证",
        "role": user.role,
        "is_active": user.is_active,
        "category_ids": [category.id for category in user.categories],
        "category_names": [category.name for category in user.categories],
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@app.post("/api/admin/login")
def admin_login(data: AdminLoginReq, response: Response, db: Session = Depends(get_db)):
    username = data.username.strip()
    user = db.query(models.AdminUser).filter(models.AdminUser.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户名或密码错误，或者账号未获得后台权限")
    authenticated = False
    if user.auth_type == "local":
        authenticated = verify_password(data.password, user.password_hash)
    elif user.auth_type == "ldap" and user.auth_source and user.auth_source.is_enabled:
        try:
            authenticated = bool(authenticate_ldap_user(user.auth_source, username, data.password))
        except (RuntimeError, ValueError):
            raise HTTPException(status_code=503, detail="LDAP认证服务暂时不可用")
    if not authenticated:
        raise HTTPException(status_code=401, detail="用户名或密码错误，或者账号未获得后台权限")
    create_session(db, user, response)
    return {"status": "ok", "user": serialize_admin_user(user)}


@app.post("/api/admin/logout")
def admin_logout(
    response: Response,
    onboard_admin_session: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
):
    clear_session(db, response, onboard_admin_session)
    return {"status": "ok"}


@app.get("/api/admin/me")
def admin_me(user: models.AdminUser = Depends(get_current_admin)):
    return serialize_admin_user(user)


@app.get("/api/public/config")
def get_config(db: Session = Depends(get_db)):
    cfg = db.query(models.SysConfig).first()
    if not cfg:
        cfg = models.SysConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    departments = (
        db.query(models.Department)
        .options(joinedload(models.Department.positions))
        .filter(models.Department.is_active.is_(True))
        .order_by(models.Department.sort_order, models.Department.id)
        .all()
    )
    dep_list = []
    for department in departments:
        positions = [
            {"id": p.id, "name": p.name}
            for p in department.positions if p.is_active
        ]
        if positions:
            dep_list.append({"id": department.id, "name": department.name, "positions": positions})

    return {
        "config": {
            "login_bg_url": cfg.login_bg_url,
            "login_bg_color": cfg.login_bg_color,
            "login_overlay_color": cfg.login_overlay_color,
            "login_overlay_opacity": cfg.login_overlay_opacity,
            "login_welcome_title": cfg.login_welcome_title,
            "login_welcome_subtitle": cfg.login_welcome_subtitle,
            "login_button_text": cfg.login_button_text,
            "header_bg_url": cfg.header_bg_url,
            "header_bg_color": cfg.header_bg_color,
            "header_overlay_color": cfg.header_overlay_color,
            "header_overlay_opacity": cfg.header_overlay_opacity,
            "header_title_color": cfg.header_title_color,
            "header_subtitle_color": cfg.header_subtitle_color,
            "header_title": cfg.header_title,
            "header_subtitle": cfg.header_subtitle,
            "employee_expired_title": cfg.employee_expired_title,
            "employee_expired_message": cfg.employee_expired_message,
            "employee_dingtalk_text": cfg.employee_dingtalk_text,
            "employee_dingtalk_url": cfg.employee_dingtalk_url,
            "employee_not_found_message": cfg.employee_not_found_message,
            "employee_service_error_message": cfg.employee_service_error_message,
        },
        "departments": dep_list,
    }


@app.post("/api/public/verify-account")
def verify_account(
    req: VerifyReq,
    db: Session = Depends(get_db),
):
    position = (
        db.query(models.Position)
        .join(models.Department)
        .filter(
            models.Position.id == req.position_id,
            models.Position.is_active.is_(True),
            models.Department.is_active.is_(True),
        )
        .first()
    )
    if not position:
        raise HTTPException(status_code=400, detail="所选岗位不存在或已停用")
    admin_record = db.query(models.AdminUser).filter(
        models.AdminUser.username == req.username.strip(),
        models.AdminUser.is_active.is_(True),
    ).first()
    if admin_record:
        auth_label = "本地" if admin_record.auth_type == "local" else "LDAP"
        raise HTTPException(
            status_code=409,
            detail=f"这是管理员账号，已为您切换到管理员预览登录，请输入{auth_label}密码后继续。",
        )

    source = db.query(models.AuthSource).filter(
        models.AuthSource.source_type == "ldap",
        models.AuthSource.is_enabled.is_(True),
        models.AuthSource.is_employee_default.is_(True),
    ).first()
    cfg = db.query(models.SysConfig).first() or models.SysConfig(id=1)
    if not source:
        raise HTTPException(status_code=503, detail=cfg.employee_service_error_message)
    try:
        ldap_user = lookup_ldap_user(source, req.username)
    except (RuntimeError, ValueError):
        raise HTTPException(status_code=503, detail=cfg.employee_service_error_message)
    if not ldap_user:
        raise HTTPException(status_code=404, detail=cfg.employee_not_found_message)
    created_at = parse_ldap_datetime(ldap_user.get("created_at"))
    if not created_at:
        raise HTTPException(status_code=422, detail="无法获取账号创建时间，请联系 IT 管理员。")
    age = datetime.utcnow() - created_at
    if age.total_seconds() < 0:
        raise HTTPException(status_code=422, detail="LDAP账号创建时间异常，请联系 IT 管理员。")
    if age > timedelta(days=source.employee_valid_days):
        return {
            "pass": False,
            "expired": True,
            "title": cfg.employee_expired_title,
            "msg": cfg.employee_expired_message,
            "dingtalk_text": cfg.employee_dingtalk_text,
            "dingtalk_url": cfg.employee_dingtalk_url,
        }
    return {
        "pass": True,
        "display_name": ldap_user.get("display_name") or req.username,
        "days": max(0, int(age.total_seconds() // 86400)),
    }


@app.post("/api/public/local-admin-preview")
@app.post("/api/public/admin-preview-login")
def admin_preview_login(data: LocalPreviewReq, db: Session = Depends(get_db)):
    position = db.get(models.Position, data.position_id)
    if not position or not position.is_active:
        raise HTTPException(status_code=400, detail="所选岗位不存在或已停用")
    user = db.query(models.AdminUser).filter(
        models.AdminUser.username == data.username.strip(),
        models.AdminUser.is_active.is_(True),
    ).first()
    authenticated = False
    if user and user.auth_type == "local":
        authenticated = verify_password(data.password, user.password_hash)
    elif user and user.auth_type == "ldap" and user.auth_source and user.auth_source.is_enabled:
        try:
            authenticated = bool(authenticate_ldap_user(user.auth_source, user.username, data.password))
        except (RuntimeError, ValueError):
            raise HTTPException(status_code=503, detail="LDAP认证服务暂时不可用")
    if not user or not authenticated:
        raise HTTPException(status_code=401, detail="管理员用户名或密码错误")
    return {"pass": True, "admin_preview": True, "display_name": user.display_name or user.username}


def document_is_visible(doc: models.Document, department_id: int, position_id: int) -> bool:
    if doc.visibility_type == "all":
        return True
    if doc.visibility_type == "department":
        return department_id in {d.id for d in doc.departments}
    if doc.visibility_type == "position":
        return position_id in {p.id for p in doc.positions}
    return False


@app.get("/api/public/steps")
def get_steps_data(position_id: int, db: Session = Depends(get_db)):
    position = (
        db.query(models.Position)
        .join(models.Department)
        .filter(
            models.Position.id == position_id,
            models.Position.is_active.is_(True),
            models.Department.is_active.is_(True),
        )
        .first()
    )
    if not position:
        raise HTTPException(status_code=404, detail="岗位不存在或已停用")

    categories = (
        db.query(models.Category)
        .filter(models.Category.is_active.is_(True))
        .order_by(models.Category.sort_order, models.Category.id)
        .all()
    )
    result = []
    for category in categories:
        docs = (
            db.query(models.Document)
            .options(joinedload(models.Document.departments), joinedload(models.Document.positions))
            .filter(
                models.Document.category_id == category.id,
                models.Document.status == "published",
            )
            .order_by(models.Document.sort_order, models.Document.id)
            .all()
        )
        visible_docs = []
        for doc in docs:
            if not document_is_visible(doc, position.department_id, position.id):
                continue
            visible_docs.append({
                "id": doc.id,
                "title": doc.title,
                "content_html": render_editor_json(doc.content_json) if doc.content_json else clean_html(doc.content_html),
                "dingtalk_url": doc.dingtalk_url,
                "software": {
                    "name": doc.software_name,
                    "sys": doc.software_sys,
                    "download_url": doc.download_url,
                    "extract_code": doc.extract_code,
                } if doc.software_name else None,
            })
        if visible_docs:
            result.append({
                "category_id": category.id,
                "category_name": category.name,
                "documents": visible_docs,
            })
    return {"categories": result}


@app.post("/api/admin/config")
def update_config(
    data: ConfigSchema,
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_superadmin),
):
    cfg = db.query(models.SysConfig).first()
    if not cfg:
        cfg = models.SysConfig(id=1)
        db.add(cfg)
    cfg.login_bg_url = data.login_bg_url or ""
    cfg.login_bg_color = normalize_color(data.login_bg_color, "#0f172a")
    cfg.login_overlay_color = normalize_color(data.login_overlay_color, "#0f172a")
    cfg.login_overlay_opacity = normalize_opacity(data.login_overlay_opacity, 65)
    cfg.login_welcome_title = (data.login_welcome_title or "欢迎新同事加入！").strip()
    cfg.login_welcome_subtitle = (data.login_welcome_subtitle or "").strip()
    cfg.login_button_text = (data.login_button_text or "开启我的入职指南 ➔").strip()
    cfg.header_bg_url = data.header_bg_url or ""
    cfg.header_bg_color = normalize_color(data.header_bg_color, "#0f172a")
    cfg.header_overlay_color = normalize_color(data.header_overlay_color, "#0f172a")
    cfg.header_overlay_opacity = normalize_opacity(data.header_overlay_opacity, 72)
    cfg.header_title_color = normalize_color(data.header_title_color, "#ffffff")
    cfg.header_subtitle_color = normalize_color(data.header_subtitle_color, "#94a3b8")
    cfg.header_title = data.header_title or ""
    cfg.header_subtitle = data.header_subtitle or ""
    cfg.employee_expired_title = (data.employee_expired_title or "入职指引访问期已结束").strip()
    cfg.employee_expired_message = (data.employee_expired_message or "").strip()
    cfg.employee_dingtalk_text = (data.employee_dingtalk_text or "钉钉服务台").strip()
    cfg.employee_dingtalk_url = (data.employee_dingtalk_url or "").strip()
    cfg.employee_not_found_message = (data.employee_not_found_message or "").strip()
    cfg.employee_service_error_message = (data.employee_service_error_message or "").strip()
    db.commit()
    return {"status": "ok"}


def serialize_auth_source(source: models.AuthSource) -> dict:
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "is_enabled": source.is_enabled,
        "is_employee_default": source.is_employee_default,
        "host": source.host,
        "port": source.port,
        "use_ssl": source.use_ssl,
        "start_tls": source.start_tls,
        "base_dn": source.base_dn,
        "bind_dn": source.bind_dn,
        "has_bind_password": bool(source.bind_password_encrypted),
        "user_search_base": source.user_search_base,
        "user_filter": source.user_filter,
        "username_attribute": source.username_attribute,
        "display_name_attribute": source.display_name_attribute,
        "created_at_attribute": source.created_at_attribute,
        "employee_valid_days": source.employee_valid_days,
        "user_count": len(source.users),
    }


@app.get("/api/admin/auth-sources")
def list_auth_sources(
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_superadmin),
):
    return [serialize_auth_source(row) for row in db.query(models.AuthSource).order_by(models.AuthSource.id).all()]


def save_auth_source(data: AuthSourceSchema, db: Session, source: Optional[models.AuthSource] = None):
    if data.use_ssl and data.start_tls:
        raise HTTPException(status_code=400, detail="LDAPS 与 StartTLS 不能同时启用")
    if data.is_employee_default and not data.is_enabled:
        raise HTTPException(status_code=400, detail="员工端默认认证源必须保持启用")
    if data.employee_valid_days < 1 or data.employee_valid_days > 365:
        raise HTTPException(status_code=400, detail="员工访问有效期应为 1 至 365 天")
    if "{username}" not in (data.user_filter or ""):
        raise HTTPException(status_code=400, detail="用户查询过滤器必须包含 {username}")
    source = source or models.AuthSource(source_type="ldap")
    source.name = data.name.strip()
    source.is_enabled = data.is_enabled
    source.is_employee_default = data.is_employee_default
    source.host = data.host.strip()
    source.port = data.port
    source.use_ssl = data.use_ssl
    source.start_tls = data.start_tls
    source.base_dn = data.base_dn.strip()
    source.bind_dn = (data.bind_dn or "").strip()
    if data.bind_password:
        source.bind_password_encrypted = encrypt_secret(data.bind_password)
    source.user_search_base = (data.user_search_base or "").strip()
    source.user_filter = (data.user_filter or "").strip()
    source.username_attribute = (data.username_attribute or "sAMAccountName").strip()
    source.display_name_attribute = (data.display_name_attribute or "displayName").strip()
    source.created_at_attribute = (data.created_at_attribute or "whenCreated").strip()
    source.employee_valid_days = data.employee_valid_days
    if data.is_employee_default:
        db.query(models.AuthSource).filter(models.AuthSource.id != (source.id or 0)).update(
            {models.AuthSource.is_employee_default: False}, synchronize_session=False
        )
    db.add(source)
    db.commit()
    db.refresh(source)
    return {"status": "ok", "id": source.id}


@app.post("/api/admin/auth-sources")
def create_auth_source(
    data: AuthSourceSchema,
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_superadmin),
):
    return save_auth_source(data, db)


@app.put("/api/admin/auth-sources/{source_id}")
def update_auth_source(
    source_id: int,
    data: AuthSourceSchema,
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_superadmin),
):
    source = db.get(models.AuthSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="LDAP认证源不存在")
    return save_auth_source(data, db, source)


@app.post("/api/admin/auth-sources/{source_id}/test")
def test_auth_source_endpoint(
    source_id: int,
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_superadmin),
):
    source = db.get(models.AuthSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="LDAP认证源不存在")
    try:
        test_ldap_source(source)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "message": "LDAP连接和查询账号验证成功"}


@app.delete("/api/admin/auth-sources/{source_id}")
def delete_auth_source(
    source_id: int,
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_superadmin),
):
    source = db.get(models.AuthSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="LDAP认证源不存在")
    if source.users:
        raise HTTPException(status_code=409, detail=f"该认证源仍有 {len(source.users)} 个后台用户，请先处理关联用户")
    db.delete(source)
    db.commit()
    return {"status": "ok"}


@app.get("/api/admin/users")
def list_admin_users(
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_superadmin),
):
    return [serialize_admin_user(row) for row in db.query(models.AdminUser).order_by(models.AdminUser.id).all()]


@app.post("/api/admin/users")
def create_admin_user(
    data: AdminUserCreateSchema,
    db: Session = Depends(get_db),
    _: models.AdminUser = Depends(require_superadmin),
):
    username = data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="请输入用户名")
    if db.query(models.AdminUser).filter(models.AdminUser.username == username).first():
        raise HTTPException(status_code=409, detail="该用户名已存在")
    if data.auth_type == "ldap" and data.role == "superadmin":
        raise HTTPException(status_code=400, detail="LDAP用户不能设置为超级管理员")
    user = models.AdminUser(
        username=username,
        display_name=(data.display_name or "").strip(),
        auth_type=data.auth_type,
        role=data.role,
        is_active=data.is_active,
    )
    if data.auth_type == "local":
        try:
            user.password_hash = hash_password(data.password or "")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        source = db.get(models.AuthSource, data.auth_source_id)
        if not source or not source.is_enabled:
            raise HTTPException(status_code=400, detail="请选择已启用的LDAP认证源")
        try:
            ldap_user = lookup_ldap_user(source, username)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not ldap_user:
            raise HTTPException(status_code=404, detail="LDAP中未找到该用户")
        user.auth_source = source
        user.external_id = ldap_user.get("external_id") or ""
        user.display_name = ldap_user.get("display_name") or username
    if data.role == "admin":
        user.categories = db.query(models.Category).filter(models.Category.id.in_(data.category_ids)).all() if data.category_ids else []
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"status": "ok", "id": user.id}


@app.put("/api/admin/users/{user_id}")
def update_admin_user(
    user_id: int,
    data: AdminUserUpdateSchema,
    db: Session = Depends(get_db),
    current: models.AdminUser = Depends(require_superadmin),
):
    user = db.get(models.AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current.id and not data.is_active:
        raise HTTPException(status_code=400, detail="不能禁用当前登录账号")
    user.display_name = (data.display_name or user.username).strip()
    user.is_active = data.is_active
    user.categories = db.query(models.Category).filter(models.Category.id.in_(data.category_ids)).all() if data.category_ids else []
    db.commit()
    return {"status": "ok"}


@app.post("/api/admin/users/{user_id}/reset-password")
def reset_admin_password(
    user_id: int,
    data: PasswordResetSchema,
    db: Session = Depends(get_db),
    current: models.AdminUser = Depends(require_superadmin),
):
    user = db.get(models.AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.auth_type != "local":
        raise HTTPException(status_code=400, detail="LDAP用户密码由LDAP管理，请联系IT管理员")
    try:
        user.password_hash = hash_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Resetting another user's password revokes their sessions. Keep the current
    # superadmin session alive when they change their own password so subsequent
    # user-management actions are not unexpectedly rejected.
    if user.id != current.id:
        db.query(models.AdminSession).filter(models.AdminSession.user_id == user.id).delete()
    db.commit()
    return {"status": "ok"}


@app.delete("/api/admin/users/{user_id}")
def delete_admin_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: models.AdminUser = Depends(require_superadmin),
):
    user = db.get(models.AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    if user.role == "superadmin" and db.query(models.AdminUser).filter(
        models.AdminUser.role == "superadmin", models.AdminUser.is_active.is_(True)
    ).count() <= 1:
        raise HTTPException(status_code=400, detail="必须至少保留一个启用的超级管理员")
    db.delete(user)
    db.commit()
    return {"status": "ok"}


@app.get("/api/admin/categories")
def list_categories(db: Session = Depends(get_db), _: models.AdminUser = Depends(get_current_admin)):
    rows = db.query(models.Category).order_by(models.Category.sort_order, models.Category.id).all()
    return [
        {"id": row.id, "name": row.name, "sort_order": row.sort_order, "is_active": row.is_active}
        for row in rows
    ]


@app.post("/api/admin/categories")
def create_category(data: CategorySchema, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    category = models.Category(**data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return {"status": "ok", "id": category.id}


@app.put("/api/admin/categories/{category_id}")
def update_category(category_id: int, data: CategorySchema, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    category = db.get(models.Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="大类不存在")
    for key, value in data.model_dump().items():
        setattr(category, key, value)
    db.commit()
    return {"status": "ok"}


@app.delete("/api/admin/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    category = db.get(models.Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="大类不存在")
    for document in list(category.documents):
        document.category_id = None
    db.flush()
    db.delete(category)
    db.commit()
    return {"status": "ok"}


@app.get("/api/admin/departments")
def list_departments(db: Session = Depends(get_db), _: models.AdminUser = Depends(get_current_admin)):
    rows = (
        db.query(models.Department)
        .options(joinedload(models.Department.positions))
        .order_by(models.Department.sort_order, models.Department.id)
        .all()
    )
    return [{
        "id": row.id,
        "name": row.name,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
        "positions": [{
            "id": p.id,
            "name": p.name,
            "department_id": p.department_id,
            "sort_order": p.sort_order,
            "is_active": p.is_active,
        } for p in row.positions],
    } for row in rows]


@app.post("/api/admin/departments")
def create_department(data: DepartmentSchema, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    department = models.Department(**data.model_dump())
    db.add(department)
    db.commit()
    db.refresh(department)
    return {"status": "ok", "id": department.id}


@app.put("/api/admin/departments/{department_id}")
def update_department(department_id: int, data: DepartmentSchema, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    department = db.get(models.Department, department_id)
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在")
    for key, value in data.model_dump().items():
        setattr(department, key, value)
    db.commit()
    return {"status": "ok"}


@app.delete("/api/admin/departments/{department_id}")
def delete_department(department_id: int, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    department = db.get(models.Department, department_id)
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在")
    if department.positions:
        raise HTTPException(status_code=409, detail="请先删除或迁移该部门下的岗位")
    db.delete(department)
    db.commit()
    return {"status": "ok"}


@app.post("/api/admin/positions")
def create_position(data: PositionSchema, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    if not db.get(models.Department, data.department_id):
        raise HTTPException(status_code=400, detail="所属部门不存在")
    position = models.Position(**data.model_dump())
    db.add(position)
    db.commit()
    db.refresh(position)
    return {"status": "ok", "id": position.id}


@app.put("/api/admin/positions/{position_id}")
def update_position(position_id: int, data: PositionSchema, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    position = db.get(models.Position, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="岗位不存在")
    if not db.get(models.Department, data.department_id):
        raise HTTPException(status_code=400, detail="所属部门不存在")
    for key, value in data.model_dump().items():
        setattr(position, key, value)
    db.commit()
    return {"status": "ok"}


@app.delete("/api/admin/positions/{position_id}")
def delete_position(position_id: int, db: Session = Depends(get_db), _: models.AdminUser = Depends(require_superadmin)):
    position = db.get(models.Position, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="岗位不存在")
    db.delete(position)
    db.commit()
    return {"status": "ok"}


def serialize_document(doc: models.Document, user: Optional[models.AdminUser] = None):
    return {
        "id": doc.id,
        "category_id": doc.category_id,
        "title": doc.title,
        "content_html": doc.content_html or "",
        "content_json": doc.content_json or "",
        "dingtalk_url": doc.dingtalk_url or "",
        "software_name": doc.software_name or "",
        "software_sys": doc.software_sys or "",
        "download_url": doc.download_url or "",
        "extract_code": doc.extract_code or "",
        "visibility_type": doc.visibility_type or "all",
        "status": doc.status or "published",
        "sort_order": doc.sort_order,
        "department_ids": [d.id for d in doc.departments],
        "position_ids": [p.id for p in doc.positions],
        "can_manage": can_manage_category(user, doc.category_id) if user else False,
    }


@app.get("/api/admin/documents")
def list_documents(
    category_id: Optional[int] = None,
    uncategorized: bool = False,
    db: Session = Depends(get_db),
    user: models.AdminUser = Depends(get_current_admin),
):
    query = (
        db.query(models.Document)
        .options(joinedload(models.Document.departments), joinedload(models.Document.positions))
    )
    if uncategorized:
        query = query.filter(models.Document.category_id.is_(None))
    elif category_id is not None:
        query = query.filter(models.Document.category_id == category_id)
    docs = query.order_by(models.Document.category_id, models.Document.sort_order, models.Document.id).all()
    return [serialize_document(doc, user) for doc in docs]


@app.post("/api/admin/uploads/image")
async def upload_document_image(image: UploadFile = File(...), _: models.AdminUser = Depends(get_current_admin)):
    extension_by_type = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    extension = extension_by_type.get(image.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、GIF 和 WebP 图片")
    content = await image.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 8MB")
    filename = f"{uuid4().hex}{extension}"
    (UPLOAD_DIR / filename).write_bytes(content)
    return {"success": 1, "file": {"url": f"/uploads/{filename}"}}


@app.post("/api/admin/uploads/background")
async def upload_background_image(image: UploadFile = File(...), _: models.AdminUser = Depends(require_superadmin)):
    extension_by_type = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    extension = extension_by_type.get(image.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="背景图仅支持 JPG、PNG 和 WebP")
    content = await image.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="背景图片不能超过 10MB")
    filename = f"bg-{uuid4().hex}{extension}"
    (BACKGROUND_DIR / filename).write_bytes(content)
    return {"success": 1, "file": {"url": f"/uploads/backgrounds/{filename}"}}


def save_document_record(data: DocSaveSchema, db: Session, user: models.AdminUser, document_id: Optional[int] = None):
    if data.category_id is not None and not db.get(models.Category, data.category_id):
        raise HTTPException(status_code=400, detail="所属大类不存在")
    if data.visibility_type == "department" and not data.department_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个部门")
    if data.visibility_type == "position" and not data.position_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个岗位")

    if document_id is None:
        if not can_manage_category(user, data.category_id):
            raise HTTPException(status_code=403, detail="您没有在该大类中新建文档的权限")
        doc = models.Document()
        db.add(doc)
    else:
        doc = db.get(models.Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        if not can_manage_category(user, doc.category_id):
            raise HTTPException(status_code=403, detail="您只能编辑已授权大类中的文档")
        if not can_manage_category(user, data.category_id):
            raise HTTPException(status_code=403, detail="不能将文档移动到未授权的大类")

    doc.category_id = data.category_id
    doc.title = data.title.strip()
    if data.content_json:
        try:
            editor_data = json.loads(data.content_json)
            if not isinstance(editor_data, dict) or not isinstance(editor_data.get("blocks"), list):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="文档编辑器数据格式错误")
        doc.content_json = json.dumps(editor_data, ensure_ascii=False, separators=(",", ":"))
        doc.content_html = render_editor_json(doc.content_json)
        doc.editor_version = 1
    else:
        doc.content_json = ""
        doc.content_html = clean_html(data.content_html)
    doc.dingtalk_url = data.dingtalk_url or ""
    doc.software_name = data.software_name or ""
    doc.software_sys = data.software_sys or ""
    doc.download_url = data.download_url or ""
    doc.extract_code = data.extract_code or ""
    doc.visibility_type = data.visibility_type
    doc.is_all_positions = data.visibility_type == "all"
    doc.status = data.status
    doc.sort_order = data.sort_order
    doc.departments = []
    doc.positions = []
    if data.visibility_type == "department":
        doc.departments = db.query(models.Department).filter(models.Department.id.in_(data.department_ids)).all()
    elif data.visibility_type == "position":
        doc.positions = db.query(models.Position).filter(models.Position.id.in_(data.position_ids)).all()
    db.commit()
    db.refresh(doc)
    return {"status": "ok", "id": doc.id}


@app.post("/api/admin/documents")
def create_document(data: DocSaveSchema, db: Session = Depends(get_db), user: models.AdminUser = Depends(get_current_admin)):
    return save_document_record(data, db, user)


@app.put("/api/admin/documents/{document_id}")
def update_document(document_id: int, data: DocSaveSchema, db: Session = Depends(get_db), user: models.AdminUser = Depends(get_current_admin)):
    return save_document_record(data, db, user, document_id)


@app.delete("/api/admin/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db), user: models.AdminUser = Depends(get_current_admin)):
    doc = db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not can_manage_category(user, doc.category_id):
        raise HTTPException(status_code=403, detail="您只能删除已授权大类中的文档")
    db.delete(doc)
    db.commit()
    return {"status": "ok"}
