"""Publication boundary tests use synthetic strings, never real credentials."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_repository.py'


class RepositoryGuardTests(unittest.TestCase):
    def test_guard_exists(self):
        self.assertTrue(SCRIPT.exists(), 'publication guard has not been implemented')

    def scan(self, path, body=b''):
        if not SCRIPT.exists():
            self.fail('publication guard has not been implemented')
        spec = importlib.util.spec_from_file_location('guard', SCRIPT)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        return guard.inspect_blob(path, body)

    def test_forbidden_artifacts(self):
        for name in ['.env', 'backend/.env.production', 'dump.sql', 'users.sqlite3',
                     'signing/client.p12', 'material/unknown', 'archive.zip', 'photo.heic']:
            with self.subTest(name=name):
                self.assertTrue(self.scan(name))

    def test_empty_environment_example_allowed(self):
        self.assertFalse(self.scan('.env.example', b'DATABASE_URL=\nJWT_SECRET=\n'))

    def test_nonempty_secret_environment_example_rejected(self):
        self.assertTrue(self.scan('.env.example', b'JWT_SECRET=' + b'x' * 40))

    def test_private_key_and_signed_config_rejected(self):
        self.assertTrue(self.scan('data.txt', b'-----BEGIN ' + b'PRIVATE KEY-----'))
        self.assertTrue(self.scan('build-profile.json5', b'"storePassword": "' + b'x' * 16 + b'"'))

    def test_historical_deleted_database_blocks_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.run(['git', '-C', tmp, *args], check=True, capture_output=True)
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (root / 'private.sqlite3').write_bytes(b'fixture')
            git('add', '.')
            git('commit', '-qm', 'fixture')
            git('rm', '-q', 'private.sqlite3')
            git('commit', '-qm', 'delete fixture')
            result = subprocess.run(['python3', str(SCRIPT), '--root', tmp, '--history'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('forbidden-path', result.stdout)
            self.assertNotIn('fixture', result.stdout)

    def test_symlink_cannot_bypass_scanning(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git', 'init', '-q', tmp], check=True)
            (Path(tmp) / 'linked.txt').symlink_to('/etc/hosts')
            result = subprocess.run(['python3', str(SCRIPT), '--root', tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('symlink', result.stdout)

if __name__ == '__main__':
    unittest.main()
