# main.py
import asyncio
import random
import logging
import yaml
import time
from room import Room
from mqtt_client import MQTTHandler
from coap_server import run_coap_room

# Configuration
NUM_FLOORS = 10
ROOMS_PER_FLOOR = 20
MQTT_ROOMS_PER_FLOOR = 10
COAP_ROOMS_PER_FLOOR = 10
TICK_INTERVAL = 5

def load_config():
    """Load configuration from YAML file"""
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {
            'num_floors': NUM_FLOORS,
            'rooms_per_floor': ROOMS_PER_FLOOR,
            'tick_interval': TICK_INTERVAL,
            'mqtt_broker': 'localhost',
            'mqtt_port': 1883
        }

def generate_room_id(building_id, floor_num, room_num):
    """Generate standardized room ID"""
    return f"{building_id}-f{floor_num:02d}-r{room_num:03d}"

async def run_mqtt_room(room, floor_num, room_num):
    """Run MQTT room node with precision timing"""
    # Startup Jitter to prevent thundering herd
    await asyncio.sleep(random.uniform(0, 3))
    
    try:
        # Initialize MQTT handler
        client_id = f"mqtt-{room.room_id}"
        mqtt = MQTTHandler(client_id, room)
        await mqtt.connect()
        
        # Subscribe to commands with QoS 2
        cmd_topic = f"campus/b01/f{floor_num:02d}/{room.room_id}/cmd"
        await mqtt.subscribe(cmd_topic, qos=2)
        
        logging.info(f"MQTT Room {room.room_id} connected and subscribed")
        
        while True:
            start_time = time.time()
            
            # Update room state
            room.update()
            
            # Get telemetry data
            telemetry_data = room.get_telemetry()
            
            # Define topics
            telemetry_topic = f"campus/b01/f{floor_num:02d}/{room.room_id}/telemetry"
            status_topic = f"campus/b01/f{floor_num:02d}/{room.room_id}/status"
            heartbeat_topic = f"campus/b01/f{floor_num:02d}/{room.room_id}/heartbeat"
            
            # Publish telemetry with QoS 1
            await mqtt.publish(telemetry_topic, telemetry_data, qos=1)
            
            # Publish status with QoS 1 (retained)
            status_data = {
                "status": "ONLINE" if not room.node_dropout else "OFFLINE",
                "timestamp": int(time.time()),
                "client_id": client_id
            }
            await mqtt.publish(status_topic, status_data, qos=1)
            
            # Publish heartbeat
            heartbeat_data = {
                "room_id": room.room_id,
                "timestamp": int(time.time()),
                "tick_count": room.tick_count
            }
            await mqtt.publish(heartbeat_topic, heartbeat_data, qos=0)
            
            # Precision timing compensation
            processing_time = time.time() - start_time
            actual_sleep = max(0, TICK_INTERVAL - processing_time)
            
            await asyncio.sleep(actual_sleep)
            
    except Exception as e:
        logging.error(f"Error in MQTT room {room.room_id}: {e}")
        # Retry connection
        await asyncio.sleep(5)

async def run_coap_room_with_port(room, floor_num, room_num, port_offset):
    """Run CoAP room with specific port"""
    try:
        await run_coap_room(room, port_offset)
        logging.info(f"CoAP Room {room.room_id} started on port {5683 + port_offset}")
    except Exception as e:
        logging.error(f"Error in CoAP room {room.room_id}: {e}")

async def main():
    """Main simulation engine"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config = load_config()
    num_floors = config.get('num_floors', NUM_FLOORS)
    rooms_per_floor = config.get('rooms_per_floor', ROOMS_PER_FLOOR)
    
    logging.info(f"Starting IoT Campus Simulation: {num_floors} floors, {rooms_per_floor} rooms per floor")
    
    tasks = []
    room_counter = 0
    coap_port_counter = 0
    
    # Generate rooms for each floor
    for floor in range(1, num_floors + 1):
        for room in range(1, rooms_per_floor + 1):
            room_id = generate_room_id("b01", floor, room)
            room_obj = Room(room_id)
            
            # Randomly assign to MQTT or CoAP (50/50 split)
            if room <= MQTT_ROOMS_PER_FLOOR:
                # MQTT Room
                task = asyncio.create_task(
                    run_mqtt_room(room_obj, floor, room)
                )
                tasks.append(task)
                logging.info(f"Created MQTT room: {room_id}")
            else:
                # CoAP Room
                task = asyncio.create_task(
                    run_coap_room_with_port(room_obj, floor, room, coap_port_counter)
                )
                tasks.append(task)
                logging.info(f"Created CoAP room: {room_id}")
                coap_port_counter += 1
            
            room_counter += 1
    
    logging.info(f"Total rooms created: {room_counter}")
    logging.info(f"MQTT rooms: {len([t for t in tasks if 'mqtt' in str(t)])}")
    logging.info(f"CoAP rooms: {len([t for t in tasks if 'coap' in str(t)])}")
    
    try:
        # Run all tasks
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logging.info("Simulation stopped by user")
    except Exception as e:
        logging.error(f"Simulation error: {e}")

if __name__ == "__main__":
    asyncio.run(main())