import httpx


class InfoService:

    async def get_current_ip(self) -> str:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://api64.ipify.org?format=json", timeout=10)
                resp.raise_for_status()
                return resp.json().get("ip", "unknown")
        except httpx.HTTPStatusError as e:
            return f"HTTP error: {e.response.status_code}"
        except httpx.TimeoutException:
            return "Timeout fetching IP"
        except Exception as e:
            return f"Error: {e}"

    async def sync_duckdns(self, domain: str, token: str) -> str:
        if not token:
            return "Error: DUCKDNS_TOKEN is not set"

        ip = await self.get_current_ip()
        if any(ip.startswith(p) for p in ("HTTP error", "Timeout", "Error")):
            return f"Failed to get current IP: {ip}"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://www.duckdns.org/update",
                    params={"domains": domain, "token": token, "ip": ip},
                    timeout=10,
                )
                resp.raise_for_status()
                text = resp.text.strip()
                if text == "OK":
                    return f"Synced {domain}.duckdns.org → {ip}"
                return f"DuckDNS returned: {text}"
        except httpx.HTTPStatusError as e:
            body = e.response.text.strip() if e.response.text else "empty"
            return f"HTTP error: {e.response.status_code} — {body}"
        except httpx.TimeoutException:
            return "Timeout syncing DuckDNS"
        except Exception as e:
            return f"Error: {e}"

    async def resolve_domain(self, domain: str) -> str:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://dns.google/resolve?name={domain}&type=A",
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                answers = data.get("Answer", [])
                if answers:
                    return ", ".join(a.get("data", "?") for a in answers)
                return "No records found"
        except httpx.HTTPStatusError as e:
            return f"HTTP error: {e.response.status_code}"
        except httpx.TimeoutException:
            return "Timeout resolving domain"
        except Exception as e:
            return f"Error: {e}"
