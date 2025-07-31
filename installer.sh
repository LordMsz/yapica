#!/bin/bash

# --- Script Start ---
echo "--- Starting Raspberry Pi Camera Server Installation ---"

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script with sudo: sudo ./installer.sh"
    exit 1
fi

# --- 1. Install picamera2 System-Wide ---
echo ""
echo "--- 1/6: Installing picamera2 and core dependencies via apt ---"
apt update
apt install -y python3-picamera2 --no-install-recommends
echo "picamera2 system installation complete."

# TODO add user setup and new folders etc.

# Copy systemd service file
cp "/home/camera_user/camera_project/pizero-camera.service" "/etc/systemd/system/pizero-camera.servic>chown root:root "/etc/systemd/system/pizero-camera.service" # Service file owned by root
chmod 644 "/etc/systemd/system/pizero-camera.service" # Standard permissions for service files
echo "Application files copied."


echo "--- 6/6: Configuring and starting systemd service ---"
systemctl daemon-reload
systemctl enable "pizero-camera.service"
systemctl start "pizero-camera.service"
echo "Systemd service 'pizero-camera.service' configured and started."


echo ""
echo "--- Installation Complete! ---"
echo "Your camera server should now be running. You can check its status with:"
echo "sudo systemctl status pizero-camera.service"
echo "To view live logs: sudo journalctl -u pizero-camera.service -f"
echo ""
echo "Remember to open your web browser to http://<your_pi_ip>:5000"
echo "You can find your Pi's IP address with: hostname -I"
echo ""
echo "Please reboot your Pi now for all changes (especially user groups) to fully take effect:"
echo "sudo reboot"