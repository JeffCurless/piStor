#!/bin/bash
# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
#
# Run the piStor unit tests.
#
# Usage:
#   ./run_tests.sh                     Run every test in tests/ (verbose)
#   ./run_tests.sh -q                  Run every test, printing only a summary
#   ./run_tests.sh tests.test_pistord  Run one test module
#   ./run_tests.sh tests.test_pistord.TestGetFanSpeed.test_empty_table_falls_back_to_full_speed
#
# Set PYTHON to use a different interpreter (default: python3).
# No Raspberry Pi hardware is needed: all GPIO access is mocked.

set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
export PYTHONDONTWRITEBYTECODE=1    # keep __pycache__ out of src/ and fantest/

VERBOSITY=-v
if [ "${1:-}" = "-q" ]; then
    VERBOSITY=
    shift
fi

if [ $# -eq 0 ]; then
    exec "$PYTHON" -m unittest discover -s tests -t . $VERBOSITY
else
    exec "$PYTHON" -m unittest $VERBOSITY "$@"
fi
