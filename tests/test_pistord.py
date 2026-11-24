# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Unit tests for src/pistord.py.

All GPIO hardware (PWMOutputDevice, CPUTemperature) is replaced with fakes and
time.sleep is patched, so these tests run quickly on any machine.  The endless
fan control loop is stopped by having the patched sleep raise StopLoop after a
given number of iterations.
'''
import io
import os
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import pistord
from configtool import AUTO_FAN, MANUAL_FAN
from tests import SRC

PISTORD_PATH = os.path.join( SRC, 'pistord.py' )

# Real implementations, saved before PistordTestCase patches them out.
REAL_GET_PIN_FACTORY = pistord.getPinFactory


class StopLoop( BaseException ):
    '''Raised by the patched sleep to break out of runFanLoop().

    Derives from BaseException so runFanLoop's "except Exception" cannot
    swallow it.
    '''


class FakeFan:  # pylint: disable=too-few-public-methods
    '''Mimics PWMOutputDevice: value must be within 0.0-1.0.'''
    def __init__( self, *args, **kwargs ):
        self.args    = args
        self.kwargs  = kwargs
        self.history = []
        self._value  = 0.0

    @property
    def value( self ):
        '''Current duty cycle.'''
        return self._value

    @value.setter
    def value( self, v ):
        if not 0.0 <= v <= 1.0:
            raise ValueError( f"PWM value {v} out of range" )
        self._value = v
        self.history.append( v )


class FakeSensor:  # pylint: disable=too-few-public-methods
    '''Mimics CPUTemperature with fixed (or failing) readings.'''
    def __init__( self, value=0.5, temperature=50.0, fail=False ):
        self._value       = value
        self._temperature = temperature
        self.fail         = fail

    @property
    def value( self ):
        '''Temperature scaled 0.0-1.0.'''
        if self.fail:
            raise OSError( "sensor read failed" )
        return self._value

    @property
    def temperature( self ):
        '''Temperature in degrees C.'''
        if self.fail:
            raise OSError( "sensor read failed" )
        return self._temperature


def stopAfter( n, fan=None, snapshots=None ):
    '''Return a sleep replacement that raises StopLoop on the n-th call.

    If fan and snapshots are given, the fan value is recorded on every call.
    '''
    calls = { 'n': 0 }
    def _sleep( _seconds ):
        calls['n'] += 1
        if snapshots is not None:
            snapshots.append( fan.value )
        if calls['n'] >= n:
            raise StopLoop()
    return _sleep


class PistordTestCase( unittest.TestCase ):
    '''Base class: replaces the module logger with a mock for every test.'''

    def setUp( self ):
        patcher = patch.object( pistord, 'log', MagicMock() )
        self.log = patcher.start()
        self.addCleanup( patcher.stop )
        # Never probe the real /dev/gpiochip* devices from unit tests.
        factory = patch.object( pistord, 'getPinFactory', return_value=None )
        self.getPinFactory = factory.start()
        self.addCleanup( factory.stop )

    def errorMessages( self ):
        '''Return all messages passed to log.error().'''
        return [ c.args[0] for c in self.log.error.call_args_list ]


# ---------------------------------------------------------------------- setupFan

class TestSetupFan( PistordTestCase ):
    '''Tests for setupFan().'''

    def test_returns_device_with_speed_zero(self):
        '''A successfully created fan is returned with its value set to 0.'''
        with patch.object( pistord, 'PWMOutputDevice', FakeFan ):
            fan = pistord.setupFan( 13 )
        self.assertIsInstance( fan, FakeFan )
        self.assertEqual( fan.value, 0 )

    def test_passes_pin_and_frequency(self):
        '''The GPIO pin and a 100 Hz PWM frequency are passed to the device.'''
        with patch.object( pistord, 'PWMOutputDevice', FakeFan ):
            fan = pistord.setupFan( 13 )
        self.assertEqual( fan.args, (13,) )
        self.assertEqual( fan.kwargs, { 'frequency': 100 } )

    def test_passes_pin_factory_when_found(self):
        '''A header pin factory is handed to the PWM device.'''
        factory = object()
        self.getPinFactory.return_value = factory
        with patch.object( pistord, 'PWMOutputDevice', FakeFan ):
            fan = pistord.setupFan( 13 )
        self.assertEqual( fan.kwargs, { 'frequency': 100, 'pin_factory': factory } )

    def test_device_error_raises_value_error(self):
        '''If the device cannot be created, ValueError is raised.'''
        with patch.object( pistord, 'PWMOutputDevice', side_effect=OSError( "busy" ) ):
            with self.assertRaises( ValueError ):
                pistord.setupFan( 13 )

    def test_device_error_is_chained_and_logged(self):
        '''The original error is chained as __cause__ and included in the log.'''
        original = OSError( "pin busy" )
        with patch.object( pistord, 'PWMOutputDevice', side_effect=original ):
            with self.assertRaises( ValueError ) as ctx:
                pistord.setupFan( 13 )
        self.assertIs( ctx.exception.__cause__, original )
        self.assertIn( "pin busy", self.errorMessages()[0] )

    def test_error_setting_initial_value_raises_value_error(self):
        '''An error setting the initial speed is also reported as ValueError.'''
        device = MagicMock()
        type( device ).value = property( lambda s: 0, MagicMock( side_effect=OSError( "x" ) ) )
        with patch.object( pistord, 'PWMOutputDevice', return_value=device ):
            with self.assertRaises( ValueError ):
                pistord.setupFan( 13 )


# ---------------------------------------------------------------------- gpiochip discovery

def fakeLgpio( chips, failing=() ):
    '''Return a fake lgpio module whose chips map number -> label.'''
    module = MagicMock()
    def _open( chip ):
        if chip in failing:
            raise OSError( "can not open gpiochip" )
        return chip
    module.gpiochip_open.side_effect = _open
    module.gpio_get_chip_info.side_effect = \
        lambda h: [ 0, 54, f'gpiochip{h}', chips[h] ]
    return module


class TestFindHeaderGPIOChip( PistordTestCase ):
    '''Tests for findHeaderGPIOChip().'''

    PI5_NORMAL = { 0: 'pinctrl-rp1', 10: 'gpio-brcmstb@107d508500',
                   11: 'gpio-brcmstb@107d517c00' }
    # Layout seen on a Pi 5 running kernel 6.12.115: no gpiochip0 or gpiochip4.
    PI5_RENUMBERED = { 11: 'gpio-brcmstb@107d517c00', 12: 'gpio-brcmstb@107d517c20',
                       13: 'gpio-brcmstb@107d508500', 14: 'gpio-brcmstb@107d508520',
                       15: 'pinctrl-rp1' }

    def find( self, chips, failing=(), links=() ):
        '''Run findHeaderGPIOChip() against fake devices.'''
        paths = [ f'/dev/gpiochip{n}' for n in chips ] + list( links )
        module = fakeLgpio( chips, failing )
        with patch.dict( sys.modules, { 'lgpio': module } ), \
             patch.object( pistord.glob, 'glob', return_value=paths ), \
             patch.object( pistord.os.path, 'islink', side_effect=lambda p: p in links ):
            return pistord.findHeaderGPIOChip(), module

    def test_pi5_header_is_gpiochip0(self):
        '''On a normal Pi 5 the RP1 chip (gpiochip0) is found.'''
        result, _ = self.find( self.PI5_NORMAL )
        self.assertEqual( result, ( 0, 'pinctrl-rp1' ) )

    def test_renumbered_kernel_finds_gpiochip15(self):
        '''When the kernel numbers the RP1 chip 15, it is still found by label.'''
        result, _ = self.find( self.PI5_RENUMBERED )
        self.assertEqual( result, ( 15, 'pinctrl-rp1' ) )

    def test_symlinks_are_skipped(self):
        '''/dev/gpiochip4 -> gpiochip0 is not opened a second time.'''
        _, module = self.find( self.PI5_NORMAL, links=( '/dev/gpiochip4', ) )
        opened = [ c.args[0] for c in module.gpiochip_open.call_args_list ]
        self.assertNotIn( 4, opened )

    def test_chips_are_closed(self):
        '''Every chip opened for probing is closed again.'''
        _, module = self.find( self.PI5_RENUMBERED )
        self.assertEqual( module.gpiochip_open.call_count, module.gpiochip_close.call_count )

    def test_unopenable_chip_is_skipped(self):
        '''A chip that cannot be opened does not stop the search.'''
        result, _ = self.find( self.PI5_RENUMBERED, failing=( 11, 12 ) )
        self.assertEqual( result, ( 15, 'pinctrl-rp1' ) )

    def test_older_pi_labels(self):
        '''Pi 4 and Pi 3 header chips are recognised.'''
        self.assertEqual( self.find( { 0: 'pinctrl-bcm2711', 1: 'raspberrypi-exp-gpio' } )[0],
                          ( 0, 'pinctrl-bcm2711' ) )
        self.assertEqual( self.find( { 0: 'pinctrl-bcm2835' } )[0], ( 0, 'pinctrl-bcm2835' ) )

    def test_no_header_chip_returns_none(self):
        '''If no chip has a header label, None is returned.'''
        result, _ = self.find( { 0: 'some-other-gpio' } )
        self.assertIsNone( result )

    def test_no_lgpio_returns_none(self):
        '''Without lgpio installed, None is returned.'''
        with patch.dict( sys.modules, { 'lgpio': None } ):
            self.assertIsNone( pistord.findHeaderGPIOChip() )


class TestMakeLGPIOFactory( unittest.TestCase ):
    '''Tests for makeLGPIOFactory(), the gpiozero chip-number workaround.'''

    def test_opens_requested_chip(self):
        '''The requested chip is opened, not the one gpiozero would pick.'''
        class BaseFactory:  # pylint: disable=too-few-public-methods
            def __init__( self ):
                self.baseInitialised = True

        class LGPIOFactory( BaseFactory ):  # pylint: disable=too-few-public-methods
            def __init__( self, chip=None ):  # pylint: disable=super-init-not-called
                raise AssertionError( "gpiozero's __init__ must be bypassed" )

        lgpio = MagicMock()
        lgpio.gpiochip_open.return_value = 'handle'
        pinClass = object()
        modules = { 'lgpio': lgpio,
                    'gpiozero.pins.lgpio': MagicMock( LGPIOFactory=LGPIOFactory,
                                                      LGPIOPin=pinClass ) }
        with patch.dict( sys.modules, modules ):
            factory = pistord.makeLGPIOFactory( 15 )
        lgpio.gpiochip_open.assert_called_once_with( 15 )
        self.assertIsInstance( factory, LGPIOFactory )
        self.assertTrue( factory.baseInitialised )
        self.assertEqual( ( factory._chip, factory._handle ), ( 15, 'handle' ) )
        self.assertIs( factory.pin_class, pinClass )


class TestGetPinFactory( PistordTestCase ):
    '''Tests for getPinFactory() (the real one, not the setUp patch).'''

    def setUp( self ):
        super().setUp()
        self.factoryClass = self.enterContext( patch.object( pistord, 'makeLGPIOFactory' ) )

    def test_factory_bound_to_found_chip(self):
        '''An LGPIOFactory is created for the header chip and the choice logged.'''
        with patch.object( pistord, 'findHeaderGPIOChip', return_value=( 15, 'pinctrl-rp1' ) ):
            factory = REAL_GET_PIN_FACTORY()
        self.factoryClass.assert_called_once_with( 15 )
        self.assertIs( factory, self.factoryClass.return_value )
        self.assertIn( "/dev/gpiochip15", self.log.info.call_args.args[0] )

    def test_no_chip_returns_none_with_warning(self):
        '''If no header chip is found, None is returned and a warning logged.'''
        with patch.object( pistord, 'findHeaderGPIOChip', return_value=None ):
            self.assertIsNone( REAL_GET_PIN_FACTORY() )
        self.log.warning.assert_called_once()
        self.factoryClass.assert_not_called()

    def test_factory_error_returns_none_with_warning(self):
        '''If the factory cannot be created, None is returned and a warning logged.'''
        self.factoryClass.side_effect = OSError( "can not open gpiochip" )
        with patch.object( pistord, 'findHeaderGPIOChip', return_value=( 15, 'pinctrl-rp1' ) ):
            self.assertIsNone( REAL_GET_PIN_FACTORY() )
        self.assertIn( "can not open gpiochip", self.log.warning.call_args.args[0] )


# ---------------------------------------------------------------------- setupTemperatureObject

class TestSetupTemperatureObject( PistordTestCase ):
    '''Tests for setupTemperatureObject().'''

    def test_returns_sensor(self):
        '''A successfully created sensor is returned.'''
        sensor = FakeSensor()
        with patch.object( pistord, 'CPUTemperature', return_value=sensor ):
            self.assertIs( pistord.setupTemperatureObject(), sensor )
        self.log.error.assert_not_called()

    def test_failure_returns_none_and_logs(self):
        '''If the sensor cannot be created, None is returned and the error logged.'''
        with patch.object( pistord, 'CPUTemperature', side_effect=OSError( "no thermal zone" ) ):
            self.assertIsNone( pistord.setupTemperatureObject() )
        self.assertIn( "no thermal zone", self.errorMessages()[0] )

    def test_default_pin_factory_when_none(self):
        '''With no pin factory, CPUTemperature is created with no arguments.'''
        with patch.object( pistord, 'CPUTemperature' ) as cls:
            pistord.setupTemperatureObject()
        cls.assert_called_once_with()

    def test_uses_given_pin_factory(self):
        '''A pin factory is passed through, so gpiozero does not probe for one.'''
        factory = object()
        with patch.object( pistord, 'CPUTemperature' ) as cls:
            pistord.setupTemperatureObject( factory )
        cls.assert_called_once_with( pin_factory=factory )


# ---------------------------------------------------------------------- autoFanSpeed

class TestAutoFanSpeed( unittest.TestCase ):
    '''Tests for autoFanSpeed().'''

    def test_adds_headroom(self):
        '''The duty cycle is the scaled temperature plus 0.1.'''
        self.assertAlmostEqual( pistord.autoFanSpeed( FakeSensor( value=0.5 ) ), 0.6 )

    def test_zero_temperature_gives_minimum(self):
        '''A scaled temperature of 0 still runs the fan at 10%.'''
        self.assertAlmostEqual( pistord.autoFanSpeed( FakeSensor( value=0.0 ) ), 0.1 )

    def test_clamped_at_one(self):
        '''Values that would exceed 1.0 are clamped to 1.0.'''
        self.assertEqual( pistord.autoFanSpeed( FakeSensor( value=0.95 ) ), 1.0 )
        self.assertEqual( pistord.autoFanSpeed( FakeSensor( value=1.0 ) ), 1.0 )

    def test_exactly_point_nine_gives_one(self):
        '''0.9 + 0.1 reaches exactly the 1.0 limit.'''
        self.assertAlmostEqual( pistord.autoFanSpeed( FakeSensor( value=0.9 ) ), 1.0 )

    def test_returns_float(self):
        '''The result is always a float.'''
        self.assertIsInstance( pistord.autoFanSpeed( FakeSensor( value=0 ) ), float )

    def test_sensor_error_propagates(self):
        '''A sensor read error is not swallowed (runFanLoop handles it).'''
        with self.assertRaises( OSError ):
            pistord.autoFanSpeed( FakeSensor( fail=True ) )


# ---------------------------------------------------------------------- getFanSpeed

TABLE = [ (20, 0), (30, 20), (70, 100) ]

class TestGetFanSpeed( PistordTestCase ):
    '''Tests for getFanSpeed().'''

    def test_between_thresholds_uses_lower_entry(self):
        '''A temperature between thresholds uses the highest one it meets.'''
        self.assertEqual( pistord.getFanSpeed( 50, TABLE ), 0.2 )

    def test_exact_threshold_matches(self):
        '''Reaching a threshold exactly selects that entry.'''
        self.assertEqual( pistord.getFanSpeed( 30, TABLE ), 0.2 )
        self.assertEqual( pistord.getFanSpeed( 70, TABLE ), 1.0 )

    def test_just_below_threshold(self):
        '''A temperature just below a threshold uses the previous entry.'''
        self.assertEqual( pistord.getFanSpeed( 29.9, TABLE ), 0.0 )

    def test_above_all_thresholds_uses_last_entry(self):
        '''Temperatures above the last threshold use the last entry.'''
        self.assertEqual( pistord.getFanSpeed( 95, TABLE ), 1.0 )

    def test_zero_speed_entry_is_not_treated_as_missing(self):
        '''A 0% entry is a real match, not the "no match" fallback.'''
        self.assertEqual( pistord.getFanSpeed( 20, TABLE ), 0.0 )

    def test_below_all_thresholds_falls_back_to_full_speed(self):
        '''A temperature below every threshold runs the fan at 100% (fail safe).'''
        self.assertEqual( pistord.getFanSpeed( 10, TABLE ), 1.0 )

    def test_negative_temperature_falls_back_to_full_speed(self):
        '''Negative temperatures below the table also fall back to 100%.'''
        self.assertEqual( pistord.getFanSpeed( -5, TABLE ), 1.0 )

    def test_empty_table_falls_back_to_full_speed(self):
        '''An empty table (e.g. empty [FanSpeeds] section) runs the fan at 100%.'''
        self.assertEqual( pistord.getFanSpeed( 50, [] ), 1.0 )

    def test_single_entry_table(self):
        '''A one-entry table applies from its threshold upward.'''
        self.assertEqual( pistord.getFanSpeed( 40, [ (40, 55) ] ), 0.55 )
        self.assertEqual( pistord.getFanSpeed( 39, [ (40, 55) ] ), 1.0 )

    def test_unsorted_table_stops_at_first_higher_threshold(self):
        '''The table must be sorted: the walk stops at the first threshold above temp.'''
        self.assertEqual( pistord.getFanSpeed( 40, [ (50, 50), (30, 20) ] ), 1.0 )

    def test_speed_over_100_is_returned_unclamped(self):
        '''Out-of-range table speeds are not clamped here (runFanLoop catches them).'''
        self.assertEqual( pistord.getFanSpeed( 50, [ (20, 150) ] ), 1.5 )

    def test_result_is_float(self):
        '''Integer percentages are converted to a float fraction.'''
        self.assertIsInstance( pistord.getFanSpeed( 50, TABLE ), float )

    def test_logs_each_entry_examined(self):
        '''Each table entry examined produces a debug line.'''
        pistord.getFanSpeed( 25, TABLE )
        self.assertEqual( self.log.debug.call_count, 2 )


# ---------------------------------------------------------------------- runFanLoop

class TestRunFanLoop( PistordTestCase ):
    '''Tests for runFanLoop(), the shared control loop.'''

    def test_sensor_shares_fan_pin_factory(self):
        '''The temperature sensor uses the fan's pin factory, including on retry.'''
        fan = FakeFan()
        fan.pin_factory = factory = object()
        sensor = MagicMock( side_effect=[ OSError( "first" ), FakeSensor() ] )
        with patch.object( pistord, 'PWMOutputDevice', return_value=fan ), \
             patch.object( pistord, 'CPUTemperature', sensor ), \
             patch.object( pistord.time, 'sleep', stopAfter( 2 ) ):
            with self.assertRaises( StopLoop ):
                pistord.runFanLoop( lambda s: 0.5 )
        self.assertEqual( [ c.kwargs for c in sensor.call_args_list ],
                          [ { 'pin_factory': factory } ] * 2 )

    def test_uses_given_pwm_gpio(self):
        '''runFanLoop() creates the fan on the GPIO it is given.'''
        with patch.object( pistord, 'PWMOutputDevice', return_value=FakeFan() ) as dev, \
             patch.object( pistord, 'CPUTemperature', return_value=FakeSensor() ), \
             patch.object( pistord.time, 'sleep', stopAfter( 1 ) ):
            with self.assertRaises( StopLoop ):
                pistord.runFanLoop( lambda s: 0.5, 19 )
        self.assertEqual( dev.call_args.args[0], 19 )

    def runLoop( self, compute, iterations, sensorFactory, fan=None ):
        '''Run the loop for the given number of iterations.

        Returns (fan, list of fan values at each sleep, the sleep mock).
        '''
        fan = fan or FakeFan()
        snapshots = []
        sleep = MagicMock( side_effect=stopAfter( iterations, fan, snapshots ) )
        with patch.object( pistord, 'PWMOutputDevice', return_value=fan ), \
             patch.object( pistord, 'CPUTemperature', side_effect=sensorFactory ), \
             patch.object( pistord.time, 'sleep', sleep ):
            with self.assertRaises( StopLoop ):
                pistord.runFanLoop( compute )
        return fan, snapshots, sleep

    def test_applies_computed_speed_each_iteration(self):
        '''The value from computeSpeed is applied to the fan every iteration.'''
        sensor = FakeSensor( value=0.3 )
        _, snaps, _ = self.runLoop( pistord.autoFanSpeed, 3, lambda: sensor )
        for v in snaps:
            self.assertAlmostEqual( v, 0.4 )

    def test_sleeps_update_period(self):
        '''The loop sleeps UPDATE_PERIOD seconds between iterations.'''
        _, _, sleep = self.runLoop( lambda s: 0.5, 2, FakeSensor )
        sleep.assert_called_with( pistord.UPDATE_PERIOD )

    def test_compute_receives_sensor(self):
        '''computeSpeed is called with the CPUTemperature object.'''
        sensor = FakeSensor()
        compute = MagicMock( return_value=0.5 )
        self.runLoop( compute, 1, lambda: sensor )
        compute.assert_called_with( sensor )

    def test_follows_changing_temperature(self):
        '''The fan speed tracks the sensor as it changes between iterations.'''
        sensor = FakeSensor( value=0.2 )
        readings = iter( [ 0.2, 0.5, 0.8 ] )
        def compute( s ):
            s._value = next( readings )  # pylint: disable=protected-access
            return pistord.autoFanSpeed( s )
        _, snaps, _ = self.runLoop( compute, 3, lambda: sensor )
        self.assertEqual( [ round( v, 2 ) for v in snaps ], [ 0.3, 0.6, 0.9 ] )

    def test_logs_status_on_first_iteration_and_every_interval(self):
        '''A status debug line is logged at iteration 0 and every LOG_INTERVAL.'''
        with patch.object( pistord, 'LOG_INTERVAL', 3 ):
            self.runLoop( lambda s: 0.5, 7, FakeSensor )
        status = [ c for c in self.log.debug.call_args_list if c.args[0].startswith( "CPU " ) ]
        self.assertEqual( len( status ), 3 )     # iterations 0, 3 and 6

    def test_warns_when_fan_at_full_speed(self):
        '''A warning is logged at the status interval when the fan is at 100%.'''
        with patch.object( pistord, 'LOG_INTERVAL', 2 ):
            self.runLoop( lambda s: 1.0, 3, FakeSensor )
        self.log.warning.assert_called_once()
        self.assertIn( "100%", self.log.warning.call_args.args[0] )

    def test_status_log_handles_integer_fan_value(self):
        '''The status line must not fail when the fan value is an int (e.g. 0).'''
        fan = FakeFan()
        fan._value = 0                     # pylint: disable=protected-access
        self.runLoop( lambda s: 0.5, 1, FakeSensor, fan=fan )
        self.log.error.assert_not_called()

    def test_no_warning_below_full_speed(self):
        '''No warning is logged while the fan is below 100%.'''
        self.runLoop( lambda s: 0.5, 3, FakeSensor )
        self.log.warning.assert_not_called()

    # ---- failure handling

    def test_pwm_failure_returns_without_looping(self):
        '''If the fan cannot be created, the loop is not started.'''
        sleep = MagicMock()
        with patch.object( pistord, 'PWMOutputDevice', side_effect=OSError( "busy" ) ), \
             patch.object( pistord.time, 'sleep', sleep ):
            pistord.runFanLoop( lambda s: 0.5 )
        sleep.assert_not_called()
        self.assertTrue( any( "not started" in m for m in self.errorMessages() ) )

    def test_sensor_unavailable_runs_fan_at_full_speed(self):
        '''If the sensor cannot be created, the fan runs at 100%.'''
        _, snaps, _ = self.runLoop( lambda s: 0.2, 3, MagicMock( side_effect=OSError( "x" ) ) )
        self.assertEqual( snaps, [ 1.0, 1.0, 1.0 ] )

    def test_sensor_failure_logged_once_per_episode(self):
        '''A persistent sensor failure logs the loop error only once.'''
        self.runLoop( lambda s: 0.2, 5, MagicMock( side_effect=OSError( "x" ) ) )
        loopErrors = [ m for m in self.errorMessages() if "100%" in m ]
        self.assertEqual( len( loopErrors ), 1 )

    def test_sensor_recovers_after_retry(self):
        '''The sensor is re-created each iteration until it succeeds.

        The first failure is at startup (setupTemperatureObject), the second is
        the retry in iteration 0, and iteration 1 succeeds.
        '''
        sensor = FakeSensor( value=0.4 )
        factory = MagicMock( side_effect=[ OSError( "a" ), OSError( "b" ), sensor ] )
        _, snaps, _ = self.runLoop( pistord.autoFanSpeed, 3, factory )
        self.assertEqual( snaps[0], 1.0 )
        self.assertAlmostEqual( snaps[1], 0.5 )
        self.assertAlmostEqual( snaps[2], 0.5 )
        self.assertEqual( factory.call_count, 3 )   # no re-creation once working
        self.log.info.assert_any_call( "Fan speed processing recovered." )

    def test_sensor_read_error_mid_run(self):
        '''A read error on a working sensor drives the fan to 100%, then recovers.'''
        sensor = FakeSensor( value=0.3 )
        results = iter( [ 0.4, OSError( "glitch" ), 0.4 ] )
        def compute( _s ):
            r = next( results )
            if isinstance( r, Exception ):
                raise r
            return r
        _, snaps, _ = self.runLoop( compute, 3, lambda: sensor )
        self.assertEqual( snaps, [ 0.4, 1.0, 0.4 ] )
        self.assertEqual( len( [ m for m in self.errorMessages() if "glitch" in m ] ), 1 )
        self.log.info.assert_any_call( "Fan speed processing recovered." )

    def test_out_of_range_speed_drives_fan_to_full(self):
        '''A computed speed outside 0.0-1.0 is rejected and the fan runs at 100%.'''
        _, snaps, _ = self.runLoop( lambda s: 1.5, 2, FakeSensor )
        self.assertEqual( snaps, [ 1.0, 1.0 ] )

    def test_repeated_episodes_each_logged(self):
        '''Each new failure episode (after a recovery) is logged again.'''
        results = iter( [ ValueError( "e1" ), 0.5, ValueError( "e2" ), 0.5 ] )
        def compute( _s ):
            r = next( results )
            if isinstance( r, Exception ):
                raise r
            return r
        self.runLoop( compute, 4, FakeSensor )
        loopErrors = [ m for m in self.errorMessages() if "100%" in m ]
        self.assertEqual( len( loopErrors ), 2 )
        self.assertEqual( self.log.info.call_count, 2 )


