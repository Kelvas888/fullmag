#!/usr/bin/env python3
"""Focused regressions for direct Docker development-image admission."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_ROOT.parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import docker_dev  # noqa: E402


class RuntimeImageContextTests(unittest.TestCase):
    def _copy_runtime_context(self, destination: Path) -> None:
        for _name, relative_source in docker_dev.RUNTIME_IMAGE_CONTEXT_FILES:
            source = REPO_ROOT / relative_source
            target = destination / relative_source
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _image_document(self, toolchain_id: str) -> dict[str, object]:
        return {
            "Config": {
                "Labels": {
                    "org.fullmag.runtime": "docker-all-gpu-v1",
                    "org.fullmag.development": "source-bind-v1",
                    "org.fullmag.toolchain.image-id": toolchain_id,
                },
            },
        }

    def test_backend_helper_change_changes_runtime_context_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            self._copy_runtime_context(checkout)

            before = docker_dev._runtime_image_context(checkout)
            backend_helper = checkout / "docker/all-in-one/backend_dev.py"
            backend_helper.write_bytes(backend_helper.read_bytes() + b"\n# context regression\n")
            after = docker_dev._runtime_image_context(checkout)

        self.assertNotEqual(before["context_sha256"], after["context_sha256"])
        self.assertNotEqual(
            before["files"]["backend_dev.py"],
            after["files"]["backend_dev.py"],
        )

    def test_stale_backend_context_receipt_is_rejected(self) -> None:
        image_id = "sha256:" + "a" * 64
        toolchain_id = "sha256:" + "b" * 64
        stale_receipt = {
            "image_id": image_id,
            "toolchain_image_id": toolchain_id,
            "base_image_id": "sha256:" + "c" * 64,
            "context_sha256": "current-base-context",
            "backend_context_sha256": "old-backend-context",
            "runtime_context_sha256": "old-runtime-context",
        }

        with patch.object(
            docker_dev,
            "_inspect_image",
            return_value=(image_id, self._image_document(toolchain_id)),
        ), patch.object(docker_dev, "_image_file", return_value=b"backend"), patch.object(
            docker_dev,
            "_read_image_metadata",
            return_value=stale_receipt,
        ):
            with self.assertRaises(docker_dev.DirectDockerError):
                docker_dev._validate_runtime_image(
                    "fullmag/fullmag-dev:direct-runtime",
                    toolchain_id,
                    {},
                    "current-base-context",
                    "sha256:" + "c" * 64,
                    expected_backend_context_sha256="new-backend-context",
                    expected_runtime_context_sha256="new-runtime-context",
                )

    def test_cold_build_without_receipt_is_not_reusable(self) -> None:
        image_id = "sha256:" + "e" * 64
        toolchain_id = "sha256:" + "f" * 64
        image = "fullmag/fullmag-dev:direct-runtime-cold"

        with patch.object(
            docker_dev,
            "_inspect_image",
            return_value=(image_id, self._image_document(toolchain_id)),
        ), patch.object(docker_dev, "_image_file", return_value=b"backend"), patch.object(
            docker_dev,
            "_read_image_metadata",
            return_value=None,
        ):
            docker_dev._validate_runtime_image(
                image,
                toolchain_id,
                {},
                None,
                image_id,
                require_receipt=False,
            )
            with self.assertRaises(docker_dev.DirectDockerError):
                docker_dev._validate_runtime_image(
                    image,
                    toolchain_id,
                    {},
                    None,
                    image_id,
                )


if __name__ == "__main__":
    unittest.main()
