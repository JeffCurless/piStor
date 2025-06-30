#!/bin/bash

echo "**********************************"
echo " piStor Fan Control Service Setup "
echo "**********************************"

# Helper variables
DOWNLOADSERVER=https://raw.githubusercontent.com/JeffCurless/argoneon/main/
INSTALLATIONFOLDER=/etc/pistor

echo "Tested on Raspberry Pi OS 12 (Bookworm)"
#
# Make sure packages are installed
#
sudo pip3 install gpiozero

#
# Create installation directory
#
sudo mkdir $INSTALLATIONFOLDER
sudo chmod 755 $INSTALLATIONFOLDER

#
# Copy files to install area
#
sudo curl -L $DOWNLOADSERVER/logger.py -o $INSTALLATIONFOLDER/logger.py --silent
sudo chmod 755 $INSTALLATIONFOLDER/logger.py
sudo curl -L $DOWNLOADSERVER/configtool.py -o $INSTALLATIONFOLDER/configtool.py --silent
sudo chmod 755 $INSTALLATIONFOLDER/configtool.py
sudo curl -L $DOWNLOADSERVER/pistord.py -o $INSTALLATIONFOLDER/pistord.py --silent
sudo chmod 755 $INSTALLATIONFOLDER/pistord.py
sudo curl -L $DOWNLOADSERVER/pistor.conf -o /etc/pistor.conf --silent
sudo chmod 755 /etc/pistor.conf

#
# Copy service to systemd area
#
sudo curl -L $DOWNLOADSERVER/pistord.service -o /lib/systemd/system/pistord.servicei --silent
sudo chmod 644 /lib/systemd/system/pistord.service

#
# Start service
#
sudo systemctl daemin-reload
sudo systemctl enable pistord.service
sudo systemctl start pistord.service

echo "Service is installed..."

