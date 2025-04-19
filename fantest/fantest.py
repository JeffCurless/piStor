from fansimulator import getCPUTemp,setFanSpeed
import time

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
    time.sleep(0.1)