# ---------------------------------------------------------------------- controlFanAuto / Manual

class TestControlFan( PistordTestCase ):
    '''Tests for controlFanAuto() and controlFanManual().'''

    def test_auto_uses_auto_fan_speed(self):
        '''Automatic mode runs the loop with autoFanSpeed.'''
        with patch.object( pistord, 'runFanLoop' ) as loop:
            pistord.controlFanAuto()
        loop.assert_called_once_with( pistord.autoFanSpeed, pistord.FAN_PWM_GPIO )
        self.assertIn( "automatic", self.log.info.call_args.args[0] )

    def test_manual_uses_table_with_temperature_in_celsius(self):
        '''Manual mode looks up the table using the temperature in degrees C.'''
        with patch.object( pistord, 'runFanLoop' ) as loop:
            pistord.controlFanManual( TABLE )
        compute = loop.call_args.args[0]
        self.assertEqual( compute( FakeSensor( value=0.01, temperature=50 ) ), 0.2 )
        self.assertEqual( compute( FakeSensor( value=0.99, temperature=10 ) ), 1.0 )

    def test_auto_passes_gpio_to_loop(self):
        '''controlFanAuto() hands its PWM GPIO to runFanLoop().'''
        with patch.object( pistord, 'runFanLoop' ) as loop:
            pistord.controlFanAuto( 12 )
        self.assertEqual( loop.call_args.args[1], 12 )

    def test_manual_passes_gpio_to_loop(self):
        '''controlFanManual() hands its PWM GPIO to runFanLoop().'''
        with patch.object( pistord, 'runFanLoop' ) as loop:
            pistord.controlFanManual( TABLE, 19 )
        self.assertEqual( loop.call_args.args[1], 19 )

    def test_manual_logs_table(self):
        '''Manual mode logs the speed table it is using.'''
        with patch.object( pistord, 'runFanLoop' ):
            pistord.controlFanManual( TABLE )
        self.assertIn( str( TABLE ), self.log.info.call_args.args[0] )


