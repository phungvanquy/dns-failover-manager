import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.cloudflare import cf_client
from app.config import settings
from app.database import async_session
from app.models import Domain, HealthStatus, HealthCheckLog, FailoverEvent

logger = logging.getLogger(__name__)

# Per-domain lock to prevent concurrent failover
_domain_locks: dict[str, asyncio.Lock] = {}


def _get_lock(domain_id: str) -> asyncio.Lock:
    if domain_id not in _domain_locks:
        _domain_locks[domain_id] = asyncio.Lock()
    return _domain_locks[domain_id]


async def check_ping(ip: str) -> tuple[bool, int, str | None]:
    """ICMP ping check. Returns (success, response_time_ms, error)."""
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "3", "-W", "3", ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=12)
        elapsed = int((time.monotonic() - start) * 1000)
        return proc.returncode == 0, elapsed, None if proc.returncode == 0 else "ping failed"
    except asyncio.TimeoutError:
        return False, int((time.monotonic() - start) * 1000), "ping timeout"
    except Exception as e:
        return False, int((time.monotonic() - start) * 1000), str(e)


async def check_tcp(ip: str, port: int) -> tuple[bool, int, str | None]:
    """TCP connect check. Returns (success, response_time_ms, error)."""
    start = time.monotonic()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=3
        )
        writer.close()
        await writer.wait_closed()
        elapsed = int((time.monotonic() - start) * 1000)
        return True, elapsed, None
    except asyncio.TimeoutError:
        return False, int((time.monotonic() - start) * 1000), "tcp connect timeout"
    except Exception as e:
        return False, int((time.monotonic() - start) * 1000), str(e)


async def check_http(ip: str, domain_name: str, endpoint: str, expected_status: int, scheme: str = "http") -> tuple[bool, int, str | None]:
    """HTTP/HTTPS check. Returns (success, response_time_ms, error)."""
    url = f"{scheme}://{ip}{endpoint}"
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                url,
                headers={"Host": domain_name},
                timeout=5,
                follow_redirects=True,
            )
            elapsed = int((time.monotonic() - start) * 1000)
            success = resp.status_code == expected_status
            err = None if success else f"status {resp.status_code} != {expected_status}"
            return success, elapsed, err
    except asyncio.TimeoutError:
        return False, int((time.monotonic() - start) * 1000), "http timeout"
    except Exception as e:
        return False, int((time.monotonic() - start) * 1000), str(e)


async def perform_check(domain: Domain, ip: str) -> tuple[bool, int, str | None]:
    """Route to the appropriate check method."""
    if domain.check_type == "ping":
        return await check_ping(ip)
    elif domain.check_type == "tcp":
        return await check_tcp(ip, domain.check_port)
    elif domain.check_type == "https":
        return await check_http(ip, domain.name, domain.check_endpoint, domain.expected_status, "https")
    else:  # http
        return await check_http(ip, domain.name, domain.check_endpoint, domain.expected_status, "http")


