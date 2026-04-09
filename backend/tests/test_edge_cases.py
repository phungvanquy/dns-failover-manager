"""Tests for edge cases and the app health endpoint."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAppHealth:
    async def test_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
class TestHealthAndEventsEndpoints:
    async def test_health_for_nonexistent_domain(self, client: AsyncClient):
        resp = await client.get("/api/domains/00000000-0000-0000-0000-000000000000/health")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_events_for_nonexistent_domain(self, client: AsyncClient):
        resp = await client.get("/api/domains/00000000-0000-0000-0000-000000000000/events")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
class TestValidation:
    async def test_create_missing_required_fields(self, client: AsyncClient):
        resp = await client.post("/api/domains", json={})
        assert resp.status_code == 422

    async def test_create_missing_name(self, client: AsyncClient):
        resp = await client.post("/api/domains", json={"zone_id": "z", "primary_ip": "1.1.1.1"})
        assert resp.status_code == 422

    async def test_create_missing_zone_id(self, client: AsyncClient):
        resp = await client.post("/api/domains", json={"name": "a.com", "primary_ip": "1.1.1.1"})
        assert resp.status_code == 422

    async def test_create_missing_primary_ip(self, client: AsyncClient):
        resp = await client.post("/api/domains", json={"name": "a.com", "zone_id": "z"})
        assert resp.status_code == 422

    async def test_switch_missing_target_ip(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.post(f"/api/domains/{domain_id}/switch", json={})
        assert resp.status_code == 422

    async def test_switch_empty_body(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.post(f"/api/domains/{domain_id}/switch")
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestDomainCheckPortField:
    async def test_default_check_port(self, client: AsyncClient):
        payload = {"name": "port-default.com", "zone_id": "z1", "primary_ip": "1.1.1.1"}
        resp = await client.post("/api/domains", json=payload)
        assert resp.json()["check_port"] == 80

    async def test_custom_check_port(self, client: AsyncClient):
        payload = {"name": "port-custom.com", "zone_id": "z1", "primary_ip": "1.1.1.1",
                   "check_type": "tcp", "check_port": 443}
        resp = await client.post("/api/domains", json=payload)
        assert resp.json()["check_port"] == 443

    async def test_update_check_port(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.put(f"/api/domains/{domain_id}", json={"check_port": 8080})
        assert resp.json()["check_port"] == 8080


@pytest.mark.asyncio
class TestDomainResponseFormat:
    async def test_response_has_all_fields(self, client: AsyncClient, sample_domain):
        required_fields = [
            "id", "name", "zone_id", "record_id", "primary_ip", "active_ip",
            "auto_revert", "check_type", "check_endpoint", "check_port",
            "check_interval", "expected_status", "ttl", "created_at", "updated_at",
            "backup_ips",
        ]
        for field in required_fields:
            assert field in sample_domain, f"Missing field: {field}"

    async def test_backup_ip_response_format(self, client: AsyncClient, sample_domain):
        for bp in sample_domain["backup_ips"]:
            assert "id" in bp
            assert "ip" in bp
            assert "priority" in bp

    async def test_health_status_response_format(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.get(f"/api/domains/{domain_id}/health")
        for h in resp.json():
            assert "id" in h
            assert "domain_id" in h
            assert "ip" in h
            assert "is_healthy" in h
            assert "consecutive_failures" in h
            assert "consecutive_successes" in h


@pytest.mark.asyncio
class TestMultipleDomains:
    async def test_create_multiple_domains(self, client: AsyncClient):
        for i in range(5):
            payload = {"name": f"multi-{i}.com", "zone_id": f"z{i}", "primary_ip": f"10.0.{i}.1"}
            resp = await client.post("/api/domains", json=payload)
            assert resp.status_code == 201
        list_resp = await client.get("/api/domains")
        assert len(list_resp.json()) == 5

    async def test_delete_one_domain_leaves_others(self, client: AsyncClient):
        ids = []
        for i in range(3):
            payload = {"name": f"del-{i}.com", "zone_id": f"z{i}", "primary_ip": f"10.0.{i}.1"}
            resp = await client.post("/api/domains", json=payload)
            ids.append(resp.json()["id"])
        await client.delete(f"/api/domains/{ids[1]}")
        list_resp = await client.get("/api/domains")
        remaining = [d["id"] for d in list_resp.json()]
        assert ids[0] in remaining
        assert ids[1] not in remaining
        assert ids[2] in remaining
