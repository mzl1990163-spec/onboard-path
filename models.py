from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


document_position = Table(
    "document_position",
    Base.metadata,
    Column("document_id", Integer, ForeignKey("document.id", ondelete="CASCADE"), primary_key=True),
    Column("position_id", Integer, ForeignKey("position.id", ondelete="CASCADE"), primary_key=True),
)

document_department = Table(
    "document_department",
    Base.metadata,
    Column("document_id", Integer, ForeignKey("document.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", Integer, ForeignKey("department.id", ondelete="CASCADE"), primary_key=True),
)

admin_user_category = Table(
    "admin_user_category",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("admin_user.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("category.id", ondelete="CASCADE"), primary_key=True),
)


class SysConfig(Base):
    __tablename__ = "sys_config"
    id = Column(Integer, primary_key=True, index=True)
    login_bg_url = Column(String(255), default="")
    login_bg_color = Column(String(20), default="#0f172a")
    login_overlay_color = Column(String(20), default="#0f172a")
    login_overlay_opacity = Column(Integer, default=65)
    login_welcome_title = Column(String(100), default="欢迎新同事加入！")
    login_welcome_subtitle = Column(String(255), default="在开始办理入职配置前，请先登记您的基础个人信息")
    login_button_text = Column(String(100), default="开启我的入职指南 ➔")
    header_bg_url = Column(String(255), default="")
    header_bg_color = Column(String(20), default="#0f172a")
    header_overlay_color = Column(String(20), default="#0f172a")
    header_overlay_opacity = Column(Integer, default=72)
    header_title_color = Column(String(20), default="#ffffff")
    header_subtitle_color = Column(String(20), default="#94a3b8")
    header_title = Column(String(100), default="新员工入职落地指引")
    header_subtitle = Column(String(255), default="")
    employee_expired_title = Column(String(120), default="入职指引访问期已结束")
    employee_expired_message = Column(String(500), default="您的新员工入职指引访问期限已结束。如有相关问题，请联系 IT 部门，或者前往钉钉服务台进行咨询。")
    employee_dingtalk_text = Column(String(80), default="钉钉服务台")
    employee_dingtalk_url = Column(String(500), default="")
    employee_not_found_message = Column(String(255), default="未查询到员工信息，请确认姓名全拼或联系 IT 部门。")
    employee_service_error_message = Column(String(255), default="认证服务暂时不可用，请稍后重试或联系 IT 部门。")


class AuthSource(Base):
    __tablename__ = "auth_source"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    source_type = Column(String(20), nullable=False, default="ldap")
    is_enabled = Column(Boolean, default=True, nullable=False)
    is_employee_default = Column(Boolean, default=False, nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, default=389, nullable=False)
    use_ssl = Column(Boolean, default=False, nullable=False)
    start_tls = Column(Boolean, default=False, nullable=False)
    base_dn = Column(String(255), nullable=False)
    bind_dn = Column(String(255), default="")
    bind_password_encrypted = Column(Text, default="")
    user_search_base = Column(String(255), default="")
    user_filter = Column(String(500), default="(&(objectClass=user)(sAMAccountName={username}))")
    username_attribute = Column(String(80), default="sAMAccountName")
    display_name_attribute = Column(String(80), default="displayName")
    created_at_attribute = Column(String(80), default="whenCreated")
    employee_valid_days = Column(Integer, default=14, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    users = relationship("AdminUser", back_populates="auth_source")


class AdminUser(Base):
    __tablename__ = "admin_user"
    __table_args__ = (UniqueConstraint("username", name="uq_admin_user_username"),)
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False)
    display_name = Column(String(100), default="")
    auth_type = Column(String(20), nullable=False, default="local")
    auth_source_id = Column(Integer, ForeignKey("auth_source.id", ondelete="RESTRICT"), nullable=True)
    external_id = Column(String(255), default="")
    password_hash = Column(String(500), default="")
    role = Column(String(20), nullable=False, default="admin")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    auth_source = relationship("AuthSource", back_populates="users")
    categories = relationship("Category", secondary=admin_user_category, back_populates="admin_users")
    sessions = relationship("AdminSession", back_populates="user", cascade="all, delete-orphan")


class AdminSession(Base):
    __tablename__ = "admin_session"
    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("admin_user.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    user = relationship("AdminUser", back_populates="sessions")


class Department(Base):
    __tablename__ = "department"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    positions = relationship(
        "Position", back_populates="department", cascade="all, delete-orphan",
        order_by="Position.sort_order, Position.id"
    )
    documents = relationship("Document", secondary=document_department, back_populates="departments")


class Position(Base):
    __tablename__ = "position"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    department_id = Column(Integer, ForeignKey("department.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    department = relationship("Department", back_populates="positions")
    documents = relationship("Document", secondary=document_position, back_populates="positions")


class Category(Base):
    __tablename__ = "category"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    documents = relationship("Document", back_populates="category", order_by="Document.sort_order, Document.id")
    admin_users = relationship("AdminUser", secondary=admin_user_category, back_populates="categories")


class Document(Base):
    __tablename__ = "document"
    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("category.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(100), nullable=False)
    content_html = Column(Text, default="")
    content_json = Column(Text, default="")
    editor_version = Column(Integer, default=1)
    dingtalk_url = Column(String(255), default="")
    software_name = Column(String(100), default="")
    software_sys = Column(String(50), default="Windows/Mac")
    download_url = Column(String(255), default="")
    extract_code = Column(String(50), default="")
    is_all_positions = Column(Boolean, default=True)  # 兼容旧数据
    visibility_type = Column(String(20), default="all")
    status = Column(String(20), default="published")
    sort_order = Column(Integer, default=0)
    category = relationship("Category", back_populates="documents")
    departments = relationship("Department", secondary=document_department, back_populates="documents")
    positions = relationship("Position", secondary=document_position, back_populates="documents")
