#!/bin/bash

# Setup script for OBS Display Capture Monitor
# For macOS systems

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"
PYTHON_SCRIPT="$SCRIPT_DIR/obs_display_monitor.py"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_NAME="com.obs.display-monitor.plist"
PLIST_PATH="$LAUNCH_AGENT_DIR/$PLIST_NAME"

echo "=== OBS Display Capture Monitor Setup ==="
echo "Script directory: $SCRIPT_DIR"
echo "Virtual environment: $VENV_PATH"
echo ""

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_PATH"
fi

# Activate virtual environment and install dependencies
echo "Installing Python dependencies..."
source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "Dependencies installed successfully!"
echo ""

# Make Python script executable
chmod +x "$PYTHON_SCRIPT"

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

echo "=== Background Service Setup ==="
echo "This will create a LaunchAgent to run the monitor in the background."
echo "The service will automatically start when you log in."
echo ""

read -p "Do you want to set up the background service? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Create LaunchAgents directory if it doesn't exist
    mkdir -p "$LAUNCH_AGENT_DIR"
    
    # Create the plist file
    cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.obs.display-monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PATH/bin/python</string>
        <string>$PYTHON_SCRIPT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/service_output.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/service_error.log</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF
    
    echo "LaunchAgent created at: $PLIST_PATH"
    
    # Load the service
    echo "Loading the service..."
    launchctl load "$PLIST_PATH"
    
    echo ""
    echo "=== Service Management Commands ==="
    echo "Start service:  launchctl load $PLIST_PATH"
    echo "Stop service:   launchctl unload $PLIST_PATH"
    echo "View logs:      tail -f $SCRIPT_DIR/logs/obs_monitor.log"
    echo "Service status: launchctl list | grep com.obs.display-monitor"
    echo ""
    echo "The service is now running in the background!"
else
    echo ""
    echo "=== Manual Usage ==="
    echo "To run the monitor manually:"
    echo "1. Activate virtual environment: source $VENV_PATH/bin/activate"
    echo "2. Run the script: python $PYTHON_SCRIPT"
    echo ""
fi

echo "=== Configuration Notes ==="
echo "• Make sure OBS Studio is running with WebSocket server enabled"
echo "• Default WebSocket settings: localhost:4455 (no password)"
echo "• The script monitors a source named 'Safari' by default"
echo "• Edit $PYTHON_SCRIPT to change the source name if needed"
echo "• Logs are saved to: $SCRIPT_DIR/logs/obs_monitor.log"
echo ""
echo "Setup complete!" 