'''
Configuration reader for the piStor fan control daemon.

Wraps Python's configparser to load and expose settings from
/etc/pistor.conf (or an alternate path). See piStorConfig for details.
'''
import os
import configparser

AUTO_FAN = 1
MANUAL_FAN = 0

class piStorConfig():
    def __init__( self, filename : str ="" ):
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
    
    def loadConfig( self, filename : str ):
        '''
        Load the configuration file into memory.

        Parameters:
            filename - Path to the .conf file to read.

        Raises:
            FileNotFoundError - if the file does not exist (caught internally
                                and printed; the config object remains empty).
        '''
        try:
            if os.path.isfile( filename ):
                self.configObj.read( filename )
                self.filename = filename
            else:
                raise FileNotFoundError( f"Configuration file {filename} does not exist." )
        except Exception as error:
            print( f"Error: {error}" )
            
    def __iter__( self ):
        '''
        Make this configuration object iterable.  Iterations occur on the
        sections of the configuration file
        '''
        self.index = 0
        self.sections = self.configObj.sections()
        return self
    
    def __next__( self ) -> str:
        '''
        This routine returns the next item in the sections list, or a
        stop iteration exception if we have no more sections.
        
        Returns:
            the name of the next section
        '''
        if self.index < len(self.sections ):
            index = self.index
            self.index += 1
            return self.sections[index]
        else:
            raise StopIteration()
        
    def getFanSpeed( self ) -> list[tuple[int,int]]:
        '''
        This member function returns a list of tuples.  The first paramter is
        the CPU temperature, the second parameter of the tuple is the fan speed.
        
        If there is no FanSpeeds section in the configuration file, a default
        value is returned, which essentially sets the fan speed to 100%
        
        Returns:
            A list of tuples used for controlling the fan speed...
        '''
        speeds = []
        try:
            for item in self.configObj['FanSpeeds']:
                temp = int(item)
                speed = int(self.configObj['FanSpeeds'][item])
                speeds.append( (temp,speed) )
        except Exception as error:
            print( f"Error: No section in configuration file named {error}" )
            speeds = [(20,0),(30,100)]

        return speeds
    
    def getMode( self ) -> int:
        '''
        This function obtains the fan mode from the configuration file.  If there
        is any issue obtaining the fan mode, automatic mode is selected.
        
        Mode Values:
            0 - Manual mode.  Utilize the fanspeed list to determine the fan
                speed based on the CPU temperature.
            1 - Automatic mode.  Modify the fan speed based on CPU temperature,
                no table is selected.
                
        Automatic mode is usually better, however if the system is running in a
        high temperature area, or there are additional factors not realted to CPU
        temperature, manual mode can be used to intensify, or decrease the overall
        fan speed.
        
        Returns:
            An integer representing the mode we are in.
        '''
        mode = 1
        try:
            mode = self.configObj.getint('mode','autofan')
        except Exception as error:
            print( f"Error: Could not locate key {error}" )
        return mode
        

import unittest
import tempfile

