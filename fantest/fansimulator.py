import time

class BoardSimulator():
    def __init__( self ):
        self._currentTemp   = 0
        self._tempCallCount = 0
        self._fanCallCount  = 0
        self._cpuProfile    = [(0,30),(10,32),(11,34),(12,35),(15,40),(25,50),(30,40),(35,50),(40,40),(50,50),(75,60),(90,55),(130,30),(200,30)]
        self._fanProfile    = [(0,0),(0.1,2),(0.20,5),(0.30,10),(0.50,20),(0.60,30),(0.70,35),(0.80,37),(0.90,40),(1.0,50)]
        self._fanSpeed      = 0

    def getValueFromProfile( self, key, profile ):
        prev = profile[0]
        for next in profile[1:]:
            if key >= prev[0] and key < next[0]:
                return prev[1]
            else:
                prev = next
        return 0
    
    def getCPUTemp(self):
        '''
        Using the temperature call count, make determine the temperature of the CPU based on the
        current fan speed (and the fan profile).
        '''
        self._tempCallCount += 1
        cputemp   = self.getValueFromProfile( self._tempCallCount, self._cpuProfile )
        reduction = self.getValueFromProfile( self._fanSpeed, self._fanProfile )
        #print( f"{cputemp} {reduction} {cputemp-reduction}" )
        self._currentTemp = cputemp - reduction
        return self._currentTemp
    
    def setFanSpeed( self, speed ):
        if speed < 0 or speed > 1:
            raise ValueError
        else:
            self._fanCallCount += 1
            self._fanSpeed = speed
            
sim = BoardSimulator()

def getCPUTemp():
    return sim.getCPUTemp()

def setFanSpeed( speed ):
    return sim.setFanSpeed( speed )

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
    