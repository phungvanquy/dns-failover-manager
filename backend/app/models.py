import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    zone_id: Mapped[str] = mapped_column(String, nullable=False)
    record_id: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_ip: Mapped[str] = mapped_column(String, nullable=False)
    active_ip: Mapped[str] = mapped_column(String, nullable=False)
    auto_revert: Mapped[bool] = mapped_column(Boolean, default=True)
    check_type: Mapped[str] = mapped_column(String, default="http")
    check_endpoint: Mapped[str] = mapped_column(String, default="/")
    check_port: Mapped[int] = mapped_column(Integer, default=80)
    check_interval: Mapped[int] = mapped_column(Integer, default=30)
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    ttl: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    backup_ips: Mapped[list["BackupIP"]] = relationship(back_populates="domain", cascade="all, delete-orphan", order_by="BackupIP.priority")
    health_statuses: Mapped[list["HealthStatus"]] = relationship(back_populates="domain", cascade="all, delete-orphan")
    failover_events: Mapped[list["FailoverEvent"]] = relationship(back_populates="domain", cascade="all, delete-orphan")


class BackupIP(Base):
    __tablename__ = "backup_ips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    ip: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    domain: Mapped["Domain"] = relationship(back_populates="backup_ips")


class HealthStatus(Base):
    __tablename__ = "health_status"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    ip: Mapped[str] = mapped_column(String, nullable=False)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_change: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    domain: Mapped["Domain"] = relationship(back_populates="health_statuses")


class FailoverEvent(Base):
    __tablename__ = "failover_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    old_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    new_ip: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)  # failover | revert | manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    domain: Mapped["Domain"] = relationship(back_populates="failover_events")


class HealthCheckLog(Base):
    __tablename__ = "health_check_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    ip: Mapped[str] = mapped_column(String, nullable=False)
    check_type: Mapped[str] = mapped_column(String, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