class TestPiStorConfig(unittest.TestCase):

    # ------------------------------------------------------------------ helpers

    def _make_conf(self, content):
        '''Write content to a temp file and return its path.'''
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(content)
        f.close()
        return f.name

    def _remove(self, path):
        if os.path.exists(path):
            os.unlink(path)

    # ------------------------------------------------------------------ __init__

    def test_init_empty_filename_skips_load(self):
        '''Empty filename should not call loadConfig; config stays empty.'''
        config = piStorConfig()
        self.assertEqual(config.filename, "")
        self.assertEqual(config.configObj.sections(), [])

    def test_init_valid_file_loads_config(self):
        '''A valid file path passed to __init__ should be loaded automatically.'''
        path = self._make_conf("[mode]\nautofan = 1\n")
        try:
            config = piStorConfig(path)
            self.assertEqual(config.filename, path)
            self.assertIn('mode', config.configObj.sections())
        finally:
            self._remove(path)

    def test_init_missing_file_does_not_raise(self):
        '''A missing file path should be handled silently; config stays empty.'''
        config = piStorConfig('/nonexistent/path/pistor.conf')
        self.assertEqual(config.configObj.sections(), [])

    # ------------------------------------------------------------------ loadConfig

    def test_loadconfig_missing_file_leaves_config_empty(self):
        '''loadConfig with a non-existent path leaves configObj unchanged.'''
        config = piStorConfig()
        config.loadConfig('/nonexistent/path.conf')
        self.assertEqual(config.configObj.sections(), [])

    def test_loadconfig_updates_filename_on_success(self):
        '''loadConfig should update self.filename when the file is read.'''
        path = self._make_conf("[mode]\nautofan = 0\n")
        try:
            config = piStorConfig()
            config.loadConfig(path)
            self.assertEqual(config.filename, path)
        finally:
            self._remove(path)

    def test_loadconfig_empty_string_treated_as_missing(self):
        '''loadConfig("") should not load anything; os.path.isfile("") is False.'''
        config = piStorConfig()
        config.loadConfig("")
        self.assertEqual(config.configObj.sections(), [])

    def test_loadconfig_can_reload_different_file(self):
        '''Calling loadConfig a second time on a new file replaces the config.'''
        path1 = self._make_conf("[mode]\nautofan = 1\n")
        path2 = self._make_conf("[mode]\nautofan = 0\n")
        try:
            config = piStorConfig(path1)
            self.assertEqual(config.getMode(), AUTO_FAN)
            config.loadConfig(path2)
            self.assertEqual(config.getMode(), MANUAL_FAN)
        finally:
            self._remove(path1)
            self._remove(path2)

    # ------------------------------------------------------------------ getMode

    def test_getmode_returns_auto_fan(self):
        '''autofan = 1 should return AUTO_FAN.'''
        path = self._make_conf("[mode]\nautofan = 1\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), AUTO_FAN)
        finally:
            self._remove(path)

    def test_getmode_returns_manual_fan(self):
        '''autofan = 0 should return MANUAL_FAN.'''
        path = self._make_conf("[mode]\nautofan = 0\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), MANUAL_FAN)
        finally:
            self._remove(path)

    def test_getmode_no_section_defaults_to_auto(self):
        '''Missing [mode] section should default to AUTO_FAN.'''
        self.assertEqual(piStorConfig().getMode(), AUTO_FAN)

    def test_getmode_missing_key_defaults_to_auto(self):
        '''[mode] section with no autofan key should default to AUTO_FAN.'''
        path = self._make_conf("[mode]\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), AUTO_FAN)
        finally:
            self._remove(path)

    def test_getmode_non_integer_value_defaults_to_auto(self):
        '''Non-integer autofan value should be caught and default to AUTO_FAN.'''
        path = self._make_conf("[mode]\nautofan = abc\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), AUTO_FAN)
        finally:
            self._remove(path)

    def test_getmode_unknown_integer_returned_as_is(self):
        '''An integer autofan value other than 0 or 1 is returned without validation.'''
        path = self._make_conf("[mode]\nautofan = 99\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), 99)
        finally:
            self._remove(path)

    def test_getmode_negative_value_returned_as_is(self):
        '''A negative autofan integer is returned without validation.'''
        path = self._make_conf("[mode]\nautofan = -1\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), -1)
        finally:
            self._remove(path)

    # ------------------------------------------------------------------ getFanSpeed

    def test_getfanspeed_normal_table(self):
        '''Standard [FanSpeeds] section should return the correct list of tuples.'''
        path = self._make_conf("[FanSpeeds]\n20 = 0\n30 = 20\n50 = 100\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(20, 0), (30, 20), (50, 100)])
        finally:
            self._remove(path)

    def test_getfanspeed_no_section_returns_hardcoded_default(self):
        '''Missing [FanSpeeds] section should return the hardcoded default list.'''
        speeds = piStorConfig().getFanSpeed()
        self.assertEqual(speeds, [(20, 0), (30, 100)])

    def test_getfanspeed_empty_section_returns_empty_list(self):
        '''[FanSpeeds] section that exists but has no entries returns [], not the default.'''
        path = self._make_conf("[FanSpeeds]\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [])
        finally:
            self._remove(path)

    def test_getfanspeed_single_entry(self):
        '''A single-entry table should be returned as a one-element list.'''
        path = self._make_conf("[FanSpeeds]\n70 = 100\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(70, 100)])
        finally:
            self._remove(path)

    def test_getfanspeed_zero_speed_boundary(self):
        '''Fan speed of 0 (fan off) should be parsed as integer zero, not omitted.'''
        path = self._make_conf("[FanSpeeds]\n20 = 0\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(20, 0)])
        finally:
            self._remove(path)

    def test_getfanspeed_max_speed_boundary(self):
        '''Fan speed of 100 should be parsed as integer 100.'''
        path = self._make_conf("[FanSpeeds]\n70 = 100\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds[0][1], 100)
        finally:
            self._remove(path)

    def test_getfanspeed_values_are_ints(self):
        '''All returned tuple elements should be Python ints, not strings.'''
        path = self._make_conf("[FanSpeeds]\n30 = 20\n50 = 75\n")
        try:
            for temp, speed in piStorConfig(path).getFanSpeed():
                self.assertIsInstance(temp,  int)
                self.assertIsInstance(speed, int)
        finally:
            self._remove(path)

    def test_getfanspeed_non_integer_key_returns_default(self):
        '''A non-integer temperature key should trigger the except branch and return the default.'''
        path = self._make_conf("[FanSpeeds]\nabc = 50\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(20, 0), (30, 100)])
        finally:
            self._remove(path)

    def test_getfanspeed_non_integer_value_returns_default(self):
        '''A non-integer fan speed value should trigger the except branch and return the default.'''
        path = self._make_conf("[FanSpeeds]\n30 = fast\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(20, 0), (30, 100)])
        finally:
            self._remove(path)

    def test_getfanspeed_preserves_order(self):
        '''Entries should be returned in the order they appear in the file.'''
        path = self._make_conf("[FanSpeeds]\n50 = 50\n30 = 20\n70 = 100\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            temps = [t for t, _ in speeds]
            self.assertEqual(temps, [50, 30, 70])
        finally:
            self._remove(path)

    # ------------------------------------------------------------------ iteration

    def test_iteration_yields_section_names(self):
        '''Iterating the config should yield the names of all sections.'''
        path = self._make_conf("[mode]\nautofan = 1\n[FanSpeeds]\n30 = 20\n")
        try:
            sections = list(piStorConfig(path))
            self.assertIn('mode',      sections)
            self.assertIn('FanSpeeds', sections)
        finally:
            self._remove(path)

    def test_iteration_empty_config_yields_nothing(self):
        '''Iterating an empty config should produce an empty sequence.'''
        self.assertEqual(list(piStorConfig()), [])

    def test_iteration_is_repeatable(self):
        '''Iterating the same config object twice should yield the same results.'''
        path = self._make_conf("[mode]\nautofan = 1\n")
        try:
            config = piStorConfig(path)
            self.assertEqual(list(config), list(config))
        finally:
            self._remove(path)

    def test_iteration_single_section(self):
        '''A config with one section should yield exactly that section.'''
        path = self._make_conf("[mode]\nautofan = 1\n")
        try:
            sections = list(piStorConfig(path))
            self.assertEqual(sections, ['mode'])
        finally:
            self._remove(path)


if __name__ == "__main__":
    unittest.main()
