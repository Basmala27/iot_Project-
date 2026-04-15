#!/usr/bin/env python3
"""
Script to create Node-RED gateway configurations for all floors
"""

import json
import os
import shutil

def create_gateway_flow(floor_number):
    """Create Node-RED flow for a specific floor"""
    
    base_flow = [
        {
            "id": "1",
            "type": "tab",
            "label": f"Floor {floor_number:02d} Gateway",
            "disabled": False,
            "info": f"IoT Gateway for Floor {floor_number:02d} - Handles MQTT and CoAP protocol translation"
        },
        {
            "id": "mqtt-broker",
            "type": "mqtt-broker",
            "z": "1",
            "name": "HiveMQ Broker",
            "broker": "hivemq-broker",
            "port": "1883",
            "clientid": f"gateway-floor-{floor_number:02d}",
            "autoConnect": True,
            "usetls": False,
            "protocolVersion": "4"
        },
        {
            "id": "mqtt-subscribe",
            "type": "mqtt in",
            "z": "1",
            "name": f"Floor {floor_number:02d} MQTT Telemetry",
            "topic": f"campus/b01/f{floor_number:02d}/+/telemetry",
            "qos": "1",
            "datatype": "json",
            "broker": "mqtt-broker",
            "nl": False,
            "rap": False,
            "x": 150,
            "y": 100,
            "wires": [["mqtt-process", "thingsboard-forward"]]
        },
        {
            "id": "mqtt-process",
            "type": "function",
            "z": "1",
            "name": "Process MQTT Data",
            "func": f"""// Process incoming MQTT telemetry
const data = msg.payload;
const topic = msg.topic;

// Extract room ID from topic
const topicParts = topic.split('/');
const roomId = topicParts[3];

// Add gateway metadata
msg.payload = {{
    ...data,
    gateway: 'floor-{floor_number:02d}',
    protocol: 'mqtt',
    processed_at: new Date().toISOString(),
    room_id: roomId
}};

return msg;""",
            "outputs": 1,
            "noerr": 0,
            "initialize": "",
            "finalize": "",
            "x": 400,
            "y": 100,
            "wires": [["floor-aggregator"]]
        },
        {
            "id": "thingsboard-forward",
            "type": "mqtt out",
            "z": "1",
            "name": "To ThingsBoard",
            "topic": "v1/devices/me/telemetry",
            "qos": "1",
            "retain": "false",
            "broker": "mqtt-broker",
            "x": 400,
            "y": 200,
            "wires": []
        },
        {
            "id": "floor-aggregator",
            "type": "function",
            "z": "1",
            "name": "Floor Data Aggregator",
            "func": f"""// Aggregate floor data for edge processing
const context = this.context();
const currentData = msg.payload;
const roomId = currentData.room_id;

// Store room data
context.set(roomId, currentData);

// Get all room data for this floor
const allRooms = context.keys();
const floorData = {{
    floor: '{floor_number:02d}',
    timestamp: new Date().toISOString(),
    total_rooms: allRooms.length,
    rooms: {{}}
}};

// Calculate floor averages
let totalTemp = 0;
let totalHumidity = 0;
let onlineCount = 0;

allRooms.forEach(roomId => {{
    const roomData = context.get(roomId);
    if (roomData) {{
        floorData.rooms[roomId] = roomData;
        totalTemp += roomData.temperature;
        totalHumidity += roomData.humidity;
        if (roomData.status === 'ONLINE') {{
            onlineCount++;
        }}
    }}
}});

floorData.average_temperature = totalTemp / allRooms.length;
floorData.average_humidity = totalHumidity / allRooms.length;
floorData.online_rooms = onlineCount;

// Send floor summary every 60 seconds
const lastSummary = context.get('lastSummary') || 0;
const now = Date.now();

if (now - lastSummary > 60000) {{
    context.set('lastSummary', now);
    msg.payload = floorData;
    return msg;
}}

return null;""",
            "outputs": 1,
            "noerr": 0,
            "initialize": "",
            "finalize": "",
            "x": 650,
            "y": 100,
            "wires": [["floor-summary-out"]]
        },
        {
            "id": "floor-summary-out",
            "type": "mqtt out",
            "z": "1",
            "name": "Floor Summary",
            "topic": f"campus/b01/f{floor_number:02d}/summary",
            "qos": "1",
            "retain": "false",
            "broker": "mqtt-broker",
            "x": 900,
            "y": 100,
            "wires": []
        },
        {
            "id": "command-handler",
            "type": "mqtt in",
            "z": "1",
            "name": f"Floor {floor_number:02d} Commands",
            "topic": f"campus/b01/f{floor_number:02d}/+/cmd",
            "qos": "2",
            "datatype": "json",
            "broker": "mqtt-broker",
            "nl": False,
            "rap": False,
            "x": 150,
            "y": 400,
            "wires": [["command-process"]]
        },
        {
            "id": "command-process",
            "type": "function",
            "z": "1",
            "name": "Process Commands",
            "func": f"""// Process incoming commands
const command = msg.payload;
const topic = msg.topic;

// Extract room ID from topic
const topicParts = topic.split('/');
const roomId = topicParts[3];

// Determine if this is an MQTT or CoAP room
const mqttRooms = ['b01-f{floor_number:02d}-r{(floor_number-1)*20+11:03d}', 'b01-f{floor_number:02d}-r{(floor_number-1)*20+12:03d}', 
                   'b01-f{floor_number:02d}-r{(floor_number-1)*20+13:03d}', 'b01-f{floor_number:02d}-r{(floor_number-1)*20+14:03d}', 'b01-f{floor_number:02d}-r{(floor_number-1)*20+15:03d}',
                   'b01-f{floor_number:02d}-r{(floor_number-1)*20+16:03d}', 'b01-f{floor_number:02d}-r{(floor_number-1)*20+17:03d}', 'b01-f{floor_number:02d}-r{(floor_number-1)*20+18:03d}', 
                   'b01-f{floor_number:02d}-r{(floor_number-1)*20+19:03d}', 'b01-f{floor_number:02d}-r{(floor_number-1)*20+20:03d}'];

if (mqttRooms.includes(roomId)) {{
    // Forward to MQTT room
    msg.topic = `campus/b01/f{floor_number:02d}/${{roomId}}/cmd`;
    return [msg, null];
}} else {{
    // Forward to CoAP room
    const roomNum = parseInt(roomId.split('-')[2].substring(1));
    const coapPort = 5683 + (({floor_number-1} * 20) + (roomNum - 1));
    msg.url = `coap://localhost:${{coapPort}}/actuators`;
    msg.method = 'PUT';
    msg.payload = JSON.stringify(command);
    return [null, msg];
}}""",
            "outputs": 2,
            "noerr": 0,
            "initialize": "",
            "finalize": "",
            "x": 400,
            "y": 400,
            "wires": [["mqtt-command-out"], ["coap-command-out"]]
        },
        {
            "id": "mqtt-command-out",
            "type": "mqtt out",
            "z": "1",
            "name": "MQTT Command",
            "topic": "",
            "qos": "2",
            "retain": "false",
            "broker": "mqtt-broker",
            "x": 650,
            "y": 350,
            "wires": []
        },
        {
            "id": "coap-command-out",
            "type": "coap request",
            "z": "1",
            "name": "CoAP Command",
            "url": "",
            "method": "PUT",
            "contenttype": "application/json",
            "payload": "",
            "x": 650,
            "y": 450,
            "wires": [["command-response"]]
        },
        {
            "id": "command-response",
            "type": "function",
            "z": "1",
            "name": "Process Response",
            "func": f"""// Process command response
const response = msg.payload;

// Add response metadata
msg.payload = {{
    response: response,
    timestamp: new Date().toISOString(),
    gateway: 'floor-{floor_number:02d}'
}};

// Publish response
msg.topic = 'campus/b01/f{floor_number:02d}/response';

return msg;""",
            "outputs": 1,
            "noerr": 0,
            "initialize": "",
            "finalize": "",
            "x": 900,
            "y": 450,
            "wires": [["response-out"]]
        },
        {
            "id": "response-out",
            "type": "mqtt out",
            "z": "1",
            "name": "Command Response",
            "topic": "",
            "qos": "1",
            "retain": "false",
            "broker": "mqtt-broker",
            "x": 1150,
            "y": 450,
            "wires": []
        }
    ]
    
    return base_flow

