
import time
from gpiozero import PWMOutputDevice
import RPi.GPIO as GPIO

PULSE          = 2
WAIT_TIME      = 1
FAN_PWM_GPIO   = 18     # Fan PWM line is connected to GPIO 13 (Pin 33)
FAN_TACK_GPIO  = 24     # Fan TAC line is connected to GPIO 18

UPDATE_PERIOD  = 5      # Number of seconds between checking the temperature and
                        # modifing the fan speed

GPIO.setmode( GPIO.BCM )
GPIO.setwarnings( False )
GPIO.setup( FAN_TACK_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP )

rpm = 0
t = time.time()

def fell(n):
    '''
    GPIO interrupt callback for falling edges on the tachometer (TAC) signal.

    Called by RPi.GPIO each time FAN_TACK_GPIO goes low. Computes the time
    delta since the last falling edge and converts it to RPM using the PULSE
    constant (pulses per revolution). Updates the global variables `t` (last
    event timestamp) and `rpm` (current fan speed in RPM).

    Edges closer than 0.005 seconds apart are ignored as debounce filtering.

    Parameters:
        n - GPIO channel number (provided by RPi.GPIO, not used directly).

    Globals modified:
        t   - Updated to the current timestamp after a valid edge.
        rpm - Updated with the computed RPM value.
    '''
    global t
    global rpm
    
    dt = time.time()-t
    
    #
    # Leave it the signal happened really fast
    #
    if dt < 0.005: return
    
    freq = 1 / dt
    rpm = int((freq / PULSE) * 60)
    #print( f"dt={dt:3.2} freq = {freq} rpm = {rpm}" )
    t = time.time()

def setupFan(fanPWMGPIO):
    '''
    This routine creates an object that we can utilize to communicate with the
    fan specified by the fanPWMGPIO parameter passed in.

    Parameter:
        fanPWMGPIO - The GPIO pin that the FAN PWM pin is connected to

    Returns:
        A fan object, with speed set to zero
    '''
    _fan = None
    try:
        _fan = PWMOutputDevice( fanPWMGPIO, frequency=100)
        _fan.value = 0
    except Exception as error:
        print( f"Error attempting to create output PWM device, error is {error}" )
        raise ValueError( "Cannot setup Fan!" )
      
    return _fan

t = time.time()
GPIO.add_event_detect( FAN_TACK_GPIO, GPIO.FALLING, fell )
fan = setupFan(FAN_PWM_GPIO)

for speed in range(0,105,5):
    print( f"Setting speed to {speed}" )
    fan.value = speed/100
    for i in range( UPDATE_PERIOD ):
        print( f"RPM = {rpm}" )
        time.sleep( WAIT_TIME )
    
fan.value = 0



