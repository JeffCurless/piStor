#
#
#
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
    def __init__(self,filename=None,level=logging.DEBUG):
        '''
        Initialize the logger.

        Parameters:
            filename - Path to the log file. Pass None to disable file logging
                       and fall back to console print statements.
            level    - Logging level (default: logging.DEBUG).
        '''
        self._logEnabled = True
        try:
            if filename == None:
                self._logEnabled = False
            else:
                logging.basicConfig( filename=filename,
                                     filemode='a',
                                     level=level,
                                     format='%(asctime)s %(process)d [%(levelname)s] %(message)s',
                                     datefmt='%b %d %y %H:%M:%S')
        except Exception as error:
            print( f"Error: Could not log events due to {error}." )
            self._logEnabled = False
            
    def info( self, message ):
        '''
        Write the message out using the info level
        
        Parameters:
            message - the message to display to the destination

        '''
        if self._logEnabled:
            logging.info( message )
        else:
            print( f"INFO: {message}" )
    
    def debug( self, message ):
        '''
        Write the message out using the debug level.

        Parameters:
            message - The message to log.
        '''
        if self._logEnabled:
            logging.debug( message )
        else:
            print( f"DEBUG: {message}" )
    
    def warn( self, message ):
        '''
        Write the message out using the warn level
 
        Parameters:
            message - The message to log

        '''
        if self._logEnabled:
            logging.warning( message )
        else:
            print( f"WARN: {message}" )

    def warning( self, message ):
        '''
        Write the message out using the warning level. Alias for warn().

        Parameters:
            message - The message to log.
        '''
        self.warn( message )

    def error( self, message ):
        '''
        Write the message out using the error level

        Parameters:
            message - The message to log

        '''
        if self._logEnabled:
            logging.error( message )
        else:
            print( f"(ERROR: {message}" )
    
    def forceConsole(self):
        '''
        This routine forces all logging messages to the console.
        
        '''
        self._logEnabled = False
#
# 
#
import unittest
import tempfile
import os
from unittest.mock import patch

