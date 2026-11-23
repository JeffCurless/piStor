# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Tests for the stand-alone scripts in fantest/:

  fantest.py - simulated threshold fan control run against fansimulator.
  test.py    - hardware fan sweep with tachometer RPM readout.

Both scripts do their work at import time, so they are executed with runpy.
test.py's hardware (RPi.GPIO and gpiozero) is replaced with mocks, and
time.sleep is patched so nothing actually waits.
'''
import io
import os
import runpy
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import fansimulator
from fansimulator import BoardSimulator
from tests import FANTEST

FANTEST_SCRIPT  = os.path.join( FANTEST, 'fantest.py' )
HARDWARE_SCRIPT = os.path.join( FANTEST, 'test.py' )


# ---------------------------------------------------------------------- fantest.py

class TestFantestScript( unittest.TestCase ):
    '''Run fantest.py against a fresh simulator in a temporary directory.'''

    def setUp( self ):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup( self.tmpdir.cleanup )
        self.cwd = os.getcwd()
        os.chdir( self.tmpdir.name )
        self.addCleanup( os.chdir, self.cwd )
        patcher = patch.object( fansimulator, 'sim', BoardSimulator() )
        self.sim = patcher.start()
        self.addCleanup( patcher.stop )

    def run_script( self ):
        '''Execute fantest.py and return its stdout.'''
        out = io.StringIO()
        with redirect_stdout( out ):
            runpy.run_path( FANTEST_SCRIPT, run_name='__main__' )
        return out.getvalue()

    def test_prints_150_passes(self):
        '''The script runs and reports 150 passes.'''
        lines = self.run_script().splitlines()
        self.assertEqual( len( lines ), 150 )
        self.assertEqual( lines[-1].split()[1], "149" )

    def test_writes_csv_with_run_name(self):
        '''Readings are written to fantest.csv under the 'run2' header.'''
        self.run_script()
        with open( 'fantest.csv', encoding='utf-8' ) as f:
            content = f.read()
        self.assertTrue( content.startswith( "\nrun2," ) )
        self.assertEqual( len( content.strip().split( ',' ) ) - 2, 150 )   # name + trailing ''

    def test_appends_to_existing_csv(self):
        '''A second run is appended to the existing data file.'''
        self.run_script()
        with patch.object( fansimulator, 'sim', BoardSimulator() ):
            self.run_script()
        with open( 'fantest.csv', encoding='utf-8' ) as f:
            self.assertEqual( f.read().count( "run2," ), 2 )

    def test_fan_only_set_when_speed_changes(self):
        '''setFanSpeed is called only when the chosen speed changes.'''
        with patch( 'fansimulator.setFanSpeed', wraps=fansimulator.setFanSpeed ) as spy:
            out = self.run_script()
        speeds = [ float( line.split()[-1] ) for line in out.splitlines() ]
        changes = sum( 1 for a, b in zip( [ 0.0 ] + speeds, speeds ) if a != b )
        self.assertEqual( spy.call_count, changes )
        self.assertGreater( changes, 0 )

    def test_speeds_follow_thresholds(self):
        '''Each printed fan speed matches the script's temperature thresholds.'''
        for line in self.run_script().splitlines():
            parts = line.split()
            temp, speed = float( parts[3] ), float( parts[5] )
            expected = 0.4 if temp > 54 else 0.2 if temp > 40 else 0.1 if temp > 30 else 0.0
            self.assertEqual( speed, expected, line )

    def test_unwritable_directory_still_runs(self):
        '''If fantest.csv cannot be created, an error is printed and stopTest fails.'''
        os.chmod( self.tmpdir.name, 0o500 )
        self.addCleanup( os.chmod, self.tmpdir.name, 0o700 )
        if os.access( self.tmpdir.name, os.W_OK ):
            self.skipTest( "running as root; directory is still writable" )
        with self.assertRaises( AttributeError ):     # closeFile() on None
            self.run_script()


