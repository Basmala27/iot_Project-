# MANUAL ADDITIONS NEEDED IN engine.py

The following manual changes are required in `engine.py` to integrate Phase 3 OTA functionality:

## 1. In imports section, add:

```python
from phase3.ota_handler import OTAHandler
```

## 2. In build_fleet(), after creating each Room, create an OTAHandler:

```python
# After: rooms[room.id] = room
room._ota = OTAHandler(room.id, mqtt_manager, cfg)
```

## 3. In room_task(), in the MQTT section after connect:

Subscribe to OTA topics:

```python
# After MQTT connection is established
for topic in room._ota.get_ota_topics():
    mqtt_manager.subscribe(topic, callback=room._ota.verify_and_apply)
```

## 4. In the on_message handler (wherever MQTT messages are received):

Add OTA message handling:

```python
# Check if message is an OTA update
if msg.topic.endswith("/ota"):
    result = room._ota.verify_and_apply(msg.payload, room.alpha, room.beta, room.current_version)
    if result and "security_alert" in result:
        # Publish security telemetry to ThingsBoard
        await mqtt_manager.publish("v1/devices/me/telemetry", result, qos=1)
    elif result:
        # Apply new configuration
        room.alpha = result["new_alpha"]
        room.beta = result["new_beta"]
        room.current_version = result["new_version"]
        # Publish version update as client attribute
        await mqtt_manager.publish("v1/devices/me/attributes",
            room._ota.build_version_attribute(room.current_version), qos=1)
```

## 5. Add current_version attribute to Room class (in room.py):

```python
# In Room.__init__(), add:
self.current_version: str = "1.0"  # Default firmware version
```

## 6. Ensure Room class has the following attributes for shadow sync:

These should already exist, but verify:
- `room.hvac_mode` (maps to reported_hvac)
- `room.light_level` (maps to reported_dimmer)

## Notes:

- The OTAHandler expects the Room object to have `alpha`, `beta`, and `current_version` attributes
- Security alerts are published as telemetry with the key "security_alert"
- Version updates are published as client attributes with the key "current_version"
- The handler supports both targeted (floor-level) and broadcast OTA updates
- SHA-256 signature verification prevents tampered configuration updates
