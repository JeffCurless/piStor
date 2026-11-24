# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Logging wrapper for the piStor fan control daemon.

Provides Logger, which writes timestamped lines to a file via the standard
logging module, or prints to the console when file logging is disabled.
Every message is flushed as soon as it is written, so the log file (or
console / journal) is always up to date even if the daemon is killed.
'''
import logging

#
# Logger - A class that is used to wrap the logging class... so we can export
#          directly to the console in debug mode, and handle any other change
#          required
#
class Logger:
    '''
    Thin wrapper around Python's logging module for piStor.

    Writes timestamped log lines to a file. Call forceConsole() to redirect
    all output to stdout instead (used in DEBUG mode).
    '''
    def __init__(self, filename: str | None = None, level: int = logging.DEBUG) -> None:
        '''
        Initialize the logger.

        Parameters:
            filename - Path to the log file. Pass None to disable file logging
                       and fall back to console print statements.  If the file
                       cannot be opened, an error is printed and console
                       output is used instead.  Note that "" is not the same
                       as None: logging then writes to stderr instead.
            level    - Logging level (default: logging.DEBUG).
        '''
        self._logEnabled = True
        try:
            if filename is None:
                self._logEnabled = False
            else:
                logging.basicConfig( filename=filename,
                                     filemode='a',
                                     level=level,
                                     format='%(asctime)s %(process)d [%(levelname)s] %(message)s',
                                     datefmt='%b %d %y %H:%M:%S')
        except Exception as error:  # pylint: disable=broad-exception-caught
            print( f"Error: Could not log events due to {error}.", flush=True )
            self._logEnabled = False

    def _write( self, level: int, prefix: str, message: object ) -> None:
        '''
        Write one message to the log file or console, then flush it.

        Parameters:
            level   - logging level used when writing to the log file.
            prefix  - Label printed before the message in console mode.
            message - The message to log.
        '''
        if self._logEnabled:
            logging.log( level, message )
            for handler in logging.root.handlers:
                try:
                    handler.flush()
                except Exception:  # pylint: disable=broad-exception-caught
                    pass    # A failed flush must never take down the daemon
        else:
            print( f"{prefix}: {message}", flush=True )

    def info( self, message: object ) -> None:
        '''
        Write the message out using the info level.

        Parameters:
            message - the message to display to the destination

        '''
        self._write( logging.INFO, "INFO", message )

    def debug( self, message: object ) -> None:
        '''
        Write the message out using the debug level.

        Parameters:
            message - The message to log.
        '''
        self._write( logging.DEBUG, "DEBUG", message )

    def warn( self, message: object ) -> None:
        '''
        Write the message out using the warning level.

        Parameters:
            message - The message to log

        '''
        self._write( logging.WARNING, "WARN", message )

    def warning( self, message: object ) -> None:
        '''
        Write the message out using the warning level. Alias for warn().

        Parameters:
            message - The message to log.
        '''
        self.warn( message )

    def error( self, message: object ) -> None:
        '''
        Write the message out using the error level.

        Parameters:
            message - The message to log

        '''
        self._write( logging.ERROR, "ERROR", message )

    def forceConsole(self) -> None:
        '''
        Send all subsequent messages to the console (stdout) instead of the
        log file.  Used in DEBUG mode.
        '''
        self._logEnabled = False
