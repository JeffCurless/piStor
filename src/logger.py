# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Logging wrapper for the piStor fan control daemon.

Provides Logger, which writes timestamped lines to a file via the standard
logging module, or prints to the console when file logging is disabled.
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
            print( f"Error: Could not log events due to {error}." )
            self._logEnabled = False

    def info( self, message: object ) -> None:
        '''
        Write the message out using the info level.

        Parameters:
            message - the message to display to the destination

        '''
        if self._logEnabled:
            logging.info( message )
        else:
            print( f"INFO: {message}" )

    def debug( self, message: object ) -> None:
        '''
        Write the message out using the debug level.

        Parameters:
            message - The message to log.
        '''
        if self._logEnabled:
            logging.debug( message )
        else:
            print( f"DEBUG: {message}" )

    def warn( self, message: object ) -> None:
        '''
        Write the message out using the warning level.

        Parameters:
            message - The message to log

        '''
        if self._logEnabled:
            logging.warning( message )
        else:
            print( f"WARN: {message}" )

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
        if self._logEnabled:
            logging.error( message )
        else:
            print( f"ERROR: {message}" )

    def forceConsole(self) -> None:
        '''
        Send all subsequent messages to the console (stdout) instead of the
        log file.  Used in DEBUG mode.
        '''
        self._logEnabled = False
