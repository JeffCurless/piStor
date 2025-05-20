from fansimulator import getCPUTemp,setFanSpeed,startTest,stopTest
import time

startTest( 'fantest.csv', 'run2' )

fanSpeed = 0
prevSpeed = 0
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
    if fanSpeed != prevSpeed:
        setFanSpeed( fanSpeed )
        prevSpeed = fanSpeed
    #time.sleep(0.1)
    
stopTest()


