#!/usr/bin/python3
#
# Setup environment and pull in all of the items we need from gpiozero.  The
# gpiozero library is the new one that supports Raspberry PI 5's (and I suspect
# will be new direction for all prior version the RPIi.)
#

from threading import Thread
from queue import Queue
from gpiozero import PWMOutputDevice
from gpiozero import CPUTemperature
from logger import Logger
import time
import sys
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
        raise valueError( "Cannot setup Fan!" )
      
    return fan

def setupTemperatureObject():
    '''
    Get a cpu temperature object, and set the min and max range.  

    When the ranges are set to the non-default values, if the temperature is
    less than min_temp we get 0, and when the temperature reaches the max we get
    a value of 1.  This value can be used directly as a duty cycle for the fan.

    Return:
        A CPU temperature object
    '''
    cpuTemp = None
    try:
        cpuTemp = CPUTemperature()
    except Exception as error:
        log.error( f"Error creating CPU temperature object, error is {error}" )
        
    return cpuTemp

def controlFanAuto():
    '''
    This routine is responsible for controlling the fan.  The fan control
    process is every period of time the code wakes up and gets the current CPU
    temp. Using the CPU temperature, we determine what fan speed to use to cool
    down the CPU

    A word on the cpu temperature object.  When setting up the CPU temperature
    object, we provide it with the minimum and maximum temperatures.  While we
    can get the current temp, we can also get a value (0->1) that directly maps
    to the minimum and maximum values we setup.  

    '''
    log.info( "Starting fan control service in automatic mode." )
    
    fan = setupFan( FAN_PWM_GPIO )
    cpuTemp = setupTemperatureObject()

    try:
        count = 0
        while True:
            if (count % 720) == 0:
                log.debug( f"CPU {cpuTemp.temperature} fan: {fan.value:0.2} cpu.value {cpuTemp.value:0.2}" )
    
            #
            # Add 0.1 to the range given if we can... max out the value
            #
            if cpuTemp.value + 0.1 <= 1.0:
                fan.value = cpuTemp.value + 0.1
            else:
                fan.value = cpuTemp.value
            time.sleep( UPDATE_PERIOD )
            count += 1
    except Exception as error:
        fan.value = 0.0
        log.error( f"An error ocurred during fan speed processing, Error is {error}" )
        
def getFanSpeed( temp, speedList ):
    '''
    Obtain the speed the fan should be running at given the current CPU temp,
    and the list of (temp,speed) tuples.  This search is walk down the list of
    tuples and stop when the temperature of the tuple is higher than the CPU
    temperature.
    
    Parameters:
        temp      - The current temperature if the CPU
        speedList - A list of tuples. Each tuple contains a CPU temp, and
                    corresponding than speed.
                   
    Returns:
        A suggested speed, normalized from 0 - 1 (0% and 100%)
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
        
def startFanControl():
    '''
    Call this function to start the fan controller.  If the system is configured
    to run automatically, call the automatic control function, if not call manual,
    if we have no idea what we are supposed todo... default to autmoatic.
    
    '''
    config = piStorConfig( '/etc/pistor.conf' )
    match config.getMode():
        case 1:
            controlFanAuto()
        case 0:
            controlFanManual( config.getFanSpeed() )
        case _:
            log.error( f"Unknown fan mode of {mode}, reverting to automatic." )
            controlFanAuto()
    
def turnOffFan():
    '''
    Attempt to turn off the fan, this is normally called from a service shutdown,
    so the code is operating in a different context, and different process.
    
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
