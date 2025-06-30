#!/bin/bash

echo "**********************************"
echo " piStor Fan Control Service Setup "
echo "**********************************"

# Helper variables
DOWNLOADSERVER=https://raw.githubusercontent.com/JeffCurless/piStor/main/
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
sudo curl -L $DOWNLOADSERVER/pistor.conf -o $INSTALLROOT/pistor.conf --silent
sudo chmod 755 $INSTALLROOT/pistor.conf

#
# Copy service to systemd area
#
sudo curl -L $DOWNLOADSERVER/pistord.service -o $INSTALLSERVICEFOLDER/pistord.service --silent
sudo chmod 644 $INSTALLSERICEFOLDER/pistord.service

#
# Start service
#
sudo systemctl daemin-reload
sudo systemctl enable pistord.service
sudo systemctl start pistord.service

echo "Service is installed..."