# ---------------------------------------------------------------------- startFanControl

class TestStartFanControl( PistordTestCase ):
    '''Tests for startFanControl() mode dispatch.'''

    def setUp( self ):
        super().setUp()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup( self.tmpdir.cleanup )
        self.conf = os.path.join( self.tmpdir.name, 'pistor.conf' )
        self.controlFanAuto   = self.enterContext( patch.object( pistord, 'controlFanAuto' ) )
        self.controlFanManual = self.enterContext( patch.object( pistord, 'controlFanManual' ) )
        p = patch.object( pistord, 'CONFIG_PATH', self.conf )
        p.start()
        self.addCleanup( p.stop )

    def writeConf( self, text ):
        '''Write the test configuration file.'''
        with open( self.conf, 'w', encoding='utf-8' ) as f:
            f.write( text )

    def test_missing_config_uses_auto_and_warns(self):
        '''With no config file, automatic mode is used and a warning logged.'''
        with redirect_stdout( io.StringIO() ):
            pistord.startFanControl()
        self.controlFanAuto.assert_called_once()
        self.controlFanManual.assert_not_called()
        self.log.warning.assert_called_once()

    def test_auto_mode(self):
        '''autofan = 1 selects automatic mode.'''
        self.writeConf( f"[mode]\nautofan = {AUTO_FAN}\n" )
        pistord.startFanControl()
        self.controlFanAuto.assert_called_once()
        self.controlFanManual.assert_not_called()

    def test_manual_mode_passes_table(self):
        '''autofan = 0 selects manual mode with the configured table.'''
        self.writeConf( f"[mode]\nautofan = {MANUAL_FAN}\n[FanSpeeds]\n20 = 0\n60 = 80\n" )
        pistord.startFanControl()
        self.controlFanManual.assert_called_once_with( [ (20, 0), (60, 80) ], 13 )
        self.controlFanAuto.assert_not_called()

    def test_unknown_mode_falls_back_to_auto(self):
        '''An unrecognised mode logs an error and uses automatic mode.'''
        self.writeConf( "[mode]\nautofan = 7\n" )
        pistord.startFanControl()
        self.controlFanAuto.assert_called_once()
        self.assertIn( "7", self.errorMessages()[0] )

    def test_invalid_mode_value_falls_back_to_auto(self):
        '''A non-integer mode falls back to automatic (via configtool's default).'''
        self.writeConf( "[mode]\nautofan = yes please\n" )
        with redirect_stdout( io.StringIO() ):
            pistord.startFanControl()
        self.controlFanAuto.assert_called_once()

    def test_config_is_a_directory_uses_auto(self):
        '''A directory at the config path is treated as a missing file.'''
        os.mkdir( self.conf )
        pistord.startFanControl()
        self.controlFanAuto.assert_called_once()

    def test_configured_pwm_gpio_used_in_auto_mode(self):
        '''[gpio] fanpwm is passed to automatic mode and logged.'''
        self.writeConf( f"[mode]\nautofan = {AUTO_FAN}\n[gpio]\nfanpwm = 12\nfantach = 24\n" )
        pistord.startFanControl()
        self.controlFanAuto.assert_called_once_with( 12 )
        logged = " ".join( c.args[0] for c in self.log.info.call_args_list )
        self.assertIn( "GPIO 12", logged )
        self.assertIn( "GPIO 24", logged )

    def test_configured_pwm_gpio_used_in_manual_mode(self):
        '''[gpio] fanpwm is passed to manual mode.'''
        self.writeConf( f"[mode]\nautofan = {MANUAL_FAN}\n[gpio]\nfanpwm = 19\n"
                        "[FanSpeeds]\n20 = 0\n" )
        pistord.startFanControl()
        self.controlFanManual.assert_called_once_with( [ (20, 0) ], 19 )

    def test_unknown_mode_uses_configured_gpio(self):
        '''The automatic fallback for an unknown mode still uses [gpio] fanpwm.'''
        self.writeConf( "[mode]\nautofan = 7\n[gpio]\nfanpwm = 12\n" )
        pistord.startFanControl()
        self.controlFanAuto.assert_called_once_with( 12 )

    def test_missing_gpio_section_uses_default(self):
        '''With no [gpio] section the fan PWM defaults to GPIO 13.'''
        self.writeConf( f"[mode]\nautofan = {AUTO_FAN}\n" )
        pistord.startFanControl()
        self.controlFanAuto.assert_called_once_with( 13 )

    def test_missing_config_uses_default_gpio(self):
        '''With no config file the fan PWM defaults to GPIO 13.'''
        pistord.startFanControl()
        self.controlFanAuto.assert_called_once_with( 13 )

    def test_bundled_template_selects_auto(self):
        '''The repository's pistor.conf template selects automatic mode.'''
        with patch.object( pistord, 'CONFIG_PATH', os.path.join( SRC, 'pistor.conf' ) ):
            pistord.startFanControl()
        self.controlFanAuto.assert_called_once()