class TestLogger(unittest.TestCase):

    def setUp(self):
        '''
        Clear root logger handlers before each test.

        logging.basicConfig() is a no-op when handlers already exist, so we
        must reset between tests to allow each one to configure fresh.
        '''
        for h in logging.root.handlers[:]:
            h.close()
            logging.root.removeHandler(h)

    def tearDown(self):
        '''Close and remove all handlers so temp files can be deleted.'''
        for h in logging.root.handlers[:]:
            h.close()
            logging.root.removeHandler(h)

    def _temp_log_path(self):
        '''Return the path of a new empty temp file.'''
        f = tempfile.NamedTemporaryFile(suffix='.log', delete=False)
        f.close()
        return f.name

    def _flush(self):
        '''Flush all root logger handlers.'''
        for h in logging.root.handlers:
            h.flush()

    # ------------------------------------------------------------------ __init__

    def test_init_none_disables_file_logging(self):
        '''Logger(None) should set _logEnabled to False.'''
        log = Logger(None)
        self.assertFalse(log._logEnabled)

    def test_init_valid_file_enables_logging(self):
        '''Logger with a writable path should set _logEnabled to True.'''
        path = self._temp_log_path()
        try:
            log = Logger(path)
            self.assertTrue(log._logEnabled)
        finally:
            os.unlink(path)

    def test_init_valid_file_creates_file(self):
        '''Logger with a valid path should create or open the log file on disk.'''
        path = self._temp_log_path()
        try:
            Logger(path)
            self.assertTrue(os.path.exists(path))
        finally:
            os.unlink(path)

    def test_init_bad_path_disables_logging(self):
        '''A path into a non-existent directory should be caught; _logEnabled set False.'''
        log = Logger('/nonexistent/directory/test.log')
        self.assertFalse(log._logEnabled)

    def test_init_empty_string_does_not_disable_logging(self):
        '''
        Logger("") leaves _logEnabled True.

        logging.basicConfig() treats an empty string as falsy and silently
        falls back to a StreamHandler rather than raising an error, so no
        exception reaches the except block and _logEnabled is not set False.
        This is a subtlety worth knowing: Logger("") is NOT equivalent to
        Logger(None).
        '''
        log = Logger("")
        self.assertTrue(log._logEnabled)

    # ------------------------------------------------------------------ forceConsole

    def test_forceconsole_sets_log_disabled(self):
        '''forceConsole() on a file-backed logger should set _logEnabled to False.'''
        path = self._temp_log_path()
        try:
            log = Logger(path)
            self.assertTrue(log._logEnabled)
            log.forceConsole()
            self.assertFalse(log._logEnabled)
        finally:
            os.unlink(path)

    def test_forceconsole_on_console_logger_is_idempotent(self):
        '''Calling forceConsole() when already in console mode leaves _logEnabled False.'''
        log = Logger(None)
        log.forceConsole()
        self.assertFalse(log._logEnabled)

    def test_forceconsole_redirects_subsequent_calls_to_print(self):
        '''After forceConsole(), log methods should print instead of writing to file.'''
        path = self._temp_log_path()
        try:
            log = Logger(path)
            log.forceConsole()
            with patch('builtins.print') as mock_print:
                log.info("redirected")
                mock_print.assert_called_once()
                self.assertIn("redirected", mock_print.call_args[0][0])
        finally:
            os.unlink(path)

    # ------------------------------------------------------------------ console output format

    def test_info_console_prefix(self):
        '''info() should print "INFO: <message>" to the console.'''
        log = Logger(None)
        with patch('builtins.print') as mock_print:
            log.info("hello")
            mock_print.assert_called_once_with("INFO: hello")

    def test_debug_console_prefix(self):
        '''debug() should print "DEBUG: <message>" to the console.'''
        log = Logger(None)
        with patch('builtins.print') as mock_print:
            log.debug("hello")
            mock_print.assert_called_once_with("DEBUG: hello")

    def test_warn_console_prefix(self):
        '''warn() should print "WARN: <message>" to the console.'''
        log = Logger(None)
        with patch('builtins.print') as mock_print:
            log.warn("hello")
            mock_print.assert_called_once_with("WARN: hello")

    def test_warning_console_prefix(self):
        '''warning() should print "WARN: <message>", identical to warn().'''
        log = Logger(None)
        with patch('builtins.print') as mock_print:
            log.warning("hello")
            mock_print.assert_called_once_with("WARN: hello")

    def test_error_console_prefix(self):
        '''error() should print "(ERROR: <message>" — note the unmatched leading paren.'''
        log = Logger(None)
        with patch('builtins.print') as mock_print:
            log.error("hello")
            mock_print.assert_called_once_with("(ERROR: hello")

    def test_console_empty_message(self):
        '''All log methods should handle an empty string message without error.'''
        log = Logger(None)
        with patch('builtins.print') as mock_print:
            log.info("")
            mock_print.assert_called_once_with("INFO: ")

    def test_console_none_message_does_not_raise(self):
        '''Log methods should accept None as a message and not raise an exception.'''
        log = Logger(None)
        with patch('builtins.print'):
            try:
                log.info(None)
                log.debug(None)
                log.warn(None)
                log.error(None)
            except Exception as e:
                self.fail(f"Logging None raised: {e}")

    def test_console_long_message(self):
        '''Log methods should handle a very long message without truncating.'''
        log = Logger(None)
        long_msg = "x" * 10000
        with patch('builtins.print') as mock_print:
            log.info(long_msg)
            mock_print.assert_called_once_with(f"INFO: {long_msg}")

    def test_console_unicode_message(self):
        '''Log methods should pass unicode characters through unchanged.'''
        log = Logger(None)
        msg = "caf\u00e9 \u4e2d\u6587"
        with patch('builtins.print') as mock_print:
            log.info(msg)
            mock_print.assert_called_once_with(f"INFO: {msg}")

    def test_console_percent_in_message_does_not_raise(self):
        '''A message containing % should not cause a string formatting error.'''
        log = Logger(None)
        with patch('builtins.print') as mock_print:
            log.info("100% complete")
            mock_print.assert_called_once_with("INFO: 100% complete")

    def test_console_newline_in_message(self):
        '''A message containing a newline should be passed through as-is.'''
        log = Logger(None)
        msg = "line1\nline2"
        with patch('builtins.print') as mock_print:
            log.info(msg)
            mock_print.assert_called_once_with(f"INFO: {msg}")

    # ------------------------------------------------------------------ warning alias

    def test_warning_is_alias_for_warn(self):
        '''warning() and warn() should produce identical console output.'''
        log = Logger(None)
        with patch('builtins.print') as mock_print:
            log.warn("test message")
            warn_args = mock_print.call_args

        with patch('builtins.print') as mock_print:
            log.warning("test message")
            warning_args = mock_print.call_args

        self.assertEqual(warn_args, warning_args)

    # ------------------------------------------------------------------ file mode output

    def test_file_info_written(self):
        '''info() should write the message to the log file.'''
        path = self._temp_log_path()
        try:
            log = Logger(path)
            log.info("info test message")
            self._flush()
            with open(path) as f:
                self.assertIn("info test message", f.read())
        finally:
            os.unlink(path)

    def test_file_debug_written(self):
        '''debug() should write the message to the log file.'''
        path = self._temp_log_path()
        try:
            log = Logger(path)
            log.debug("debug test message")
            self._flush()
            with open(path) as f:
                self.assertIn("debug test message", f.read())
        finally:
            os.unlink(path)

    def test_file_warn_written(self):
        '''warn() should write the message to the log file.'''
        path = self._temp_log_path()
        try:
            log = Logger(path)
            log.warn("warn test message")
            self._flush()
            with open(path) as f:
                self.assertIn("warn test message", f.read())
        finally:
            os.unlink(path)

    def test_file_error_written(self):
        '''error() should write the message to the log file.'''
        path = self._temp_log_path()
        try:
            log = Logger(path)
            log.error("error test message")
            self._flush()
            with open(path) as f:
                self.assertIn("error test message", f.read())
        finally:
            os.unlink(path)

    def test_file_level_labels_present(self):
        '''Log file entries should include bracketed level labels from the format string.'''
        path = self._temp_log_path()
        try:
            log = Logger(path)
            log.info("label check")
            log.error("error label check")
            self._flush()
            with open(path) as f:
                content = f.read()
            self.assertIn("[INFO]",  content)
            self.assertIn("[ERROR]", content)
        finally:
            os.unlink(path)

    def test_file_opened_in_append_mode(self):
        '''Logger should open the file in append mode, preserving existing content.'''
        path = self._temp_log_path()
        try:
            with open(path, 'w') as f:
                f.write("pre-existing content\n")
            log = Logger(path)
            log.info("new entry")
            self._flush()
            with open(path) as f:
                content = f.read()
            self.assertIn("pre-existing content", content)
            self.assertIn("new entry", content)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()


