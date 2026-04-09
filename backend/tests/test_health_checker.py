"""Tests for health checker: check functions, status transitions, failover, auto-revert."""
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Domain, BackupIP, HealthStatus, FailoverEvent, HealthCheckLog
from app.health_checker import (
    check_ping, check_tcp, check_http, perform_check, process_domain, _do_switch,
)


@pytest.mark.asyncio
class TestCheckPing:
    async def test_ping_success(self):
        with patch("app.health_checker.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc
            success, ms, err = await check_ping("1.1.1.1")
            assert success is True
            assert err is None

    async def test_ping_failure(self):
        with patch("app.health_checker.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc
            success, ms, err = await check_ping("10.255.255.1")
            assert success is False

    async def test_ping_timeout(self):
        with patch("app.health_checker.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_exec.return_value = mock_proc
            success, ms, err = await check_ping("10.255.255.1")
            assert success is False
            assert "timeout" in err


@pytest.mark.asyncio
class TestCheckTcp:
    async def test_tcp_success(self):
        mock_writer = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        with patch("app.health_checker.asyncio.open_connection", return_value=(AsyncMock(), mock_writer)):
            success, ms, err = await check_tcp("1.1.1.1", 80)
            assert success is True
            assert err is None

    async def test_tcp_timeout(self):
        with patch("app.health_checker.asyncio.open_connection", side_effect=asyncio.TimeoutError):
            success, ms, err = await check_tcp("10.255.255.1", 9999)
            assert success is False
            assert "timeout" in err

    async def test_tcp_connection_refused(self):
        with patch("app.health_checker.asyncio.open_connection", side_effect=ConnectionRefusedError("refused")):
            success, ms, err = await check_tcp("127.0.0.1", 19999)
            assert success is False
            assert "refused" in err


@pytest.mark.asyncio
class TestCheckHttp:
    async def test_http_success(self):
        with patch("app.health_checker.httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            success, ms, err = await check_http("1.1.1.1", "example.com", "/healthz", 200)
            assert success is True
            assert err is None

    async def test_http_wrong_status(self):
        with patch("app.health_checker.httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            success, ms, err = await check_http("1.1.1.1", "example.com", "/", 200)
            assert success is False
            assert "503" in err

    async def test_http_timeout(self):
        with patch("app.health_checker.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            success, ms, err = await check_http("1.1.1.1", "example.com", "/", 200)
            assert success is False


@pytest.mark.asyncio
class TestPerformCheck:
    async def test_routes_to_ping(self):
        domain = MagicMock()
        domain.check_type = "ping"
        with patch("app.health_checker.check_ping", new_callable=AsyncMock, return_value=(True, 10, None)) as mock:
            result = await perform_check(domain, "1.1.1.1")
            mock.assert_called_once_with("1.1.1.1")
            assert result == (True, 10, None)

    async def test_routes_to_tcp(self):
        domain = MagicMock()
        domain.check_type = "tcp"
        domain.check_port = 443
        with patch("app.health_checker.check_tcp", new_callable=AsyncMock, return_value=(True, 5, None)) as mock:
            result = await perform_check(domain, "1.1.1.1")
            mock.assert_called_once_with("1.1.1.1", 443)

    async def test_routes_to_http(self):
        domain = MagicMock()
        domain.check_type = "http"
        domain.name = "example.com"
        domain.check_endpoint = "/health"
        domain.expected_status = 200
        with patch("app.health_checker.check_http", new_callable=AsyncMock, return_value=(True, 20, None)) as mock:
            await perform_check(domain, "1.1.1.1")
            mock.assert_called_once_with("1.1.1.1", "example.com", "/health", 200, "http")

    async def test_routes_to_https(self):
        domain = MagicMock()
        domain.check_type = "https"
        domain.name = "example.com"
        domain.check_endpoint = "/"
        domain.expected_status = 200
        with patch("app.health_checker.check_http", new_callable=AsyncMock, return_value=(True, 20, None)) as mock:
            await perform_check(domain, "1.1.1.1")
            mock.assert_called_once_with("1.1.1.1", "example.com", "/", 200, "https")
