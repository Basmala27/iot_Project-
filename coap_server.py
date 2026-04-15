# coap_server.py
import asyncio
import json
import logging
from aiocoap import Message, Context, resource
from aiocoap.numbers import ContentFormat
import time
import random

class TelemetryResource(resource.Resource):
    """CoAP resource for telemetry data"""
    def __init__(self, room):
        super().__init__()
        self.room = room
        self.observers = set()

    async def render_get(self, request):
        """Handle GET requests for telemetry"""
        telemetry = self.room.get_telemetry()
        payload = json.dumps(telemetry).encode('utf-8')
        
        return Message(
            payload=payload,
            content_format=ContentFormat.APPLICATION_JSON
        )

    def add_observation(self, request, serverobservation):
        """Add observer for telemetry updates"""
        self.observers.add(serverobservation)
        serverobservation.accept()
        
        # Schedule periodic updates
        asyncio.create_task(self.periodic_update(serverobservation))

    async def periodic_update(self, observation):
        """Send periodic telemetry updates to observers"""
        while True:
            try:
                self.room.update()
                telemetry = self.room.get_telemetry()
                payload = json.dumps(telemetry).encode('utf-8')
                
                observation.trigger(Message(
                    payload=payload,
                    content_format=ContentFormat.APPLICATION_JSON
                ))
                
                await asyncio.sleep(5)  # Update interval
                
            except Exception as e:
                logging.error(f"Error in periodic update: {e}")
                break

class ActuatorResource(resource.Resource):
    """CoAP resource for actuator control"""
    def __init__(self, room):
        super().__init__()
        self.room = room

    async def render_put(self, request):
        """Handle PUT requests for actuator control"""
        try:
            command = json.loads(request.payload.decode('utf-8'))
            result = self.room.process_command(command)
            
            return Message(
                payload=json.dumps(result).encode('utf-8'),
                content_format=ContentFormat.APPLICATION_JSON
            )
            
        except Exception as e:
            error_response = {
                "status": "error",
                "message": str(e),
                "room_id": self.room.room_id
            }
            return Message(
                payload=json.dumps(error_response).encode('utf-8'),
                code=4.00  # Bad Request
            )

class CoAPServer:
    """CoAP Server for individual room"""
    def __init__(self, room, port=5683):
        self.room = room
        self.port = port
        self.context = None
        self.site = None

    async def start(self):
        """Start CoAP server"""
        try:
            # Create CoAP context
            self.context = await Context.create_server_context(self.port)
            
            # Create resource tree
            self.site = resource.Site()
            
            # Add resources
            telemetry_path = f"telemetry"
            actuator_path = f"actuators"
            
            self.site.add_resource([telemetry_path], TelemetryResource(self.room))
            self.site.add_resource([actuator_path], ActuatorResource(self.room))
            
            # Mount site
            self.context.serversite = self.site
            
            logging.info(f"CoAP Server for {self.room.room_id} started on port {self.port}")
            
        except Exception as e:
            logging.error(f"Failed to start CoAP server: {e}")
            raise

    async def stop(self):
        """Stop CoAP server"""
        if self.context:
            await self.context.shutdown()
            logging.info(f"CoAP Server for {self.room.room_id} stopped")

class CoAPNode:
    """Complete CoAP node with room simulation"""
    def __init__(self, room, base_port=5683):
        self.room = room
        self.server = CoAPServer(room, base_port)
        self.running = False

    async def start(self):
        """Start CoAP node"""
        self.running = True
        
        # Add startup jitter
        await asyncio.sleep(random.uniform(0, 3))
        
        try:
            await self.server.start()
            logging.info(f"CoAP Node {self.room.room_id} started successfully")
        except Exception as e:
            logging.error(f"Failed to start CoAP Node {self.room.room_id}: {e}")
            raise

    async def stop(self):
        """Stop CoAP node"""
        self.running = False
        await self.server.stop()

async def run_coap_room(room, port_offset=0):
    """Run CoAP room server"""
    node = CoAPNode(room, port=5683 + port_offset)
    
    try:
        await node.start()
        
        # Keep server running
        while node.running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logging.error(f"Error in CoAP room {room.room_id}: {e}")
    finally:
        await node.stop()
