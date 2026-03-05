#!/usr/bin/python3
'''
piStor fan control daemon for Raspberry Pi 5.

Reads CPU temperature via gpiozero and adjusts a PWM fan connected to:
  - Fan PWM: GPIO 13 (Pin 33)
  - Fan tachometer: GPIO 18

CLI arguments:
  SERVICE   - Start the fan control daemon in a background thread.
  SHUTDOWN  - Log shutdown and exit (fan stops when process exits).
  VERSION   - Print the daemon version number.
  DEBUG     - Run fan control in the foreground, logging to console.

Requires the gpiozero library (sudo pip3 install gpiozero).
'''
#
# Setup environment and pull in all of the items we need from gpiozero.  The
# gpiozero library is the new one that supports Raspberry PI 5's (and I suspect
# will be new direction for all prior version the RPIi.)
#

from threading import Thread
from queue import Queue
from gpiozero import PWMOutputDevice, GPIODevice
from gpiozero import CPUTemperature
from logger import Logger
import time
import sys
import os
from configtool import *

#
# Some helpful constants
#

PYSTOR_VERSION = 1.0    # Version of this service
minTemp        = 10     # Minimum temp we care about (for CPU Temperature object)
maxTemp        = 80     # Maximum temp we can let the CPU get to
FAN_PWM_GPIO   = 13     # Fan PWM line is connected to GPIO 13 (Pin 33)
FAN_TACK_GPIO  = 18     # Fan TAC line is connected to GPIO 18

UPDATE_PERIOD  = 5      # Number of seconds between checking the temperature and
                        # modifing the fan speed


# Setup a logging object
#
log = Logger('/var/log/piStord.log')

def setupFan(fanPWMGPIO):
    '''
    This routine creates an object that we can utilize to communicate with the
    fan specified by the fanPWMGPIO parameter passed in.

    Parameter:
        fanPWMGPIO - The GPIO pin that the FAN PWM pin is connected to

    Returns:
        A fan object, with speed set to zero
    '''
    fan = None
    try:
        fan = PWMOutputDevice( fanPWMGPIO, frequency=100)
        fan.value = 0
    except Exception as error:
        log.error( "Error attempting to create output PWM device, error is {error}" )
        raise ValueError( "Cannot setup Fan!" )
      
    return fan

def setupTemperatureObject():
    '''
    Create and return a default CPUTemperature object.

    Return:
        A CPUTemperature object, or None if creation fails.
    '''
    cpuTemp = None
    try:
        cpuTemp = CPUTemperature()
    except Exception as error:
        log.error( f"Error creating CPU temperature object, error is {error}" )
        
    return cpuTemp

def controlFanAuto():
    '''
    Control the fan automatically based on CPU temperature.

    Runs an infinite loop waking every UPDATE_PERIOD seconds. On each iteration
    the fan duty cycle is set to cpuTemp.value + 0.1, clamped to 1.0. Every
    720 iterations a debug log line is emitted (and a warning if the fan is
    already at 100%).
    '''
    log.info( "Starting fan control service in automatic mode." )
    
    fan = setupFan( FAN_PWM_GPIO )
    cpuTemp = setupTemperatureObject()

    try:
        count = 0
        while True:
            if (count % 720) == 0:
                if fan.value >= 1.0:
                    log.warning( f"Temperature at {cpuTemp.temperature} fan running at 100%." )
                log.debug( f"CPU {cpuTemp.temperature} fan: {fan.value:0.2} cpu.value {cpuTemp.value:0.2}" )
    
            #
            # Add 0.1 to the range given if we can... max out the value
            #
            if cpuTemp.value + 0.1 <= 1.0:
                fan.value = cpuTemp.value + 0.1
            else:
                fan.value = 1.0
            time.sleep( UPDATE_PERIOD )
            
            count += 1
    except Exception as error:
        fan.value = 0.0
        log.error( f"An error ocurred during fan speed processing, Error is {error}" )
        
