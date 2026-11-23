#!/usr/bin/python3
# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
piStor fan control daemon for Raspberry Pi 5.

Reads CPU temperature via gpiozero and adjusts a PWM fan connected to:
  - Fan PWM: GPIO 13 (Pin 33)
  - Fan tachometer: GPIO 18 (not currently read)

The control mode comes from /etc/pistor.conf (automatic if the file is
missing) and messages are logged to /var/log/piStord.log.

CLI arguments:
  SERVICE   - Start the fan control daemon in a background thread.
  SHUTDOWN  - Set the fan speed to zero and exit.  Run by systemd
              (ExecStopPost) after the service stops.
  VERSION   - Print the daemon version number.
  DEBUG     - Run fan control in the foreground, logging to console.

Requires the gpiozero library (sudo pip3 install gpiozero).
'''
#
# Setup environment and pull in all of the items we need from gpiozero.  The
# gpiozero library is the new one that supports Raspberry PI 5's (and I suspect
# will be new direction for all prior version the RPIi.)
#

import os
import sys
import time
from collections.abc import Callable
from threading import Thread

from gpiozero import CPUTemperature, PWMOutputDevice

from configtool import AUTO_FAN, MANUAL_FAN, piStorConfig
from logger import Logger

#
# Some helpful constants
#

PYSTOR_VERSION = 1.0    # Version of this service
MIN_TEMP       = 10     # Minimum temp we care about (for CPU Temperature object)
MAX_TEMP       = 80     # Maximum temp we can let the CPU get to
FAN_PWM_GPIO   = 13     # Fan PWM line is connected to GPIO 13 (Pin 33)
FAN_TACK_GPIO  = 18     # Fan TAC line is connected to GPIO 18

UPDATE_PERIOD  = 5      # Number of seconds between checking the temperature and
                        # modifing the fan speed
LOG_INTERVAL   = 720    # Loop iterations between status log lines (1 hour)

CONFIG_PATH = '/etc/pistor.conf'
LOG_PATH    = '/var/log/piStord.log'

#
# Console logger by default so importing this module has no side effects; the
# main entry point replaces it with a file logger.
#
log = Logger(None)

def setupFan(fanPWMGPIO: int) -> PWMOutputDevice:
    '''
    This routine creates an object that we can utilize to communicate with the
    fan specified by the fanPWMGPIO parameter passed in.

    Parameters:
        fanPWMGPIO - The GPIO pin that the FAN PWM pin is connected to

    Returns:
        A fan object, with speed set to zero

    Raises:
        ValueError - if the PWM device cannot be created.
    '''
    try:
        fan = PWMOutputDevice( fanPWMGPIO, frequency=100)
        fan.value = 0
    except Exception as error:  # pylint: disable=broad-exception-caught
        log.error( f"Error attempting to create output PWM device, error is {error}" )
        raise ValueError( "Cannot setup Fan!" ) from error

    return fan

def setupTemperatureObject() -> CPUTemperature | None:
    '''
    Create and return a default CPUTemperature object.

    Returns:
        A CPUTemperature object, or None if creation fails (the error is
        logged).
    '''
    try:
        return CPUTemperature()
    except Exception as error:  # pylint: disable=broad-exception-caught
        log.error( f"Error creating CPU temperature object, error is {error}" )
        return None

def runFanLoop( computeSpeed: Callable[[CPUTemperature], float] ) -> None:
    '''
    Run the fan control loop forever, waking every UPDATE_PERIOD seconds.

    On each iteration the fan duty cycle is set to computeSpeed(cpuTemp).
    Every LOG_INTERVAL iterations a debug line is logged (plus a warning if the
    fan is at 100%).

    Failure handling: if the temperature sensor is unavailable or any error
    occurs while computing/applying the speed, the fan is driven to 100% and
    the loop keeps retrying. The error is logged once per failure episode, and
    recovery is logged when it clears.  If the fan PWM device itself cannot be
    created, the error is logged and the loop is not started.

    Parameters:
        computeSpeed - Function mapping a CPUTemperature object to a fan duty
                       cycle in the range 0.0-1.0.
    '''
    try:
        fan = setupFan( FAN_PWM_GPIO )
    except ValueError as error:
        log.error( f"Fan control not started: {error}" )
        return
    cpuTemp = setupTemperatureObject()

    count = 0
    failing = False
    while True:
        try:
            if cpuTemp is None:
                cpuTemp = CPUTemperature()
            if (count % LOG_INTERVAL) == 0:
                if fan.value >= 1.0:
                    log.warning( f"Temperature at {cpuTemp.temperature} fan running at 100%." )
                log.debug( f"CPU {cpuTemp.temperature} fan: {fan.value:.2f} "
                           f"cpu.value {cpuTemp.value:.2f}" )
            fan.value = computeSpeed( cpuTemp )
            if failing:
                log.info( "Fan speed processing recovered." )
                failing = False
        except Exception as error:  # pylint: disable=broad-exception-caught
            fan.value = 1.0
            if not failing:
                log.error( f"An error occurred during fan speed processing, running fan "
                           f"at 100%. Error is {error}" )
                failing = True
        time.sleep( UPDATE_PERIOD )
        count += 1

def autoFanSpeed( cpuTemp: CPUTemperature ) -> float:
    '''
    Return the automatic-mode duty cycle: cpuTemp.value + 0.1, clamped to 1.0.

    cpuTemp.value is the CPU temperature scaled to 0.0-1.0 across the
    CPUTemperature object's min/max range (0-100C by default).

    Parameters:
        cpuTemp - The CPUTemperature object to read.

    Returns:
        Fan duty cycle in the range 0.1-1.0.
    '''
    return min( float(cpuTemp.value) + 0.1, 1.0 )

def controlFanAuto() -> None:
    '''
    Control the fan automatically based on CPU temperature (see autoFanSpeed).
    Runs forever unless the fan cannot be set up.
    '''
    log.info( "Starting fan control service in automatic mode." )
    runFanLoop( autoFanSpeed )

def getFanSpeed( temp: float, speedList: list[tuple[int, int]] ) -> float:
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

def controlFanManual( cpufanSpeed: list[tuple[int, int]] ) -> None:
    '''
    Control the fan from the manual speed table in the configuration file
    (see getFanSpeed).  Runs forever unless the fan cannot be set up.

    Parameters:
        cpufanSpeed - A list of tuples containing a CPU temp and the corresponding
                      fan speed.
    '''
    log.info( f"Starting fan control service in manual mode using data: {cpufanSpeed}." )
    runFanLoop( lambda cpuTemp: getFanSpeed( cpuTemp.temperature, cpufanSpeed ) )

def startFanControl() -> None:
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
    if mode == AUTO_FAN:
        controlFanAuto()
    elif mode == MANUAL_FAN:
        controlFanManual( config.getFanSpeed() )
    else:
        log.error( f"Unknown fan mode of {mode}, reverting to automatic." )
        controlFanAuto()

def turnOffFan() -> None:
    '''
    Set the fan speed to zero. Called when the SHUTDOWN CLI argument is used.

    Any GPIO errors are logged but not raised.
    '''
    try:
        fan = setupFan( FAN_PWM_GPIO )
        fan.value = 0
    except Exception as error:  # pylint: disable=broad-exception-caught
        log.error( f"Could not turn off fan, Error: {error}" )

def usage() -> None:
    '''
    Print the usage of this service, if anyone runs it locally.
    '''
    print( "piStord - Fan Service for the piStor data server.\n" )
    print( "usage: pystord <options>" )
    print( "    SHUTDOWN    - Shutdown the piStor fan... issued when the user shutdown "
           "the service." )
    print( "    SERVICE     - Launch the pistord Daemon so we can control the fan." )
    print( "    VERSION     - Report the version of the piStor Daemon." )
    print( "    DEBUG       - Launches the fan control without spawning a thread." )

#
# Main entry point
#

if __name__ == "__main__":
    log = Logger( LOG_PATH )
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
                except Exception as error:  # pylint: disable=broad-exception-caught
                    log.error( f"Could not start service threads, Error {error}" )

            case "VERSION":
                print( f"Version: {PYSTOR_VERSION}" )
            case "DEBUG":
                log.forceConsole()
                startFanControl()
            case _:
                usage()
    else:
        usage()