# ---------------------------------------------------------------------- turnOffFan / usage

class TestTurnOffFanAndUsage( PistordTestCase ):
    '''Tests for turnOffFan() and usage().'''

    def setUp( self ):
        super().setUp()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup( self.tmpdir.cleanup )
        self.conf = os.path.join( self.tmpdir.name, 'pistor.conf' )
        p = patch.object( pistord, 'CONFIG_PATH', self.conf )
        p.start()
        self.addCleanup( p.stop )

    def test_turn_off_uses_default_gpio_without_config(self):
        '''With no config file, the fan on GPIO 13 is turned off.'''
        with patch.object( pistord, 'PWMOutputDevice', return_value=FakeFan() ) as dev:
            pistord.turnOffFan()
        self.assertEqual( dev.call_args.args[0], 13 )

    def test_turn_off_uses_configured_gpio(self):
        '''SHUTDOWN turns off the fan on the [gpio] fanpwm GPIO.'''
        with open( self.conf, 'w', encoding='utf-8' ) as f:
            f.write( "[gpio]\nfanpwm = 12\n" )
        with patch.object( pistord, 'PWMOutputDevice', return_value=FakeFan() ) as dev:
            pistord.turnOffFan()
        self.assertEqual( dev.call_args.args[0], 12 )

    def test_turn_off_sets_zero(self):
        '''turnOffFan() sets the fan duty cycle to zero.'''
        fan = FakeFan()
        fan.value = 0.7
        with patch.object( pistord, 'PWMOutputDevice', return_value=fan ):
            pistord.turnOffFan()
        self.assertEqual( fan.value, 0 )
        self.log.error.assert_not_called()

    def test_turn_off_failure_is_logged_not_raised(self):
        '''A GPIO error during shutdown is logged and not raised.'''
        with patch.object( pistord, 'PWMOutputDevice', side_effect=OSError( "busy" ) ):
            pistord.turnOffFan()
        self.assertTrue( any( "Could not turn off fan" in m for m in self.errorMessages() ) )

    def test_usage_lists_every_command(self):
        '''usage() mentions every supported CLI command.'''
        out = io.StringIO()
        with redirect_stdout( out ):
            pistord.usage()
        for cmd in ( "SHUTDOWN", "SERVICE", "VERSION", "DEBUG" ):
            self.assertIn( cmd, out.getvalue() )


