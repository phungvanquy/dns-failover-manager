"""Tests for health status transitions, failover logic, and auto-revert via process_domain."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Domain, HealthStatus, FailoverEvent, HealthCheckLog
from tests.conftest import test_async_session


@pytest.mark.asyncio
class TestHealthStatusTransitions:
    """Test that health statuses change correctly after repeated checks via the API."""

    async def test_health_starts_healthy(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.get(f"/api/domains/{domain_id}/health")
        for h in resp.json():
            assert h["is_healthy"] is True
            assert h["consecutive_failures"] == 0

    async def test_events_initially_empty(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.get(f"/api/domains/{domain_id}/events")
        assert resp.json() == []


@pytest.mark.asyncio
class TestProcessDomainFailover:
    """Test process_domain with mocked checks to verify failover logic."""

    async def _get_domain(self, name: str) -> Domain:
        async with test_async_session() as sess:
            result = await sess.execute(
                select(Domain).where(Domain.name == name).options(selectinload(Domain.backup_ips))
            )
            return result.scalar_one()

    async def test_failover_when_primary_down(self, client: AsyncClient, sample_domain):
        """When primary IP fails enough times, should failover to backup."""
        from app.health_checker import process_domain

        async def mock_check(domain, ip):
            if ip == "10.0.0.1":
                return (False, 100, "ping failed")
            return (True, 10, None)

        with patch("app.health_checker.perform_check", side_effect=mock_check), \
             patch("app.health_checker.async_session", test_async_session), \
             patch("app.health_checker.cf_client") as mock_cf:
            mock_cf.get_record_id = AsyncMock(return_value="rec-123")
            mock_cf.update_dns_record = AsyncMock(return_value={})

            for _ in range(settings.FAILURE_THRESHOLD):
                domain = await self._get_domain("test.example.com")
                await process_domain(domain)

        # Verify failover happened
        async with test_async_session() as sess:
            result = await sess.execute(select(Domain).where(Domain.name == "test.example.com"))
            dom = result.scalar_one()
            assert dom.active_ip == "10.0.0.2"

            result = await sess.execute(select(FailoverEvent).where(FailoverEvent.domain_id == dom.id))
            events = result.scalars().all()
            assert any(e.reason == "failover" for e in events)

    async def test_no_failover_when_healthy(self, client: AsyncClient, sample_domain):
        """No failover if all checks pass."""
        from app.health_checker import process_domain

        async def mock_check(domain, ip):
            return (True, 10, None)

        with patch("app.health_checker.perform_check", side_effect=mock_check), \
             patch("app.health_checker.async_session", test_async_session):
            domain = await self._get_domain("test.example.com")
            await process_domain(domain)

        async with test_async_session() as sess:
            result = await sess.execute(select(Domain).where(Domain.name == "test.example.com"))
            dom = result.scalar_one()
            assert dom.active_ip == "10.0.0.1"  # Unchanged

    async def test_auto_revert_to_primary(self, client: AsyncClient, sample_domain):
        """When primary recovers and auto_revert is on, should switch back."""
        from app.health_checker import process_domain

        # Manually set active_ip to backup
        async with test_async_session() as sess:
            result = await sess.execute(select(Domain).where(Domain.name == "test.example.com"))
            dom = result.scalar_one()
            dom.active_ip = "10.0.0.2"
            await sess.commit()

        # All IPs healthy → should revert to primary
        async def mock_check(domain, ip):
            return (True, 10, None)

        with patch("app.health_checker.perform_check", side_effect=mock_check), \
             patch("app.health_checker.async_session", test_async_session), \
             patch("app.health_checker.cf_client") as mock_cf:
            mock_cf.get_record_id = AsyncMock(return_value="rec-123")
            mock_cf.update_dns_record = AsyncMock(return_value={})

            domain = await self._get_domain("test.example.com")
            await process_domain(domain)

        async with test_async_session() as sess:
            result = await sess.execute(select(Domain).where(Domain.name == "test.example.com"))
            dom = result.scalar_one()
            assert dom.active_ip == "10.0.0.1"  # Reverted

            result = await sess.execute(select(FailoverEvent).where(FailoverEvent.domain_id == dom.id))
            events = result.scalars().all()
            assert any(e.reason == "revert" for e in events)

    async def test_all_ips_down_no_failover(self, client: AsyncClient, sample_domain):
        """When all IPs are down, no failover target available."""
        from app.health_checker import process_domain

        async def mock_check(domain, ip):
            return (False, 100, "down")

        with patch("app.health_checker.perform_check", side_effect=mock_check), \
             patch("app.health_checker.async_session", test_async_session):
            for _ in range(settings.FAILURE_THRESHOLD):
                domain = await self._get_domain("test.example.com")
                await process_domain(domain)

        async with test_async_session() as sess:
            result = await sess.execute(select(Domain).where(Domain.name == "test.example.com"))
            dom = result.scalar_one()
            # Still on primary since no healthy target
            assert dom.active_ip == "10.0.0.1"

    async def test_check_logs_created(self, client: AsyncClient, sample_domain):
        """Health check logs should be created after process_domain."""
        from app.health_checker import process_domain

        async def mock_check(domain, ip):
            return (True, 15, None)

        with patch("app.health_checker.perform_check", side_effect=mock_check), \
             patch("app.health_checker.async_session", test_async_session):
            domain = await self._get_domain("test.example.com")
            await process_domain(domain)

        async with test_async_session() as sess:
            result = await sess.execute(
                select(HealthCheckLog).where(HealthCheckLog.domain_id == domain.id)
            )
            logs = result.scalars().all()
            assert len(logs) == 3  # primary + 2 backups
            for log in logs:
                assert log.success is True
