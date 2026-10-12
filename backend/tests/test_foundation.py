from pathlib import Path
import importlib.util
import unittest


class FoundationTests(unittest.TestCase):
    def test_database_models_exist(self):
        self.assertIsNotNone(importlib.util.find_spec('app.models'), 'new schema not implemented')

    def test_isolation_settings_exist(self):
        self.assertIsNotNone(importlib.util.find_spec('app.settings'), 'isolated settings not implemented')

    def test_versioned_migration_exists(self):
        self.assertTrue(list((Path(__file__).resolve().parents[1] / 'alembic/versions').glob('*.py')),
                        'no versioned database migration')
