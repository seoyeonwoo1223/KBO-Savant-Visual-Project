from __future__ import annotations

import json
import re
import time
from typing import Any

import requests


class VisualBaseballClient:
    def __init__(self, base_url: str = "https://visualbaseball.com", timeout: int = 30):
        self.base_url, self.timeout, self.session = base_url.rstrip("/"), timeout, requests.Session()

    def bootstrap(self) -> None:
        response = self.session.get(f"{self.base_url}/schedule", timeout=self.timeout); response.raise_for_status()
        token = re.search(r'<meta name="api-token" content="([^"]+)"', response.text, re.I)
        if not token: raise RuntimeError("Public API token was not present in the session page")
        self.session.headers.update({"X-Api-Token": token.group(1), "User-Agent": "visualbaseball-savant-collector/1.0"})

    def get_json(self, path: str, referer: str = "/schedule") -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                if "X-Api-Token" not in self.session.headers:
                    self.bootstrap()
                response = self.session.get(f"{self.base_url}{path}", headers={"Referer": f"{self.base_url}{referer}"}, timeout=self.timeout)
                if response.status_code == 403:
                    self.session.headers.pop("X-Api-Token", None)
                    raise requests.HTTPError("403 requires a refreshed public session", response=response)
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"transient HTTP {response.status_code}", response=response)
                response.raise_for_status()
                # The API omits a reliable charset. Decode its UTF-8 bytes explicitly so
                # Korean final-status text (종료) is not mojibake and skipped as non-final.
                payload = json.loads(response.content.decode("utf-8-sig"))
                time.sleep(1)
                return payload
            except (requests.RequestException, json.JSONDecodeError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"GET failed after retries: {path}: {last_error}") from last_error
