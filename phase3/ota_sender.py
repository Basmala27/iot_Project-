"""
ota_sender.py — Phase 3: OTA Configuration Update Sender

Sends signed OTA configuration updates to the IoT fleet over MQTT.
Supports broadcast (all floors), floor-level, and room-level targeting.

Usage:
    python phase3/ota_sender.py --target all --alpha 0.01 --beta 0.20 --version 1.1
    python phase3/ota_sender.py --target floor --floor 5 --alpha 0.015 --beta 0.25 --version 1.2
    python phase3/ota_sender.py --target room --floor 5 --room-id b01-f05-r503 --alpha 0.02 --beta 0.30 --version 1.3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import paho.mqtt.client as mqtt

# Add parent directory to path to import config
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from config import cfg

logger = logging.getLogger(__name__)


def send_ota_update(
    target: str,
    building: str,
    floor: int | None,
    room_id: str | None,
    new_params: dict,
    num_floors: int = 10,
) -> None:
    """
    Send a signed OTA configuration update to the fleet.

    Args:
        target: Target scope - "all", "floor", or "room"
        building: Building ID (e.g., "b01")
        floor: Floor number (required for "floor" and "room" targets)
        room_id: Room ID (required for "room" target)
        new_params: Dictionary containing at minimum: alpha, beta, version
        num_floors: Total number of floors (used for broadcast)
    """
    # Sign the payload with SHA-256 — must use sort_keys=True
    config_json = json.dumps(new_params, sort_keys=True)
    signature = hashlib.sha256(config_json.encode()).hexdigest()

    # Build list of topics to publish to
    # NOTE: MQTT wildcards (+, #) are for SUBSCRIBE only — never use in publish topics
    if target == "all":
        # Broadcast: publish to every floor individually
        topics = [
            f"campus/{building}/f{f:02d}/ota"
            for f in range(1, num_floors + 1)
        ]
        target_room = None
    elif target == "floor":
        if floor is None:
            raise ValueError("Floor parameter required for floor-level targeting")
        topics = [f"campus/{building}/f{floor:02d}/ota"]
        target_room = None
    elif target == "room":
        if floor is None:
            raise ValueError("Floor parameter required for room-level targeting")
        topics = [f"campus/{building}/f{floor:02d}/ota"]
        target_room = room_id
    else:
        raise ValueError(f"Invalid target: {target}. Must be 'all', 'floor', or 'room'")

    # Build the complete payload
    payload = {
        "config": new_params,
        "signature": signature,
        "target_room": target_room,
    }
    payload_json = json.dumps(payload)

    # Connect to MQTT broker and publish to all topics
    client = mqtt.Client(client_id="ota_sender")
    client.connect(cfg.mqtt.broker_host, cfg.mqtt.broker_port, 60)
    client.loop_start()

    for topic in topics:
        result = client.publish(topic, payload_json, qos=2)
        result.wait_for_publish()
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(
                "[OTA] Published → %s | version=%s | sig=%s...",
                topic, new_params.get("version"), signature[:16],
            )
        else:
            logger.error("[OTA] Failed to publish to %s: rc=%d", topic, result.rc)

    client.loop_stop()
    client.disconnect()
    logger.info("[OTA] Done. Published to %d topic(s). SHA-256: %s", len(topics), signature)


def main() -> None:
    """Main entry point for OTA sender script."""
    parser = argparse.ArgumentParser(
        description="Send signed OTA configuration updates to the IoT fleet"
    )
    parser.add_argument(
        "--target",
        choices=["all", "floor", "room"],
        required=True,
        help="Target scope: all (broadcast), floor, or room",
    )
    parser.add_argument(
        "--floor",
        type=int,
        help="Floor number (required for 'floor' and 'room' targets)",
    )
    parser.add_argument(
        "--room-id",
        type=str,
        help="Room ID (required for 'room' target, e.g., b01-f05-r503)",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        required=True,
        help="New thermal leakage coefficient (alpha)",
    )
    parser.add_argument(
        "--beta",
        type=float,
        required=True,
        help="New HVAC effectiveness coefficient (beta)",
    )
    parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="New firmware version string (e.g. 1.1)",
    )

    args = parser.parse_args()

    if args.target in ["floor", "room"] and args.floor is None:
        parser.error("--floor is required for 'floor' and 'room' targets")

    if args.target == "room" and args.room_id is None:
        parser.error("--room-id is required for 'room' target")

    new_params = {
        "alpha":   args.alpha,
        "beta":    args.beta,
        "version": args.version,
    }

    send_ota_update(
        target=args.target,
        building=cfg.simulation.building_id,
        floor=args.floor,
        room_id=args.room_id,
        new_params=new_params,
        num_floors=cfg.simulation.num_floors,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    main()