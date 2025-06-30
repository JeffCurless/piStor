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
    Initialize the logger.  
    '''
    def __init__(self,filename=None,level=logging.DEBUG):
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
        Write the message out using the deug level
        
        Parameters:
            message - The message to log
            
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
if __name__ == "__main__":
    log = Logger("test.log")
    log.warn( "Testing..." )


