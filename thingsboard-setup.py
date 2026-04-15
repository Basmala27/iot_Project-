#!/usr/bin/env python3
"""
ThingsBoard Configuration Script
Sets up device registry, asset hierarchy, and rule chains for IoT Campus
"""

import json
import requests
import time
import logging

# ThingsBoard Configuration
TB_URL = "http://localhost:9090"
TB_USERNAME = "tenant@thingsboard.org"
TB_PASSWORD = "tenant"

class ThingsBoardSetup:
    def __init__(self, base_url=TB_URL, username=TB_USERNAME, password=TB_PASSWORD):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token = None
        self.session = requests.Session()
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def login(self):
        """Login to ThingsBoard and get JWT token"""
        login_url = f"{self.base_url}/api/auth/login"
        credentials = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            response = self.session.post(login_url, json=credentials)
            response.raise_for_status()
            
            self.token = response.json()["token"]
            self.session.headers.update({"X-Authorization": f"Bearer {self.token}"})
            self.logger.info("Successfully logged into ThingsBoard")
            return True
            
        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            return False

    def create_device_profile(self, name, device_type, transport_type="MQTT"):
        """Create device profile for IoT devices"""
        profile_data = {
            "name": name,
            "type": device_type,
            "transportType": transport_type,
            "profileData": {
                "configuration": {
                    "type": "DEFAULT"
                },
                "transportConfiguration": {
                    "type": "DEFAULT",
                    "deviceTelemetryTopicFilter": "v1/devices/me/telemetry",
                    "deviceAttributesTopicFilter": "v1/devices/me/attributes"
                }
            },
            "provisionDeviceKey": f"{name.lower().replace(' ', '-')}-key",
            "provisionDeviceSecret": f"{name.lower().replace(' ', '-')}-secret"
        }
        
        try:
            response = self.session.post(f"{self.base_url}/api/deviceProfile", json=profile_data)
            response.raise_for_status()
            profile = response.json()
            self.logger.info(f"Created device profile: {name}")
            return profile
            
        except Exception as e:
            self.logger.error(f"Failed to create device profile {name}: {e}")
            return None

    def create_asset(self, name, asset_type, parent_id=None):
        """Create asset in ThingsBoard"""
        asset_data = {
            "name": name,
            "type": asset_type,
            "label": name
        }
        
        if parent_id:
            asset_data["parentId"] = parent_id
            
        try:
            response = self.session.post(f"{self.base_url}/api/asset", json=asset_data)
            response.raise_for_status()
            asset = response.json()
            self.logger.info(f"Created asset: {name}")
            return asset
            
        except Exception as e:
            self.logger.error(f"Failed to create asset {name}: {e}")
            return None

    def create_device(self, name, device_profile_id, asset_id=None):
        """Create device in ThingsBoard"""
        device_data = {
            "name": name,
            "type": "IoT Device",
            "label": name,
            "deviceProfileId": {
                "entityType": "DEVICE_PROFILE",
                "id": device_profile_id
            }
        }
        
        if asset_id:
            device_data["assetId"] = asset_id
            
        try:
            response = self.session.post(f"{self.base_url}/api/device", json=device_data)
            response.raise_for_status()
            device = response.json()
            self.logger.info(f"Created device: {name}")
            return device
            
        except Exception as e:
            self.logger.error(f"Failed to create device {name}: {e}")
            return None

    def create_relation(self, from_entity, to_entity, relation_type="Contains"):
        """Create relation between entities"""
        relation_data = {
            "from": from_entity,
            "to": to_entity,
            "type": relation_type
        }
        
        try:
            response = self.session.post(f"{self.base_url}/api/relation", json=relation_data)
            response.raise_for_status()
            self.logger.info(f"Created relation: {from_entity['id']} -> {to_entity['id']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create relation: {e}")
            return False

    def create_rule_chain(self, name, root=False):
        """Create rule chain"""
        rule_chain_data = {
            "name": name,
            "type": "CORE",
            "debugMode": False,
            "configuration": {}
        }
        
        try:
            response = self.session.post(f"{self.base_url}/api/ruleChain", json=rule_chain_data)
            response.raise_for_status()
            rule_chain = response.json()
            
            if root:
                # Set as root rule chain
                self.session.post(f"{self.base_url}/api/ruleChain/{rule_chain['id']['id']}/root")
                
            self.logger.info(f"Created rule chain: {name}")
            return rule_chain
            
        except Exception as e:
            self.logger.error(f"Failed to create rule chain {name}: {e}")
            return None

    def setup_campus_hierarchy(self):
        """Setup complete campus asset hierarchy"""
        self.logger.info("Setting up campus asset hierarchy...")
        
        # Create main campus asset
        campus = self.create_asset("IoT Campus", "Campus")
        
        # Create building
        building = self.create_asset("Building B01", "Building", campus["id"]["id"])
        
        # Create floors
        floors = []
        for floor_num in range(1, 11):
            floor = self.create_asset(f"Floor {floor_num:02d}", "Floor", building["id"]["id"])
            floors.append(floor)
        
        # Create rooms for each floor
        rooms = []
        for floor_num, floor in enumerate(floors, 1):
            for room_num in range(1, 21):
                room_id = f"b01-f{floor_num:02d}-r{room_num:03d}"
                room = self.create_asset(f"Room {room_id}", "Room", floor["id"]["id"])
                rooms.append(room)
        
        self.logger.info(f"Created {len(floors)} floors and {len(rooms)} rooms")
        return campus, building, floors, rooms

    def setup_device_profiles(self):
        """Setup device profiles for different device types"""
        self.logger.info("Creating device profiles...")
        
        mqtt_profile = self.create_device_profile("MQTT IoT Device", "DEFAULT", "MQTT")
        coap_profile = self.create_device_profile("CoAP IoT Device", "DEFAULT", "HTTP")
        
        return mqtt_profile, coap_profile

    def setup_devices(self, mqtt_profile, coap_profile, rooms):
        """Setup all IoT devices"""
        self.logger.info("Creating IoT devices...")
        
        devices = []
        
        for i, room in enumerate(rooms):
            room_id = room["name"].replace("Room ", "")
            
            # Determine device type based on room number
            if (i % 20) < 10:  # First 10 rooms per floor are MQTT
                device = self.create_device(f"MQTT-{room_id}", mqtt_profile["id"]["id"], room["id"]["id"])
            else:  # Last 10 rooms per floor are CoAP
                device = self.create_device(f"CoAP-{room_id}", coap_profile["id"]["id"], room["id"]["id"])
            
            if device:
                devices.append(device)
        
        self.logger.info(f"Created {len(devices)} devices")
        return devices

    def setup_rule_chains(self):
        """Setup rule chains for processing"""
        self.logger.info("Creating rule chains...")
        
        # Main rule chain
        main_chain = self.create_rule_chain("IoT Campus Main", root=True)
        
        # Alert rule chain
        alert_chain = self.create_rule_chain("Alert Processing")
        
        return main_chain, alert_chain

    def create_dashboard(self, name):
        """Create dashboard"""
        dashboard_config = {
            "title": name,
            "description": "IoT Campus Monitoring Dashboard",
            "image": None,
            "mobileHide": False,
            "mobileOrder": 0,
            "configuration": {
                "widgets": [
                    {
                        "id": "fleet_health",
                        "title": "Fleet Health Overview",
                        "type": "entities_table",
                        "sizeX": 12,
                        "sizeY": 6,
                        "config": {
                            "entitiesTitle": "Devices",
                            "searchEnabled": True,
                            "displayEntityLabel": True,
                            "entityAlias": "all_devices",
                            "columns": [
                                {"name": "Name", "key": "name"},
                                {"name": "Type", "key": "type"},
                                {"name": "Status", "key": "status"},
                                {"name": "Temperature", "key": "temperature"},
                                {"name": "Humidity", "key": "humidity"}
                            ]
                        }
                    },
                    {
                        "id": "temperature_chart",
                        "title": "Temperature Trends",
                        "type": "timeseries",
                        "sizeX": 8,
                        "sizeY": 6,
                        "config": {
                            "datasources": [
                                {
                                    "type": "entity",
                                    "entityAlias": "temperature_data"
                                }
                            ],
                            "settings": {
                                "showLegend": True,
                                "smoothLines": True
                            }
                        }
                    },
                    {
                        "id": "floor_summary",
                        "title": "Floor Summary",
                        "type": "cards",
                        "sizeX": 4,
                        "sizeY": 6,
                        "config": {
                            "cardLayout": "horizontal",
                            "cards": [
                                {"title": "Total Devices", "value": "200"},
                                {"title": "Online", "value": "190"},
                                {"title": "Alerts", "value": "5"},
                                {"title": "Avg Temperature", "value": "22.5°C"}
                            ]
                        }
                    }
                ]
            }
        }
        
        try:
            response = self.session.post(f"{self.base_url}/api/dashboard", json=dashboard_config)
            response.raise_for_status()
            dashboard = response.json()
            self.logger.info(f"Created dashboard: {name}")
            return dashboard
            
        except Exception as e:
            self.logger.error(f"Failed to create dashboard {name}: {e}")
            return None

    def run_complete_setup(self):
        """Run complete ThingsBoard setup"""
        if not self.login():
            return False
        
        # Setup hierarchy
        campus, building, floors, rooms = self.setup_campus_hierarchy()
        
        # Setup device profiles
        mqtt_profile, coap_profile = self.setup_device_profiles()
        
        # Setup devices
        devices = self.setup_devices(mqtt_profile, coap_profile, rooms)
        
        # Setup rule chains
        main_chain, alert_chain = self.setup_rule_chains()
        
        # Create dashboard
        dashboard = self.create_dashboard("IoT Campus Dashboard")
        
        self.logger.info("ThingsBoard setup completed successfully!")
        return True

def main():
    """Main setup function"""
    print("Starting ThingsBoard setup...")
    print("Make sure ThingsBoard is running at http://localhost:9090")
    print("Default credentials: tenant@thingsboard.org / tenant")
    print()
    
    setup = ThingsBoardSetup()
    
    if setup.run_complete_setup():
        print("\n✅ ThingsBoard setup completed successfully!")
        print("\nNext steps:")
        print("1. Access ThingsBoard Dashboard: http://localhost:9090")
        print("2. Login with tenant credentials")
        print("3. Verify device registry and asset hierarchy")
        print("4. Check the IoT Campus Dashboard")
        print("5. Test device connectivity")
    else:
        print("\n❌ ThingsBoard setup failed!")
        print("Please check the logs and ensure ThingsBoard is running.")

if __name__ == "__main__":
    main()
