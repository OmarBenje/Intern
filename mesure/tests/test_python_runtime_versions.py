"""A Python patch mismatch must no longer pass VM/Docker campaign preparation."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from campagnes17 import validate_runtime_versions


class PythonRuntimeVersionsTests(unittest.TestCase):
    def setUp(self):
        self.versions = dict(python='3.12.15', django='6.1.1', drf='3.18.1', gunicorn='23.0.0')

    def test_equal_versions_are_accepted(self):
        validate_runtime_versions(self.versions, self.versions.copy())

    def test_python_patch_difference_is_rejected_even_when_frameworks_match(self):
        with self.assertRaisesRegex(RuntimeError, 'versions differ: python'):
            validate_runtime_versions({**self.versions, 'python': '3.12.3'}, self.versions)

    def test_missing_python_version_cannot_silently_pass(self):
        incomplete = {key: value for key, value in self.versions.items() if key != 'python'}
        with self.assertRaisesRegex(RuntimeError, 'Missing runtime version: python'):
            validate_runtime_versions(incomplete, self.versions)
