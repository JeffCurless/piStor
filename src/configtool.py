# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Configuration reader for the piStor fan control daemon.

Wraps Python's configparser to load and expose settings from
/etc/pistor.conf (or an alternate path). See piStorConfig for details.
'''
import configparser
import os
from collections.abc import Iterator

AUTO_FAN = 1
MANUAL_FAN = 0

DEFAULT_FAN_PWM_GPIO  = 13  # Fan PWM line, GPIO 13 (Pin 33)
DEFAULT_FAN_TACH_GPIO = 18  # Fan tachometer line, GPIO 18 (Pin 12)
MIN_GPIO = 0                # Lowest BCM GPIO number on the 40-pin header
MAX_GPIO = 27               # Highest BCM GPIO number on the 40-pin header

class piStorConfig():  # pylint: disable=invalid-name
    '''
    Reader for the piStor configuration file (see module docstring).
    '''
    def __init__( self, filename : str ="" ) -> None:
        '''
        Initialize the configuration object.

        Parameters:
            filename - Path to the config file. If non-empty, loadConfig() is
                       called automatically during initialization.
        '''
        self.filename  = filename
        self.configObj = configparser.ConfigParser()
        if filename != "":
            self.loadConfig( filename )

    def loadConfig( self, filename : str ) -> None:
        '''
        Load the configuration file into memory.

        Calling this again with another file merges that file into the current
        configuration: values in the new file override existing ones, and
        sections or keys only present in the earlier file are kept.

        Parameters:
            filename - Path to the .conf file to read.

        Errors:
            If the file does not exist, an error is printed and the
            configuration is left unchanged.  No exception is raised.
        '''
        try:
            if os.path.isfile( filename ):
                self.configObj.read( filename )
                self.filename = filename
            else:
                raise FileNotFoundError( f"Configuration file {filename} does not exist." )
        except Exception as error:  # pylint: disable=broad-exception-caught
            print( f"Error: {error}" )

    def __iter__( self ) -> Iterator[str]:
        '''
        Make this configuration object iterable.  Iterations occur on the
        sections of the configuration file.  Each call returns an independent
        iterator, so nested or concurrent loops do not interfere.
        '''
        return iter( self.configObj.sections() )

    def getFanSpeed( self ) -> list[tuple[int,int]]:
        '''
        Return the manual-mode fan speed table from the [FanSpeeds] section.

        Each entry is a (cpu_temp, fan_speed_pct) tuple of ints, in the order
        they appear in the file.

        If the [FanSpeeds] section is missing, or any key or value is not an
        integer, an error is printed and the default table [(20,0),(30,100)]
        is returned: fan off below 30C, full speed at 30C and above.  An
        existing but empty [FanSpeeds] section returns an empty list.

        Returns:
            A list of (cpu_temp, fan_speed_pct) tuples.
        '''
        speeds: list[tuple[int, int]] = []
        try:
            for item in self.configObj['FanSpeeds']:
                temp = int(item)
                speed = int(self.configObj['FanSpeeds'][item])
                speeds.append( (temp,speed) )
        except KeyError as error:
            print( f"Error: No section in configuration file named {error}" )
            speeds = [(20,0),(30,100)]
        except Exception as error:  # pylint: disable=broad-exception-caught
            print( f"Error: Invalid [FanSpeeds] entry, using defaults: {error}" )
            speeds = [(20,0),(30,100)]

        return speeds

    def getMode( self ) -> int:
        '''
        Return the fan mode from the autofan key of the [mode] section.  If the
        section or key is missing, or the value is not an integer, an error is
        printed and automatic mode (1) is returned.  Other integer values are
        returned unchanged, without validation.

        Mode Values:
            0 - Manual mode.  Utilize the fanspeed list to determine the fan
                speed based on the CPU temperature.
            1 - Automatic mode.  Modify the fan speed based on CPU temperature,
                no table is selected.

        Automatic mode is usually better, however if the system is running in a
        high temperature area, or there are additional factors not related to CPU
        temperature, manual mode can be used to intensify, or decrease the overall
        fan speed.

        Returns:
            The fan mode as an integer (AUTO_FAN = 1, MANUAL_FAN = 0).
        '''
        mode = 1
        try:
            mode = self.configObj.getint('mode','autofan')
        except Exception as error:  # pylint: disable=broad-exception-caught
            print( f"Error: Could not locate key {error}" )
        return mode

    def _getGPIO( self, key: str, default: int ) -> int:
        '''
        Return a BCM GPIO number from the [gpio] section.

        If the section or key is missing, the default is returned silently.
        If the value is not an integer, or is outside the header's GPIO range
        (MIN_GPIO-MAX_GPIO), an error is printed and the default is returned.

        Parameters:
            key     - Option name in the [gpio] section.
            default - GPIO number to use when the option is missing or invalid.

        Returns:
            The GPIO number as an integer.
        '''
        if not self.configObj.has_option( 'gpio', key ):
            return default
        try:
            gpio = self.configObj.getint( 'gpio', key )
        except ValueError as error:
            print( f"Error: Invalid [gpio] {key} value, using GPIO {default}: {error}" )
            return default
        if not MIN_GPIO <= gpio <= MAX_GPIO:
            print( f"Error: [gpio] {key} = {gpio} is outside GPIO {MIN_GPIO}-{MAX_GPIO}, "
                   f"using GPIO {default}" )
            return default
        return gpio

    def getFanPWMGPIO( self ) -> int:
        '''
        Return the GPIO the fan PWM (speed control) line is connected to, from
        the fanpwm key of the [gpio] section.  Defaults to GPIO 13 (Pin 33)
        when missing or invalid.

        Returns:
            The BCM GPIO number as an integer.
        '''
        return self._getGPIO( 'fanpwm', DEFAULT_FAN_PWM_GPIO )

    def getFanTachGPIO( self ) -> int:
        '''
        Return the GPIO the fan tachometer line is connected to, from the
        fantach key of the [gpio] section.  Defaults to GPIO 18 (Pin 12) when
        missing or invalid.

        Returns:
            The BCM GPIO number as an integer.
        '''
        return self._getGPIO( 'fantach', DEFAULT_FAN_TACH_GPIO )
