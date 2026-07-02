#!/usr/bin/env bash
set -e

cd ~/GO2_Project/go2_bridge_ws

echo "[Laptop] Starting GO2 Dashboard backend..."
echo "[Laptop] Robot ID should be: GO2_001"
echo "[Laptop] Make sure Jetson bridge connects to this laptop IP."
echo ""

bash scripts/start_backend.sh
