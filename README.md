# piStor
Raspberry PI based storage using a Radxa Penta Hat

## STL files for 3d printing the case

- piStor - Case Body.stl     - The main case body.
- piStor - Case Bottom.stl   - The bottom of the case, contains the Raspberry PI 5 and Radxa Penta Hat.
- piStor - Case Top.stl      - The Top of the case.  This protects the fan blades, and redirects air flow.
- piStor - Foot.stl          - Print out of a TPU or Flex filament, helps cut down on vibration.
- piStor - MicroSD Hatch.stl - Hatch to cover the SD card area of the PI.

## Build Instructions

## Installation

Install the service using the provided setup script. It downloads all required files from GitHub, places them under `/etc/pistor/`, installs the systemd unit, and starts the service.

```bash
sudo bash setup.sh
```

**Prerequisites** — the `gpiozero` library must be installed before running the setup script:

```bash
sudo pip3 install gpiozero
```

**Service management after install:**

```bash
sudo systemctl status pistord.service
sudo systemctl start pistord.service
sudo systemctl stop pistord.service
sudo systemctl restart pistord.service
```

**Logs** are written to `/var/log/piStord.log` and can also be viewed via journald:

```bash
journalctl -u pistord.service
```

## Fan Speed Service

### Hardware

The service controls a PWM fan connected to the following GPIO pins on the Raspberry Pi 5:

| Signal      | GPIO | Header Pin |
|-------------|------|------------|
| PWM control | 13   | Pin 33     |
| Tachometer  | 18   | —          |

### Fan Control Modes

The service operates in one of two modes, selected by the `autofan` key in `/etc/pistor.conf`.

#### Automatic Mode (`autofan = 1`)

Fan speed is set continuously based on CPU temperature. Every 5 seconds the daemon reads the CPU temperature as a 0.0–1.0 value (where 0.0 = 0 °C and 1.0 = 100 °C) and adds 0.1 of headroom, clamped to a maximum of 1.0 (100%). For example, a CPU at 50 °C produces a fan duty cycle of 60%.

This can, depending on the fan manufacturer, cause fluctuation in fan noise as temperature changes. However with a quality fan (such as a Noctua), the variation is minimal.

#### Manual Mode (`autofan = 0`)

Fan speed is determined by a temperature threshold table defined in the `[FanSpeeds]` section of the config file. The daemon walks the table every 5 seconds and applies the speed for the highest threshold the CPU temperature meets or exceeds. If the CPU temperature is below all thresholds the fan runs at 100% as a safe fallback.

Example table:

```ini
[FanSpeeds]
  30 = 25   # at or above 30 °C → 25% fan speed
  40 = 30   # at or above 40 °C → 30%
  50 = 55   # at or above 50 °C → 55%
  65 = 100  # at or above 65 °C → 100%
```

### Configuration File

The configuration file is installed at `/etc/pistor.conf`. If the file is missing when the service starts, it will log a warning and run in automatic mode with default settings.

```ini
[mode]
   autofan = 1        # 1 = automatic mode, 0 = manual table mode

[FanSpeeds]           # Only used when autofan = 0
   20 = 0             # CPU temp (°C) = fan speed (%)
   30 = 20
   40 = 30
   50 = 40
   60 = 50
   65 = 70
   70 = 100
```

### Running Locally

The daemon can be run directly from the command line for testing:

```bash
# Print version
python3 pistord.py VERSION

# Run fan control in the foreground with console logging (no thread spawned)
python3 pistord.py DEBUG

# Start as a background thread (normal service mode)
python3 pistord.py SERVICE

# Signal shutdown
python3 pistord.py SHUTDOWN
```

## Work that needs to be completed

- [x] Implement the initial service for running the fan speed
- [x] Add in support for reading the configuration file
- [x] Add support for proper logging (move the logging out of the main file?)
- [x] Support for selecting the users configuration settings
- [X] Create installer script
- [X] Publish scripts on Printables
- [ ] Add Uninstall support
- [ ] Support other Operating Systems

## Supported Operating Systems

> [!NOTE]
> This code is currently only supported on 64 bit Raspberry PI OS.  There is not current plan to make it operational on any other OS at this time.