async def process_domain(domain: Domain):
    """Run health checks for all IPs of a domain and handle failover."""
    lock = _get_lock(str(domain.id))
    async with lock:
        async with async_session() as db:
            # Collect all IPs to check
            all_ips = [domain.primary_ip] + [bp.ip for bp in domain.backup_ips]

            for ip in all_ips:
                success, response_time_ms, error_msg = await perform_check(domain, ip)

                # Get or create health status
                result = await db.execute(
                    select(HealthStatus).where(
                        HealthStatus.domain_id == domain.id,
                        HealthStatus.ip == ip,
                    )
                )
                hs = result.scalar_one_or_none()
                if not hs:
                    hs = HealthStatus(domain_id=domain.id, ip=ip, is_healthy=True)
                    db.add(hs)

                now = datetime.now(timezone.utc)
                was_healthy = hs.is_healthy

                if success:
                    hs.consecutive_failures = 0
                    hs.consecutive_successes += 1
                    if not was_healthy and hs.consecutive_successes >= settings.SUCCESS_THRESHOLD:
                        hs.is_healthy = True
                        hs.last_status_change = now
                        logger.info("IP %s for %s is now UP", ip, domain.name)
                else:
                    hs.consecutive_successes = 0
                    hs.consecutive_failures += 1
                    if was_healthy and hs.consecutive_failures >= settings.FAILURE_THRESHOLD:
                        hs.is_healthy = False
                        hs.last_status_change = now
                        logger.warning("IP %s for %s is now DOWN", ip, domain.name)

                hs.last_checked = now

                # Log the check
                db.add(HealthCheckLog(
                    domain_id=domain.id,
                    ip=ip,
                    check_type=domain.check_type,
                    success=success,
                    response_time_ms=response_time_ms,
                    error_message=error_msg,
                ))

            await db.commit()

            # --- Failover logic ---
            # Re-fetch health statuses after commit
            result = await db.execute(
                select(HealthStatus).where(HealthStatus.domain_id == domain.id)
            )
            health_map = {hs.ip: hs for hs in result.scalars().all()}

            # Re-fetch domain to get current active_ip
            from app.models import Domain as DomainModel
            result = await db.execute(
                select(DomainModel).where(DomainModel.id == domain.id).options(selectinload(DomainModel.backup_ips))
            )
            dom = result.scalar_one()

            active_health = health_map.get(dom.active_ip)
            active_is_down = active_health and not active_health.is_healthy

            # Auto-revert: if active != primary and primary is healthy
            primary_health = health_map.get(dom.primary_ip)
            if (dom.auto_revert
                    and dom.active_ip != dom.primary_ip
                    and primary_health and primary_health.is_healthy):
                await _do_switch(db, dom, dom.primary_ip, "revert")
                return

            # Failover: if active IP is down, switch to first healthy
            if active_is_down:
                priority_ips = [dom.primary_ip] + [bp.ip for bp in dom.backup_ips]
                for candidate in priority_ips:
                    if candidate == dom.active_ip:
                        continue
                    h = health_map.get(candidate)
                    if h and h.is_healthy:
                        await _do_switch(db, dom, candidate, "failover")
                        return
                logger.error("All IPs down for %s, no failover target available", dom.name)


async def _do_switch(db, domain: Domain, new_ip: str, reason: str):
    """Perform DNS switch via Cloudflare and update DB."""
    # Auto-discover record_id if missing
    if not domain.record_id:
        try:
            domain.record_id = await cf_client.get_record_id(domain.zone_id, domain.name)
        except Exception as e:
            logger.error("Cannot discover record_id for %s: %s", domain.name, e)
            return

    if not domain.record_id:
        logger.error("No record_id for %s, skipping DNS update", domain.name)
        return

    try:
        await cf_client.update_dns_record(
            zone_id=domain.zone_id,
            record_id=domain.record_id,
            domain_name=domain.name,
            ip=new_ip,
            ttl=domain.ttl,
        )
    except Exception as e:
        logger.error("Cloudflare DNS update failed for %s: %s", domain.name, e)
        return

    old_ip = domain.active_ip
    domain.active_ip = new_ip
    db.add(FailoverEvent(domain_id=domain.id, old_ip=old_ip, new_ip=new_ip, reason=reason))
    await db.commit()
    logger.info("DNS %s for %s: %s -> %s", reason, domain.name, old_ip, new_ip)


async def run_health_checks():
    """Single pass: check all domains."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Domain).options(selectinload(Domain.backup_ips))
            )
            domains = result.scalars().all()

        for domain in domains:
            try:
                await process_domain(domain)
            except Exception as e:
                logger.error("Health check error for %s: %s", domain.name, e)
    except Exception as e:
        logger.error("Health check run failed: %s", e)


async def health_check_loop():
    """Background loop that runs health checks continuously."""
    logger.info("Health check worker started")
    while True:
        await run_health_checks()
        await asyncio.sleep(settings.DEFAULT_CHECK_INTERVAL)