def getFanSpeed( temp, speedList ):
    '''
    Return the fan duty cycle for the given CPU temperature.

    Walks speedList in order, updating the candidate speed for each threshold
    that temp meets or exceeds, and stopping at the first threshold that temp
    falls below. If temp is below all thresholds (no match), returns 1.0 (100%)
    as a safe fallback.

    Parameters:
        temp      - The current CPU temperature in degrees Celsius.
        speedList - A list of (cpu_temp, fan_speed_pct) tuples sorted ascending
                    by cpu_temp. fan_speed_pct is in the 0-100 range.

    Returns:
        Fan duty cycle as a float in the range 0.0-1.0 (normalized from 0-100%).
    '''
    speed = -1
    for item in speedList:
        log.debug( f"CPU: {temp} tuple: {item} speed: {speed}" )
        if temp >= item[0]:
            speed = item[1]
        else:
            break
    if speed == -1:
        speed = 100
    return speed / 100
  
def controlFanManual( cpufanSpeed ):
    '''
    Perform the fan speed operations based on the manual settings from the
    configuration file.
    
    Parameters:
        cpufanSpeed - A list of tuples containing a CPU temp and the corresponding
                      fan speed.
    '''
    
    log.info( f"Starting fan control service in manual mode using data: {cpufanSpeed}." )
    fan = setupFan( FAN_PWM_GPIO )
    cpuTemp = setupTemperatureObject()
    
    try:
        count = 0
        while True:
            if (count % 720) == 0:
                log.debug( f"CPU {cpuTemp.temperature} fan: {fan.value:0.2} cpu.value {cpuTemp.value:0.2}" )
                
            #
            fan.value = getFanSpeed( cpuTemp.temperature, cpufanSpeed )
            
            #
            time.sleep( UPDATE_PERIOD )            
            count += 1
    except Exception as error:
        fan.value = 0.0
        log.error( f"An error occured during fan speed processing, Error is {error}" )
        
CONFIG_PATH = '/etc/pistor.conf'

def startFanControl():
    '''
    Start the fan controller using the mode from /etc/pistor.conf.

    If the config file does not exist, logs a warning and starts in automatic
    mode with default settings. Otherwise reads the config and dispatches to
    the appropriate control function:
      1 (AUTO_FAN)   - calls controlFanAuto()
      0 (MANUAL_FAN) - calls controlFanManual() with the configured speed table
      other          - logs an error and falls back to controlFanAuto()
    '''
    if not os.path.isfile( CONFIG_PATH ):
        log.warning( f"Config file {CONFIG_PATH} not found, starting with defaults (auto mode)." )
        controlFanAuto()
        return

    config = piStorConfig( CONFIG_PATH )
    mode = config.getMode()
    match mode:
        case 1:
            controlFanAuto()
        case 0:
            controlFanManual( config.getFanSpeed() )
        case _:
            log.error( f"Unknown fan mode of {mode}, reverting to automatic." )
            controlFanAuto()
    
def turnOffFan():
    '''
    Log the fan shutdown message. Called when the SHUTDOWN CLI argument is used.

    The fan itself stops when the service process exits and gpiozero releases the
    GPIO pin. Any GPIO errors are logged but do not raise.
    '''
    try:
        fan = setupFan( FAN_PWM_GPIO )
        fan.value = 0
    except Exception as error:
        log.error( f"Could not turn off fan, Error: {error}" )
        
def usage():
    '''
    Print the usage of this service, if anyone runs it locally.
    '''
    print( "piStord - Fan Service for the piStor data server.\n" )
    print( "usage: pystord <options>" )
    print( "    SHUTDOWN    - Shutdown the piStor fan... issued when the user shutdown the service." )
    print( "    SERVICE     - Launch the pistord Daemon so we can control the fan." )
    print( "    VERSION     - Report the version of the piStor Daemon." )
    print( "    DEBUG       - Launches the fan control without spawning a thread." )

#
# Main entry point
#

if len(sys.argv) > 1:
    cmd = sys.argv[1].upper()
    match cmd:
        case "SHUTDOWN":
            log.info( "piStor Fan Service stopping..." )
            turnOffFan()
        
        case "SERVICE":
            try:
                log.info( f"piStor Fan Service starting... Version {PYSTOR_VERSION}." )
                thread1 = Thread(target = startFanControl )
                thread1.start()
            except Exception as error:
                log.info( f"Could not start sercice threads, Error {error}" )

        case "VERSION":
            print( f"Version: {PYSTOR_VERSION}" )
        case "DEBUG":
            log.forceConsole()
            startFanControl()
        case _:
            usage()
else:
    usage()
