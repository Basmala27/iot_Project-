# IoT Campus Phase 2 - Complete Implementation

## Overview
IoT Campus simulation with 200 devices (100 MQTT + 100 CoAP), Node-RED gateways, ThingsBoard integration, and enterprise-grade security.

## Architecture
- **200 IoT Devices**: 100 MQTT nodes + 100 CoAP nodes
- **10 Node-RED Gateways**: Protocol translation and edge processing
- **HiveMQ**: MQTT broker with QoS 2 support
- **ThingsBoard**: Cloud monitoring and device management
- **Docker**: Containerized infrastructure

## Features
- Async Python simulation with physics-based thermal model
- Hybrid MQTT/CoAP protocol support
- TLS/DTLS security framework
- Performance monitoring (<500ms latency)
- Real-time telemetry dashboard

## Quick Start
```bash
# Start infrastructure
docker run -d --name hivemq-broker --network host -p 1883:1883 -p 8080:8080 hivemq/hivemq-ce:2024.1
docker run -d --name thingsboard --network host -p 9090:9090 -e TB_QUEUE_TYPE=in-memory thingsboard/tb-postgres:3.7.0
docker run -d --name gateway-floor-01 --network host -p 1881:1880 -v "${PWD}/node-red-flows/floor-01:/data" nodered/node-red:3.1.3

# Start simulation
python main.py

# Performance test
python performance_monitor.py
```

## Files
- `main.py` - Main simulation engine
- `room.py` - Physics model
- `mqtt_client.py` - MQTT client
- `coap_server.py` - CoAP server
- `docker-compose.yml` - Infrastructure
- `node-red-flows/` - Gateway configurations
- `thingsboard-setup.py` - Device registry
- `security-setup.py` - TLS/DTLS certificates
- `performance_monitor.py` - Benchmarks

## Performance
- **Latency**: <500ms round-trip
- **Throughput**: >40 messages/second
- **Reliability**: QoS 2 + CON messages
- **Security**: TLS/DTLS with certificates

## Phase 2 Status: COMPLETED
All deliverables implemented and tested.
