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
from datetime import datetime
from pathlib import Path

try:
    import websocket
except ImportError:
    print("Error: websocket-client not installed. Run: pip install websocket-client")
    sys.exit(1)


class OBSDisplayMonitor:
    def __init__(self, source_name="Safari", host="localhost", port=4455, password=""):
        self.source_name = source_name
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.running = False
        self.monitor_interval = 5.0  # Check every 5 seconds
        self.last_restart_time = 0
        self.restart_cooldown = 30.0  # Minimum 30 seconds between restarts
        self.request_id = 1
        
        # Setup logging
        self.setup_logging()
        
    def setup_logging(self):
        """Setup logging configuration"""
        log_dir = Path.home() / "fun" / "LiveStream" / "utils" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "obs_monitor.log"
        
        logging.basicConfig(
            level=logging.DEBUG,  # Changed to DEBUG for more detailed output
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
                
                # Send Identify with auth
                payload = {
                    "op": 1,  # Identify OpCode
                    "d": {
                        "rpcVersion": 1,
                        "authentication": auth,
                        "eventSubscriptions": 33  # General events
                    }
                }
            else:
                # Send Identify without auth
                payload = {
                    "op": 1,  # Identify OpCode
                    "d": {
                        "rpcVersion": 1,
                        "eventSubscriptions": 33  # General events
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
    
    def is_source_active(self):
        """Check if the display capture source is currently active"""
        try:
            self.logger.debug(f"Checking if source '{self.source_name}' is active...")
            
            # Get current program scene
            scene_response = self._send_request("GetCurrentProgramScene")
            if not scene_response:
                self.logger.warning("Could not get current program scene")
                return False
            
            current_scene = scene_response.get('responseData', {}).get('currentProgramSceneName')
            if not current_scene:
                self.logger.warning("Current scene name is empty")
                return False
            
            self.logger.debug(f"Current scene: '{current_scene}'")
            
            # Get scene items
            items_response = self._send_request("GetSceneItemList", {"sceneName": current_scene})
            if not items_response:
                self.logger.debug("Could not get scene items, assuming source is OK")
                return True  # If we can't check, assume it's OK
            
            scene_items = items_response.get('responseData', {}).get('sceneItems', [])
            self.logger.debug(f"Scene has {len(scene_items)} items")
            
            # Look for our source
            source_found_in_scene = False
            for item in scene_items:
                item_name = item.get('sourceName', '')
                if item_name == self.source_name:
                    source_found_in_scene = True
                    is_enabled = item.get('sceneItemEnabled', False)
                    self.logger.debug(f"Found source '{self.source_name}' in scene, enabled: {is_enabled}")
                    return is_enabled
                self.logger.debug(f"Scene item: '{item_name}' (enabled: {item.get('sceneItemEnabled', False)})")
            
            if not source_found_in_scene:
                self.logger.debug(f"Source '{self.source_name}' not found in current scene '{current_scene}' - checking if it exists as input")
                
                # Check if the source exists at all and get its settings
                input_response = self._send_request("GetInputSettings", {"inputName": self.source_name})
                if input_response:
                    self.logger.debug(f"Source exists as input, assuming it's OK (not in current scene)")
                    return True
                else:
                    self.logger.warning(f"Source '{self.source_name}' doesn't exist as input")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking source status: {e}")
            return False
    
    def restart_display_capture(self):
        """Restart the display capture source by toggling capture settings"""
        current_time = time.time()
        
        # Check cooldown period
        if current_time - self.last_restart_time < self.restart_cooldown:
            self.logger.info(f"Restart cooldown active. Waiting {self.restart_cooldown - (current_time - self.last_restart_time):.1f} more seconds")
            return False
        
        try:
            self.logger.info("\n" + "-" * 60)
            self.logger.info("""
🔄 RESTARTING DISPLAY CAPTURE 🔄
Time: {}
Source: {}
--------------------------------------------------""".format(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.source_name
            ))
            
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
                self.last_restart_time = current_time
                self.logger.info("""
✅ RESTART SUCCESSFUL ✅
--------------------------------------------------""")
                return True
            
            self.logger.error("""
❌ RESTART FAILED ❌
--------------------------------------------------""")
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to restart display capture: {e}")
            return False
    
    async def monitor_loop(self):
        """Main monitoring loop"""
        self.logger.info(f"Starting monitor loop for source '{self.source_name}'")
        self.logger.info(f"Monitor interval: {self.monitor_interval}s, Max failures before restart: 3")
        
        consecutive_failures = 0
        max_consecutive_failures = 3
        check_count = 0
        
        while self.running:
            try:
                check_count += 1
                self.logger.info(f"=== Check #{check_count} ===")
                
                # Check if source is still active
                is_active = self.is_source_active()
                self.logger.info(f"Source '{self.source_name}' active: {is_active}")
                
                if not is_active:
                    consecutive_failures += 1
                    self.logger.warning(f"Source '{self.source_name}' appears inactive (failure #{consecutive_failures}/{max_consecutive_failures})")
                    
                    if consecutive_failures >= max_consecutive_failures:
                        self.logger.warning("""
⚠️  DISPLAY CAPTURE ISSUE DETECTED ⚠️
Source: {}
Failures: {} consecutive checks
Action: Attempting restart...
--------------------------------------------------""".format(
                            self.source_name,
                            consecutive_failures
                        ))
                        
                        if self.restart_display_capture():
                            consecutive_failures = 0  # Reset counter on successful restart
                            self.logger.info("✓ Resuming normal monitoring")
                        else:
                            self.logger.error("✗ Will retry on next check")
                else:
                    if consecutive_failures > 0:
                        self.logger.info(f"✓ Source '{self.source_name}' is now active again (was inactive for {consecutive_failures} checks)")
                    else:
                        self.logger.info(f"✓ Source '{self.source_name}' is active and healthy")
                    consecutive_failures = 0
                
                # Wait before next check
                self.logger.debug(f"Waiting {self.monitor_interval}s before next check...")
                await asyncio.sleep(self.monitor_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}")
                consecutive_failures += 1
                await asyncio.sleep(self.monitor_interval)
    
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
    # Configuration - modify these as needed
    SOURCE_NAME = "Safari"  # Name of your Display Capture source in OBS
    OBS_HOST = "localhost"
    OBS_PORT = 4455
    OBS_PASSWORD = ""  # Set if you have a password configured
    
    print(f"OBS Display Capture Monitor")
    print(f"Monitoring source: {SOURCE_NAME}")
    print(f"OBS WebSocket: {OBS_HOST}:{OBS_PORT}")
    print(f"Press Ctrl+C to stop")
    print("-" * 50)
    
    monitor = OBSDisplayMonitor(
        source_name=SOURCE_NAME,
        host=OBS_HOST,
        port=OBS_PORT,
        password=OBS_PASSWORD
    )
    
    try:
        monitor.start()
    except Exception as e:
        print(f"Failed to start monitor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 