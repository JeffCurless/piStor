#!/usr/bin/python3
# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
piStor fan control daemon for Raspberry Pi 5.

Reads CPU temperature via gpiozero and adjusts a PWM fan connected to:
  - Fan PWM: GPIO 13 (Pin 33) by default
  - Fan tachometer: GPIO 18 (Pin 12) by default (not currently read)
Both GPIOs can be changed in the [gpio] section of /etc/pistor.conf.

The control mode comes from /etc/pistor.conf (automatic if the file is
missing) and messages are logged to /var/log/piStord.log.

CLI arguments:
  SERVICE   - Run the fan control daemon (in the foreground, under systemd).
  SHUTDOWN  - Set the fan speed to zero and exit.  Run by systemd
              (ExecStopPost) after the service stops.
  VERSION   - Print the daemon version number.
  DEBUG     - Run fan control in the foreground, logging to console.

SIGTERM, SIGINT and SIGHUP stop fan control and turn the fan off.  The fan
PWM line is left driven low when the process exits (see releaseFanLow), because
4-pin fans pull an undriven (input) PWM line high, which runs them at 100%.

Requires the gpiozero library (sudo pip3 install gpiozero).
'''
#
# Setup environment and pull in all of the items we need from gpiozero.  The
# gpiozero library is the new one that supports Raspberry PI 5's (and I suspect
# will be new direction for all prior version the RPIi.)
#

import glob
import os
import re
import signal
import sys
import time
from collections.abc import Callable

from gpiozero import CPUTemperature, PWMOutputDevice

from configtool import (AUTO_FAN, DEFAULT_FAN_PWM_GPIO, DEFAULT_FAN_TACH_GPIO,
                        MANUAL_FAN, piStorConfig)
from logger import Logger

#
# Some helpful constants
#

PYSTOR_VERSION = "1.1.3"  # Service version, "Major.Minor.Edit".  Change it with
                        # ./build_deb.sh --bump so debian/changelog matches.
MIN_TEMP       = 10     # Minimum temp we care about (for CPU Temperature object)
MAX_TEMP       = 80     # Maximum temp we can let the CPU get to
FAN_PWM_GPIO   = DEFAULT_FAN_PWM_GPIO   # Default fan PWM GPIO 13 (Pin 33); see [gpio] fanpwm
FAN_TACK_GPIO  = DEFAULT_FAN_TACH_GPIO  # Default fan TAC GPIO 18 (Pin 12); see [gpio] fantach

UPDATE_PERIOD  = 5      # Number of seconds between checking the temperature and
                        # modifing the fan speed
LOG_INTERVAL   = 720    # Loop iterations between status log lines (1 hour)

#
# Labels of the gpiochip that drives the 40-pin header, newest Pi first.  The
# chip's number varies by kernel (Pi 5 is usually gpiochip0, but some kernels
# number it gpiochip15), so it is located by label rather than number.
#
HEADER_CHIP_LABELS = ( 'pinctrl-rp1',      # Raspberry Pi 5 / CM5
                       'pinctrl-bcm2711',  # Raspberry Pi 4 / CM4
                       'pinctrl-bcm2835' ) # Raspberry Pi 3 and earlier
GPIOCHIP_GLOB = '/dev/gpiochip*'

CONFIG_PATH = '/etc/pistor.conf'
LOG_PATH    = '/var/log/piStord.log'

#
# Console logger by default so importing this module has no side effects; the
# main entry point replaces it with a file logger.
#
log = Logger(None)

SHUTDOWN_SIGNALS = ( signal.SIGTERM, signal.SIGINT, signal.SIGHUP )

class ShutdownRequested( BaseException ):
    '''
    Raised by the signal handler to stop the fan control loop.  Derives from
    BaseException so the loop's "except Exception" error handling cannot
    swallow it.
    '''

def onShutdownSignal( signum: int, _frame: object ) -> None:
    '''
    Signal handler for SHUTDOWN_SIGNALS: raise ShutdownRequested.

    Parameters:
        signum - The signal number received.
        _frame - The interrupted stack frame (unused).
    '''
    raise ShutdownRequested( signal.Signals( signum ).name )

def installSignalHandlers() -> None:
    '''
    Make SHUTDOWN_SIGNALS stop fan control (raise ShutdownRequested) instead
    of killing the process without cleanup.  Must be called from the main
    thread.
    '''
    for sig in SHUTDOWN_SIGNALS:
        signal.signal( sig, onShutdownSignal )

def findHeaderGPIOChip() -> tuple[int, str] | None:
    '''
    Find the gpiochip that drives the 40-pin GPIO header.

    Opens each /dev/gpiochipN device with lgpio and returns the first whose
    label is in HEADER_CHIP_LABELS (checked in that order).  Symlinks such as
    /dev/gpiochip4 -> gpiochip0 are skipped so each chip is only opened once.

    Returns:
        A (chip number, label) tuple, or None if lgpio is not installed or no
        header chip is found.
    '''
    try:
        import lgpio  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None

    found: dict[str, int] = {}
    for path in sorted( glob.glob( GPIOCHIP_GLOB ) ):
        match = re.search( r'gpiochip(\d+)$', path )
        if match is None or os.path.islink( path ):
            continue
        chip = int( match.group( 1 ) )
        try:
            handle = lgpio.gpiochip_open( chip )
            try:
                label = lgpio.gpio_get_chip_info( handle )[3]
            finally:
                lgpio.gpiochip_close( handle )
        except Exception:  # pylint: disable=broad-exception-caught
            continue    # Not openable (e.g. permissions); try the next chip
        found.setdefault( label, chip )

    for label in HEADER_CHIP_LABELS:
        if label in found:
            return ( found[label], label )
    return None

def makeLGPIOFactory( chip: int ) -> object:
    '''
    Create a gpiozero LGPIOFactory that uses the given gpiochip.

    gpiozero 2.0.1's LGPIOFactory ignores its chip argument and always opens
    gpiochip4 or gpiochip0, so this subclass opens the requested chip itself.

    Parameters:
        chip - The /dev/gpiochipN number to open.

    Returns:
        An LGPIOFactory instance bound to that chip.

    Raises:
        lgpio.error (or ImportError) if the chip cannot be opened.
    '''
    # pylint: disable=import-outside-toplevel
    import lgpio
    from gpiozero.pins.lgpio import LGPIOFactory, LGPIOPin

    class ChipLGPIOFactory( LGPIOFactory ):  # pylint: disable=too-few-public-methods
        '''LGPIOFactory bound to a specific gpiochip.'''
        def __init__( self, chipNumber: int ) -> None:  # pylint: disable=super-init-not-called
            # Skip LGPIOFactory.__init__ (it picks its own chip) and run the
            # base pin factory setup, then open the requested chip.
            super( LGPIOFactory, self ).__init__()  # pylint: disable=bad-super-call
            self._handle   = lgpio.gpiochip_open( chipNumber )
            self._chip     = chipNumber
            self.pin_class = LGPIOPin

    return ChipLGPIOFactory( chip )

def getPinFactory() -> object | None:
    '''
    Return a gpiozero lgpio pin factory bound to the GPIO header's gpiochip.

    gpiozero picks the gpiochip by number (4 or 0 on a Pi 5), which fails on
    kernels that number the header chip differently ("can not open
    gpiochip").  This locates the chip by label instead (findHeaderGPIOChip).

    Returns:
        An LGPIOFactory for the header chip, or None to let gpiozero choose
        its default pin factory (the reason is logged).
    '''
    header = findHeaderGPIOChip()
    if header is None:
        log.warning( "Could not find the GPIO header gpiochip, using gpiozero's default." )
        return None
    chip, label = header
    try:
        factory = makeLGPIOFactory( chip )
    except Exception as error:  # pylint: disable=broad-exception-caught
        log.warning( f"Could not open /dev/gpiochip{chip} ({label}), using gpiozero's "
                     f"default. Error: {error}" )
        return None
    log.info( f"Using /dev/gpiochip{chip} ({label}) for the GPIO header." )
    return factory

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
        factory = getPinFactory()
        if factory is None:
            fan = PWMOutputDevice( fanPWMGPIO, frequency=100 )
        else:
            fan = PWMOutputDevice( fanPWMGPIO, frequency=100, pin_factory=factory )
        fan.value = 0
    except Exception as error:  # pylint: disable=broad-exception-caught
        log.error( f"Error attempting to create output PWM device, error is {error}" )
        raise ValueError( "Cannot setup Fan!" ) from error

    return fan

def driveLineLow( gpio: int ) -> bool:
    '''
    Claim a header GPIO as an output driven low, then release it.

    Releasing a line through the kernel leaves it driving its last level, so
    the pin stays low after this process exits.  (gpiozero instead resets
    pins it closes to inputs.)

    Parameters:
        gpio - The BCM GPIO number.

    Returns:
        True if the line was driven low, False if lgpio or the header gpiochip
        is unavailable or the line could not be claimed (the reason is logged).
    '''
    header = findHeaderGPIOChip()
    if header is None:
        log.warning( f"Could not find the GPIO header gpiochip to drive GPIO {gpio} low." )
        return False
    chip, _ = header
    try:
        import lgpio  # pylint: disable=import-outside-toplevel
        handle = lgpio.gpiochip_open( chip )
        try:
            lgpio.gpio_claim_output( handle, gpio, 0 )
        finally:
            lgpio.gpiochip_close( handle )
    except Exception as error:  # pylint: disable=broad-exception-caught
        log.warning( f"Could not drive GPIO {gpio} low, Error: {error}" )
        return False
    return True

def releaseFanLow( fan: PWMOutputDevice, fanPWMGPIO: int ) -> bool:
    '''
    Turn the fan off and leave its PWM line driven low after this process
    exits.

    gpiozero resets the pins it closes (including at interpreter exit) to
    inputs with no pull.  4-pin fans pull an undriven PWM line high (an
    internal pull-up), which runs the fan at 100%, so after setting the speed to zero the
    gpiozero device and its pin factory are closed, and the line is then
    claimed as a low output and released (driveLineLow).  The fan may briefly
    see a high level between those two steps.

    Parameters:
        fan        - The fan's PWMOutputDevice (closed by this call).
        fanPWMGPIO - GPIO the fan PWM line is connected to.

    Returns:
        True if the PWM line was left driven low, False otherwise.
    '''
    fan.value = 0
    factory = getattr( fan, 'pin_factory', None )
    fan.close()
    if factory is not None:
        factory.close()     # Stops gpiozero resetting the pin again at exit
    return driveLineLow( fanPWMGPIO )

def newCPUTemperature( pinFactory: object | None = None ) -> CPUTemperature:
    '''
    Create a CPUTemperature object.

    Passing the fan's pin factory stops gpiozero from probing for a default
    one, which logs a PinFactoryFallback warning on kernels where its own
    gpiochip lookup fails.

    Parameters:
        pinFactory - gpiozero pin factory to use, or None for gpiozero's default.

    Returns:
        A CPUTemperature object.

    Raises:
        Any error raised by gpiozero while creating the object.
    '''
    if pinFactory is None:
        return CPUTemperature()
    return CPUTemperature( pin_factory=pinFactory )

def setupTemperatureObject( pinFactory: object | None = None ) -> CPUTemperature | None:
    '''
    Create and return a CPUTemperature object.

    Parameters:
        pinFactory - gpiozero pin factory to use, or None for gpiozero's default.

    Returns:
        A CPUTemperature object, or None if creation fails (the error is
        logged).
    '''
    try:
        return newCPUTemperature( pinFactory )
    except Exception as error:  # pylint: disable=broad-exception-caught
        log.error( f"Error creating CPU temperature object, error is {error}" )
        return None

def runFanLoop( computeSpeed: Callable[[CPUTemperature], float],
                fanPWMGPIO: int = FAN_PWM_GPIO ) -> None:
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

    The loop ends on ShutdownRequested (a shutdown signal) or
    KeyboardInterrupt: the fan is turned off with releaseFanLow() and the
    function returns.

    Parameters:
        computeSpeed - Function mapping a CPUTemperature object to a fan duty
                       cycle in the range 0.0-1.0.
        fanPWMGPIO   - GPIO the fan PWM line is connected to.
    '''
    try:
        fan = setupFan( fanPWMGPIO )
    except ValueError as error:
        log.error( f"Fan control not started: {error}" )
        return
    pinFactory = getattr( fan, 'pin_factory', None )
    cpuTemp = setupTemperatureObject( pinFactory )

    count = 0
    failing = False
    try:
        while True:
            try:
                if cpuTemp is None:
                    cpuTemp = newCPUTemperature( pinFactory )
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
    except ( ShutdownRequested, KeyboardInterrupt ) as reason:
        log.info( f"Fan control stopping ({reason or 'interrupted'}), turning the fan off." )
        try:
            releaseFanLow( fan, fanPWMGPIO )
        except Exception as error:  # pylint: disable=broad-exception-caught
            log.error( f"Could not turn off fan, Error: {error}" )

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

def controlFanAuto( fanPWMGPIO: int = FAN_PWM_GPIO ) -> None:
    '''
    Control the fan automatically based on CPU temperature (see autoFanSpeed).
    Runs forever unless the fan cannot be set up.

    Parameters:
        fanPWMGPIO - GPIO the fan PWM line is connected to.
    '''
    log.info( "Starting fan control service in automatic mode." )
    runFanLoop( autoFanSpeed, fanPWMGPIO )

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

def controlFanManual( cpufanSpeed: list[tuple[int, int]],
                      fanPWMGPIO: int = FAN_PWM_GPIO ) -> None:
    '''
    Control the fan from the manual speed table in the configuration file
    (see getFanSpeed).  Runs forever unless the fan cannot be set up.

    Parameters:
        cpufanSpeed - A list of tuples containing a CPU temp and the corresponding
                      fan speed.
        fanPWMGPIO  - GPIO the fan PWM line is connected to.
    '''
    log.info( f"Starting fan control service in manual mode using data: {cpufanSpeed}." )
    runFanLoop( lambda cpuTemp: getFanSpeed( cpuTemp.temperature, cpufanSpeed ),
                fanPWMGPIO )

def getGPIOConfig( config: piStorConfig | None = None ) -> tuple[int, int]:
    '''
    Return the (fan PWM GPIO, fan tachometer GPIO) pair from the [gpio]
    section of the configuration.

    Parameters:
        config - A loaded configuration.  If None, CONFIG_PATH is read; when
                 that file does not exist the defaults (13, 18) are returned.

    Returns:
        A (fanPWMGPIO, fanTachGPIO) tuple of BCM GPIO numbers.
    '''
    if config is None:
        if not os.path.isfile( CONFIG_PATH ):
            return ( FAN_PWM_GPIO, FAN_TACK_GPIO )
        config = piStorConfig( CONFIG_PATH )
    return ( config.getFanPWMGPIO(), config.getFanTachGPIO() )

def startFanControl() -> None:
    '''
    Start the fan controller using the mode and GPIOs from /etc/pistor.conf.

    If the config file does not exist, logs a warning and starts in automatic
    mode with default settings (fan PWM on GPIO 13). Otherwise reads the
    config and dispatches to the appropriate control function, using the
    fan PWM GPIO from the [gpio] section:
      1 (AUTO_FAN)   - calls controlFanAuto()
      0 (MANUAL_FAN) - calls controlFanManual() with the configured speed table
      other          - logs an error and falls back to controlFanAuto()
    '''
    if not os.path.isfile( CONFIG_PATH ):
        log.warning( f"Config file {CONFIG_PATH} not found, starting with defaults (auto mode)." )
        log.info( f"Fan PWM on GPIO {FAN_PWM_GPIO}, tachometer on GPIO {FAN_TACK_GPIO}." )
        controlFanAuto( FAN_PWM_GPIO )
        return

    config = piStorConfig( CONFIG_PATH )
    fanPWMGPIO, fanTachGPIO = getGPIOConfig( config )
    log.info( f"Fan PWM on GPIO {fanPWMGPIO}, tachometer on GPIO {fanTachGPIO}." )
    mode = config.getMode()
    if mode == AUTO_FAN:
        controlFanAuto( fanPWMGPIO )
    elif mode == MANUAL_FAN:
        controlFanManual( config.getFanSpeed(), fanPWMGPIO )
    else:
        log.error( f"Unknown fan mode of {mode}, reverting to automatic." )
        controlFanAuto( fanPWMGPIO )

def turnOffFan() -> None:
    '''
    Set the fan speed to zero. Called when the SHUTDOWN CLI argument is used.
    Uses the fan PWM GPIO from /etc/pistor.conf, so it stops the same fan the
    service drives, and leaves the PWM line driven low after exit
    (releaseFanLow).

    Any GPIO errors are logged but not raised.
    '''
    try:
        fanPWMGPIO, _ = getGPIOConfig()
        fan = setupFan( fanPWMGPIO )
        releaseFanLow( fan, fanPWMGPIO )
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
    print( "    DEBUG       - Launches the fan control, logging to the console." )

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
                # Runs in the main thread: Python only delivers signals there,
                # and the signal handlers are what turn the fan off on stop.
                log.info( f"piStor Fan Service starting... Version {PYSTOR_VERSION}." )
                installSignalHandlers()
                startFanControl()

            case "VERSION":
                print( f"Version: {PYSTOR_VERSION}" )
            case "DEBUG":
                log.forceConsole()
                installSignalHandlers()
                startFanControl()
            case _:
                usage()
    else:
        usage()
