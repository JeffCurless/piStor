#!/bin/bash
# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
#
# Build the pistor Debian package into dist/.
#
# Usage:
#   ./build_deb.sh                  Build dist/pistor_<version>_all.deb
#   ./build_deb.sh --no-test        Build without running the unit tests
#   ./build_deb.sh --bump 1.1.3 ["msg"]
#                                   Set the version to 1.1.3 in src/pistord.py and
#                                   debian/changelog, then build.  Versions are
#                                   Major.Minor.Edit (three numbers).
#   ./build_deb.sh --clean          Remove dist/ and debhelper build files
#   ./build_deb.sh --help           Show this help
#
# Build tools: sudo apt install debhelper dpkg-dev
#
# Install the result with:
#   sudo apt install ./dist/pistor_<version>_all.deb
# apt pulls in python3-gpiozero and python3-lgpio automatically.

set -euo pipefail
cd "$(dirname "$0")"

DIST=dist
PKG=pistor

usage() {
    sed -n '5,22p' "$0" | sed 's/^# \{0,1\}//'
}

die() {
    echo "build_deb.sh: $*" >&2
    exit 1
}

# Print the PYSTOR_VERSION string from src/pistord.py.
srcVersion() {
    sed -n 's/^PYSTOR_VERSION *= *"\([^"]*\)".*/\1/p' src/pistord.py
}

# Make sure a command exists, naming the apt package that provides it.
need() {
    command -v "$1" >/dev/null 2>&1 || die "'$1' not found; run: sudo apt install $2"
}

clean() {
    rm -rf "$DIST"
    if command -v dh_clean >/dev/null 2>&1; then
        dh_clean
    fi
    echo "Cleaned build output."
}

# Set the version in both src/pistord.py and debian/changelog.
bump() {
    local version=$1
    local message=${2:-"New upstream version $version."}

    [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid version '$version' (expected Major.Minor.Edit, e.g. 1.1.3)"
    [ "$version" != "$(dpkg-parsechangelog -S Version)" ] || die "version $version is already in debian/changelog"

    sed -i "s/^\(PYSTOR_VERSION *= *\)\"[^\"]*\"/\1\"$version\"/" src/pistord.py
    [ "$(srcVersion)" = "$version" ] || die "could not update PYSTOR_VERSION in src/pistord.py"

    # Prepend a new debian/changelog entry, signed by the package maintainer.
    local maintainer changelog
    maintainer=$(sed -n 's/^Maintainer: *//p' debian/control)
    changelog=$(mktemp)
    {
        echo "$PKG ($version) unstable; urgency=medium"
        echo
        # Wrap at 76 columns so lintian accepts the line length.
        echo "$message" | fold -s -w 72 | sed -e '1s/^/  * /' -e '2,$s/^/    /' -e 's/ *$//'
        echo
        echo " -- $maintainer  $(date -R)"
        echo
        cat debian/changelog
    } > "$changelog"
    mv "$changelog" debian/changelog
    chmod 644 debian/changelog
    echo "Version set to $version."
}

RUN_TESTS=1
while [ $# -gt 0 ]; do
    case "$1" in
        --no-test)
            RUN_TESTS=0
            ;;
        --bump)
            [ $# -ge 2 ] || die "--bump needs a version, e.g. --bump 1.1.3"
            if [ $# -ge 3 ] && [[ "$3" != --* ]]; then
                bump "$2" "$3"
                shift 2
            else
                bump "$2"
                shift
            fi
            ;;
        --clean)
            clean
            exit 0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "unknown option '$1'"
            ;;
    esac
    shift
done

need dpkg-buildpackage dpkg-dev
need dh debhelper

# The package version (debian/changelog) must match PYSTOR_VERSION.
PKG_VERSION=$(dpkg-parsechangelog -S Version)
SRC_VERSION=$(srcVersion)
if [ "$PKG_VERSION" != "$SRC_VERSION" ]; then
    die "version mismatch: debian/changelog=$PKG_VERSION, src/pistord.py=$SRC_VERSION
Fix with: ./build_deb.sh --bump $SRC_VERSION"
fi

BUILD_OPTIONS=${DEB_BUILD_OPTIONS:-}
if [ "$RUN_TESTS" -eq 0 ]; then
    BUILD_OPTIONS="$BUILD_OPTIONS nocheck"
fi

echo "Building $PKG $PKG_VERSION..."
DEB_BUILD_OPTIONS="$BUILD_OPTIONS" dpkg-buildpackage -us -uc -b

# dpkg-buildpackage writes to the parent directory; collect the results.
mkdir -p "$DIST"
mv ../"$PKG"_"$PKG_VERSION"_all.deb \
   ../"$PKG"_"$PKG_VERSION"_*.buildinfo \
   ../"$PKG"_"$PKG_VERSION"_*.changes \
   "$DIST"/
dh_clean

DEB="$DIST/${PKG}_${PKG_VERSION}_all.deb"
if command -v lintian >/dev/null 2>&1; then
    echo "Running lintian..."
    lintian "$DEB" || echo "lintian reported issues (see above)."
fi

echo
echo "Built $DEB"
echo "Install with: sudo apt install ./$DEB"
