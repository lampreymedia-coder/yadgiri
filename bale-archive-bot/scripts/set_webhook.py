"""Register (or inspect) the webhook.

Usage:
    BALE_BOT_TOKEN=... WEBHOOK_BASE_URL=https://your.domain \
    WEBHOOK_SECRET_PATH=<random> python scripts/set_webhook.py [--info] [--delete]
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

BASE = os.environ.get("BALE_API_BASE", "https://tapi.bale.ai")
TOKEN = os.environ.get("BALE_BOT_TOKEN", "")


async def main() -> int:
    if not TOKEN:
        print("BALE_BOT_TOKEN is required", file=sys.stderr)
        return 2
    async with httpx.AsyncClient(timeout=15) as client:
        if "--info" in sys.argv:
            response = await client.post(f"{BASE}/bot{TOKEN}/getWebhookInfo")
            print(response.text)
            return 0
        if "--delete" in sys.argv:
            response = await client.post(f"{BASE}/bot{TOKEN}/setWebhook", json={"url": ""})
            print(response.text)
            return 0
        base_url = os.environ.get("WEBHOOK_BASE_URL", "").rstrip("/")
        secret = os.environ.get("WEBHOOK_SECRET_PATH", "")
        if not base_url or not secret:
            print("WEBHOOK_BASE_URL and WEBHOOK_SECRET_PATH are required", file=sys.stderr)
            return 2
        url = f"{base_url}/webhook/{secret}"
        response = await client.post(f"{BASE}/bot{TOKEN}/setWebhook", json={"url": url})
        print(response.text)
        return 0 if response.json().get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
