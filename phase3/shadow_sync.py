"""
shadow_sync.py — Phase 3: Shadow State Synchronization Checker

Queries ThingsBoard REST API to check sync status for all devices.
Compares Shared Attributes (desired state) vs Client Attributes (reported state)
to identify rooms that are out of sync.

Usage:
    python shadow_sync.py
    python shadow_sync.py --filter-unsynced
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ThingsBoard connection settings
TB_URL = os.getenv("TB_URL", "http://localhost:8080")
TB_USER = os.getenv("TB_USER", "tenant@thingsboard.org")
TB_PASS = os.getenv("TB_PASS", "tenant")

# Rate limiting delay between API calls (same as provision_hierarchy.py)
_RATE_DELAY = 0.1


class TBClient:
    """
    ThingsBoard REST API client for shadow synchronization checks.
    
    Handles authentication and provides methods for querying devices and attributes.
    """

    def __init__(self, url: str, username: str, password: str) -> None:
        """
        Initialize ThingsBoard client.

        Args:
            url: ThingsBoard base URL
            username: Login username
            password: Login password
        """
        self.url = url
        self.username = username
        self.password = password
        self.token: str | None = None

    def login(self) -> None:
        """Authenticate with ThingsBoard and store JWT token."""
        payload = {"username": self.username, "password": self.password}
        response = requests.post(f"{self.url}/api/auth/login", json=payload)
        response.raise_for_status()
        self.token = response.json()["token"]
        logger.info(f"Successfully logged in to ThingsBoard at {self.url}")

    def _get_headers(self) -> dict[str, str]:
        """
        Get HTTP headers with authorization token.

        Returns:
            Dictionary with Authorization header

        Raises:
            ValueError: If not logged in (no token available)
        """
        if not self.token:
            raise ValueError("Not logged in. Call login() first.")
        return {"X-Authorization": f"Bearer {self.token}"}

    def _get(self, endpoint: str, params: dict | None = None) -> Any:
        """
        Perform GET request to ThingsBoard API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.url}{endpoint}"
        response = requests.get(url, params=params, headers=self._get_headers())
        response.raise_for_status()
        time.sleep(_RATE_DELAY)
        return response.json()

    def get_attributes(self, device_id: str, scope: str) -> dict[str, Any]:
        """
        Get device attributes for a specific scope.

        Args:
            device_id: Device ID (UUID)
            scope: Attribute scope - "CLIENT_SCOPE", "SHARED_SCOPE", or "SERVER_SCOPE"

        Returns:
            Dictionary of attribute key-value pairs
        """
        endpoint = f"/api/plugins/telemetry/DEVICE/{device_id}/values/attributes/{scope}"
        data = self._get(endpoint)
        # Convert list of dicts to single dict
        return {item["key"]: item["value"] for item in data}

    def get_all_devices(self, page_size: int = 50) -> list[dict[str, Any]]:
        """
        Get all devices with pagination.

        Args:
            page_size: Number of devices per page

        Returns:
            List of device dictionaries with id and name
        """
        devices = []
        page = 0
        while True:
            params = {"pageSize": page_size, "page": page}
            data = self._get("/api/tenant/devices", params=params)
            devices.extend(data["data"])
            if len(data["data"]) < page_size:
                break
            page += 1
        return devices


def check_all_devices(client: TBClient) -> list[dict[str, Any]]:
    """
    Check sync status for all devices.

    For each device, compares Shared Attributes (desired state) with
    Client Attributes (reported state) to determine if the device is in sync.

    Args:
        client: ThingsBoard client instance

    Returns:
        List of dictionaries with sync status for each device
    """
    devices = client.get_all_devices()
    results = []

    logger.info(f"Checking sync status for {len(devices)} devices...")

    for device in devices:
        device_id = device["id"]["id"]
        device_name = device["name"]

        try:
            # Get shared attributes (desired state)
            shared_attrs = client.get_attributes(device_id, "SHARED_SCOPE")
            # Get client attributes (reported state)
            client_attrs = client.get_attributes(device_id, "CLIENT_SCOPE")

            # Extract relevant attributes
            desired_hvac = shared_attrs.get("desired_hvac")
            desired_dimmer = shared_attrs.get("desired_dimmer")
            reported_hvac = client_attrs.get("reported_hvac")
            reported_dimmer = client_attrs.get("reported_dimmer")
            current_version = client_attrs.get("current_version", "unknown")

            # Determine sync status
            in_sync = desired_hvac == reported_hvac and desired_dimmer == reported_dimmer

            results.append(
                {
                    "device_name": device_name,
                    "desired_hvac": desired_hvac,
                    "reported_hvac": reported_hvac,
                    "desired_dimmer": desired_dimmer,
                    "reported_dimmer": reported_dimmer,
                    "current_version": current_version,
                    "in_sync": in_sync,
                }
            )

        except Exception as e:
            logger.error(f"Error checking device {device_name}: {e}")
            results.append(
                {
                    "device_name": device_name,
                    "desired_hvac": None,
                    "reported_hvac": None,
                    "desired_dimmer": None,
                    "reported_dimmer": None,
                    "current_version": "error",
                    "in_sync": False,
                }
            )

    return results


def print_sync_report(results: list[dict[str, Any]], show_unsynced_only: bool = False) -> None:
    """
    Print a formatted sync status report.

    Args:
        results: List of device sync status dictionaries
        show_unsynced_only: If True, only show out-of-sync devices
    """
    # Filter results if requested
    if show_unsynced_only:
        filtered_results = [r for r in results if not r["in_sync"]]
    else:
        filtered_results = results

    # Print header
    print("\n" + "=" * 120)
    print("SHADOW STATE SYNCHRONIZATION REPORT")
    print("=" * 120)
    print(
        f"{'Device':<20} {'Desired HVAC':<15} {'Reported HVAC':<15} "
        f"{'Desired Dimmer':<15} {'Reported Dimmer':<15} {'Version':<10} {'Status':<15}"
    )
    print("-" * 120)

    # Print each device
    for result in filtered_results:
        status = "✓ IN SYNC" if result["in_sync"] else "✗ OUT OF SYNC"
        print(
            f"{result['device_name']:<20} "
            f"{str(result['desired_hvac']):<15} "
            f"{str(result['reported_hvac']):<15} "
            f"{str(result['desired_dimmer']):<15} "
            f"{str(result['reported_dimmer']):<15} "
            f"{str(result['current_version']):<10} "
            f"{status:<15}"
        )

    # Print summary
    total = len(results)
    in_sync_count = sum(1 for r in results if r["in_sync"])
    out_of_sync_count = total - in_sync_count

    print("-" * 120)
    print(f"SUMMARY: Total: {total} | In Sync: {in_sync_count} | Out of Sync: {out_of_sync_count}")
    print("=" * 120 + "\n")


def main() -> None:
    """Main entry point for shadow sync checker."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check shadow state synchronization for all devices"
    )
    parser.add_argument(
        "--filter-unsynced",
        action="store_true",
        help="Show only out-of-sync devices",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    try:
        client = TBClient(TB_URL, TB_USER, TB_PASS)
        client.login()
        results = check_all_devices(client)
        print_sync_report(results, show_unsynced_only=args.filter_unsynced)
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error: {e}")
        logger.error(f"Is ThingsBoard running at {TB_URL}?")
    except Exception as e:
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    main()