# ---------------------------------------------------------------------- command line

class TestCommandLine( unittest.TestCase ):
    '''Run pistord.py as __main__ with different arguments.'''

    def runMain( self, *args, pwm=None, thread=None ):
        '''Execute pistord.py as a script with hardware and logging patched.

        Returns (stdout text, mock Logger class, fan).
        '''
        loggerClass = MagicMock()
        fan = FakeFan()
        pwm = pwm if pwm is not None else MagicMock( return_value=fan )
        out = io.StringIO()
        patches = [
            patch.object( sys, 'argv', [ PISTORD_PATH, *args ] ),
            patch( 'logger.Logger', loggerClass ),
            patch( 'gpiozero.PWMOutputDevice', pwm ),
            patch( 'gpiozero.CPUTemperature', MagicMock( side_effect=OSError( "no sensor" ) ) ),
            patch( 'threading.Thread', thread or MagicMock() ),
            patch( 'time.sleep', MagicMock( side_effect=StopLoop ) ),
            patch.dict( sys.modules, { 'lgpio': None } ),   # no real gpiochip probing
        ]
        for p in patches:
            p.start()
            self.addCleanup( p.stop )
        with redirect_stdout( out ):
            runpy.run_path( PISTORD_PATH, run_name='__main__' )
        return out.getvalue(), loggerClass, fan

    def test_version(self):
        '''VERSION prints the version number.'''
        out, _, _ = self.runMain( 'VERSION' )
        self.assertIn( f"Version: {pistord.PYSTOR_VERSION}", out )

    def test_command_is_case_insensitive(self):
        '''Commands are accepted in any case.'''
        out, _, _ = self.runMain( 'version' )
        self.assertIn( "Version:", out )

    def test_main_logs_to_log_file(self):
        '''Running as a script creates the logger with LOG_PATH.'''
        _, loggerClass, _ = self.runMain( 'VERSION' )
        loggerClass.assert_called_with( pistord.LOG_PATH )

    def test_no_arguments_prints_usage(self):
        '''With no arguments, usage is printed.'''
        out, _, _ = self.runMain()
        self.assertIn( "usage:", out )

    def test_unknown_argument_prints_usage(self):
        '''An unknown command prints usage.'''
        out, _, _ = self.runMain( 'BOGUS' )
        self.assertIn( "usage:", out )

    def test_shutdown_turns_fan_off(self):
        '''SHUTDOWN sets the fan to zero.'''
        _, _, fan = self.runMain( 'SHUTDOWN' )
        self.assertEqual( fan.history, [ 0, 0 ] )   # setupFan() then turnOffFan()

    def test_service_starts_thread(self):
        '''SERVICE starts startFanControl in a background thread.'''
        thread = MagicMock()
        self.runMain( 'SERVICE', thread=thread )
        thread.assert_called_once()
        self.assertEqual( thread.call_args.kwargs['target'].__name__, 'startFanControl' )
        thread.return_value.start.assert_called_once()

    def test_service_thread_failure_is_logged(self):
        '''A failure to start the service thread is logged as an error.'''
        thread = MagicMock( side_effect=RuntimeError( "can't start new thread" ) )
        _, loggerClass, _ = self.runMain( 'SERVICE', thread=thread )
        loggerClass.return_value.error.assert_called_once()

    def test_debug_forces_console_and_runs_in_foreground(self):
        '''DEBUG switches logging to the console and runs fan control directly.'''
        with self.assertRaises( StopLoop ):
            self.runMain( 'DEBUG' )

    def test_debug_with_broken_fan_returns(self):
        '''DEBUG with an unusable fan logs the error and exits normally.'''
        _, loggerClass, _ = self.runMain( 'DEBUG', pwm=MagicMock( side_effect=OSError( "busy" ) ) )
        loggerClass.return_value.forceConsole.assert_called_once()
        loggerClass.return_value.error.assert_called()


if __name__ == "__main__":
    unittest.main()
