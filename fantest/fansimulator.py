'''
Hardware simulator for testing piStor fan control logic without real GPIO.

Provides BoardSimulator, which mimics a Raspberry Pi board by returning
simulated CPU temperatures (affected by fan speed) and recording fan speed
calls. Module-level functions (getCPUTemp, setFanSpeed, startTest, stopTest)
wrap a global BoardSimulator instance for drop-in compatibility with pistord.py.
'''
import time

class BoardSimulator():
    def __init__( self ):
        '''
        Initialize the board simulator with default profiles and state.

        Instance variables:
            _currentTemp   - Last computed CPU temperature (°C).
            _tempCallCount - Number of times getCPUTemp() has been called.
            _fanCallCount  - Number of times setFanSpeed() has been called.
            _cpuProfile    - List of (call_count, base_temp) pairs that model
                             how CPU temperature evolves over time.
            _fanProfile    - List of (fan_speed, temp_reduction) pairs that model
                             the cooling effect of the fan.
            _fanSpeed      - Current fan speed (0.0-1.0).
            _testName      - Name of the active test run.
            _recordData    - Whether temperature readings are written to file.
            _file          - Open file object for data recording, or None.
        '''
        self._currentTemp   = 0
        self._tempCallCount = 0
        self._fanCallCount  = 0
        self._cpuProfile    = [(0,30),(10,32),(11,34),(12,35),(15,40),(25,50),(30,40),(35,50),(40,40),(50,50),(75,60),(90,55),(130,30),(200,30)]
        self._fanProfile    = [(0,0),(0.1,2),(0.20,5),(0.30,10),(0.50,20),(0.60,30),(0.70,35),(0.80,37),(0.90,40),(1.0,50)]
        self._fanSpeed      = 0
        self._testName      = "nothing"
        self._recordData    = False
        self._file          = None
        
    def resetSystem(self):
        '''
        Reset temperature, temp call counter, and fan call counter to zero.
        '''
        self._currentTemp   = 0
        self._tempCallCount = 0
        self._fanCallCount  = 0
        
    def getValueFromProfile( self, key, profile ):
        '''
        Look up a value from a sorted range profile.

        Scans the profile list and returns the value associated with the range
        that contains key. A range [prev[0], next[0]) returns prev[1].

        Parameters:
            key     - The lookup key (e.g. call count or fan speed).
            profile - A list of (range_start, value) tuples sorted ascending
                      by range_start.

        Returns:
            The value for the matching range, or 0 if no range matches.
        '''
        prev = profile[0]
        for next in profile[1:]:
            if key >= prev[0] and key < next[0]:
                return prev[1]
            else:
                prev = next
        return 0
    
    def recordData( self, data ):
        '''
        Write a data value to the output file if recording is enabled.

        Parameters:
            data - The value to append to the current CSV row.
        '''
        if self._recordData:
            self._file.write( f"{data}," )
    
    def getCPUTemp(self):
        '''
        Return the simulated CPU temperature for the current call iteration.

        Increments the temp call counter, looks up the base temperature from
        _cpuProfile using the counter, then subtracts the cooling reduction from
        _fanProfile based on the current fan speed. The result is stored in
        _currentTemp, recorded to file if recording is active, and returned.

        Returns:
            Simulated CPU temperature in degrees Celsius (float).
        '''
        self._tempCallCount += 1
        cputemp   = self.getValueFromProfile( self._tempCallCount, self._cpuProfile )
        reduction = self.getValueFromProfile( self._fanSpeed, self._fanProfile )
        self._currentTemp = cputemp - reduction
        self.recordData( self._currentTemp )
        return self._currentTemp
    
    def setFanSpeed( self, speed ):
        '''
        Set the simulated fan speed and increment the fan call counter.

        Parameters:
            speed - Fan duty cycle as a float in the range 0.0-1.0.

        Raises:
            ValueError - if speed is outside the 0.0-1.0 range.
        '''
        if speed < 0 or speed > 1:
            raise ValueError
        else:
            self._fanCallCount += 1
            self._fanSpeed = speed
            
    def startNamedTest( self, name ):
        '''
        Begin a named test run, resetting system state and writing a row header.

        Parameters:
            name - Label for this test run, written as the first field in the
                   CSV row if data recording is active.
        '''
        self._testName = name
        self.resetSystem()
        if self._recordData:
            self._file.write( f"\n{self._testName}," )
        
    def generateBaseline(self, count = 150):
        '''
        Generate a baseline temperature dataset with no fan intervention.

        Writes a 'baseline' row header to the data file, then calls getCPUTemp()
        `count` times with the fan at its current (default) speed.

        Parameters:
            count - Number of temperature samples to collect (default: 150).
        '''
        self._testName = 'baseline'
        self._file.write( f"\n{self._testName},")
        for i in range(count):
            getCPUTemp()
    
    def createDataFile( self, filename ):
        '''
        Open a CSV data file for appending and enable data recording.

        Parameters:
            filename - Path to the output file. Opened in append mode so
                       multiple test runs can be stored in the same file.
        '''
        try:
            self._file = open( filename, 'a' )
            self._recordData = True
            #self.generateBaseline()
        except Exception as error:
            print( f"Error trying to create data file {filename}.  Error {error}" )
            
    def closeFile( self ):
        '''
        Close the data recording file.
        '''
        self._file.close()
        
sim = BoardSimulator()

def getCPUTemp():
    '''Return the simulated CPU temperature from the global BoardSimulator instance.'''
    return sim.getCPUTemp()

def setFanSpeed( speed ):
    '''Set the simulated fan speed on the global BoardSimulator instance (0.0-1.0).'''
    return sim.setFanSpeed( speed )

def startTest( filename, name ):
    '''
    Open a data file and begin a named test run on the global BoardSimulator instance.

    Parameters:
        filename - Path to the CSV output file.
        name     - Label for this test run.
    '''
    sim.createDataFile( filename )
    sim.startNamedTest( name )

def stopTest():
    '''Close the data recording file on the global BoardSimulator instance.'''
    sim.closeFile()

if __name__ == "__main__":
    fanspeed = 0
    for i in range(150):
        temp = getCPUTemp()
        if temp > 54:
            fanSpeed = 0.4
        elif temp > 40:
            fanSpeed = 0.2
        elif temp > 30:
            fanSpeed = 0.1
        else:
            fanSpeed = 0
        print( f"Pass {i} CPU {temp} Fan {fanSpeed}" )
        setFanSpeed( fanSpeed )
        time.sleep(0.5)
    