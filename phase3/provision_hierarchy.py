"""
provision_hierarchy.py — Phase 3: Live ThingsBoard provisioner.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Any, Optional

import requests

# Allow running from project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from phase3.topology import build_topology, all_rooms, CampusAsset

# ─────────────────────── logging ────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger("provision")

# ─────────────────────── config ─────────────────────────────────────────────

TB_URL = os.environ.get("TB_URL", "http://localhost:9090")
TB_USER = os.environ.get("TB_USER", "tenant@campus.com")
TB_PASS = os.environ.get("TB_PASS", "password123")

_RATE_DELAY = 0.05


# ─────────────────────── TB REST client ─────────────────────────────────────

class TBClient:

    def __init__(self, base_url: str, dry_run: bool = False) -> None:
        self.base = base_url.rstrip("/")
        self.dry = dry_run
        self._token: Optional[str] = None

    # ───────────────── auth ─────────────────

    def login(self, email: str, password: str) -> None:

        if self.dry:
            log.info("[DRY RUN] login")
            self._token = "dry-token"
            return

        resp = requests.post(
            f"{self.base}/api/auth/login",
            json={
                "username": email,
                "password": password,
            },
            timeout=10,
        )

        resp.raise_for_status()

        data = resp.json()

        self._token = data["token"]

        log.info("Authenticated as %s", email)

    @property
    def _headers(self) -> dict:
        return {
            "X-Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ───────────────── GET ─────────────────

    def _get(self, path: str, params: dict | None = None) -> Any:

        if self.dry:
            return {}

        resp = requests.get(
            f"{self.base}{path}",
            headers=self._headers,
            params=params,
            timeout=10,
        )

        resp.raise_for_status()

        if not resp.text.strip():
            return {}

        try:
            return resp.json()
        except Exception:
            return {}

    # ───────────────── POST ─────────────────

    def _post(self, path: str, body: dict) -> Any:

        if self.dry:
            log.info("[DRY-RUN] POST %s", path)
            return {}

        resp = requests.post(
            f"{self.base}{path}",
            headers=self._headers,
            json=body,
            timeout=10,
        )

        resp.raise_for_status()

        # Some TB APIs return 204 with empty body
        if not resp.text.strip():
            return {}

        try:
            return resp.json()
        except Exception:
            return {}

    # ───────────────── ATTRIBUTES ─────────────────

    def _post_attr(self, path: str, body: dict) -> None:

        if self.dry:
            log.info("[DRY-RUN] POST ATTR %s", path)
            return

        resp = requests.post(
            f"{self.base}{path}",
            headers=self._headers,
            json=body,
            timeout=10,
        )

        resp.raise_for_status()

    # ───────────────── ASSETS ─────────────────

    def find_asset_by_name(self, name: str) -> Optional[str]:

        try:
            data = self._get(
                "/api/tenant/assets",
                {
                    "pageSize": 1,
                    "page": 0,
                    "textSearch": name,
                },
            )

            for item in data.get("data", []):
                if item.get("name") == name:
                    return item["id"]["id"]

        except Exception:
            pass

        return None

    def upsert_asset(self, name: str, asset_type: str, label: str) -> str:

        existing_id = self.find_asset_by_name(name)

        if existing_id:
            log.info("Asset exists: %s", name)
            return existing_id

        body = {
            "name": name,
            "type": asset_type,
            "label": label,
        }

        result = self._post("/api/asset", body)

        asset_id = result.get("id", {}).get("id", "unknown")

        log.info(
            "Created asset %-30s [%s] id=%s",
            name,
            asset_type,
            asset_id,
        )

        time.sleep(_RATE_DELAY)

        return asset_id

    # ───────────────── RELATIONS ─────────────────

    def add_relation(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        rel_type: str = "Contains",
    ) -> None:

        body = {
            "from": {
                "entityType": from_type.upper(),
                "id": from_id,
            },
            "to": {
                "entityType": to_type.upper(),
                "id": to_id,
            },
            "type": rel_type,
            "typeGroup": "COMMON",
        }

        self._post("/api/relation", body)

        time.sleep(_RATE_DELAY)

    # ───────────────── SERVER ATTRIBUTES ─────────────────

    def set_server_attributes(self, asset_id: str, attrs: dict) -> None:

        self._post_attr(
            f"/api/plugins/telemetry/ASSET/{asset_id}/attributes/SERVER_SCOPE",
            attrs,
        )

        time.sleep(_RATE_DELAY)

    # ───────────────── DEVICES ─────────────────

    def find_device_by_name(self, name: str) -> Optional[str]:

        try:
            data = self._get(
                "/api/tenant/devices",
                {
                    "pageSize": 1,
                    "page": 0,
                    "textSearch": name,
                },
            )

            for item in data.get("data", []):
                if item.get("name") == name:
                    return item["id"]["id"]

        except Exception:
            pass

        return None

    def add_device_relation(self, room_id: str, device_id: str) -> None:

        body = {
            "from": {
                "entityType": "ASSET",
                "id": room_id,
            },
            "to": {
                "entityType": "DEVICE",
                "id": device_id,
            },
            "type": "Contains",
            "typeGroup": "COMMON",
        }

        self._post("/api/relation", body)

        time.sleep(_RATE_DELAY)


# ─────────────────────── provisioner ────────────────────────────────────────

def provision(client: TBClient, campus: CampusAsset) -> None:

    id_map: dict[str, str] = {}

    # Campus
    log.info("=== Creating campus root: %s ===", campus.asset_name)

    campus_id = client.upsert_asset(
        campus.asset_name,
        "Campus",
        campus.label,
    )

    id_map[campus.asset_name] = campus_id

    for building in campus.buildings:

        # Building
        log.info("=== Creating building: %s ===", building.asset_name)

        b_id = client.upsert_asset(
            building.asset_name,
            "Building",
            building.label,
        )

        id_map[building.asset_name] = b_id

        client.add_relation("ASSET", campus_id, "ASSET", b_id)

        for floor in building.floors:

            # Floor
            log.info("Creating floor: %s", floor.asset_name)

            f_id = client.upsert_asset(
                floor.asset_name,
                "Floor",
                floor.label,
            )

            id_map[floor.asset_name] = f_id

            client.add_relation("ASSET", b_id, "ASSET", f_id)

            for room in floor.rooms:

                # Room
                r_id = client.upsert_asset(
                    room.asset_name,
                    "Room",
                    room.label,
                )

                id_map[room.asset_name] = r_id

                client.add_relation("ASSET", f_id, "ASSET", r_id)

                # Attributes
                a = room.attributes

                attrs = {
                    "square_footage": a.square_footage,
                    "occupant_capacity": a.occupant_capacity,
                    "coordinates_x": a.coordinates_x,
                    "coordinates_y": a.coordinates_y,
                    "room_type": a.room_type,
                }

                client.set_server_attributes(r_id, attrs)

                # Devices
                for device_name in room.devices:

                    device_id = client.find_device_by_name(device_name)

                    if device_id:
                        client.add_device_relation(r_id, device_id)
                    else:
                        log.warning("Device not found: %s", device_name)

    log.info(
        "Provisioning complete. Assets created: %d",
        len(id_map),
    )


# ─────────────────────── args ───────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:

    p = argparse.ArgumentParser()

    p.add_argument("--dry-run", action="store_true")

    p.add_argument("--url", default=TB_URL)

    p.add_argument("--user", default=TB_USER)

    p.add_argument("--pass", dest="password", default=TB_PASS)

    return p.parse_args()


# ─────────────────────── main ───────────────────────────────────────────────

def main() -> None:

    args = _parse_args()

    client = TBClient(
        args.url,
        dry_run=args.dry_run,
    )

    client.login(args.user, args.password)

    campus = build_topology()

    provision(client, campus)


if __name__ == "__main__":
    main()
    