#!/usr/bin/env python3
"""
Security Setup Script for IoT Campus
Implements TLS/DTLS security framework and generates certificates
"""

import os
import subprocess
import json
import logging
from pathlib import Path

class SecuritySetup:
    def __init__(self, base_dir="security"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def generate_ca_certificate(self):
        """Generate Certificate Authority certificate"""
        ca_dir = self.base_dir / "ca"
        ca_dir.mkdir(exist_ok=True)
        
        # CA private key
        ca_key_cmd = [
            "openssl", "genrsa", "-out", str(ca_dir / "ca-key.pem"), "4096"
        ]
        
        # CA certificate
        ca_cert_cmd = [
            "openssl", "req", "-new", "-x509", "-days", "3650",
            "-key", str(ca_dir / "ca-key.pem"),
            "-out", str(ca_dir / "ca-cert.pem"),
            "-subj", "/C=US/ST=State/L=City/O=IoT Campus/OU=Security/CN=IoT-Campus-CA"
        ]
        
        try:
            subprocess.run(ca_key_cmd, check=True, capture_output=True)
            subprocess.run(ca_cert_cmd, check=True, capture_output=True)
            self.logger.info("CA certificate generated successfully")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to generate CA certificate: {e}")
            return False

    def generate_server_certificate(self, server_name, server_ip="127.0.0.1"):
        """Generate server certificate for TLS"""
        server_dir = self.base_dir / "servers" / server_name
        server_dir.mkdir(parents=True, exist_ok=True)
        
        # Server private key
        server_key_cmd = [
            "openssl", "genrsa", "-out", str(server_dir / f"{server_name}-key.pem"), "2048"
        ]
        
        # Server CSR
        server_csr_cmd = [
            "openssl", "req", "-new",
            "-key", str(server_dir / f"{server_name}-key.pem"),
            "-out", str(server_dir / f"{server_name}-csr.pem"),
            "-subj", f"/C=US/ST=State/L=City/O=IoT Campus/OU={server_name}/CN={server_name}"
        ]
        
        # Server certificate
        server_cert_cmd = [
            "openssl", "x509", "-req", "-days", "365",
            "-in", str(server_dir / f"{server_name}-csr.pem"),
            "-CA", str(self.base_dir / "ca" / "ca-cert.pem"),
            "-CAkey", str(self.base_dir / "ca" / "ca-key.pem"),
            "-CAcreateserial",
            "-out", str(server_dir / f"{server_name}-cert.pem"),
            "-extensions", "v3_req",
            "-extfile", str(self._create_server_config(server_name, server_ip))
        ]
        
        try:
            subprocess.run(server_key_cmd, check=True, capture_output=True)
            subprocess.run(server_csr_cmd, check=True, capture_output=True)
            subprocess.run(server_cert_cmd, check=True, capture_output=True)
            self.logger.info(f"Server certificate for {server_name} generated successfully")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to generate server certificate for {server_name}: {e}")
            return False

    def generate_device_certificates(self, device_count=200):
        """Generate certificates for IoT devices"""
        devices_dir = self.base_dir / "devices"
        devices_dir.mkdir(exist_ok=True)
        
        for i in range(1, device_count + 1):
            device_id = f"device-{i:04d}"
            device_dir = devices_dir / device_id
            device_dir.mkdir(exist_ok=True)
            
            # Device private key
            device_key_cmd = [
                "openssl", "genrsa", "-out", str(device_dir / f"{device_id}-key.pem"), "2048"
            ]
            
            # Device CSR
            device_csr_cmd = [
                "openssl", "req", "-new",
                "-key", str(device_dir / f"{device_id}-key.pem"),
                "-out", str(device_dir / f"{device_id}-csr.pem"),
                "-subj", f"/C=US/ST=State/L=City/O=IoT Campus/OU=Devices/CN={device_id}"
            ]
            
            # Device certificate
            device_cert_cmd = [
                "openssl", "x509", "-req", "-days", "365",
                "-in", str(device_dir / f"{device_id}-csr.pem"),
                "-CA", str(self.base_dir / "ca" / "ca-cert.pem"),
                "-CAkey", str(self.base_dir / "ca" / "ca-key.pem"),
                "-CAcreateserial",
                "-out", str(device_dir / f"{device_id}-cert.pem")
            ]
            
            try:
                subprocess.run(device_key_cmd, check=True, capture_output=True)
                subprocess.run(device_csr_cmd, check=True, capture_output=True)
                subprocess.run(device_cert_cmd, check=True, capture_output=True)
                
                # Create device bundle
                bundle = {
                    "device_id": device_id,
                    "certificate": str(device_dir / f"{device_id}-cert.pem"),
                    "private_key": str(device_dir / f"{device_id}-key.pem"),
                    "ca_certificate": str(self.base_dir / "ca" / "ca-cert.pem")
                }
                
                with open(device_dir / "bundle.json", "w") as f:
                    json.dump(bundle, f, indent=2)
                    
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to generate certificate for {device_id}: {e}")
                continue
        
        self.logger.info(f"Generated certificates for {device_count} devices")
        return True

    def _create_server_config(self, server_name, server_ip):
        """Create OpenSSL config for server certificate"""
        config_content = f"""
[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = {server_name}
DNS.2 = localhost
IP.1 = {server_ip}
IP.2 = 127.0.0.1
"""
        config_file = self.base_dir / f"{server_name}-config.cnf"
        with open(config_file, "w") as f:
            f.write(config_content)
        
        return config_file

    def generate_psk_credentials(self, device_count=200):
        """Generate Pre-Shared Keys for CoAP DTLS"""
        psk_dir = self.base_dir / "psk"
        psk_dir.mkdir(exist_ok=True)
        
        psk_credentials = {}
        
        for i in range(1, device_count + 1):
            device_id = f"device-{i:04d}"
            # Generate random PSK (32 bytes for security)
            psk = os.urandom(32).hex()
            
            psk_credentials[device_id] = {
                "psk": psk,
                "identity": device_id,
                "algorithm": "AES-256-GCM"
            }
        
        # Save PSK credentials
        with open(psk_dir / "psk_credentials.json", "w") as f:
            json.dump(psk_credentials, f, indent=2)
        
        self.logger.info(f"Generated PSK credentials for {device_count} devices")
        return psk_credentials

    def create_hivemq_security_config(self):
        """Create HiveMQ security configuration"""
        hivemq_dir = self.base_dir / "hivemq"
        hivemq_dir.mkdir(exist_ok=True)
        
        security_config = {
            "use-ssl-for-tcp-listener": True,
            "tls-keystore-path": str(self.base_dir / "servers" / "hivemq" / "hivemq-keystore.jks"),
            "tls-keystore-password": "changeit",
            "tls-client-authentication-mode": "REQUIRED",
            "tls-truststore-path": str(self.base_dir / "ca" / "ca-truststore.jks"),
            "tls-truststore-password": "changeit"
        }
        
        with open(hivemq_dir / "security-config.xml", "w") as f:
            json.dump(security_config, f, indent=2)
        
        self.logger.info("HiveMQ security configuration created")
        return True

    def create_thingsboard_security_config(self):
        """Create ThingsBoard security configuration"""
        tb_dir = self.base_dir / "thingsboard"
        tb_dir.mkdir(exist_ok=True)
        
        security_config = {
            "mqtt": {
                "ssl": {
                    "enabled": True,
                    "keystore": str(self.base_dir / "servers" / "thingsboard" / "tb-keystore.jks"),
                    "keystore_password": "changeit",
                    "key_password": "changeit",
                    "truststore": str(self.base_dir / "ca" / "ca-truststore.jks"),
                    "truststore_password": "changeit"
                }
            },
            "coap": {
                "dtls": {
                    "enabled": True,
                    "psk_credentials_file": str(self.base_dir / "psk" / "psk_credentials.json")
                }
            }
        }
        
        with open(tb_dir / "security-config.json", "w") as f:
            json.dump(security_config, f, indent=2)
        
        self.logger.info("ThingsBoard security configuration created")
        return True

    def create_device_security_bundles(self):
        """Create security bundles for each device"""
        bundles_dir = self.base_dir / "device_bundles"
        bundles_dir.mkdir(exist_ok=True)
        
        # Load PSK credentials
        with open(self.base_dir / "psk" / "psk_credentials.json", "r") as f:
            psk_credentials = json.load(f)
        
        for device_id, psk_info in psk_credentials.items():
            device_num = device_id.split("-")[1]
            device_dir = self.base_dir / "devices" / device_id
            
            if device_dir.exists():
                bundle = {
                    "device_id": device_id,
                    "mqtt": {
                        "certificate": str(device_dir / f"{device_id}-cert.pem"),
                        "private_key": str(device_dir / f"{device_id}-key.pem"),
                        "ca_certificate": str(self.base_dir / "ca" / "ca-cert.pem"),
                        "broker": "hivemq-broker:8883",
                        "client_id": f"mqtt-{device_id}"
                    },
                    "coap": {
                        "psk": psk_info["psk"],
                        "identity": psk_info["identity"],
                        "algorithm": psk_info["algorithm"],
                        "server": "localhost:5684"
                    },
                    "thingsboard": {
                        "access_token": f"{device_id}_token",
                        "host": "thingsboard:1883",
                        "port": 1883
                    }
                }
                
                with open(bundles_dir / f"{device_id}_bundle.json", "w") as f:
                    json.dump(bundle, f, indent=2)
        
        self.logger.info("Device security bundles created")
        return True

    def run_complete_setup(self, device_count=200):
        """Run complete security setup"""
        self.logger.info("Starting complete security setup...")
        
        # Generate CA certificate
        if not self.generate_ca_certificate():
            return False
        
        # Generate server certificates
        servers = ["hivemq", "thingsboard", "gateway-floor-01"]
        for server in servers:
            self.generate_server_certificate(server)
        
        # Generate device certificates
        self.generate_device_certificates(device_count)
        
        # Generate PSK credentials
        self.generate_psk_credentials(device_count)
        
        # Create security configurations
        self.create_hivemq_security_config()
        self.create_thingsboard_security_config()
        
        # Create device bundles
        self.create_device_security_bundles()
        
        self.logger.info("Security setup completed successfully!")
        return True

def main():
    """Main security setup function"""
    print("Starting IoT Campus Security Setup...")
    print("This will generate TLS certificates and PSK credentials for all devices")
    print()
    
    setup = SecuritySetup()
    
    if setup.run_complete_setup(200):
        print("\n✅ Security setup completed successfully!")
        print("\nGenerated security artifacts:")
        print("1. CA Certificate: security/ca/")
        print("2. Server Certificates: security/servers/")
        print("3. Device Certificates: security/devices/")
        print("4. PSK Credentials: security/psk/")
        print("5. Device Bundles: security/device_bundles/")
        print("\nNext steps:")
        print("1. Copy certificates to appropriate containers")
        print("2. Update MQTT/CoAP clients to use TLS/DTLS")
        print("3. Configure HiveMQ and ThingsBoard security")
        print("4. Test secure connections")
    else:
        print("\n❌ Security setup failed!")
        print("Please check the logs and ensure OpenSSL is installed.")

if __name__ == "__main__":
    main()
