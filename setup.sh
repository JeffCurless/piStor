#!/bin/bash
# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT

# Stop at the first failed command (e.g. a failed download)
set -e

echo "**********************************"
echo " piStor Fan Control Service Setup "
echo "**********************************"

# Helper variables
DOWNLOADSERVER=https://raw.githubusercontent.com/JeffCurless/piStor/main/src
INSTALLROOT=/etc
INSTALLATIONFOLDER=$INSTALLROOT/pistor
INSTALLSERVICEFOLDER=/lib/systemd/system

echo "Tested on Raspberry Pi OS 12 (Bookworm)"
#
# Make sure packages are installed
#
#sudo apt install python3
#sudo pip3 install gpiozero

#
# Create installation directory
#
sudo mkdir -p $INSTALLATIONFOLDER
sudo chmod 755 $INSTALLATIONFOLDER

#
# Copy files to install area
#
sudo curl -fsSL $DOWNLOADSERVER/logger.py -o $INSTALLATIONFOLDER/logger.py
sudo chmod 755 $INSTALLATIONFOLDER/logger.py
sudo curl -fsSL $DOWNLOADSERVER/configtool.py -o $INSTALLATIONFOLDER/configtool.py
sudo chmod 755 $INSTALLATIONFOLDER/configtool.py
sudo curl -fsSL $DOWNLOADSERVER/pistord.py -o $INSTALLATIONFOLDER/pistord.py
sudo chmod 755 $INSTALLATIONFOLDER/pistord.py
#
# Install the default configuration only if there isn't one already, so a
# reinstall keeps the user's settings.
#
if [ -f $INSTALLROOT/pistor.conf ]; then
    echo "Keeping existing $INSTALLROOT/pistor.conf"
else
    sudo curl -fsSL $DOWNLOADSERVER/pistor.conf -o $INSTALLROOT/pistor.conf
    sudo chmod 644 $INSTALLROOT/pistor.conf
fi

#
# Copy service to systemd area
#
sudo curl -fsSL $DOWNLOADSERVER/pistord.service -o $INSTALLSERVICEFOLDER/pistord.service
sudo chmod 644 $INSTALLSERVICEFOLDER/pistord.service

#
# Start service
#
sudo systemctl daemon-reload
sudo systemctl enable pistord.service
sudo systemctl start pistord.service

echo "Service is installed..."

