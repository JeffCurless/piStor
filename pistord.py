#!/usr/bin/python3
#
# Setup environment and pull in all of the items we need from gpiozero.  The gpiozero library is the new one that
# supports Raspberry PI 5's (and I suspect will be new direction for all prior version the RPIi.)
#

from threading import Thread
from queue import Queue
from gpiozero import PWMOutputDevice
from gpiozero import CPUTemperature
import time
import sys
import logging

#
# Some helpful constants
#

PYSTOR_VERSION = 1.0    # Version of this service
minTemp        = 10     # Minimum temp we care about (for CPU Temperature object)
maxTemp        = 80     # Maximum temp we can let the CPU get to
FAN_PWM_GPIO   = 14     # Fan PWM line is connected to GPIO 14
FAN_TACK_GPIO  = 18     # Fan TAC line is connected to GPIO 18

UPDATE_PERIOD  = 5      # Number of seconds between checking the temperature and modifing the fan speed

class Logger:
    def __init__(self,level=logging.DEBUG):
        self._logEnabled = True
        try:
            logging.basicConfig( filename='/var/log/piStord.log',
                                 filemode='a',
                                 level=level,
                                 format='%(asctime)s %(process)d [%(levelname)s] %(message)s',
                                 datefmt='%b %d %y %H:%M:%S')
        except Exception as error:
            print( f"Error: Could not log events due to {error}." )
            self._logEnabled = False
    def info( self, message ):
        if self._logEnabled:
            logging.info( message )
        else:
            print( f"INFO: {message}" )
    
    def debug( self, message ):
        if self._logEnabled:
            logging.debug( message )
        else:
            print( f"DEBUG: {message}" )
    
    def error( self, message ):
        if self._logEnabled:
            logging.error( message )
        else:
            print( f"(ERROR: {message}" )
    
    def forceConsole():
        self._logEnabled = False
#
# Setup a logging object
#
log = Logger()
            
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

    When the ranges are set to the non-default values, if the temperature is less
    than min_temp we get 0, and when the temperature reaches the max we get a 
    value of 1.  This value can be used directly as a duty cycle for the fan.

    Return:
        A CPU temperature object
    '''
    cpuTemp = None
    try:
        cpuTemp = CPUTemperature()
    except Exception as error:
        log.error( f"Error creating CPU temperature object, error is {error}" )
        
    return cpuTemp

def controlFan():
    '''
    This routine is responsible for controlling the fan.  The fan control process is every period of time
    the code wakes up and gets the current CPU temp.  Using the CPU temperature, we determine what fan speed
    to use to cool down the CPU

    A word on the cpu temperature object.  When setting up the CPU temperature object, we provide it with the
    minimum and maximum temperatures.  While we can get the current temp, we can also get a value (0->1) that
    directly maps to the minimum and maximum values we setup.  

    '''
    fan = setupFan( FAN_PWM_GPIO )
    cpuTemp = setupTemperatureObject()

    try:
        count = 0
        while True:
            if (count % 720) == 0:
                logg.debug( f"cpu {cpuTemp.temperature} fan: {fan.value:0.2} cpu.value {cpuTemp.value:0.2}" )
    
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
        
def turnOffFan():
    '''
    Attempt to turn off the fan, this is normally called from a service shutdown, so
    the code is operating in a different context, and different process.
    
    '''
    try:
        fan = setupFan( FAN_PWM_GPIO )
        fan.value = 0
    except Exception as error:
        log.error( f"Could not turn off fan, Error: {error}" )
        
def usage():
    print( "piStord - Fan Service for the piStor data server.\n" )
    print( "usage: pystord <options>" )
    print( "    SHUTDOWN    - Shutdown the piStor fan... issued when the user shutdown the service." )
    print( "    SERVICE     - Launch the pistord Daemon so we can control the fan." )
    print( "    VERSION     - Report the version of the piStor Daemon." )
    print( "    DEBUG       - Launches the fan control without spawning a thread." )

if len(sys.argv) > 1:
    cmd = sys.argv[1].upper()
    match cmd:
        case "SHUTDOWN":
            log.info( "piStor Fan Service stopping..." )
            turnOffFan()
        
        case "SERVICE":
            try:
                log.info( f"piStor Fan Service starting... Version {PYSTOR_VERSION}." )
                thread1 = Thread(target = controlFan )
                thread1.start()
            except Exception as error:
                log.info( f"Could not start sercice threads, Error {error}" )

        case "VERSION":
            print( f"Version: {PYSTOR_VERSION}" )
        case "DEBUG":
            log.forceConsole()
            controlFan()
        case _:
            usage()
else:
    usage()
