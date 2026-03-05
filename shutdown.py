'''
Inter-process shutdown signaling for piStor using POSIX shared memory.

QuickShutdown allows a separate process (e.g. the systemd ExecStop handler)
to signal the running fan control daemon to shut down gracefully by writing
a flag byte into a named shared memory segment.

Note: This module is a work in progress and is not yet integrated into pistord.py.
'''
import threading
from multiprocessing import shared_memory

class QuickShutdown:
    def __init__(self):
        '''
        Create the shared memory segment and thread lock.

        Allocates a 32-byte POSIX shared memory segment named 'Test' and a
        threading.Lock for safe concurrent access to the shutdown flag byte.
        '''
        self._sm = shared_memory.SharedMemory( name='Test', size=32, create=True )
        self._lock = threading.Lock()
        
    def __del__(self):
        '''
        Close and unlink the shared memory segment on object deletion.
        '''
        self._sm.close()
        self._sm.unlink()
        
    @property
    def shutdown( self ) -> int:
        '''
        Return the shutdown flag byte from shared memory (thread-safe).

        Returns:
            0 if no shutdown has been requested, non-zero otherwise.
        '''
        with self._lock:
            return self._sm.buf[0]

    @shutdown.setter
    def shutdown( self, value : int ):
        '''
        Write the shutdown flag byte to shared memory (thread-safe).

        Parameters:
            value - Integer value to write (0 = running, 1 = shutdown requested).
        '''
        with self._lock:
            self._sm.buf[0] = value

    