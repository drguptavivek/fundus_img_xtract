#!/bin/bash

# Installation script for Fundus Image Manager systemd service
# This script sets up the application to run as a systemd service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
SERVICE_NAME="fundus-img-xtract"
SERVICE_FILE="fundus-img-xtract.service"
INSTALL_DIR="/opt/fundus_img_xtract"
LOG_DIR="/var/log/fundus-img-xtract"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

print_info "Installing Fundus Image Manager as systemd service..."

# Get installation directory from user if different from default
read -p "Enter installation directory [$INSTALL_DIR]: " USER_INSTALL_DIR
if [ ! -z "$USER_INSTALL_DIR" ]; then
    INSTALL_DIR="$USER_INSTALL_DIR"
fi

# Check if directory exists
if [ ! -d "$INSTALL_DIR" ]; then
    print_error "Installation directory $INSTALL_DIR does not exist"
    print_info "Please clone the repository to $INSTALL_DIR first"
    exit 1
fi

# Update service file with actual installation path
print_info "Updating service file with installation path..."
sed -i "s|/opt/fundus_img_xtract|$INSTALL_DIR|g" "$SERVICE_FILE"

# Also update the virtual environment path in the service file
VENV_PATH="$INSTALL_DIR/.venv"
if [ ! -d "$VENV_PATH" ]; then
    print_warn "Virtual environment not found at $VENV_PATH"
    print_info "The service file will use uv from system PATH"
else
    print_info "Virtual environment found at $VENV_PATH"
    # Update the service file to use the virtual environment
    sed -i "s|/opt/fundus_img_xtract/.venv|$VENV_PATH|g" "$SERVICE_FILE"
fi

# Create log directory
print_info "Creating log directory..."
mkdir -p "$LOG_DIR"
chown www-data:www-data "$LOG_DIR"
chmod 755 "$LOG_DIR"

# Copy service file to systemd
print_info "Installing systemd service file..."
cp "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME.service"

# Set proper permissions
chmod 644 "/etc/systemd/system/$SERVICE_NAME.service"

# Reload systemd daemon
print_info "Reloading systemd daemon..."
systemctl daemon-reload

# Enable the service to start on boot
print_info "Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME"

print_info "Service installed successfully!"
print_info ""
print_info "To start the service: sudo systemctl start $SERVICE_NAME"
print_info "To stop the service: sudo systemctl stop $SERVICE_NAME"
print_info "To restart the service: sudo systemctl restart $SERVICE_NAME"
print_info "To check service status: sudo systemctl status $SERVICE_NAME"
print_info "To view logs: sudo journalctl -u $SERVICE_NAME -f"
print_info ""
print_warn "Make sure your .env file is properly configured in $INSTALL_DIR/.env"
print_warn "The service will run as user www-data, ensure proper file permissions"