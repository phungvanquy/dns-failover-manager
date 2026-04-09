"""Tests for Force Switch endpoint and Cloudflare integration."""
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestForceSwitch:
    async def test_switch_to_backup(self, client: AsyncClient, sample_domain, mock_cloudflare):
        domain_id = sample_domain["id"]
        resp = await client.post(
            f"/api/domains/{domain_id}/switch",
            json={"target_ip": "10.0.0.2"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_ip"] == "10.0.0.2"
        mock_cloudflare.update_dns_record.assert_called_once()

    async def test_switch_to_primary(self, client: AsyncClient, sample_domain, mock_cloudflare):
        domain_id = sample_domain["id"]
        # First switch to backup
        await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "10.0.0.2"})
        mock_cloudflare.update_dns_record.reset_mock()
        # Then switch back to primary
        resp = await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "10.0.0.1"})
        assert resp.status_code == 200
        assert resp.json()["active_ip"] == "10.0.0.1"
        mock_cloudflare.update_dns_record.assert_called_once()

    async def test_switch_invalid_ip(self, client: AsyncClient, sample_domain):
        domain_id = sample_domain["id"]
        resp = await client.post(
            f"/api/domains/{domain_id}/switch",
            json={"target_ip": "99.99.99.99"},
        )
        assert resp.status_code == 400
        assert "not in domain's IP pool" in resp.json()["detail"]

    async def test_switch_not_found(self, client: AsyncClient):
        resp = await client.post(
            "/api/domains/00000000-0000-0000-0000-000000000000/switch",
            json={"target_ip": "1.1.1.1"},
        )
        assert resp.status_code == 404

    async def test_switch_creates_event(self, client: AsyncClient, sample_domain, mock_cloudflare):
        domain_id = sample_domain["id"]
        await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "10.0.0.2"})
        events_resp = await client.get(f"/api/domains/{domain_id}/events")
        events = events_resp.json()
        assert len(events) == 1
        assert events[0]["old_ip"] == "10.0.0.1"
        assert events[0]["new_ip"] == "10.0.0.2"
        assert events[0]["reason"] == "manual"

    async def test_switch_auto_discovers_record_id(self, client: AsyncClient, mock_cloudflare):
        # Create domain without record_id (mock returns test-record-id-123)
        payload = {"name": "norec.com", "zone_id": "z1", "primary_ip": "1.1.1.1",
                   "backup_ips": [{"ip": "2.2.2.2", "priority": 1}]}
        create_resp = await client.post("/api/domains", json=payload)
        domain_id = create_resp.json()["id"]

        mock_cloudflare.get_record_id.reset_mock()
        mock_cloudflare.get_record_id.return_value = "discovered-record-456"

        resp = await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "2.2.2.2"})
        assert resp.status_code == 200

    async def test_switch_cloudflare_failure(self, client: AsyncClient, sample_domain, mock_cloudflare):
        domain_id = sample_domain["id"]
        mock_cloudflare.update_dns_record.side_effect = Exception("CF API down")
        resp = await client.post(
            f"/api/domains/{domain_id}/switch",
            json={"target_ip": "10.0.0.2"},
        )
        assert resp.status_code == 502
        assert "Cloudflare DNS update failed" in resp.json()["detail"]

    async def test_switch_no_record_id_and_discovery_fails(self, client: AsyncClient, mock_cloudflare):
        mock_cloudflare.get_record_id.return_value = None
        payload = {"name": "norec2.com", "zone_id": "z1", "primary_ip": "1.1.1.1",
                   "record_id": None,
                   "backup_ips": [{"ip": "2.2.2.2", "priority": 1}]}
        # Create will set record_id=None since get_record_id returns None
        create_resp = await client.post("/api/domains", json=payload)
        domain_id = create_resp.json()["id"]
        assert create_resp.json()["record_id"] is None

        resp = await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "2.2.2.2"})
        assert resp.status_code == 400
        assert "No DNS A record found" in resp.json()["detail"]

    async def test_switch_calls_cloudflare_with_correct_params(self, client: AsyncClient, sample_domain, mock_cloudflare):
        domain_id = sample_domain["id"]
        await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "10.0.0.3"})
        call_kwargs = mock_cloudflare.update_dns_record.call_args
        assert call_kwargs.kwargs["zone_id"] == "zone-abc-123"
        assert call_kwargs.kwargs["domain_name"] == "test.example.com"
        assert call_kwargs.kwargs["ip"] == "10.0.0.3"
        assert call_kwargs.kwargs["ttl"] == 60

    async def test_multiple_switches_create_events(self, client: AsyncClient, sample_domain, mock_cloudflare):
        domain_id = sample_domain["id"]
        await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "10.0.0.2"})
        await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "10.0.0.3"})
        await client.post(f"/api/domains/{domain_id}/switch", json={"target_ip": "10.0.0.1"})
        events_resp = await client.get(f"/api/domains/{domain_id}/events")
        events = events_resp.json()
        assert len(events) == 3
        # Events are ordered desc
        assert events[0]["new_ip"] == "10.0.0.1"
        assert events[1]["new_ip"] == "10.0.0.3"
        assert events[2]["new_ip"] == "10.0.0.2"
