#
#
#
import os
import configparser

AUTO_FAN = 1
MANUAL_FAN = 0

class piStorConfig():
    def __init__( self, filename : str ="" ):
        '''
        Initialize the configuration object, so that the configuration can be
        utiized within the piStor application.
        '''
        self.filename  = filename
        self.configObj = configparser.ConfigParser()
        if filename != "":
            self.loadConfig( filename )
    
    def loadConfig( self, filename : str ):
        '''
        Load the configuration file into memory
        '''
        try:
            if os.path.isfile( filename ):
                self.configObj.read( filename )
                self.filename = filename
            else:
                raise FileNotFoundError( f"Configuration file {filename} does not exist." )
        except Exception as error:
            print( f"Error: {error}" )
            
    def __iter__( self ):
        '''
        Make this configuration object iterable.  Iterations occur on the
        sections of the configuration file
        '''
        self.index = 0
        self.sections = self.configObj.sections()
        return self
    
    def __next__( self ) -> str:
        '''
        This routine returns the next item in the sections list, or a
        stop iteration exception if we have no more sections.
        
        Returns:
            the name of the next section
        '''
        if self.index < len(self.sections ):
            index = self.index
            self.index += 1
            return self.sections[index]
        else:
            raise StopIteration()
        
    def getFanSpeed( self ) -> list[tuple[int,int]]:
        '''
        This member function returns a list of tuples.  The first paramter is
        the CPU temperature, the second parameter of the tuple is the fan speed.
        
        If there is no FanSpeeds section in the configuration file, a default
        value is returned, which essentially sets the fan speed to 100%
        
        Returns:
            A list of tuples used for controlling the fan speed...
        '''
        speeds = []
        try:
            for item in self.configObj['FanSpeeds']:
                temp = int(item)
                speed = int(self.configObj['FanSpeeds'][item])
                speeds.append( (temp,speed) )
        except Exception as error:
            print( f"Error: No section in configuration file named {error}" )
            speeds = [(20,0),(30,100)]

        return speeds
    
    def getMode( self ) -> int:
        '''
        This function obtains the fan mode from the configuration file.  If there
        is any issue obtaining the fan mode, automatic mode is selected.
        
        Mode Values:
            0 - Manual mode.  Utilize the fanspeed list to determine the fan
                speed based on the CPU temperature.
            1 - Automatic mode.  Modify the fan speed based on CPU temperature,
                no table is selected.
                
        Automatic mode is usually better, however if the system is running in a
        high temperature area, or there are additional factors not realted to CPU
        temperature, manual mode can be used to intensify, or decrease the overall
        fan speed.
        
        Returns:
            An integer representing the mode we are in.
        '''
        mode = 1
        try:
            mode = self.configObj.getint('mode','autofan')
        except Exception as error:
            print( f"Error: Could not locate key {error}" )
        return mode
        

if __name__ == "__main__":
    print( "Create configuration object..." )
    config = piStorConfig('./pistor.conf' )
        
    print( f"Speeds = {config.getFanSpeed()}" )
    print( f"Mode = {config.getMode()}" )
    