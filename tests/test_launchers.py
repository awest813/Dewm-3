"""Exercise launchers against isolated Steam libraries and a fake engine."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
BASH = os.environ.get('BASH_TEST_EXECUTABLE', shutil.which('bash'))


@unittest.skipUnless(BASH, 'bash required')
class Launchers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        shutil.copytree(REPO / 'scripts', self.repo / 'scripts')
        self.home = self.root / 'home'
        self.home.mkdir()
        self.binary = self.repo / 'build' / 'dhewm3'
        self.binary.parent.mkdir()
        self.binary.write_text('#!/usr/bin/env bash\nprintf "ARG:%s\\n" "$@"\n')
        self.binary.chmod(0o755)

    def data(self, folder):
        (folder / 'base').mkdir(parents=True)
        for index in range(9):
            (folder / 'base' / f'pak{index:03}.pk4').write_bytes(b'fixture')
        return folder

    def run_script(self, name, *args):
        # Set HOME inside bash too: Git Bash startup can replace Windows HOME.
        return subprocess.run(
            [BASH, '-c', 'export HOME="$1" XDG_DATA_HOME="$1/.local/share"; shift; bash "$@"',
             'test', self.home.as_posix(), (self.repo / 'scripts' / name).as_posix(), *args],
            capture_output=True, text=True, timeout=20)

    def test_explicit_path_and_arguments(self):
        data = self.data(self.root / 'Doom 3')
        for name in ('linux-run.sh', 'macos-run.sh'):
            with self.subTest(name=name):
                result = self.run_script(name, data.as_posix(), '+set', 'r_fullscreen', '0')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'ARG:{data.as_posix()}', result.stdout)
                self.assertIn('ARG:r_fullscreen\nARG:0', result.stdout)

    def test_invalid_path_preserves_saved_path(self):
        invalid = self.data(self.root / 'incomplete')
        (invalid / 'base' / 'pak008.pk4').unlink()
        for name, relative in (
            ('linux-run.sh', '.local/share/dhewm3/gamepath'),
            ('macos-run.sh', 'Library/Application Support/dhewm3/gamepath'),
        ):
            with self.subTest(name=name):
                prefs = self.home / relative
                prefs.parent.mkdir(parents=True, exist_ok=True)
                prefs.write_text('previous path\n')
                result = self.run_script(name, invalid.as_posix())
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('ARG:', result.stdout)
                self.assertEqual(prefs.read_text(), 'previous path\n')

    def test_empty_archive_rejected(self):
        data = self.data(self.root / 'empty archive')
        (data / 'base' / 'pak003.pk4').write_bytes(b'')
        for name in ('linux-run.sh', 'macos-run.sh'):
            self.assertNotEqual(self.run_script(name, data.as_posix()).returncode, 0)

    def test_archive_directory_rejected(self):
        data = self.data(self.root / 'directory archive')
        archive = data / 'base/pak003.pk4'
        archive.unlink()
        archive.mkdir()
        for name in ('linux-run.sh', 'macos-run.sh'):
            self.assertNotEqual(self.run_script(name, data.as_posix()).returncode, 0)

    def test_steam_extra_libraries(self):
        data = self.data(self.root / 'extra library' / 'steamapps/common/Doom 3')
        for name, relative in (
            ('linux-run.sh', '.local/share/Steam'),
            ('linux-run.sh', '.var/app/com.valvesoftware.Steam/.local/share/Steam'),
            ('macos-run.sh', 'Library/Application Support/Steam'),
        ):
            with self.subTest(relative=relative):
                # Keep discovery scenarios independent.
                shutil.rmtree(self.home)
                self.home.mkdir()
                vdf = self.home / relative / 'steamapps/libraryfolders.vdf'
                vdf.parent.mkdir(parents=True)
                vdf.write_text('"libraryfolders" {\n "0" {\n "path" "' +
                               data.parents[2].as_posix() + '"\n }\n }')
                result = self.run_script(name, '+set', 'r_fullscreen', '0')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'ARG:{data.as_posix()}', result.stdout)

    def test_packaged_launcher_forwards_path_once(self):
        data = self.data(self.root / 'game')
        result = self.run_script('linux-package.sh', self.binary.parent.as_posix())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        import tarfile
        archive = next(self.repo.glob('dhewm3-linux-*.tar.gz'))
        with tarfile.open(archive) as bundle:
            bundle.extractall(self.root / 'package', filter='data')
        launcher = self.root / 'package/dhewm3/run.sh'
        result = subprocess.run([BASH, launcher.as_posix(), data.as_posix(), '+set', 'r_fullscreen', '0'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count(f'ARG:{data.as_posix()}\n'), 1)
        result = subprocess.run([BASH, launcher.as_posix()], capture_output=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)

    def test_engine_check_detects_crash_and_missing_help(self):
        checker = (self.repo / 'scripts/check-engine.sh').as_posix()
        for body, expected in (
            ('echo "Commandline arguments:"; echo fs_basepath; exit 1', 0),
            ('echo "Commandline arguments:"; echo fs_basepath; exit 139', 1),
            ('echo "library missing"; exit 1', 1),
        ):
            self.binary.write_text('#!/usr/bin/env bash\n' + body + '\n')
            result = subprocess.run([BASH, checker, self.binary.as_posix()], capture_output=True, timeout=20)
            self.assertEqual(result.returncode, expected)


if __name__ == '__main__':
    unittest.main()
