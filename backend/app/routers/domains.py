import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cloudflare import cf_client
from app.database import get_db
from app.models import Domain, BackupIP, HealthStatus, FailoverEvent
from app.schemas import (
    DomainCreate, DomainOut, DomainUpdate,
    HealthStatusOut, FailoverEventOut, ForceSwitchRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/domains", response_model=list[DomainOut])
async def list_domains(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Domain).options(selectinload(Domain.backup_ips)))
    return result.scalars().all()


@router.post("/domains", response_model=DomainOut, status_code=201)
async def create_domain(data: DomainCreate, db: AsyncSession = Depends(get_db)):
    # Auto-discover record_id from Cloudflare if not provided
    record_id = data.record_id
    if not record_id:
        try:
            record_id = await cf_client.get_record_id(data.zone_id, data.name)
            logger.info("Auto-discovered record_id=%s for %s", record_id, data.name)
        except Exception as e:
            logger.warning("Could not auto-discover record_id for %s: %s", data.name, e)

    domain = Domain(
        name=data.name,
        zone_id=data.zone_id,
        record_id=record_id,
        primary_ip=data.primary_ip,
        active_ip=data.primary_ip,
        auto_revert=data.auto_revert,
        check_type=data.check_type,
        check_endpoint=data.check_endpoint,
        check_port=data.check_port,
        check_interval=data.check_interval,
        expected_status=data.expected_status,
        ttl=data.ttl,
        monitoring_enabled=data.monitoring_enabled,
    )
    db.add(domain)
    await db.flush()

    for bp in data.backup_ips:
        db.add(BackupIP(domain_id=domain.id, ip=bp.ip, priority=bp.priority))

    # Create health status entries for all unique IPs
    all_ips = dict.fromkeys([data.primary_ip] + [bp.ip for bp in data.backup_ips])
    for ip in all_ips:
        db.add(HealthStatus(domain_id=domain.id, ip=ip, is_healthy=True))

    await db.commit()
    await db.refresh(domain)
    await db.refresh(domain, ["backup_ips"])
    return domain


@router.get("/domains/{domain_id}", response_model=DomainOut)
async def get_domain(domain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Domain).where(Domain.id == domain_id).options(selectinload(Domain.backup_ips))
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    return domain


@router.put("/domains/{domain_id}", response_model=DomainOut)
async def update_domain(domain_id: uuid.UUID, data: DomainUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Domain).where(Domain.id == domain_id).options(selectinload(Domain.backup_ips))
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    update_data = data.model_dump(exclude_unset=True)
    backup_ips_data = update_data.pop("backup_ips", None)

    for key, value in update_data.items():
        setattr(domain, key, value)

    if backup_ips_data is not None:
        await db.execute(delete(BackupIP).where(BackupIP.domain_id == domain_id))
        for bp in backup_ips_data:
            db.add(BackupIP(domain_id=domain_id, ip=bp["ip"], priority=bp["priority"]))
        # Rebuild health statuses
        await db.execute(delete(HealthStatus).where(HealthStatus.domain_id == domain_id))
        await db.flush()
        all_ips = dict.fromkeys([domain.primary_ip] + [bp["ip"] for bp in backup_ips_data])
        for ip in all_ips:
            db.add(HealthStatus(domain_id=domain_id, ip=ip, is_healthy=True))

    await db.commit()
    await db.refresh(domain)
    await db.refresh(domain, ["backup_ips"])
    return domain


@router.delete("/domains/{domain_id}", status_code=204)
async def delete_domain(domain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    await db.delete(domain)
    await db.commit()


@router.get("/domains/{domain_id}/health", response_model=list[HealthStatusOut])
async def get_domain_health(domain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HealthStatus).where(HealthStatus.domain_id == domain_id))
    return result.scalars().all()


@router.get("/domains/{domain_id}/events", response_model=list[FailoverEventOut])
async def get_domain_events(domain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FailoverEvent).where(FailoverEvent.domain_id == domain_id).order_by(FailoverEvent.created_at.desc())
    )
    return result.scalars().all()


@router.post("/domains/{domain_id}/switch", response_model=DomainOut)
async def force_switch(domain_id: uuid.UUID, data: ForceSwitchRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Domain).where(Domain.id == domain_id).options(selectinload(Domain.backup_ips))
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    valid_ips = [domain.primary_ip] + [bp.ip for bp in domain.backup_ips]
    if data.target_ip not in valid_ips:
        raise HTTPException(status_code=400, detail="Target IP not in domain's IP pool")

    # Auto-discover record_id if missing
    if not domain.record_id:
        try:
            domain.record_id = await cf_client.get_record_id(domain.zone_id, domain.name)
            logger.info("Auto-discovered record_id=%s for %s", domain.record_id, domain.name)
        except Exception as e:
            logger.error("Failed to discover record_id for %s: %s", domain.name, e)
            raise HTTPException(status_code=500, detail=f"Could not find DNS record for {domain.name}: {e}")

    if not domain.record_id:
        raise HTTPException(status_code=400, detail=f"No DNS A record found for {domain.name} in zone {domain.zone_id}")

    # Update Cloudflare DNS
    try:
        await cf_client.update_dns_record(
            zone_id=domain.zone_id,
            record_id=domain.record_id,
            domain_name=domain.name,
            ip=data.target_ip,
            ttl=domain.ttl,
        )
    except Exception as e:
        logger.error("Cloudflare DNS update failed for %s: %s", domain.name, e)
        raise HTTPException(status_code=502, detail=f"Cloudflare DNS update failed: {e}")

    old_ip = domain.active_ip
    domain.active_ip = data.target_ip
    db.add(FailoverEvent(domain_id=domain_id, old_ip=old_ip, new_ip=data.target_ip, reason="manual"))
    await db.commit()
    await db.refresh(domain)
    await db.refresh(domain, ["backup_ips"])
    return domain


@router.post("/domains/{domain_id}/monitoring", response_model=DomainOut)
async def toggle_monitoring(domain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Domain).where(Domain.id == domain_id).options(selectinload(Domain.backup_ips))
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    domain.monitoring_enabled = not domain.monitoring_enabled
    await db.commit()
    await db.refresh(domain)
    await db.refresh(domain, ["backup_ips"])
    return domain