# ---------------------------------------------------------------------- test.py (hardware sweep)

class TestHardwareScript( unittest.TestCase ):
    '''Run fantest/test.py with RPi.GPIO and gpiozero mocked.'''

    def setUp( self ):
        self.gpio = MagicMock()
        rpi = types.ModuleType( 'RPi' )
        rpi.GPIO = self.gpio
        mods = patch.dict( sys.modules, { 'RPi': rpi, 'RPi.GPIO': self.gpio } )
        mods.start()
        self.addCleanup( mods.stop )
        self.fan = MagicMock()
        self.values = []
        type( self.fan ).value = property( lambda s: self.values[-1] if self.values else 0,
                                           lambda s, v: self.values.append( v ) )

    def run_script( self, pwm=None ):
        '''Execute test.py; return (stdout, script globals).'''
        out = io.StringIO()
        pwm = pwm or MagicMock( return_value=self.fan )
        with patch( 'gpiozero.PWMOutputDevice', pwm ), patch( 'time.sleep' ), \
             redirect_stdout( out ):
            g = runpy.run_path( HARDWARE_SCRIPT, run_name='__main__' )
        return out.getvalue(), g

    def test_configures_tachometer_input(self):
        '''The tachometer pin is set up as a pulled-up input with an edge callback.'''
        _, g = self.run_script()
        self.gpio.setup.assert_called_once_with( g['FAN_TACK_GPIO'], self.gpio.IN,
                                                 pull_up_down=self.gpio.PUD_UP )
        self.gpio.add_event_detect.assert_called_once()
        self.assertEqual( self.gpio.add_event_detect.call_args.args[2].__name__, 'fell' )

    def test_sweeps_0_to_100_then_off(self):
        '''The fan steps from 0% to 100% in 5% steps, then turns off.'''
        self.run_script()
        expected = [ 0 ] + [ s / 100 for s in range( 0, 105, 5 ) ] + [ 0 ]
        self.assertEqual( self.values, expected )

    def test_prints_rpm_readings_per_step(self):
        '''UPDATE_PERIOD RPM readings are printed at each of the 21 steps.'''
        out, g = self.run_script()
        self.assertEqual( out.count( "Setting speed to" ), 21 )
        self.assertEqual( out.count( "RPM =" ), 21 * g['UPDATE_PERIOD'] )

    def test_fan_setup_failure_raises(self):
        '''If the PWM device cannot be created, ValueError stops the script.'''
        with self.assertRaises( ValueError ):
            self.run_script( pwm=MagicMock( side_effect=OSError( "busy" ) ) )

    # ---- fell() tachometer callback

    def fell_with_dt( self, dt ):
        '''Call fell() as if the previous edge was dt seconds ago; return rpm.'''
        _, g = self.run_script()
        fell = g['fell']
        fell.__globals__['t'] = 1000.0
        fell.__globals__['rpm'] = 0
        with patch( 'time.time', return_value=1000.0 + dt ):
            fell( 24 )
        return fell.__globals__['rpm'], fell.__globals__['t']

    def test_fell_computes_rpm(self):
        '''An edge 10 ms after the last gives 100 Hz / 2 pulses * 60 = 3000 RPM.'''
        rpm, t = self.fell_with_dt( 0.01 )
        self.assertEqual( rpm, 3000 )
        self.assertEqual( t, 1000.01 )

    def test_fell_slow_fan(self):
        '''An edge 1 s after the last gives 30 RPM.'''
        rpm, _ = self.fell_with_dt( 1.0 )
        self.assertEqual( rpm, 30 )

    def test_fell_ignores_bounce(self):
        '''Edges less than 5 ms apart are ignored (debounce).'''
        rpm, t = self.fell_with_dt( 0.004 )
        self.assertEqual( rpm, 0 )
        self.assertEqual( t, 1000.0 )


if __name__ == "__main__":
    unittest.main()
