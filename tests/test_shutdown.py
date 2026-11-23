# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Unit tests for src/shutdown.py (QuickShutdown).

These use real POSIX shared memory, with a unique segment name per test so
they never collide with each other or with a running daemon.
'''
import threading
import unittest
import uuid
from multiprocessing import shared_memory
from unittest.mock import MagicMock, patch

import shutdown
from shutdown import QuickShutdown, SHM_NAME


def segmentExists( name ):
    '''Return True if a shared memory segment with this name exists.'''
    try:
        sm = shared_memory.SharedMemory( name=name, create=False )
    except FileNotFoundError:
        return False
    sm.close()
    return True


class TestQuickShutdown( unittest.TestCase ):
    '''Tests for QuickShutdown.'''

    def setUp( self ):
        self.name = f"piStorTest_{uuid.uuid4().hex[:12]}"
        self.addCleanup( self.cleanupSegment )

    def cleanupSegment( self ):
        '''Remove the test segment if a test left it behind.'''
        try:
            sm = shared_memory.SharedMemory( name=self.name, create=False )
            sm.close()
            sm.unlink()
        except FileNotFoundError:
            pass

    # ---- positive

    def test_creates_segment(self):
        '''Creating an instance creates the named shared memory segment.'''
        qs = QuickShutdown( self.name )
        self.assertTrue( segmentExists( self.name ) )
        del qs

    def test_initial_flag_is_zero(self):
        '''A new segment starts with no shutdown requested.'''
        qs = QuickShutdown( self.name )
        self.assertEqual( qs.shutdown, 0 )

    def test_set_and_get_flag(self):
        '''The flag reads back the value written.'''
        qs = QuickShutdown( self.name )
        qs.shutdown = 1
        self.assertEqual( qs.shutdown, 1 )
        qs.shutdown = 0
        self.assertEqual( qs.shutdown, 0 )

    def test_boundary_values(self):
        '''0 and 255 are the smallest and largest values that fit in the byte.'''
        qs = QuickShutdown( self.name )
        for v in ( 0, 255 ):
            qs.shutdown = v
            self.assertEqual( qs.shutdown, v )

    def test_second_instance_attaches_to_existing_segment(self):
        '''A second instance with the same name shares the first one's flag.'''
        first = QuickShutdown( self.name )
        second = QuickShutdown( self.name )
        first.shutdown = 1
        self.assertEqual( second.shutdown, 1 )

    def test_visible_to_independent_reader(self):
        '''Another process attaching by name sees the flag (simulated here).'''
        qs = QuickShutdown( self.name )
        qs.shutdown = 1
        reader = shared_memory.SharedMemory( name=self.name, create=False )
        try:
            self.assertEqual( reader.buf[0], 1 )
        finally:
            reader.close()

    def test_delete_unlinks_segment(self):
        '''Deleting the instance removes the shared memory segment.'''
        qs = QuickShutdown( self.name )
        del qs
        self.assertFalse( segmentExists( self.name ) )

    def test_default_name(self):
        '''Without a name, the SHM_NAME segment is used.'''
        fake = MagicMock()
        with patch.object( shutdown.shared_memory, 'SharedMemory', return_value=fake ) as sm:
            qs = QuickShutdown()
            sm.assert_called_once_with( name=SHM_NAME, size=32, create=True )
            del qs

    def test_concurrent_writers(self):
        '''Concurrent writes from several threads do not raise.'''
        qs = QuickShutdown( self.name )
        errors = []
        def writer( v ):
            try:
                for _ in range( 200 ):
                    qs.shutdown = v
                    _ = qs.shutdown
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append( e )
        threads = [ threading.Thread( target=writer, args=( v, ) ) for v in range( 4 ) ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual( errors, [] )
        self.assertIn( qs.shutdown, range( 4 ) )

    # ---- negative

    def test_value_too_large_rejected(self):
        '''Values above 255 do not fit in the byte and raise ValueError.'''
        qs = QuickShutdown( self.name )
        with self.assertRaises( ValueError ):
            qs.shutdown = 256
        self.assertEqual( qs.shutdown, 0 )

    def test_negative_value_rejected(self):
        '''Negative values raise ValueError.'''
        qs = QuickShutdown( self.name )
        with self.assertRaises( ValueError ):
            qs.shutdown = -1

    def test_non_integer_value_rejected(self):
        '''Non-integer values raise TypeError.'''
        qs = QuickShutdown( self.name )
        with self.assertRaises( TypeError ):
            qs.shutdown = "1"

    def test_delete_after_other_instance_unlinked(self):
        '''Deleting an instance whose segment was already unlinked does not raise.'''
        first = QuickShutdown( self.name )
        second = QuickShutdown( self.name )
        del first                       # unlinks the segment
        second.__del__()                # pylint: disable=unnecessary-dunder-call

    def test_delete_when_init_failed(self):
        '''__del__ is safe on an object whose __init__ never completed.'''
        qs = QuickShutdown.__new__( QuickShutdown )
        qs.__del__()                    # pylint: disable=unnecessary-dunder-call

    def test_init_error_other_than_exists_propagates(self):
        '''Errors other than "already exists" are raised to the caller.'''
        with patch.object( shutdown.shared_memory, 'SharedMemory',
                           side_effect=PermissionError( "denied" ) ):
            with self.assertRaises( PermissionError ):
                QuickShutdown( self.name )

    def test_invalid_name_rejected(self):
        '''A segment name containing "/" is invalid on Linux.'''
        with self.assertRaises( OSError ):
            QuickShutdown( "bad/name" )


if __name__ == "__main__":
    unittest.main()
