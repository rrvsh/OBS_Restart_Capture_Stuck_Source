#!/usr/bin/env python3
"""
Test script to verify OBS restart functionality
"""

import sys
import time
from obs_display_monitor import OBSDisplayMonitor

def test_restart():
    """Test the restart functionality"""
    print("=== OBS Restart Test ===")
    
    monitor = OBSDisplayMonitor(source_name="Safari")
    
    # Connect to OBS
    if not monitor.connect_to_obs():
        print("❌ Failed to connect to OBS")
        return False
    
    print("✅ Connected to OBS")
    
    # Check if source exists
    if not monitor.check_source_exists():
        print("❌ Source not found")
        monitor.disconnect_from_obs()
        return False
    
    print("✅ Source found")
    
    # Test restart functionality
    print("\n🔄 Testing restart functionality...")
    success = monitor.restart_display_capture()
    
    if success:
        print("✅ Restart function executed successfully")
    else:
        print("❌ Restart function failed")
    
    monitor.disconnect_from_obs()
    return success

if __name__ == "__main__":
    test_restart() 