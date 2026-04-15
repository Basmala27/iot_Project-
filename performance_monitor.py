#!/usr/bin/env python3
"""
Performance Monitoring and Latency Benchmarking for IoT Campus
Monitors system performance, latency, and generates benchmarks
"""

import asyncio
import time
import json
import logging
import statistics
import psutil
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from collections import defaultdict, deque
import paho.mqtt.client as mqtt
import requests

class PerformanceMonitor:
    def __init__(self, mqtt_broker="localhost", mqtt_port=1883, thingsboard_url="http://localhost:9090"):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.thingsboard_url = thingsboard_url
        
        # Performance metrics storage
        self.latency_data = deque(maxlen=1000)
        self.throughput_data = deque(maxlen=1000)
        self.cpu_usage = deque(maxlen=1000)
        self.memory_usage = deque(maxlen=1000)
        self.message_counts = defaultdict(int)
        
        # Benchmark results
        self.benchmark_results = {}
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    async def measure_round_trip_latency(self, test_duration=300):
        """Measure round-trip latency for MQTT commands"""
        self.logger.info(f"Starting round-trip latency test for {test_duration} seconds...")
        
        latencies = []
        start_time = time.time()
        
        # MQTT client for testing
        client = mqtt.Client()
        client.connect(self.mqtt_broker, self.mqtt_port, 60)
        
        def on_message(client, userdata, msg):
            received_time = time.time()
            payload = json.loads(msg.payload.decode())
            sent_time = payload.get("timestamp")
            
            if sent_time:
                latency = (received_time - sent_time) * 1000  # Convert to ms
                latencies.append(latency)
        
        client.subscribe("campus/+/+/response")
        client.on_message = on_message
        client.loop_start()
        
        # Send test commands
        while time.time() - start_time < test_duration:
            # Send command to random room
            floor = random.randint(1, 10)
            room = random.randint(1, 20)
            room_id = f"b01-f{floor:02d}-r{room:03d}"
            
            command = {
                "hvac_mode": random.choice(["ON", "OFF", "ECO"]),
                "timestamp": time.time(),
                "test_id": f"latency_test_{int(time.time())}"
            }
            
            client.publish(f"campus/b01/f{floor:02d}/{room_id}/cmd", json.dumps(command))
            await asyncio.sleep(0.1)
        
        client.loop_stop()
        client.disconnect()
        
        # Calculate statistics
        if latencies:
            self.benchmark_results["round_trip_latency"] = {
                "mean_ms": statistics.mean(latencies),
                "median_ms": statistics.median(latencies),
                "p95_ms": statistics.quantiles(latencies, n=20)[18],  # 95th percentile
                "p99_ms": statistics.quantiles(latencies, n=100)[98],  # 99th percentile
                "max_ms": max(latencies),
                "min_ms": min(latencies),
                "samples": len(latencies)
            }
            
            self.logger.info(f"Round-trip latency: Mean={self.benchmark_results['round_trip_latency']['mean_ms']:.2f}ms")
        
        return latencies

    async def measure_throughput(self, test_duration=300):
        """Measure message throughput"""
        self.logger.info(f"Starting throughput test for {test_duration} seconds...")
        
        message_counts = defaultdict(int)
        start_time = time.time()
        
        # MQTT client for monitoring
        client = mqtt.Client()
        client.connect(self.mqtt_broker, self.mqtt_port, 60)
        
        def on_message(client, userdata, msg):
            topic = msg.topic
            message_counts[topic] += 1
            self.message_counts[topic] += 1
        
        client.subscribe("campus/#")
        client.on_message = on_message
        client.loop_start()
        
        # Monitor for test duration
        await asyncio.sleep(test_duration)
        
        client.loop_stop()
        client.disconnect()
        
        # Calculate throughput
        total_messages = sum(message_counts.values())
        throughput_per_second = total_messages / test_duration
        
        self.benchmark_results["throughput"] = {
            "total_messages": total_messages,
            "messages_per_second": throughput_per_second,
            "test_duration": test_duration,
            "topic_counts": dict(message_counts)
        }
        
        self.logger.info(f"Throughput: {throughput_per_second:.2f} messages/second")
        return throughput_per_second

    async def monitor_system_resources(self, duration=300):
        """Monitor CPU and memory usage"""
        self.logger.info(f"Starting system resource monitoring for {duration} seconds...")
        
        start_time = time.time()
        
        while time.time() - start_time < duration:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.cpu_usage.append(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.memory_usage.append(memory.percent)
            
            await asyncio.sleep(1)
        
        # Calculate statistics
        if self.cpu_usage:
            self.benchmark_results["cpu_usage"] = {
                "mean_percent": statistics.mean(self.cpu_usage),
                "max_percent": max(self.cpu_usage),
                "min_percent": min(self.cpu_usage),
                "samples": len(self.cpu_usage)
            }
        
        if self.memory_usage:
            self.benchmark_results["memory_usage"] = {
                "mean_percent": statistics.mean(self.memory_usage),
                "max_percent": max(self.memory_usage),
                "min_percent": min(self.memory_usage),
                "samples": len(self.memory_usage)
            }
        
        self.logger.info(f"CPU Usage: Mean={self.benchmark_results.get('cpu_usage', {}).get('mean_percent', 0):.2f}%")
        self.logger.info(f"Memory Usage: Mean={self.benchmark_results.get('memory_usage', {}).get('mean_percent', 0):.2f}%")

    async def check_thingsboard_health(self):
        """Check ThingsBoard health and response time"""
        self.logger.info("Checking ThingsBoard health...")
        
        try:
            # Check API health
            start_time = time.time()
            response = requests.get(f"{self.thingsboard_url}/api/noauth/health", timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            self.benchmark_results["thingsboard_health"] = {
                "status_code": response.status_code,
                "response_time_ms": response_time,
                "healthy": response.status_code == 200
            }
            
            self.logger.info(f"ThingsBoard health: {response.status_code}, Response time: {response_time:.2f}ms")
            
        except Exception as e:
            self.logger.error(f"ThingsBoard health check failed: {e}")
            self.benchmark_results["thingsboard_health"] = {
                "status": "error",
                "error": str(e)
            }

    async def check_hivemq_health(self):
        """Check HiveMQ health and client count"""
        self.logger.info("Checking HiveMQ health...")
        
        try:
            # Check Control Center
            start_time = time.time()
            response = requests.get(f"http://localhost:8080", timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            self.benchmark_results["hivemq_health"] = {
                "status_code": response.status_code,
                "response_time_ms": response_time,
                "healthy": response.status_code == 200
            }
            
            self.logger.info(f"HiveMQ health: {response.status_code}, Response time: {response_time:.2f}ms")
            
        except Exception as e:
            self.logger.error(f"HiveMQ health check failed: {e}")
            self.benchmark_results["hivemq_health"] = {
                "status": "error",
                "error": str(e)
            }

    def generate_performance_report(self):
        """Generate comprehensive performance report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "test_duration": "5 minutes",
            "system_info": {
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "python_version": psutil.sys.version
            },
            "benchmark_results": self.benchmark_results,
            "summary": {
                "latency_target_met": self.benchmark_results.get("round_trip_latency", {}).get("mean_ms", 999) < 500,
                "throughput_target_met": self.benchmark_results.get("throughput", {}).get("messages_per_second", 0) > 40,
                "system_stable": self.benchmark_results.get("cpu_usage", {}).get("mean_percent", 100) < 80
            }
        }
        
        # Save report
        with open("performance_report.json", "w") as f:
            json.dump(report, f, indent=2)
        
        return report

    def create_performance_charts(self):
        """Create performance visualization charts"""
        if not self.cpu_usage or not self.memory_usage:
            self.logger.warning("No data available for charts")
            return
        
        # Create subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        # CPU Usage Chart
        ax1.plot(list(self.cpu_usage))
        ax1.set_title('CPU Usage Over Time')
        ax1.set_ylabel('CPU %')
        ax1.set_xlabel('Time (seconds)')
        ax1.grid(True)
        
        # Memory Usage Chart
        ax2.plot(list(self.memory_usage), color='orange')
        ax2.set_title('Memory Usage Over Time')
        ax2.set_ylabel('Memory %')
        ax2.set_xlabel('Time (seconds)')
        ax2.grid(True)
        
        # Latency Distribution
        if self.latency_data:
            ax3.hist(list(self.latency_data), bins=50, alpha=0.7, color='green')
            ax3.set_title('Latency Distribution')
            ax3.set_xlabel('Latency (ms)')
            ax3.set_ylabel('Frequency')
            ax3.grid(True)
        
        # Throughput Chart
        if self.throughput_data:
            ax4.plot(list(self.throughput_data), color='red')
            ax4.set_title('Message Throughput')
            ax4.set_ylabel('Messages/second')
            ax4.set_xlabel('Time (seconds)')
            ax4.grid(True)
        
        plt.tight_layout()
        plt.savefig('performance_charts.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info("Performance charts saved to performance_charts.png")

    async def run_complete_benchmark(self, test_duration=300):
        """Run complete performance benchmark suite"""
        self.logger.info("Starting complete performance benchmark...")
        
        # Start system monitoring
        monitoring_task = asyncio.create_task(self.monitor_system_resources(test_duration))
        
        # Run benchmarks
        await asyncio.gather([
            self.measure_round_trip_latency(test_duration),
            self.measure_throughput(test_duration),
            self.check_thingsboard_health(),
            self.check_hivemq_health()
        ])
        
        # Wait for monitoring to complete
        await monitoring_task
        
        # Generate report and charts
        report = self.generate_performance_report()
        self.create_performance_charts()
        
        # Print summary
        self.print_summary(report)
        
        return report

    def print_summary(self, report):
        """Print performance summary"""
        print("\n" + "="*60)
        print("IoT CAMPUS PERFORMANCE BENCHMARK REPORT")
        print("="*60)
        
        results = report["benchmark_results"]
        
        # Latency Summary
        if "round_trip_latency" in results:
            latency = results["round_trip_latency"]
            print(f"\nRound-Trip Latency:")
            print(f"  Mean: {latency['mean_ms']:.2f}ms")
            print(f"  95th Percentile: {latency['p95_ms']:.2f}ms")
            print(f"  99th Percentile: {latency['p99_ms']:.2f}ms")
            print(f"  Target (<500ms): {'PASS' if latency['mean_ms'] < 500 else 'FAIL'}")
        
        # Throughput Summary
        if "throughput" in results:
            throughput = results["throughput"]
            print(f"\nMessage Throughput:")
            print(f"  Messages/Second: {throughput['messages_per_second']:.2f}")
            print(f"  Total Messages: {throughput['total_messages']}")
            print(f"  Target (>40 msg/s): {'PASS' if throughput['messages_per_second'] > 40 else 'FAIL'}")
        
        # System Resources
        if "cpu_usage" in results:
            cpu = results["cpu_usage"]
            print(f"\nCPU Usage:")
            print(f"  Mean: {cpu['mean_percent']:.2f}%")
            print(f"  Max: {cpu['max_percent']:.2f}%")
            print(f"  Target (<80%): {'PASS' if cpu['mean_percent'] < 80 else 'FAIL'}")
        
        if "memory_usage" in results:
            memory = results["memory_usage"]
            print(f"\nMemory Usage:")
            print(f"  Mean: {memory['mean_percent']:.2f}%")
            print(f"  Max: {memory['max_percent']:.2f}%")
            print(f"  Target (<80%): {'PASS' if memory['mean_percent'] < 80 else 'FAIL'}")
        
        # Health Checks
        print(f"\nService Health:")
        if "thingsboard_health" in results:
            tb = results["thingsboard_health"]
            print(f"  ThingsBoard: {'HEALTHY' if tb.get('healthy') else 'UNHEALTHY'}")
        
        if "hivemq_health" in results:
            hivemq = results["hivemq_health"]
            print(f"  HiveMQ: {'HEALTHY' if hivemq.get('healthy') else 'UNHEALTHY'}")
        
        # Overall Summary
        summary = report["summary"]
        print(f"\nOverall Summary:")
        print(f"  Latency Target Met: {'YES' if summary['latency_target_met'] else 'NO'}")
        print(f"  Throughput Target Met: {'YES' if summary['throughput_target_met'] else 'NO'}")
        print(f"  System Stable: {'YES' if summary['system_stable'] else 'NO'}")
        
        print("\n" + "="*60)

async def main():
    """Main performance monitoring function"""
    print("Starting IoT Campus Performance Monitoring...")
    print("This will run comprehensive benchmarks for 5 minutes")
    print()
    
    monitor = PerformanceMonitor()
    
    try:
        report = await monitor.run_complete_benchmark(300)  # 5 minutes
        
        print("\nBenchmark completed successfully!")
        print("Files generated:")
        print("1. performance_report.json - Detailed benchmark results")
        print("2. performance_charts.png - Performance visualization charts")
        
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user")
    except Exception as e:
        print(f"\nBenchmark failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
