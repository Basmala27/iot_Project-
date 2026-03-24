import yaml
import sqlite3
import time
import random
import asyncio
import paho.mqtt.client as mqtt
import logging

# Load config
with open("config.yaml") as f:
    config = yaml.safe_load(f)

NUM_FLOORS = config['num_floors']
ROOMS_PER_FLOOR = config['rooms_per_floor']
TICK_INTERVAL = config['tick_interval']
FAULT_RATE = config['fault_rate']
TEMP_RANGE = {'min': 18, 'max': 26}  # You can add this to config.yaml if you want
BROKER = config['mqtt_broker']
PORT = config['mqtt_port']

# DB setup
conn = sqlite3.connect('iot_simulation.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS rooms (
    room_id TEXT PRIMARY KEY,
    last_temp REAL,
    last_humidity REAL,
    hvac_mode TEXT,
    target_temp REAL,
    last_update INTEGER
)
''')
conn.commit()

# Fleet – rooms
rooms = []
for floor in range(1, NUM_FLOORS + 1):
    for room_num in range(1, ROOMS_PER_FLOOR + 1):
        room_id = f"b01-f{floor:02}-r{room_num:03}"
        rooms.append({
            "room_id": room_id,
            "temp": 22.0,
            "humidity": 50.0,
            "hvac_mode": "ECO",
            "target_temp": 22.0,
            "occupancy": False,
            "light_level": 0,
            "floor": floor,
            "room_num": room_num,
            "mqtt_topic": f"campus/bldg_01/floor_{floor:02}/room_{room_num:03}/telemetry"
        })

# Save room state to DB
def save_room(room):
    cursor.execute('''
    INSERT OR REPLACE INTO rooms
    (room_id, last_temp, last_humidity, hvac_mode, target_temp, last_update)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (room['room_id'], room['temp'], room['humidity'], room['hvac_mode'], room['target_temp'], int(time.time())))
    conn.commit()

# Load previous state from DB
def load_all_rooms():
    cursor.execute("SELECT * FROM rooms")
    rows = cursor.fetchall()
    for row in rows:
        room = next((r for r in rooms if r['room_id'] == row[0]), None)
        if room:
            room['temp'], room['humidity'], room['hvac_mode'], room['target_temp'] = row[1], row[2], row[3], row[4]

# MQTT Setup
client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")

client.on_connect = on_connect
client.connect(BROKER, PORT, 60)
client.loop_start()  # Start MQTT loop in background

def mqtt_publish(payload, topic):
    client.publish(topic, str(payload))

# Logging setup
logging.basicConfig(filename='simulation.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Apply faults: Drift, Frozen, Node Drop
def apply_faults(room):
    node_dropped = False

    # Drift Fault
    if random.random() < FAULT_RATE['drift']:
        temp_change = random.uniform(-0.5, 0.5)
        humidity_change = random.uniform(-2, 2)
        room['temp'] = max(TEMP_RANGE['min'], min(TEMP_RANGE['max'], room['temp'] + temp_change))
        room['humidity'] = max(30, min(70, room['humidity'] + humidity_change))
        room['light_level'] += random.randint(-5, 5)
        logging.info(f"Room {room['room_id']} DRIFT applied: temp={room['temp']:.2f}, humidity={room['humidity']:.2f}, light={room['light_level']}")

    # Frozen Fault
    frozen_duration = 5
    if random.random() < FAULT_RATE['frozen']:
        room['frozen'] = True
        room['frozen_timestamp'] = time.time()
        logging.info(f"Room {room['room_id']} FROZEN applied (values unchanged)")

    if room.get('frozen') and time.time() - room['frozen_timestamp'] < frozen_duration:
        return node_dropped  # Skip update if frozen

    # Node Drop
    if random.random() < FAULT_RATE['drop']:
        node_dropped = True
        logging.info(f"Room {room['room_id']} NODE DROPPED")

    return node_dropped

# Async task for each room
async def room_task(room):
    while True:
        node_silent = apply_faults(room)
        if not node_silent:
            save_room(room)
            payload = {
                "room_id": room['room_id'],
                "temp": room['temp'],
                "humidity": room['humidity'],
                "hvac_mode": room['hvac_mode'],
                "target_temp": room['target_temp'],
                "timestamp": int(time.time())
            }
            mqtt_publish(payload, room['mqtt_topic'])
            print(f"Room {room['room_id']} updated: temp={room['temp']:.2f}, hvac={room['hvac_mode']}")
        else:
            print(f"Room {room['room_id']} skipped (Node Drop)")
        await asyncio.sleep(TICK_INTERVAL)

# Main async loop
async def main():
    load_all_rooms()
    tasks = [asyncio.create_task(room_task(room)) for room in rooms]
    await asyncio.gather(*tasks)

asyncio.run(main())