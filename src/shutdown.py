# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Inter-process shutdown signaling for piStor using POSIX shared memory.

QuickShutdown allows a separate process (e.g. the systemd ExecStop handler)
to signal the running fan control daemon to shut down gracefully by writing
a flag byte into a named shared memory segment.

Note: This module is a work in progress and is not yet integrated into pistord.py.
'''
import threading
from multiprocessing import shared_memory

SHM_NAME = 'piStorShutdown'

class QuickShutdown:
    '''
    Shutdown flag shared between processes via POSIX shared memory.
    '''
    def __init__(self, name: str = SHM_NAME) -> None:
        '''
        Create (or attach to) the shared memory segment and thread lock.

        Allocates a 32-byte POSIX shared memory segment with the given name and
        a threading.Lock for safe concurrent access to the shutdown flag byte.
        If a segment with that name already exists (another instance, or one
        left behind by a crash), it is attached to instead of failing.

        Parameters:
            name - Name of the shared memory segment.
        '''
        self._sm: shared_memory.SharedMemory | None = None
        self._lock = threading.Lock()
        try:
            self._sm = shared_memory.SharedMemory( name=name, size=32, create=True )
        except FileExistsError:
            self._sm = shared_memory.SharedMemory( name=name, create=False )

    def __del__(self) -> None:
        '''
        Close and unlink the shared memory segment on object deletion.  Safe to
        call even if __init__ failed or the segment was already unlinked.
        '''
        sm = getattr( self, '_sm', None )
        if sm is None:
            return
        sm.close()
        try:
            sm.unlink()
        except FileNotFoundError:
            pass

    @property
    def shutdown( self ) -> int:
        '''
        Return the shutdown flag byte from shared memory (thread-safe).

        Returns:
            0 if no shutdown has been requested, non-zero otherwise.
        '''
        assert self._sm is not None
        with self._lock:
            return self._sm.buf[0]

    @shutdown.setter
    def shutdown( self, value : int ) -> None:
        '''
        Write the shutdown flag byte to shared memory (thread-safe).

        Parameters:
            value - Integer value to write, 0-255 (0 = running,
                    1 = shutdown requested).
        '''
        assert self._sm is not None
        with self._lock:
            self._sm.buf[0] = value
