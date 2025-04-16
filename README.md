# piStor
Raspberry PI based storage using a Radxa Penta Hat

## STL files for 3d printing the case

- piStor - Case Body.stl     - The main case body.
- piStor - Case Bottom.stl   - The bottom of the case, contains the Raspberry PI 5 and Radxa Penta Hat.
- piStor - Case Top.stl      - The Top of the case.  This protects the fan blades, and redirects air flow.
- piStor - Foot.stl          - Print out of a TPU or Flex filamanet, helps cut down on vibration.
- piStor - MicroSD Hatch.stl - Hatch to cover the SD card area of the PI.

## Build Instructions

## Fan Speed Service

The fan service will operate in one of two modes.

1. Fully automatic and variable.
2. Defined ranges.

With the variable speed fan, as the CPU temperature rises, the Fan speed will increase.  This can, depending on the fan manufacturer cause a irritable fluxuation in the noise comming from the fan, if the settings are change quickly enough.  However with a good fan (Noctua for instance), the fan noise is very limited and I find this very acceptable.

The other option for fan speed is a table of CPU temperatures, with the fan speed set accordingly.  For instance you may decide that if your CPU is running at 65C, you want the fan at 100%, or if its at 40C, you want the speed to be 30%.

30 = 25
40 = 30
50 = 55
65 = 100

The decision as to how yo want the fan controlled is based on the contents of the fanconfig.ini file.

Default fanconfig.ini

```
[mode]
  fancontrol = 0  # 0 - automatic, 1 - Ranges

[FanSpeeds]
  # CPU temp = Fan Speed Percentage
  29 = 0
  30 = 20
  40 = 30
  50 = 40
  60 = 50
  65 = 70
  70 = 100

```

## Work that needs to be completed

- [x] Implement the initial service for running the fan speed
- [ ] Add in support for reading the config file
- [ ] Add support for proper logging (move the logging out of the main file?)
- [ ] Support for selecting the users configuration settings
- [ ] Create installer script
- [ ] Publish scripts on printables

## Supported Operating Systems

> [!NOTE]
> This code is currently only supported on 64 bit Raspberry PI OS.  There is not current plan to make it operational on any other OS at this time.