def create_package_json():
    """Create package.json for Node-RED"""
    return {
        "name": f"floor-gateway",
        "description": "Node-RED IoT Gateway for Floor",
        "version": "1.0.0",
        "dependencies": {
            "node-red-contrib-coap": "^0.3.0",
            "node-red-contrib-mqtt-broker": "^1.0.0"
        },
        "node-red": {
            "settings": {
                "mqttReconnectTime": 15000,
                "serialReconnectTime": 15000,
                "debugMaxLength": 1000
            }
        }
    }

def create_settings_js(floor_number):
    """Create Node-RED settings.js for a specific floor"""
    return f"""module.exports = {{
    uiPort: process.env.PORT || 1880,
    mqttReconnectTime: 15000,
    serialReconnectTime: 15000,
    debugMaxLength: 1000,
    functionGlobalContext: {{
        floor: '{floor_number:02d}',
        gateway: 'floor-{floor_number:02d}'
    }},
    logging: {{
        console: {{
            level: "info",
            metrics: false,
            audit: false
        }}
    }}
}}"""

def main():
    """Create all gateway configurations"""
    print("Creating Node-RED gateway configurations...")
    
    # Create base directory
    base_dir = "node-red-flows"
    os.makedirs(base_dir, exist_ok=True)
    
    # Create modules directory
    modules_dir = os.path.join(base_dir, "node-red-modules")
    os.makedirs(modules_dir, exist_ok=True)
    
    for floor in range(1, 11):
        floor_dir = os.path.join(base_dir, f"floor-{floor:02d}")
        os.makedirs(floor_dir, exist_ok=True)
        
        # Create flows.json
        flows = create_gateway_flow(floor)
        flows_file = os.path.join(floor_dir, "flows.json")
        with open(flows_file, 'w') as f:
            json.dump(flows, f, indent=2)
        
        # Create package.json
        package_json = create_package_json()
        package_file = os.path.join(floor_dir, "package.json")
        with open(package_file, 'w') as f:
            json.dump(package_json, f, indent=2)
        
        # Create settings.js
        settings_js = create_settings_js(floor)
        settings_file = os.path.join(floor_dir, "settings.js")
        with open(settings_file, 'w') as f:
            f.write(settings_js)
        
        print(f"Created configuration for Floor {floor:02d}")
    
    print(f"\nAll gateway configurations created in {base_dir}/")
    print("Each floor has its own Node-RED configuration with:")
    print("- MQTT telemetry processing")
    print("- CoAP observation support")
    print("- Command handling and routing")
    print("- Floor-level data aggregation")
    print("- Protocol translation capabilities")

if __name__ == "__main__":
    main()
