# OBS Display Capture Monitor

A Python script that monitors and automatically restarts OBS Studio Display Capture sources when they become inactive. Specifically designed for macOS to handle display capture issues.

## Features

- 🔍 Monitors Display Capture sources in real-time
- 🔄 Automatically restarts capture when issues are detected
- 📝 Comprehensive logging with visual markers
- 🔒 Graceful shutdown handling
- 🎯 Focused on macOS Display Capture sources
- 🛠 Uses OBS WebSocket v5 protocol

## Requirements

- OBS Studio 31.0.0 or later
- Python 3.7 or later
- OBS WebSocket enabled (Tools → WebSocket Server Settings)
- Required Python packages:
  ```
  websocket-client>=1.8.0
  ```

## Installation

1. Clone or download this repository
2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Configure OBS WebSocket:
   - Open OBS Studio
   - Go to Tools → WebSocket Server Settings
   - Enable WebSocket Server
   - Note the port (default: 4455)
   - Set a password if needed

2. Run the script:
   ```bash
   python obs_display_monitor.py
   ```

3. For background service:
   ```bash
   ./setup_obs_monitor.sh
   ```

## How It Works

### Monitoring Workflow

1. **Connection**: 
   - Connects to OBS via WebSocket
   - Authenticates if password is configured
   - Verifies target source exists

2. **Monitoring Loop**:
   - Checks source status every 5 seconds
   - Tracks consecutive failures
   - Triggers restart after 3 consecutive failures
   - Maintains 30-second cooldown between restarts

3. **Restart Process**:
   - Gets current source settings
   - Toggles between window/display capture types
   - Forces OBS to reinitialize the capture
   - Verifies success

### Key Functions

\`\`\`python
def restart_display_capture(self):
    """
    Restarts display capture by toggling capture type:
    1. Gets current settings
    2. Switches from window (type 0) to display (type 1)
    3. Switches back after delay
    This forces OBS to reinitialize the capture
    """
\`\`\`

\`\`\`python
def is_source_active(self):
    """
    Checks if source is active by:
    1. Getting current scene
    2. Finding source in scene items
    3. Checking enabled status
    4. Verifying source exists as input
    """
\`\`\`

### Log Markers

The script uses distinct visual markers in logs:

```
⚠️  DISPLAY CAPTURE ISSUE DETECTED ⚠️
Source: Safari
Failures: 3 consecutive checks
Action: Attempting restart...
--------------------------------------------------

🔄 RESTARTING DISPLAY CAPTURE 🔄
Time: 2025-06-24 03:59:23
Source: Safari
--------------------------------------------------

✅ RESTART SUCCESSFUL ✅
--------------------------------------------------
```

## Configuration

Key settings in `obs_display_monitor.py`:

```python
SOURCE_NAME = "Safari"    # Name of Display Capture source
OBS_HOST = "localhost"    # OBS WebSocket host
OBS_PORT = 4455          # OBS WebSocket port
OBS_PASSWORD = ""        # OBS WebSocket password if set

# Monitoring settings
monitor_interval = 5.0    # Check interval in seconds
restart_cooldown = 30.0   # Minimum time between restarts
max_consecutive_failures = 3  # Failures before restart
```

## Troubleshooting

1. **Connection Issues**:
   - Verify OBS is running
   - Check WebSocket server is enabled
   - Confirm port number
   - Check password if configured

2. **Source Not Found**:
   - Verify source name matches exactly
   - Check source exists in current scene
   - Confirm source type is Display Capture

3. **Restart Not Working**:
   - Check OBS logs for errors
   - Verify source settings
   - Try manual restart for comparison

## Logs

Logs are stored in `~/fun/LiveStream/utils/logs/obs_monitor.log` with the following information:
- Connection status
- Source checks
- Restart attempts and results
- Error messages

## Testing

Use `test_restart.py` to verify restart functionality:
```bash
python test_restart.py
```

## License

MIT License - Feel free to modify and distribute as needed.

## Service Management

To manage the background service:

```bash
# Check service status
launchctl list | grep com.obs.display-monitor

# Stop the service
launchctl unload ~/Library/LaunchAgents/com.obs.display-monitor.plist

# Start the service
launchctl load ~/Library/LaunchAgents/com.obs.display-monitor.plist

# Restart the service
launchctl unload ~/Library/LaunchAgents/com.obs.display-monitor.plist && launchctl load ~/Library/LaunchAgents/com.obs.display-monitor.plist

# View service logs
tail -f ~/fun/LiveStream/utils/logs/obs_monitor.log
``` 