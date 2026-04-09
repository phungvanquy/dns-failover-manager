import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class CloudflareClient:
    def __init__(self):
        self.base_url = settings.CLOUDFLARE_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json",
        }

    async def list_dns_records(self, zone_id: str, name: str | None = None, record_type: str = "A") -> list[dict]:
        """List DNS records for a zone, optionally filtered by name and type."""
        params: dict = {"type": record_type}
        if name:
            params["name"] = name
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/zones/{zone_id}/dns_records",
                headers=self.headers,
                params=params,
                timeout=10,
            )
            data = resp.json()
            if not data.get("success"):
                logger.error("Cloudflare list_dns_records failed: %s", data.get("errors"))
                raise Exception(f"Cloudflare API error: {data.get('errors')}")
            return data.get("result", [])

    async def get_record_id(self, zone_id: str, domain_name: str) -> str | None:
        """Find the record ID for a domain A record."""
        records = await self.list_dns_records(zone_id, name=domain_name, record_type="A")
        if records:
            return records[0]["id"]
        return None

    async def update_dns_record(self, zone_id: str, record_id: str, domain_name: str, ip: str, ttl: int = 60, proxied: bool = False) -> dict:
        """Update a DNS A record to point to a new IP."""
        payload = {
            "type": "A",
            "name": domain_name,
            "content": ip,
            "ttl": ttl,
            "proxied": proxied,
        }
        logger.info("Updating Cloudflare DNS: zone=%s record=%s domain=%s -> %s", zone_id, record_id, domain_name, ip)

        retries = 3
        for attempt in range(retries):
            async with httpx.AsyncClient() as client:
                resp = await client.put(
                    f"{self.base_url}/zones/{zone_id}/dns_records/{record_id}",
                    headers=self.headers,
                    json=payload,
                    timeout=10,
                )
                data = resp.json()

                if data.get("success"):
                    logger.info("Cloudflare DNS updated successfully: %s -> %s", domain_name, ip)
                    return data.get("result", {})

                # Retry on rate limit or server error
                if resp.status_code in (429, 500, 502, 503):
                    wait = 2 ** attempt
                    logger.warning("Cloudflare API error (attempt %d/%d), retrying in %ds: %s", attempt + 1, retries, wait, data.get("errors"))
                    import asyncio
                    await asyncio.sleep(wait)
                    continue

                logger.error("Cloudflare update_dns_record failed: %s", data.get("errors"))
                raise Exception(f"Cloudflare API error: {data.get('errors')}")

        raise Exception("Cloudflare API failed after retries")


cf_client = CloudflareClient()
