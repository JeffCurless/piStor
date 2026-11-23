# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Fan control test script for piStor.

Exercises the BoardSimulator by running a simulated fan control loop over
150 iterations, adjusting fan speed based on CPU temperature thresholds and
recording results to fantest.csv (test name 'run2') via the fansimulator
module.  The fan speed is only sent when it changes.
'''
from fansimulator import getCPUTemp,setFanSpeed,startTest,stopTest

startTest( 'fantest.csv', 'run2' )

fanSpeed = 0.0
prevSpeed = 0.0
for i in range(150):
    temp = getCPUTemp()
    if temp > 54:
        fanSpeed = 0.4
    elif temp > 40:
        fanSpeed = 0.2
    elif temp > 30:
        fanSpeed = 0.1
    else:
        fanSpeed = 0.0
    print( f"Pass {i} CPU {temp} Fan {fanSpeed}" )
    if fanSpeed != prevSpeed:
        setFanSpeed( fanSpeed )
        prevSpeed = fanSpeed
    #time.sleep(0.1)

stopTest()
