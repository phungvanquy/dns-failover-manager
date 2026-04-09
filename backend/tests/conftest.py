import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/dns_failover_test"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with test_async_session() as session:
        yield session


@pytest_asyncio.fixture
async def db_session():
    async with test_async_session() as session:
        yield session


@pytest.fixture(autouse=True)
def mock_cloudflare():
    """Mock all Cloudflare API calls globally."""
    with patch("app.routers.domains.cf_client") as mock_cf:
        mock_cf.get_record_id = AsyncMock(return_value="test-record-id-123")
        mock_cf.update_dns_record = AsyncMock(return_value={"id": "test-record-id-123"})
        mock_cf.list_dns_records = AsyncMock(return_value=[{"id": "test-record-id-123"}])
        yield mock_cf


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client with DB override."""
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_domain(client: AsyncClient):
    """Create a sample domain and return the response data."""
    payload = {
        "name": "test.example.com",
        "zone_id": "zone-abc-123",
        "primary_ip": "10.0.0.1",
        "check_type": "http",
        "check_endpoint": "/healthz",
        "check_interval": 30,
        "expected_status": 200,
        "ttl": 60,
        "auto_revert": True,
        "backup_ips": [
            {"ip": "10.0.0.2", "priority": 1},
            {"ip": "10.0.0.3", "priority": 2},
        ],
    }
    resp = await client.post("/api/domains", json=payload)
    assert resp.status_code == 201
    return resp.json()


@pytest_asyncio.fixture
async def sample_domain_ping(client: AsyncClient):
    """Create a sample domain with ping check type."""
    payload = {
        "name": "ping.example.com",
        "zone_id": "zone-ping-123",
        "primary_ip": "10.1.0.1",
        "check_type": "ping",
        "auto_revert": False,
        "backup_ips": [
            {"ip": "10.1.0.2", "priority": 1},
        ],
    }
    resp = await client.post("/api/domains", json=payload)
    assert resp.status_code == 201
    return resp.json()
