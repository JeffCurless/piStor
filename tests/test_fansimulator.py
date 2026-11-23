# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Unit tests for fantest/fansimulator.py (BoardSimulator and module wrappers).
'''
import io
import os
import runpy
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import fansimulator
from fansimulator import AMBIENT_TEMP, BoardSimulator
from tests import FANTEST


class TempDirTestCase( unittest.TestCase ):
    '''Base class providing a temporary directory for data files.'''

    def setUp( self ):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup( self.tmpdir.cleanup )

    def path( self, name='data.csv' ):
        '''Return a path inside the temporary directory.'''
        return os.path.join( self.tmpdir.name, name )

    @staticmethod
    def read( path ):
        '''Return the contents of a file.'''
        with open( path, encoding='utf-8' ) as f:
            return f.read()


# ---------------------------------------------------------------------- getValueFromProfile

class TestGetValueFromProfile( unittest.TestCase ):
    '''Tests for BoardSimulator.getValueFromProfile().'''

    PROFILE = [ (0, 10), (5, 20), (10, 30) ]

    def setUp( self ):
        self.sim = BoardSimulator()

    def test_value_in_first_range(self):
        '''A key inside the first range returns its value.'''
        self.assertEqual( self.sim.getValueFromProfile( 2, self.PROFILE ), 10 )

    def test_range_start_is_inclusive(self):
        '''A key equal to a range start belongs to that range.'''
        self.assertEqual( self.sim.getValueFromProfile( 0, self.PROFILE ), 10 )
        self.assertEqual( self.sim.getValueFromProfile( 5, self.PROFILE ), 20 )

    def test_range_end_is_exclusive(self):
        '''A key just below the next start still belongs to the earlier range.'''
        self.assertEqual( self.sim.getValueFromProfile( 4.999, self.PROFILE ), 10 )

    def test_float_keys(self):
        '''Float keys work, as used by the fan profile.'''
        sim = self.sim
        self.assertEqual( sim.getValueFromProfile( 0.25, sim._fanProfile ), 5 )  # pylint: disable=protected-access

    def test_last_entry_applies_from_its_start_onward(self):
        '''The last entry applies to every key at or above its start.'''
        self.assertEqual( self.sim.getValueFromProfile( 10, self.PROFILE ), 30 )
        self.assertEqual( self.sim.getValueFromProfile( 99, self.PROFILE ), 30 )

    def test_key_below_first_start_returns_zero(self):
        '''A key below the first range matches nothing.'''
        self.assertEqual( self.sim.getValueFromProfile( -1, self.PROFILE ), 0 )

    def test_single_entry_profile(self):
        '''A one-entry profile applies from its start onward.'''
        self.assertEqual( self.sim.getValueFromProfile( 0, [ (0, 10) ] ), 10 )
        self.assertEqual( self.sim.getValueFromProfile( 5, [ (0, 10) ] ), 10 )
        self.assertEqual( self.sim.getValueFromProfile( -1, [ (0, 10) ] ), 0 )

    def test_empty_profile_returns_zero(self):
        '''An empty profile matches nothing and returns 0.'''
        self.assertEqual( self.sim.getValueFromProfile( 0, [] ), 0 )

    def test_fan_profile_full_speed(self):
        '''Full fan speed (1.0) uses the last, strongest cooling entry.'''
        sim = self.sim
        self.assertEqual( sim.getValueFromProfile( 1.0, sim._fanProfile ), 50 )  # pylint: disable=protected-access

    def test_fan_profile_cooling_never_decreases(self):
        '''More fan speed never gives less cooling, from 0.0 to 1.0.'''
        sim = self.sim
        cooling = [ sim.getValueFromProfile( s / 100, sim._fanProfile )  # pylint: disable=protected-access
                    for s in range( 0, 101 ) ]
        self.assertEqual( cooling, sorted( cooling ) )


# ---------------------------------------------------------------------- setFanSpeed

class TestSetFanSpeed( unittest.TestCase ):
    '''Tests for BoardSimulator.setFanSpeed().'''

    def setUp( self ):
        self.sim = BoardSimulator()

    def test_valid_speeds_accepted(self):
        '''0.0, 0.5 and 1.0 are accepted and counted.'''
        for i, v in enumerate( ( 0.0, 0.5, 1.0 ), start=1 ):
            self.sim.setFanSpeed( v )
            self.assertEqual( self.sim._fanSpeed, v )        # pylint: disable=protected-access
            self.assertEqual( self.sim._fanCallCount, i )    # pylint: disable=protected-access

    def test_below_zero_rejected(self):
        '''Negative speeds raise ValueError and change nothing.'''
        self.sim.setFanSpeed( 0.3 )
        with self.assertRaises( ValueError ):
            self.sim.setFanSpeed( -0.01 )
        self.assertEqual( self.sim._fanSpeed, 0.3 )          # pylint: disable=protected-access
        self.assertEqual( self.sim._fanCallCount, 1 )        # pylint: disable=protected-access

    def test_above_one_rejected(self):
        '''Speeds above 1.0 raise ValueError.'''
        with self.assertRaises( ValueError ):
            self.sim.setFanSpeed( 1.01 )

    def test_non_numeric_rejected(self):
        '''A non-numeric speed raises TypeError.'''
        with self.assertRaises( TypeError ):
            self.sim.setFanSpeed( "fast" )


# ---------------------------------------------------------------------- getCPUTemp

class TestGetCPUTemp( unittest.TestCase ):
    '''Tests for BoardSimulator.getCPUTemp().'''

    def setUp( self ):
        self.sim = BoardSimulator()

    def test_first_reading_uses_profile(self):
        '''The first call returns the base temperature for call 1.'''
        self.assertEqual( self.sim.getCPUTemp(), 30 )

    def test_increments_call_count_and_stores_temp(self):
        '''Each call advances the counter and stores the current temperature.'''
        self.sim.getCPUTemp()
        t = self.sim.getCPUTemp()
        self.assertEqual( self.sim._tempCallCount, 2 )       # pylint: disable=protected-access
        self.assertEqual( self.sim._currentTemp, t )         # pylint: disable=protected-access

    def test_follows_cpu_profile_over_time(self):
        '''Temperatures follow the CPU profile as calls accumulate.'''
        temps = [ self.sim.getCPUTemp() for _ in range( 30 ) ]
        self.assertEqual( temps[0], 30 )      # call 1
        self.assertEqual( temps[10], 34 )     # call 11
        self.assertEqual( temps[24], 50 )     # call 25

    def test_fan_reduces_temperature(self):
        '''Running the fan lowers the simulated temperature.'''
        self.sim.setFanSpeed( 0.2 )
        self.assertEqual( self.sim.getCPUTemp(), 30 - 5 )

    def advanceTo( self, call ):
        '''Advance the simulator so the next reading is for the given call number.'''
        for _ in range( call - 1 ):
            self.sim.getCPUTemp()

    def test_full_fan_speed_cools_most(self):
        '''At the 60C peak, full speed cools more than 80% speed.'''
        self.advanceTo( 80 )                      # base temperature 60
        self.sim.setFanSpeed( 0.8 )
        at80 = self.sim.getCPUTemp()              # 60 - 37
        self.sim.setFanSpeed( 1.0 )
        at100 = self.sim.getCPUTemp()             # 60 - 50, floored at ambient
        self.assertEqual( at80, 23 )
        self.assertEqual( at100, AMBIENT_TEMP )
        self.assertLess( at100, at80 )

    def test_never_below_ambient(self):
        '''Strong cooling cannot take the CPU below AMBIENT_TEMP.'''
        self.sim.setFanSpeed( 0.9 )               # 30 - 40 would be -10
        self.assertEqual( self.sim.getCPUTemp(), AMBIENT_TEMP )

    def test_no_fan_temperatures_unchanged(self):
        '''With the fan off, readings follow the CPU profile exactly.'''
        temps = [ self.sim.getCPUTemp() for _ in range( 200 ) ]
        self.assertEqual( max( temps ), 60 )
        self.assertGreaterEqual( min( temps ), 30 )

    def test_profile_end_holds_last_temperature(self):
        '''After the end of the CPU profile the last base temperature is kept.'''
        for _ in range( 250 ):
            self.sim.getCPUTemp()
        self.assertEqual( self.sim.getCPUTemp(), 30 )

    def test_reset_system(self):
        '''resetSystem() clears the counters and temperature.'''
        self.sim.getCPUTemp()
        self.sim.setFanSpeed( 0.5 )
        self.sim.resetSystem()
        self.assertEqual( self.sim._tempCallCount, 0 )       # pylint: disable=protected-access
        self.assertEqual( self.sim._fanCallCount, 0 )        # pylint: disable=protected-access
        self.assertEqual( self.sim._currentTemp, 0 )         # pylint: disable=protected-access


# ---------------------------------------------------------------------- data recording

class TestDataRecording( TempDirTestCase ):
    '''Tests for the CSV recording methods.'''

    def setUp( self ):
        super().setUp()
        self.sim = BoardSimulator()

    def test_not_recording_by_default(self):
        '''Without a data file, readings are not written anywhere.'''
        self.sim.recordData( 42 )            # must not raise
        self.assertFalse( self.sim._recordData )             # pylint: disable=protected-access

    def test_create_data_file_enables_recording(self):
        '''createDataFile() opens the file and turns recording on.'''
        self.sim.createDataFile( self.path() )
        self.sim.recordData( 42 )
        self.sim.closeFile()
        self.assertEqual( self.read( self.path() ), "42," )

    def test_data_file_is_appended(self):
        '''An existing data file is appended to, not overwritten.'''
        with open( self.path(), 'w', encoding='utf-8' ) as f:
            f.write( "old," )
        self.sim.createDataFile( self.path() )
        self.sim.recordData( 1 )
        self.sim.closeFile()
        self.assertEqual( self.read( self.path() ), "old,1," )

    def test_readings_recorded(self):
        '''Each getCPUTemp() call appends the reading.'''
        self.sim.createDataFile( self.path() )
        self.sim.getCPUTemp()
        self.sim.getCPUTemp()
        self.sim.closeFile()
        self.assertEqual( self.read( self.path() ), "30,30," )

    def test_start_named_test_writes_header_and_resets(self):
        '''startNamedTest() writes a row header and resets the counters.'''
        self.sim.createDataFile( self.path() )
        self.sim.getCPUTemp()
        self.sim.startNamedTest( "runA" )
        self.sim.closeFile()
        self.assertEqual( self.read( self.path() ), "30,\nrunA," )
        self.assertEqual( self.sim._tempCallCount, 0 )       # pylint: disable=protected-access

    def test_start_named_test_without_file(self):
        '''startNamedTest() without a data file just records the name.'''
        self.sim.startNamedTest( "runB" )
        self.assertEqual( self.sim._testName, "runB" )       # pylint: disable=protected-access

    def test_bad_path_disables_recording(self):
        '''An unwritable path prints an error and leaves recording off.'''
        out = io.StringIO()
        with redirect_stdout( out ):
            self.sim.createDataFile( os.path.join( self.tmpdir.name, "missing", "x.csv" ) )
        self.assertIn( "Error", out.getvalue() )
        self.assertFalse( self.sim._recordData )             # pylint: disable=protected-access

    def test_close_without_file_raises(self):
        '''closeFile() with no open file raises AttributeError.'''
        with self.assertRaises( AttributeError ):
            self.sim.closeFile()

    def test_generate_baseline_uses_own_instance(self):
        '''generateBaseline() records readings from this simulator, not the global one.'''
        self.sim.createDataFile( self.path() )
        other = BoardSimulator()
        with patch.object( fansimulator, 'sim', other ):
            self.sim.generateBaseline( 3 )
        self.sim.closeFile()
        self.assertEqual( self.read( self.path() ), "\nbaseline,30,30,30," )
        self.assertEqual( self.sim._testName, 'baseline' )          # pylint: disable=protected-access
        self.assertEqual( other._tempCallCount, 0 )                  # pylint: disable=protected-access

    def test_generate_baseline_without_file_raises(self):
        '''generateBaseline() needs an open data file.'''
        with self.assertRaises( AttributeError ):
            self.sim.generateBaseline( 1 )


# ---------------------------------------------------------------------- module-level wrappers

class TestModuleWrappers( TempDirTestCase ):
    '''Tests for getCPUTemp/setFanSpeed/startTest/stopTest.'''

    def setUp( self ):
        super().setUp()
        patcher = patch.object( fansimulator, 'sim', BoardSimulator() )
        self.sim = patcher.start()
        self.addCleanup( patcher.stop )

    def test_get_and_set_use_global_sim(self):
        '''The wrappers act on the module's global simulator.'''
        fansimulator.setFanSpeed( 0.2 )
        self.assertEqual( fansimulator.getCPUTemp(), 25 )
        self.assertEqual( self.sim._fanCallCount, 1 )        # pylint: disable=protected-access

    def test_set_invalid_speed_raises(self):
        '''Invalid speeds raise through the wrapper.'''
        with self.assertRaises( ValueError ):
            fansimulator.setFanSpeed( 2 )

    def test_start_and_stop_test(self):
        '''startTest() opens the file with a header; stopTest() closes it.'''
        fansimulator.startTest( self.path(), "wrapped" )
        fansimulator.getCPUTemp()
        fansimulator.stopTest()
        self.assertEqual( self.read( self.path() ), "\nwrapped,30," )
        self.assertTrue( self.sim._file.closed )             # pylint: disable=protected-access

    def test_stop_without_start_raises(self):
        '''stopTest() before startTest() raises AttributeError.'''
        with self.assertRaises( AttributeError ):
            fansimulator.stopTest()


# ---------------------------------------------------------------------- __main__ demo

class TestSimulatorMain( unittest.TestCase ):
    '''Run fansimulator.py as a script.'''

    def test_demo_runs_150_passes(self):
        '''The demo prints 150 passes and never sets an invalid speed.'''
        out = io.StringIO()
        with patch( 'time.sleep' ), redirect_stdout( out ):
            runpy.run_path( os.path.join( FANTEST, 'fansimulator.py' ), run_name='__main__' )
        lines = out.getvalue().splitlines()
        self.assertEqual( len( lines ), 150 )
        self.assertTrue( lines[0].startswith( "Pass 0 CPU" ) )


if __name__ == "__main__":
    unittest.main()
