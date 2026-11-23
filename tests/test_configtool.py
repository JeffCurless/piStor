# Copyright (c) 2024-2026 Jeff Curless
# SPDX-License-Identifier: MIT
'''
Unit tests for src/configtool.py (piStorConfig).
'''
import os
import tempfile
import unittest
from contextlib import redirect_stdout
import io

from configtool import AUTO_FAN, MANUAL_FAN, piStorConfig
from tests import SRC

class TestPiStorConfig(unittest.TestCase):
    '''Unit tests for piStorConfig.'''

    # ------------------------------------------------------------------ helpers

    def _make_conf(self, content):
        '''Write content to a temp file and return its path.'''
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(content)
        f.close()
        return f.name

    def _remove(self, path):
        '''Delete path if it exists.'''
        if os.path.exists(path):
            os.unlink(path)

    # ------------------------------------------------------------------ __init__

    def test_init_empty_filename_skips_load(self):
        '''Empty filename should not call loadConfig; config stays empty.'''
        config = piStorConfig()
        self.assertEqual(config.filename, "")
        self.assertEqual(config.configObj.sections(), [])

    def test_init_valid_file_loads_config(self):
        '''A valid file path passed to __init__ should be loaded automatically.'''
        path = self._make_conf("[mode]\nautofan = 1\n")
        try:
            config = piStorConfig(path)
            self.assertEqual(config.filename, path)
            self.assertIn('mode', config.configObj.sections())
        finally:
            self._remove(path)

    def test_init_missing_file_does_not_raise(self):
        '''A missing file path should be handled silently; config stays empty.'''
        config = piStorConfig('/nonexistent/path/pistor.conf')
        self.assertEqual(config.configObj.sections(), [])

    # ------------------------------------------------------------------ loadConfig

    def test_loadconfig_missing_file_leaves_config_empty(self):
        '''loadConfig with a non-existent path leaves configObj unchanged.'''
        config = piStorConfig()
        config.loadConfig('/nonexistent/path.conf')
        self.assertEqual(config.configObj.sections(), [])

    def test_loadconfig_updates_filename_on_success(self):
        '''loadConfig should update self.filename when the file is read.'''
        path = self._make_conf("[mode]\nautofan = 0\n")
        try:
            config = piStorConfig()
            config.loadConfig(path)
            self.assertEqual(config.filename, path)
        finally:
            self._remove(path)

    def test_loadconfig_empty_string_treated_as_missing(self):
        '''loadConfig("") should not load anything; os.path.isfile("") is False.'''
        config = piStorConfig()
        config.loadConfig("")
        self.assertEqual(config.configObj.sections(), [])

    def test_loadconfig_can_reload_different_file(self):
        '''Calling loadConfig a second time merges the new file, overriding existing values.'''
        path1 = self._make_conf("[mode]\nautofan = 1\n")
        path2 = self._make_conf("[mode]\nautofan = 0\n")
        try:
            config = piStorConfig(path1)
            self.assertEqual(config.getMode(), AUTO_FAN)
            config.loadConfig(path2)
            self.assertEqual(config.getMode(), MANUAL_FAN)
        finally:
            self._remove(path1)
            self._remove(path2)

    # ------------------------------------------------------------------ getMode

    def test_getmode_returns_auto_fan(self):
        '''autofan = 1 should return AUTO_FAN.'''
        path = self._make_conf("[mode]\nautofan = 1\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), AUTO_FAN)
        finally:
            self._remove(path)

    def test_getmode_returns_manual_fan(self):
        '''autofan = 0 should return MANUAL_FAN.'''
        path = self._make_conf("[mode]\nautofan = 0\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), MANUAL_FAN)
        finally:
            self._remove(path)

    def test_getmode_no_section_defaults_to_auto(self):
        '''Missing [mode] section should default to AUTO_FAN.'''
        self.assertEqual(piStorConfig().getMode(), AUTO_FAN)

    def test_getmode_missing_key_defaults_to_auto(self):
        '''[mode] section with no autofan key should default to AUTO_FAN.'''
        path = self._make_conf("[mode]\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), AUTO_FAN)
        finally:
            self._remove(path)

    def test_getmode_non_integer_value_defaults_to_auto(self):
        '''Non-integer autofan value should be caught and default to AUTO_FAN.'''
        path = self._make_conf("[mode]\nautofan = abc\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), AUTO_FAN)
        finally:
            self._remove(path)

    def test_getmode_unknown_integer_returned_as_is(self):
        '''An integer autofan value other than 0 or 1 is returned without validation.'''
        path = self._make_conf("[mode]\nautofan = 99\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), 99)
        finally:
            self._remove(path)

    def test_getmode_negative_value_returned_as_is(self):
        '''A negative autofan integer is returned without validation.'''
        path = self._make_conf("[mode]\nautofan = -1\n")
        try:
            self.assertEqual(piStorConfig(path).getMode(), -1)
        finally:
            self._remove(path)

    # ------------------------------------------------------------------ getFanSpeed

    def test_getfanspeed_normal_table(self):
        '''Standard [FanSpeeds] section should return the correct list of tuples.'''
        path = self._make_conf("[FanSpeeds]\n20 = 0\n30 = 20\n50 = 100\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(20, 0), (30, 20), (50, 100)])
        finally:
            self._remove(path)

    def test_getfanspeed_no_section_returns_hardcoded_default(self):
        '''Missing [FanSpeeds] section should return the hardcoded default list.'''
        speeds = piStorConfig().getFanSpeed()
        self.assertEqual(speeds, [(20, 0), (30, 100)])

    def test_getfanspeed_empty_section_returns_empty_list(self):
        '''[FanSpeeds] section that exists but has no entries returns [], not the default.'''
        path = self._make_conf("[FanSpeeds]\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [])
        finally:
            self._remove(path)

    def test_getfanspeed_single_entry(self):
        '''A single-entry table should be returned as a one-element list.'''
        path = self._make_conf("[FanSpeeds]\n70 = 100\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(70, 100)])
        finally:
            self._remove(path)

    def test_getfanspeed_zero_speed_boundary(self):
        '''Fan speed of 0 (fan off) should be parsed as integer zero, not omitted.'''
        path = self._make_conf("[FanSpeeds]\n20 = 0\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(20, 0)])
        finally:
            self._remove(path)

    def test_getfanspeed_max_speed_boundary(self):
        '''Fan speed of 100 should be parsed as integer 100.'''
        path = self._make_conf("[FanSpeeds]\n70 = 100\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds[0][1], 100)
        finally:
            self._remove(path)

    def test_getfanspeed_values_are_ints(self):
        '''All returned tuple elements should be Python ints, not strings.'''
        path = self._make_conf("[FanSpeeds]\n30 = 20\n50 = 75\n")
        try:
            for temp, speed in piStorConfig(path).getFanSpeed():
                self.assertIsInstance(temp,  int)
                self.assertIsInstance(speed, int)
        finally:
            self._remove(path)

    def test_getfanspeed_non_integer_key_returns_default(self):
        '''A non-integer temperature key should trigger the except branch and return the default.'''
        path = self._make_conf("[FanSpeeds]\nabc = 50\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(20, 0), (30, 100)])
        finally:
            self._remove(path)

    def test_getfanspeed_non_integer_value_returns_default(self):
        '''A non-integer fan speed value should trigger the except branch and return the default.'''
        path = self._make_conf("[FanSpeeds]\n30 = fast\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            self.assertEqual(speeds, [(20, 0), (30, 100)])
        finally:
            self._remove(path)

    def test_getfanspeed_preserves_order(self):
        '''Entries should be returned in the order they appear in the file.'''
        path = self._make_conf("[FanSpeeds]\n50 = 50\n30 = 20\n70 = 100\n")
        try:
            speeds = piStorConfig(path).getFanSpeed()
            temps = [t for t, _ in speeds]
            self.assertEqual(temps, [50, 30, 70])
        finally:
            self._remove(path)

    # ------------------------------------------------------------------ iteration

    def test_iteration_yields_section_names(self):
        '''Iterating the config should yield the names of all sections.'''
        path = self._make_conf("[mode]\nautofan = 1\n[FanSpeeds]\n30 = 20\n")
        try:
            sections = list(piStorConfig(path))
            self.assertIn('mode',      sections)
            self.assertIn('FanSpeeds', sections)
        finally:
            self._remove(path)

    def test_iteration_empty_config_yields_nothing(self):
        '''Iterating an empty config should produce an empty sequence.'''
        self.assertEqual(list(piStorConfig()), [])

    def test_iteration_is_repeatable(self):
        '''Iterating the same config object twice should yield the same results.'''
        path = self._make_conf("[mode]\nautofan = 1\n")
        try:
            config = piStorConfig(path)
            self.assertEqual(list(config), list(config))
        finally:
            self._remove(path)

    def test_iteration_single_section(self):
        '''A config with one section should yield exactly that section.'''
        path = self._make_conf("[mode]\nautofan = 1\n")
        try:
            sections = list(piStorConfig(path))
            self.assertEqual(sections, ['mode'])
        finally:
            self._remove(path)


class TestPiStorConfigExtra(unittest.TestCase):
    '''Additional positive and negative tests for piStorConfig.'''

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.out = io.StringIO()
        self.enterContext(redirect_stdout(self.out))

    def conf(self, content):
        '''Write content to a config file in the temp directory and return its path.'''
        path = os.path.join(self.tmpdir.name, 'test.conf')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    # ---- positive

    def test_bundled_template_parses(self):
        '''The repository's pistor.conf template loads with the expected values.'''
        config = piStorConfig(os.path.join(SRC, 'pistor.conf'))
        self.assertEqual(config.getMode(), AUTO_FAN)
        table = config.getFanSpeed()
        self.assertEqual(table[0], (20, 0))
        self.assertEqual(table[-1], (70, 100))
        self.assertEqual(table, sorted(table))
        self.assertEqual(self.out.getvalue(), "")

    def test_comment_lines_ignored(self):
        '''Lines starting with # or ; are comments.'''
        config = piStorConfig(self.conf("# header\n; note\n[mode]\n# c\nautofan = 0\n"))
        self.assertEqual(config.getMode(), MANUAL_FAN)

    def test_indented_keys_and_spaces(self):
        '''Indented keys and spaces around values are accepted.'''
        config = piStorConfig(self.conf("[mode]\n   autofan   =   0  \n"))
        self.assertEqual(config.getMode(), MANUAL_FAN)

    def test_colon_separator(self):
        '''configparser also accepts ":" as a separator.'''
        config = piStorConfig(self.conf("[FanSpeeds]\n40: 50\n"))
        self.assertEqual(config.getFanSpeed(), [(40, 50)])

    def test_option_names_case_insensitive(self):
        '''Option names are case-insensitive.'''
        config = piStorConfig(self.conf("[mode]\nAUTOFAN = 0\n"))
        self.assertEqual(config.getMode(), MANUAL_FAN)

    def test_negative_temperature_threshold(self):
        '''Negative temperatures are valid integers.'''
        config = piStorConfig(self.conf("[FanSpeeds]\n-10 = 0\n"))
        self.assertEqual(config.getFanSpeed(), [(-10, 0)])

    def test_nested_iteration_is_independent(self):
        '''Nested loops over the same config do not interfere.'''
        config = piStorConfig(self.conf("[a]\n[b]\n"))
        pairs = [(x, y) for x in config for y in config]
        self.assertEqual(pairs, [('a', 'a'), ('a', 'b'), ('b', 'a'), ('b', 'b')])

    def test_iter_returns_new_iterator(self):
        '''iter() returns a fresh iterator each time.'''
        config = piStorConfig(self.conf("[a]\n"))
        self.assertIsNot(iter(config), iter(config))

    # ---- negative

    def test_section_names_case_sensitive(self):
        '''[fanspeeds] is not [FanSpeeds]: the default table is returned.'''
        config = piStorConfig(self.conf("[fanspeeds]\n40 = 50\n"))
        self.assertEqual(config.getFanSpeed(), [(20, 0), (30, 100)])

    def test_float_temperature_key_returns_default(self):
        '''A non-integer temperature such as 20.5 is rejected.'''
        config = piStorConfig(self.conf("[FanSpeeds]\n20.5 = 50\n"))
        self.assertEqual(config.getFanSpeed(), [(20, 0), (30, 100)])

    def test_percent_sign_value_returns_default(self):
        '''A value like "50%" is rejected (and must not crash interpolation).'''
        config = piStorConfig(self.conf("[FanSpeeds]\n40 = 50%\n"))
        self.assertEqual(config.getFanSpeed(), [(20, 0), (30, 100)])

    def test_missing_value_returns_default(self):
        '''A key with an empty value is rejected.'''
        config = piStorConfig(self.conf("[FanSpeeds]\n40 =\n"))
        self.assertEqual(config.getFanSpeed(), [(20, 0), (30, 100)])

    def test_boolean_mode_value_defaults_to_auto(self):
        '''autofan = true is not an integer, so automatic mode is used.'''
        config = piStorConfig(self.conf("[mode]\nautofan = true\n"))
        self.assertEqual(config.getMode(), AUTO_FAN)
        self.assertIn("Error", self.out.getvalue())

    def test_missing_section_header_does_not_raise(self):
        '''A file with no [section] header is reported, not raised.'''
        config = piStorConfig(self.conf("autofan = 0\n"))
        self.assertEqual(config.configObj.sections(), [])
        self.assertEqual(config.getMode(), AUTO_FAN)
        self.assertIn("Error", self.out.getvalue())

    def test_duplicate_option_does_not_raise(self):
        '''A duplicated key is reported, not raised.'''
        piStorConfig(self.conf("[FanSpeeds]\n40 = 10\n40 = 20\n"))
        self.assertIn("Error", self.out.getvalue())

    def test_duplicate_section_does_not_raise(self):
        '''A duplicated section is reported, not raised.'''
        piStorConfig(self.conf("[mode]\nautofan = 1\n[mode]\nautofan = 0\n"))
        self.assertIn("Error", self.out.getvalue())

    def test_directory_path_treated_as_missing(self):
        '''A directory path is not a file and is reported as missing.'''
        config = piStorConfig(self.tmpdir.name)
        self.assertEqual(config.configObj.sections(), [])
        self.assertIn("does not exist", self.out.getvalue())

    def test_missing_file_keeps_previous_filename(self):
        '''A failed load does not change the stored filename.'''
        path = self.conf("[mode]\nautofan = 1\n")
        config = piStorConfig(path)
        config.loadConfig(os.path.join(self.tmpdir.name, 'nope.conf'))
        self.assertEqual(config.filename, path)
        self.assertEqual(config.getMode(), AUTO_FAN)

    def test_binary_file_does_not_raise(self):
        '''A file that is not valid UTF-8 text is reported, not raised.'''
        path = os.path.join(self.tmpdir.name, 'bin.conf')
        with open(path, 'wb') as f:
            f.write(b"\xff\xfe\x00[mode]\x00")
        piStorConfig(path)
        self.assertIn("Error", self.out.getvalue())


if __name__ == "__main__":
    unittest.main()
