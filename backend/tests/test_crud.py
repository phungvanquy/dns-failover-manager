"""Tests for Domain CRUD API endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestListDomains:
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/api/domains")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_domains(self, client: AsyncClient, sample_domain):
        resp = await client.get("/api/domains")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test.example.com"


@pytest.mark.asyncio
class TestCreateDomain:
    async def test_create_minimal(self, client: AsyncClient):
        payload = {"name": "minimal.com", "zone_id": "z1", "primary_ip": "1.1.1.1"}
        resp = await client.post("/api/domains", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "minimal.com"
        assert data["active_ip"] == "1.1.1.1"
        assert data["check_type"] == "http"
        assert data["check_port"] == 80
        assert data["ttl"] == 60
        assert data["auto_revert"] is True
        assert data["backup_ips"] == []
        assert data["record_id"] == "test-record-id-123"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_with_backups(self, client: AsyncClient, sample_domain):
        assert len(sample_domain["backup_ips"]) == 2
        assert sample_domain["backup_ips"][0]["ip"] == "10.0.0.2"
        assert sample_domain["backup_ips"][0]["priority"] == 1
        assert sample_domain["backup_ips"][1]["ip"] == "10.0.0.3"
        assert sample_domain["backup_ips"][1]["priority"] == 2

    async def test_create_with_all_check_types(self, client: AsyncClient):
        for ct in ["http", "https", "tcp", "ping"]:
            payload = {"name": f"{ct}.example.com", "zone_id": "z1", "primary_ip": "1.1.1.1", "check_type": ct}
            resp = await client.post("/api/domains", json=payload)
            assert resp.status_code == 201
            assert resp.json()["check_type"] == ct

    async def test_create_sets_active_ip_to_primary(self, client: AsyncClient):
        payload = {"name": "active.com", "zone_id": "z1", "primary_ip": "9.9.9.9"}
        resp = await client.post("/api/domains", json=payload)
        assert resp.json()["active_ip"] == "9.9.9.9"

    async def test_create_auto_discovers_record_id(self, client: AsyncClient, mock_cloudflare):
        payload = {"name": "discover.com", "zone_id": "z1", "primary_ip": "1.1.1.1"}
        resp = await client.post("/api/domains", json=payload)
        assert resp.status_code == 201
        assert resp.json()["record_id"] == "test-record-id-123"
        mock_cloudflare.get_record_id.assert_called_once_with("z1", "discover.com")

    async def test_create_with_explicit_record_id(self, client: AsyncClient, mock_cloudflare):
        payload = {"name": "explicit.com", "zone_id": "z1", "primary_ip": "1.1.1.1", "record_id": "my-record"}
        resp = await client.post("/api/domains", json=payload)
        assert resp.status_code == 201
        assert resp.json()["record_id"] == "my-record"
        mock_cloudflare.get_record_id.assert_not_called()

    async def test_create_duplicate_name_fails(self, client: AsyncClient, sample_domain):
        payload = {"name": "test.example.com", "zone_id": "z2", "primary_ip": "2.2.2.2"}
        resp = await client.post("/api/domains", json=payload)
        assert resp.status_code == 409

    async def test_create_initializes_health_status(self, client: AsyncClient):
        payload = {
            "name": "health-init.com", "zone_id": "z1", "primary_ip": "1.1.1.1",
            "backup_ips": [{"ip": "2.2.2.2", "priority": 1}],
        }
        resp = await client.post("/api/domains", json=payload)
        domain_id = resp.json()["id"]
        health_resp = await client.get(f"/api/domains/{domain_id}/health")
        assert health_resp.status_code == 200
        health = health_resp.json()
        assert len(health) == 2
        ips = {h["ip"] for h in health}
        assert ips == {"1.1.1.1", "2.2.2.2"}
        for h in health:
            assert h["is_healthy"] is True
            assert h["consecutive_failures"] == 0


@pytest.mark.asyncio
class TestGetDomain:
    async def test_get_existing(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.get(f"/api/domains/{domain_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test.example.com"

    async def test_get_not_found(self, client: AsyncClient):
        resp = await client.get("/api/domains/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_get_invalid_uuid(self, client: AsyncClient):
        resp = await client.get("/api/domains/not-a-uuid")
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestUpdateDomain:
    async def test_update_name(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.put(f"/api/domains/{domain_id}", json={"name": "updated.example.com"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated.example.com"

    async def test_update_check_type(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.put(f"/api/domains/{domain_id}", json={"check_type": "ping"})
        assert resp.status_code == 200
        assert resp.json()["check_type"] == "ping"

    async def test_update_backup_ips(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        new_backups = [{"ip": "10.0.0.99", "priority": 1}]
        resp = await client.put(f"/api/domains/{domain_id}", json={"backup_ips": new_backups})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["backup_ips"]) == 1
        assert data["backup_ips"][0]["ip"] == "10.0.0.99"

    async def test_update_rebuilds_health_on_backup_change(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        new_backups = [{"ip": "10.0.0.50", "priority": 1}]
        await client.put(f"/api/domains/{domain_id}", json={"backup_ips": new_backups})
        health_resp = await client.get(f"/api/domains/{domain_id}/health")
        health = health_resp.json()
        ips = {h["ip"] for h in health}
        assert "10.0.0.50" in ips
        assert "10.0.0.2" not in ips  # old backup removed

    async def test_update_not_found(self, client: AsyncClient):
        resp = await client.put("/api/domains/00000000-0000-0000-0000-000000000000", json={"name": "x"})
        assert resp.status_code == 404

    async def test_partial_update(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.put(f"/api/domains/{domain_id}", json={"ttl": 120})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ttl"] == 120
        assert data["name"] == "test.example.com"  # unchanged


@pytest.mark.asyncio
class TestDeleteDomain:
    async def test_delete_existing(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.delete(f"/api/domains/{domain_id}")
        assert resp.status_code == 204
        # Verify gone
        resp2 = await client.get(f"/api/domains/{domain_id}")
        assert resp2.status_code == 404

    async def test_delete_cascades(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        await client.delete(f"/api/domains/{domain_id}")
        health_resp = await client.get(f"/api/domains/{domain_id}/health")
        assert health_resp.json() == []

    async def test_delete_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/domains/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
