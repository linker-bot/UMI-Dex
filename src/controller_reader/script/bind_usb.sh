#!/bin/bash
set -e

# 获取脚本所在目录（而不是当前工作目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "start copy l6encoder_usb.rules to /etc/udev/rules.d/"
sudo cp "$SCRIPT_DIR/l6encoder_usb.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
echo "Finish!!!"
