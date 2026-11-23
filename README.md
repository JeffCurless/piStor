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

piStor can be installed two ways: as a Debian package (recommended) or with the older `setup.sh` script. Both install the same `pistord.service`.

### Debian package (recommended)

Build the package on the Pi (see [Building the Debian Package](#building-the-debian-package)), then install it with apt:

```bash
sudo apt install ./dist/pistor_1.0.1_all.deb
```

apt automatically installs the required Raspberry Pi OS packages, so there is no need for `pip` or a virtual environment:

| Dependency         | Purpose |
|--------------------|---------|
| `python3` (>= 3.10) | Runs the daemon |
| `python3-gpiozero` | Fan PWM output and CPU temperature |
| `python3-lgpio`    | GPIO backend used by gpiozero on the Raspberry Pi 5 |

The package installs:

| Path | Contents |
|------|----------|
| `/usr/lib/pistor/` | The daemon (`pistord.py`, `configtool.py`, `logger.py`) |
| `/etc/pistor.conf` | Default configuration, kept on upgrade and on `apt remove` |
| `/usr/lib/systemd/system/pistord.service` | systemd unit, enabled and started on install |
| `/etc/logrotate.d/pistor` | Rotates `/var/log/piStord.log` weekly, keeping 4 old logs |

If piStor was previously installed with `setup.sh`, the package stops the service and removes the old scripts from `/etc/pistor/`. An existing `/etc/pistor.conf` is kept; if it differs from the packaged default, dpkg asks which version to keep.

**Upgrading** — build or download the newer `.deb` and install it the same way; the service is restarted automatically and your `/etc/pistor.conf` is kept:

```bash
sudo apt install ./dist/pistor_<version>_all.deb
```

**Uninstalling:**

```bash
sudo apt remove pistor    # stop and remove the service, keep /etc/pistor.conf
sudo apt purge pistor     # also delete /etc/pistor.conf
```

**Checking the installed version:**

```bash
dpkg -s pistor | grep Version
```

### Setup script

Alternatively, install the service using the provided setup script. It downloads all required files from GitHub, places them under `/etc/pistor/`, installs the systemd unit, and starts the service. This method has no uninstall support.

```bash
sudo bash setup.sh
```

**Prerequisites** — the `gpiozero` library must be installed before running the setup script:

```bash
sudo apt install python3-gpiozero python3-lgpio
```

### Service Management

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

## Building the Debian Package

The package is built on the Raspberry Pi with `build_deb.sh`. Install the build tools once:

```bash
sudo apt install debhelper dpkg-dev
```

Then build from the top of the repository:

```bash
./build_deb.sh
```

This runs the unit tests, builds `dist/pistor_<version>_all.deb`, and checks it with `lintian` if that is installed. If any test fails, no package is built.

| Command | Effect |
|---------|--------|
| `./build_deb.sh` | Run the unit tests, build the package into `dist/`, and run lintian if installed |
| `./build_deb.sh --no-test` | Build without running the unit tests |
| `./build_deb.sh --bump 1.0.2 "What changed"` | Set a new version (see below), then build |
| `./build_deb.sh --clean` | Remove `dist/` and the debhelper build files |
| `./build_deb.sh --help` | Show usage |

The packaging files live in `debian/`. The package uses its own unit file, `debian/pistor.pistord.service`, because it installs the daemon to `/usr/lib/pistor/`; `src/pistord.service` is used only by `setup.sh`.

### Versioning

Versions have three parts, `Major.Minor.Edit` (for example `1.0.1`):

- **Major** — incompatible changes, such as a new configuration file format.
- **Minor** — new features.
- **Edit** — bug fixes and small changes.

The version is stored in two places that must match: `PYSTOR_VERSION` in `src/pistord.py` and the top entry of `debian/changelog`. Both the build and the unit tests fail if they differ, so always change the version with `--bump`, which updates both and adds a changelog entry:

```bash
./build_deb.sh --bump 1.0.2 "Fix fan speed table parsing."
```

`--bump` only accepts three-part versions and refuses a version that is already in the changelog. Commit `src/pistord.py` and `debian/changelog` together after bumping.

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

The daemon can be run directly from the command line for testing (from the `src/` directory):

```bash
# Print version (e.g. "Version: 1.0.1")
python3 pistord.py VERSION

# Run fan control in the foreground with console logging (no thread spawned)
python3 pistord.py DEBUG

# Start as a background thread (normal service mode)
python3 pistord.py SERVICE

# Signal shutdown
python3 pistord.py SHUTDOWN
```

## Running the Tests

The unit tests live in `tests/` and use Python's built-in `unittest`. All GPIO hardware is mocked, so they run on any machine with Python 3.11+:

```bash
./run_tests.sh                       # run every test (verbose)
./run_tests.sh -q                    # summary only
./run_tests.sh tests.test_pistord    # run one module
```

## Work that needs to be completed

- [x] Implement the initial service for running the fan speed
- [x] Add in support for reading the configuration file
- [x] Add support for proper logging (move the logging out of the main file?)
- [x] Support for selecting the users configuration settings
- [X] Create installer script
- [X] Create Debian package
- [X] Publish scripts on Printables
- [X] Add Uninstall support (Debian package: `apt remove` / `apt purge`)
- [ ] Support other Operating Systems

## Supported Operating Systems

> [!NOTE]
> This code is currently only supported on 64 bit Raspberry PI OS.  There is not current plan to make it operational on any other OS at this time.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

Copyright (c) 2024-2026 Jeff Curless
