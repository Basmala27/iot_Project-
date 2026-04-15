# mqtt_client.py
import gmqtt
import asyncio
import json
import logging

BROKER = "localhost"
PORT = 1883

class MQTTHandler:
    def __init__(self, client_id, room=None):
        self.client = gmqtt.Client(client_id)
        self.room = room
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        
        # Set Last Will and Testament
        self.client.set_config({
            'will_message': {
                'topic': f'campus/b01/f01/{client_id}/status',
                'payload': json.dumps({'status': 'OFFLINE', 'timestamp': 0}),
                'qos': 1,
                'retain': True
            }
        })

    async def connect(self):
        try:
            await self.client.connect(BROKER, PORT)
            logging.info(f"MQTT Client {self.client.client_id} connected")
        except Exception as e:
            logging.error(f"MQTT Connection failed: {e}")
            raise

    async def publish(self, topic, message, qos=2):
        """Publish with QoS 2 for critical messages"""
        payload = json.dumps(message, default=str)
        self.client.publish(topic, payload, qos=qos, retain=False)

    async def publish_command(self, topic, message):
        """Publish commands with QoS 2 for exactly-once delivery"""
        await self.publish(topic, message, qos=2)

    async def subscribe(self, topic, qos=2):
        """Subscribe with QoS 2 for critical commands"""
        self.client.subscribe(topic, qos=qos)

    def on_connect(self, client, flags, rc, properties):
        logging.info(f"Connected with result code {rc}")

    def on_disconnect(self, client, packet, exc=None):
        logging.info(f"Disconnected from broker")

    async def on_message(self, client, topic, payload, qos, properties):
        try:
            msg = json.loads(payload.decode())
            logging.info(f"[COMMAND RECEIVED] {topic}: {msg}")

            if self.room:
                if "hvac_mode" in msg:
                    self.room.hvac_mode = msg["hvac_mode"]
                    logging.info(f"Updated HVAC mode for {self.room.room_id} to {msg['hvac_mode']}")
                
                if "lighting_dimmer" in msg:
                    self.room.lighting_dimmer = msg["lighting_dimmer"]
                    
                if "target_temp" in msg:
                    self.room.target_temp = msg["target_temp"]
                    
        except Exception as e:
            logging.error(f"Error processing message: {e}")