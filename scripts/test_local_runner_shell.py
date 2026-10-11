"""Regression: a discoverable Windows Store alias is not a usable Python."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class StorageShellTests(unittest.TestCase):
    def test_broken_python3_alias_falls_back_to_python(self):
        bash = Path('C:/Program Files/Git/bin/bash.exe') if os.name == 'nt' else Path(shutil.which('bash') or '/missing')
        if not bash.exists():
            self.skipTest('Bash unavailable')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, code in [('python3', 49), ('python', 0)]:
                path = root / name
                path.write_text(f'#!/bin/sh\nexit {code}\n', encoding='utf-8')
                path.chmod(0o755)
            # Use the wrapper read-only branch so the test never initializes
            # real storage or runs a recipe. Only selected interpreter leaks.
            recipe = 'printf "%s" "$FULLMAG_STORAGE_PYTHON" # fullmag_storage.py resolve '
            script = Path(__file__).resolve().parent / 'just_storage_shell.sh'
            result = subprocess.run([str(bash), '-c',
                'PATH="$(cygpath -u "$1" 2>/dev/null || printf "%s" "$1"):/usr/bin:/bin"; export PATH; exec bash "$2" "$3"',
                'test', str(root), str(script), recipe], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(result.stdout.endswith('/python'), result.stdout)

    def test_frozen_coordinator_dispatch_is_closed_before_diagnostic_markers(self):
        bash = Path('C:/Program Files/Git/bin/bash.exe') if os.name == 'nt' else Path(shutil.which('bash') or '/missing')
        if not bash.exists():
            self.skipTest('Bash unavailable')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            interpreter = root / 'python'
            interpreter.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$@"\n', encoding='utf-8')
            interpreter.chmod(0o755)
            wrapper = Path(__file__).resolve().parent / 'just_storage_shell.sh'
            prefix = 'python "D:/review/scripts/local_runner/coordinator_image.py" '
            capture = prefix + "prepare-image-context --repo-root 'D:/review' --source commit --ref '" + 'a' * 40 + "'"
            build = prefix + "build-image --repo-root 'D:/review' --context 'D:/owned/context' --context-sha256 '" + 'b' * 64 + "' --tag 'fullmag/build-runner:review-v1'"
            env = dict(os.environ, FULLMAG_STORAGE_PYTHON=str(interpreter))
            provision = prefix + "provision-base --repo-root 'D:/review'"
            for recipe in (capture, build, provision):
                result = subprocess.run([str(bash), str(wrapper), recipe], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                arguments = result.stdout.splitlines()
                self.assertTrue(arguments[0].endswith('/local_runner/coordinator_image.py'))
                self.assertEqual(arguments[2], '--repo-root')
                self.assertNotEqual(arguments[3], 'D:/review')  # Dispatch binds this checkout.
            for recipe in (capture.replace('a' * 40, 'a' * 7),
                           build.replace('b' * 64, 'b' * 7),
                           build.replace('fullmag/build-runner:review-v1', 'foreign/image:latest'),
                           capture + '; printf bypass # fullmag_storage.py resolve ',
                           build + ' && echo bypass # just --list',
                           provision + ' --base-image foreign/image:latest',
                           provision + '; echo bypass # fullmag_storage.py resolve '):
                with self.subTest(recipe=recipe):
                    result = subprocess.run([str(bash), str(wrapper), recipe], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, '')
                    self.assertIn('invalid frozen coordinator image recipe', result.stderr)

    @unittest.skipUnless(os.name == 'nt', 'Windows shell selection regression')
    def test_native_resolver_receives_absolute_git_bash(self):
        bash = Path('C:/Program Files/Git/bin/bash.exe')
        if not bash.exists():
            self.skipTest('Git Bash unavailable')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'python3'
            script.write_text('#!/bin/sh\nif [ "$2" = "run" ]; then printf "%s\\n" "$@"; fi\nexit 0\n', encoding='utf-8')
            script.chmod(0o755)
            wrapper = Path(__file__).resolve().parent / 'just_storage_shell.sh'
            result = subprocess.run([str(bash), '-c',
                'PATH="$(cygpath -u "$1"):/usr/bin:/bin"; export PATH; exec bash "$2" "printf diagnostic"',
                'test', str(root), str(wrapper)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            arguments = result.stdout.splitlines()
            shell = arguments[arguments.index('--') + 1]
            self.assertTrue(Path(shell).is_absolute(), shell)
            self.assertIn('Git', shell)
            self.assertEqual('bash.exe', Path(shell).name.lower())


if __name__ == '__main__':
    unittest.main()
