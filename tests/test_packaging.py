# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Tests for the Debian packaging in debian/.
'''
import os
import re
import unittest

import pistord

from tests import ROOT


class TestPackageVersion( unittest.TestCase ):
    '''The package version must track the daemon's PYSTOR_VERSION.'''

    def test_changelog_matches_daemon_version( self ):
        with open( os.path.join( ROOT, 'debian', 'changelog' ), encoding='utf-8' ) as f:
            first = f.readline()
        match = re.match( r'^pistor \(([^)]+)\)', first )
        self.assertIsNotNone( match, f"Unexpected changelog header: {first!r}" )
        self.assertEqual( match.group( 1 ), pistord.PYSTOR_VERSION )

    def test_version_is_major_minor_edit( self ):
        self.assertRegex( pistord.PYSTOR_VERSION, r'^\d+\.\d+\.\d+$' )

    def test_service_runs_installed_daemon( self ):
        with open( os.path.join( ROOT, 'debian', 'pistor.pistord.service' ),
                   encoding='utf-8' ) as f:
            unit = f.read()
        self.assertIn( '/usr/lib/pistor/pistord.py SERVICE', unit )
        self.assertIn( '/usr/lib/pistor/pistord.py SHUTDOWN', unit )


if __name__ == '__main__':
    unittest.main()
