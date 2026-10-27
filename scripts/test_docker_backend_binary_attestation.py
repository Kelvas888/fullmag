"""Contract for the host-side backend binary attestation script.

A shared backend package (docs/guides/shared-build-storage.md) links one sealed
payload into every consuming group, so a published binary legitimately has
more than one hardlink. The attestation must accept that sealed form and keep
rejecting writable multi-link files.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fullmag_docker_runtime as runtime


def _run_attestation(package_bin: Path, *names: str) -> subprocess.CompletedProcess:
    script = runtime._BACKEND_BINARY_DIGESTS_SCRIPT.replace(
        '"/opt/fullmag/package/bin/"', repr(str(package_bin) + os.sep)
    )
    return subprocess.run(
        [sys.executable, "-I", "-c", script, *names],
        capture_output=True, text=True, timeout=60,
    )


@unittest.skipUnless(hasattr(os, "O_CLOEXEC"), "attestation runs in the Linux backend container")
class BackendBinaryAttestationContract(unittest.TestCase):
    def setUp(self):
        self._root = tempfile.TemporaryDirectory()
        self.root = Path(self._root.name)
        self.bin = self.root / "package" / "bin"
        self.bin.mkdir(parents=True)
        self.shared = self.root / "shared"
        self.shared.mkdir()

    def tearDown(self):
        for path in self.root.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        self._root.cleanup()

    def _linked_binary(self, *, sealed: bool) -> None:
        payload = self.shared / "fullmag-api"
        payload.write_bytes(b"binary")
        if sealed:
            os.chmod(payload, stat.S_IREAD | stat.S_IEXEC)
        os.link(payload, self.bin / "fullmag-api")

    def test_sealed_shared_hardlink_is_attested(self):
        self._linked_binary(sealed=True)
        self.assertGreater(os.stat(self.bin / "fullmag-api").st_nlink, 1)
        result = _run_attestation(self.bin, "fullmag-api")
        self.assertEqual(result.returncode, 0, result.stderr)
        digests = json.loads(result.stdout)
        self.assertEqual(
            digests["fullmag-api"],
            "9a3a45d01531a20e89ac6ae10b0b0beb0492acd7216a368aa062d1a5fecaf9cd",
        )

    def test_writable_multi_link_binary_is_rejected(self):
        self._linked_binary(sealed=False)
        result = _run_attestation(self.bin, "fullmag-api")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime artifact is not one regular file", result.stderr)

    def test_single_link_writable_binary_is_attested(self):
        (self.bin / "fullmag-api").write_bytes(b"binary")
        result = _run_attestation(self.bin, "fullmag-api")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
