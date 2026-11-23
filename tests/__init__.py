# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Test package for piStor.

Importing this package puts src/ and fantest/ on sys.path so test modules can
import the code under test directly.  If gpiozero is not installed (e.g. when
running on a development machine instead of a Raspberry Pi) a minimal stub is
registered so pistord.py can still be imported; every test patches the
hardware classes anyway, so no real GPIO is ever touched.
'''
import os
import sys
import types

ROOT    = os.path.dirname( os.path.dirname( os.path.abspath( __file__ ) ) )
SRC     = os.path.join( ROOT, 'src' )
FANTEST = os.path.join( ROOT, 'fantest' )

for _path in ( SRC, FANTEST ):
    if _path not in sys.path:
        sys.path.insert( 0, _path )

try:
    import gpiozero  # pylint: disable=unused-import
except ImportError:
    _stub = types.ModuleType( 'gpiozero' )

    class _NoHardware:  # pylint: disable=too-few-public-methods
        '''Placeholder that fails loudly if a test forgets to patch it.'''
        def __init__( self, *args, **kwargs ):
            raise RuntimeError( 'gpiozero stub: patch this class in the test' )

    _stub.PWMOutputDevice = _NoHardware
    _stub.CPUTemperature  = _NoHardware
    sys.modules['gpiozero'] = _stub
