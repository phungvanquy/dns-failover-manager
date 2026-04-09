import uuid
from datetime import datetime

from pydantic import BaseModel


# --- BackupIP ---
class BackupIPBase(BaseModel):
    ip: str
    priority: int


class BackupIPCreate(BackupIPBase):
    pass


class BackupIPOut(BackupIPBase):
    id: uuid.UUID
    model_config = {"from_attributes": True}


# --- Domain ---
class DomainBase(BaseModel):
    name: str
    zone_id: str
    record_id: str | None = None
    primary_ip: str
    auto_revert: bool = True
    check_type: str = "http"
    check_endpoint: str = "/"
    check_port: int = 80
    check_interval: int = 30
    expected_status: int = 200
    ttl: int = 60


class DomainCreate(DomainBase):
    backup_ips: list[BackupIPCreate] = []


class DomainUpdate(BaseModel):
    name: str | None = None
    zone_id: str | None = None
    record_id: str | None = None
    primary_ip: str | None = None
    auto_revert: bool | None = None
    check_type: str | None = None
    check_endpoint: str | None = None
    check_port: int | None = None
    check_interval: int | None = None
    expected_status: int | None = None
    ttl: int | None = None
    backup_ips: list[BackupIPCreate] | None = None


class DomainOut(DomainBase):
    id: uuid.UUID
    active_ip: str
    created_at: datetime
    updated_at: datetime
    backup_ips: list[BackupIPOut] = []
    model_config = {"from_attributes": True}


# --- HealthStatus ---
class HealthStatusOut(BaseModel):
    id: uuid.UUID
    domain_id: uuid.UUID
    ip: str
    is_healthy: bool
    consecutive_failures: int
    consecutive_successes: int
    last_checked: datetime | None
    last_status_change: datetime | None
    model_config = {"from_attributes": True}


# --- FailoverEvent ---
class FailoverEventOut(BaseModel):
    id: uuid.UUID
    domain_id: uuid.UUID
    old_ip: str | None
    new_ip: str
    reason: str
    created_at: datetime
    model_config = {"from_attributes": True}


# --- Force Switch ---
class ForceSwitchRequest(BaseModel):
    target_ip: str
