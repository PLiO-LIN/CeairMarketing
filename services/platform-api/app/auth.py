from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_session
from .db_models import TenantMembershipRecord, TenantRecord, UserRecord


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_value, digest_value = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value)
        expected = base64.urlsafe_b64decode(digest_value)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_token(user_id: int) -> str:
    settings = get_settings()
    payload = {"sub": user_id, "exp": int(time.time()) + settings.token_ttl_minutes * 60}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(settings.token_secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def decode_token(token: str) -> int:
    settings = get_settings()
    try:
        body, signature_value = token.split(".", 1)
        expected = hmac.new(settings.token_secret.encode(), body.encode(), hashlib.sha256).digest()
        signature = base64.urlsafe_b64decode(signature_value + "=" * (-len(signature_value) % 4))
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return int(payload["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效或已过期") from exc


@dataclass
class TenantContext:
    user_id: int
    username: str
    display_name: str
    tenant_id: int
    tenant_code: str
    tenant_name: str
    role: str


def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> UserRecord:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    user = session.get(UserRecord, decode_token(authorization[7:]))
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不可用")
    return user


def get_tenant_context(
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-ID"),
    user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TenantContext:
    memberships = session.scalars(
        select(TenantMembershipRecord).where(TenantMembershipRecord.user_id == user.id).order_by(TenantMembershipRecord.id)
    ).all()
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户未加入任何租户")
    membership = next((item for item in memberships if item.tenant_id == x_tenant_id), memberships[0] if x_tenant_id is None else None)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该租户")
    tenant = session.get(TenantRecord, membership.tenant_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="租户不可用")
    return TenantContext(user.id, user.username, user.display_name, tenant.id, tenant.code, tenant.name, membership.role)


def require_write(context: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if context.role not in {"admin", "manager", "analyst"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色没有写入权限")
    return context


def require_admin(context: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if context.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅租户管理员可执行此操作")
    return context


def require_platform_admin(user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅平台管理员可执行此操作")
    return user
