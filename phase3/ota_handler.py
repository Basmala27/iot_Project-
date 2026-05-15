"""
ota_handler.py — Phase 3: OTA Configuration Update Handler

Provides OTA receive and verify logic for individual rooms.
Intended to be imported into engine.py as a mixin/module.

Usage:
    from phase3.ota_handler import OTAHandler
    
    room._ota = OTAHandler(room.id, mqtt_manager, cfg)
    for topic in room._ota.get_ota_topics():
        mqtt_manager.subscribe(topic, callback=room._ota.verify_and_apply)
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class OTAHandler:
    """
    Handles OTA configuration updates for a single room.
    
    Manages subscription to OTA topics, payload verification via SHA-256,
    and application of new configuration parameters.
    """

    def __init__(self, room_id: str, mqtt_client: Any, cfg: Any) -> None:
        """
        Initialize OTA handler for a room.

        Args:
            room_id: Room identifier (e.g., "b01-f01-r001")
            mqtt_client: MQTT client instance (for reference)
            cfg: Configuration object with simulation settings
        """
        self.room_id = room_id
        self.mqtt_client = mqtt_client
        self.cfg = cfg
        
        # Extract floor from room_id (e.g., "b01-f01-r001" -> "f01")
        parts = room_id.split("-")
        if len(parts) >= 2:
            self.floor_id = parts[1]
        else:
            raise ValueError(f"Invalid room_id format: {room_id}")

        self.building = cfg.simulation.building_id

    def get_ota_topics(self) -> list[str]:
        """
        Get the OTA topics this room should subscribe to.

        Returns:
            List of MQTT topic strings for OTA subscriptions:
            - Targeted floor topic: campus/{building}/{floor_id}/ota
            - Broadcast topic: campus/{building}/broadcast/ota
        """
        return [
            f"campus/{self.building}/{self.floor_id}/ota",
            f"campus/{self.building}/broadcast/ota",
        ]

    def verify_and_apply(
        self,
        raw_payload: bytes,
        current_alpha: float,
        current_beta: float,
        current_version: str,
    ) -> dict | None:
        """
        Verify OTA payload signature and apply configuration if valid.

        Args:
            raw_payload: Raw JSON payload bytes from MQTT
            current_alpha: Current alpha value in the room
            current_beta: Current beta value in the room
            current_version: Current firmware version string

        Returns:
            Dictionary with new config if valid, security alert dict if invalid,
            or None if message is not for this room.
        """
        try:
            message = json.loads(raw_payload.decode())
        except json.JSONDecodeError as e:
            logger.error(f"[{self.room_id}] Failed to parse OTA payload: {e}")
            return None

        # Extract config and signature
        config = message.get("config")
        signature = message.get("signature")
        target_room = message.get("target_room")

        if not config or not signature:
            logger.warning(f"[{self.room_id}] OTA payload missing config or signature")
            return None

        # Check if this update is targeted to this specific room
        if target_room and target_room != self.room_id:
            logger.debug(
                f"[{self.room_id}] OTA update targeted to {target_room}, skipping"
            )
            return None

        # Verify signature by recalculating SHA-256
        config_json = json.dumps(config, sort_keys=True)
        calculated_signature = hashlib.sha256(config_json.encode()).hexdigest()

        if calculated_signature != signature:
            logger.warning(
                f"[{self.room_id}] SECURITY ALERT: Signature mismatch! "
                f"Expected: {signature}, Calculated: {calculated_signature}"
            )
            return {
                "security_alert": "TAMPER_DETECTED",
                "room_id": self.room_id,
                "received_signature": signature,
            }

        # Signature verified - extract new parameters
        new_alpha = config.get("alpha")
        new_beta = config.get("beta")
        new_version = config.get("version")

        if new_alpha is None or new_beta is None or new_version is None:
            logger.warning(
                f"[{self.room_id}] OTA config missing required parameters "
                f"(alpha, beta, or version)"
            )
            return None

        logger.info(
            f"[{self.room_id}] OTA update verified and applied: "
            f"alpha: {current_alpha} -> {new_alpha}, "
            f"beta: {current_beta} -> {new_beta}, "
            f"version: {current_version} -> {new_version}"
        )

        return {
            "new_alpha": new_alpha,
            "new_beta": new_beta,
            "new_version": new_version,
        }

    def build_version_attribute(self, version: str) -> dict:
        """
        Build the version attribute dictionary for ThingsBoard client attributes.

        Args:
            version: Current firmware version string

        Returns:
            Dictionary with current_version key for ThingsBoard attributes
        """
        return {"current_version": version}

    def build_tamper_telemetry(self, received_sig: str) -> dict:
        """
        Build tamper detection telemetry for security alert.

        Args:
            received_sig: The invalid signature that was received

        Returns:
            Dictionary with security alert details for telemetry
        """
        return {
            "security_alert": "TAMPER_DETECTED",
            "room_id": self.room_id,
            "received_signature": received_sig,
        }
