#!/usr/bin/env python3
"""
OBS Display Capture Monitor

Monitors a Display Capture source in OBS Studio and automatically restarts
it when the source becomes inactive or non-functional.

Uses OBS WebSocket API for reliable monitoring without pixel monitoring.
Designed to run completely in background on macOS.
"""

import asyncio
import json
import logging
import signal
import sys
import time
import base64
import hashlib
import os
import argparse
from datetime import datetime
from pathlib import Path

try:
    import websocket
except ImportError:
    print("Error: websocket-client not installed. Run: pip install websocket-client")
    sys.exit(1)


class OBSDisplayMonitor:
    def __init__(self, source_name, host, port, password, interval, threshold, cooldown):
        self.source_name = source_name
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.running = True
        self.monitor_interval = interval
        self.stuck_threshold = threshold
        self.last_restart = 0
        self.restart_cooldown = cooldown
        self.request_id = 1
        
        # Setup logging
        self.setup_logging()
        
    def setup_logging(self):
        """Setup logging configuration"""
        log_dir = Path.cwd() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "obs_monitor.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _build_auth_string(self, salt, challenge):
        """Build authentication string for OBS WebSocket"""
        secret = base64.b64encode(
            hashlib.sha256(
                (self.password + salt).encode('utf-8')
            ).digest()
        )
        auth = base64.b64encode(
            hashlib.sha256(
                secret + challenge.encode('utf-8')
            ).digest()
        ).decode('utf-8')
        return auth
    
    def _authenticate(self):
        """Authenticate with OBS WebSocket"""
        try:
            # Receive hello message
            message = self.ws.recv()
            result = json.loads(message)
            
            if result.get('op') != 0:  # Hello OpCode
                raise Exception("Expected Hello message")
            
            auth_data = result['d'].get('authentication')
            if auth_data and self.password:
                # Build auth string
                auth = self._build_auth_string(
                    auth_data['salt'], 
                    auth_data['challenge']
                )
                
                # Send Identify with auth and subscribe to all input events
                payload = {
                    "op": 1,  # Identify OpCode
                    "d": {
                        "rpcVersion": 1,
                        "authentication": auth,
                        "eventSubscriptions": 33 | (1 << 14)  # General events + Input events
                    }
                }
            else:
                # Send Identify without auth but with input events subscription
                payload = {
                    "op": 1,  # Identify OpCode
                    "d": {
                        "rpcVersion": 1,
                        "eventSubscriptions": 33 | (1 << 14)  # General events + Input events
                    }
                }
            
            self.ws.send(json.dumps(payload))
            
            # Receive Identified message
            message = self.ws.recv()
            result = json.loads(message)
            
            if result.get('op') != 2:  # Identified OpCode
                raise Exception(f"Authentication failed: {result}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False
    
    def connect_to_obs(self):
        """Establish connection to OBS WebSocket"""
        try:
            self.logger.info(f"Connecting to OBS WebSocket at {self.host}:{self.port}")
            url = f"ws://{self.host}:{self.port}"
            self.ws = websocket.create_connection(url)
            
            # Authenticate
            if not self._authenticate():
                return False
            
            # Test connection by getting version
            version_response = self._send_request("GetVersion")
            if version_response:
                obs_version = version_response.get('responseData', {}).get('obsVersion', 'Unknown')
                self.logger.info(f"Connected to OBS Studio {obs_version}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to connect to OBS: {e}")
            return False
    
    def disconnect_from_obs(self):
        """Disconnect from OBS WebSocket"""
        if self.ws:
            try:
                self.ws.close()
                self.logger.info("Disconnected from OBS WebSocket")
            except Exception as e:
                self.logger.error(f"Error disconnecting from OBS: {e}")
            finally:
                self.ws = None
    
    def _send_request(self, request_type, request_data=None):
        """Send a request to OBS and return the response"""
        if not self.ws:
            return None
        
        try:
            request_id = f"req_{self.request_id}"
            self.request_id += 1
            
            payload = {
                "op": 6,  # Request OpCode
                "d": {
                    "requestId": request_id,
                    "requestType": request_type,
                    "requestData": request_data or {}
                }
            }
            
            self.ws.send(json.dumps(payload))
            
            # Wait for response
            message = self.ws.recv()
            response = json.loads(message)
            
            if response.get('op') == 7 and response.get('d', {}).get('requestId') == request_id:
                return response.get('d')
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error sending request {request_type}: {e}")
            return None
    
    def check_source_exists(self):
        """Check if the target source exists in OBS"""
        try:
            self.logger.info(f"Checking if source '{self.source_name}' exists...")
            response = self._send_request("GetInputList")
            self.logger.debug(f"GetInputList response: {response}")
            
            if not response:
                self.logger.error("No response from GetInputList")
                return False
            
            inputs = response.get('responseData', {}).get('inputs', [])
            input_names = [inp.get('inputName', '') for inp in inputs]
            
            self.logger.info(f"Found {len(inputs)} inputs in OBS: {input_names}")
            
            if self.source_name not in input_names:
                self.logger.error(f"Source '{self.source_name}' not found in OBS")
                self.logger.info(f"Available inputs: {', '.join(input_names)}")
                return False
            
            self.logger.info(f"✓ Source '{self.source_name}' found in OBS")
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking source existence: {e}")
            return False
    
    def _is_source_frozen(self, prev_hash):
        """
        Check if the source is frozen by comparing screenshot hashes.
        Returns a tuple: (is_frozen, current_hash)
        """
        current_hash = self._get_screenshot_hash()
        
        if current_hash is None:
            self.logger.warning("⚠️ Failed to get screenshot, cannot determine state.")
            return False, prev_hash # Assume not frozen if we can't get a screenshot

        is_frozen = (current_hash == prev_hash)
        return is_frozen, current_hash
    
    def _get_screenshot_hash(self):
        """Get MD5 hash of current source screenshot."""
        try:
            response = self._send_request("GetSourceScreenshot", {
                "sourceName": self.source_name,
                "imageFormat": "png",
                "imageWidth": 320,  # Small size for quick comparison
                "imageHeight": 180,
                "imageCompressionQuality": 50
            })
            
            if response and 'responseData' in response:
                # Extract base64 data from data URL
                image_data = response['responseData']['imageData'].split(',', 1)[1]
                # Get MD5 hash of the image data
                return hashlib.md5(base64.b64decode(image_data)).hexdigest()
            return None
        except Exception as e:
            self.logger.error(f"Failed to get screenshot: {e}")
            return None

    def _restart_capture(self):
        """Restart the display capture source by toggling capture settings"""
        try:
            current_time = time.time()
            if current_time - self.last_restart < self.restart_cooldown:
                self.logger.info("⏳ Skipping restart - cooldown period active")
                return False

            self.logger.warning(f"{'='*50}")
            self.logger.warning("🔄 RESTARTING DISPLAY CAPTURE")
            self.logger.warning(f"Source: {self.source_name}")
            self.logger.warning(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Get current settings
            settings_response = self._send_request("GetInputSettings", {
                "inputName": self.source_name
            })
            
            if not settings_response or 'responseData' not in settings_response:
                self.logger.error("Failed to get source settings")
                return False

            current_settings = settings_response['responseData'].get('inputSettings', {})
            self.logger.debug(f"Current settings: {json.dumps(current_settings, indent=2)}")
            
            # Method 1: Toggle capture type between window and display
            original_type = current_settings.get('type', 0)
            new_type = 1 if original_type == 0 else 0
            
            # Change to opposite type
            self._send_request("SetInputSettings", {
                "inputName": self.source_name,
                "inputSettings": {**current_settings, "type": new_type}
            })
            time.sleep(0.5)
            
            # Change back to original type
            response = self._send_request("SetInputSettings", {
                "inputName": self.source_name,
                "inputSettings": {**current_settings, "type": original_type}
            })
            
            if response and response.get('requestStatus', {}).get('result'):
                self.last_restart = current_time
                self.logger.warning("✅ Restart completed")
                self.logger.warning(f"{'='*50}")
                return True
            
            self.logger.error("❌ Restart failed")
            return False
            
        except Exception as e:
            self.logger.error(f"❌ Failed to restart capture: {e}")
            return False

    async def monitor_loop(self):
        """Main monitoring loop using screenshot comparison."""
        self.logger.info(f"Starting monitor loop for source '{self.source_name}'")
        self.logger.info(f"Monitor interval: {self.monitor_interval}s, Stuck threshold: {self.stuck_threshold} frames")
        
        prev_hash = None
        identical_count = 0
        check_count = 0
        
        while self.running:
            try:
                check_count += 1
                self.logger.info(f"=== Check #{check_count} ===")
                
                is_frozen, current_hash = await asyncio.to_thread(self._is_source_frozen, prev_hash)
                
                if is_frozen:
                    identical_count += 1
                    self.logger.warning(f"⚠️ Identical frame detected (count: {identical_count}/{self.stuck_threshold})")
                    
                    if identical_count >= self.stuck_threshold:
                        self.logger.warning("❗ Display capture appears to be frozen")
                        if self._restart_capture():
                            identical_count = 0  # Reset counter after restart
                            # After a restart, the hash will be different, so we fetch a new one
                            current_hash = self._get_screenshot_hash() 
                else:
                    if identical_count > 0:
                        self.logger.info("✅ Frame changed - display capture is active")
                    identical_count = 0
                
                prev_hash = current_hash
                await asyncio.sleep(self.monitor_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(2)  # Wait before retrying
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def start(self):
        """Start the monitoring service"""
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.logger.info("Starting OBS Display Capture Monitor")
        
        # Connect to OBS
        if not self.connect_to_obs():
            self.logger.error("Failed to connect to OBS. Exiting.")
            return False
        
        # Verify source exists
        if not self.check_source_exists():
            self.logger.error("Target source not found. Exiting.")
            self.disconnect_from_obs()
            return False
        
        self.running = True
        
        try:
            # Run the monitoring loop
            asyncio.run(self.monitor_loop())
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
        finally:
            self.stop()
        
        return True
    
    def stop(self):
        """Stop the monitoring service"""
        self.logger.info("Stopping OBS Display Capture Monitor")
        self.running = False
        self.disconnect_from_obs()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="OBS Display Capture Monitor")
    parser.add_argument(
        '--source', 
        type=str, 
        default="Safari", 
        help="Name of the Display Capture source in OBS"
    )
    parser.add_argument(
        '--host', 
        type=str, 
        default="localhost", 
        help="OBS WebSocket host"
    )
    parser.add_argument(
        '--port', 
        type=int, 
        default=4455, 
        help="OBS WebSocket port"
    )
    parser.add_argument(
        '--password', 
        type=str, 
        default="", 
        help="OBS WebSocket password"
    )
    parser.add_argument(
        '--interval', 
        type=float, 
        default=1.0, 
        help="How often to check for freezes (seconds)"
    )
    parser.add_argument(
        '--threshold', 
        type=int, 
        default=1, 
        help="How many identical frames before considering frozen"
    )
    parser.add_argument(
        '--cooldown', 
        type=int, 
        default=30, 
        help="Minimum time between restarts (seconds)"
    )
    
    args = parser.parse_args()
    
    print(f"OBS Display Capture Monitor")
    print(f"Monitoring source: {args.source}")
    print(f"OBS WebSocket: {args.host}:{args.port}")
    print(f"Press Ctrl+C to stop")
    print("-" * 50)
    
    monitor = OBSDisplayMonitor(
        source_name=args.source,
        host=args.host,
        port=args.port,
        password=args.password,
        interval=args.interval,
        threshold=args.threshold,
        cooldown=args.cooldown
    )
    
    try:
        monitor.start()
    except Exception as e:
        print(f"Failed to start monitor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 