from __future__ import annotations

import ctypes
import os
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import fullmag.cuda_device_identity as cuda_identity
from fullmag.model.problem import RuntimeSelection


class _FakeFunction:
    def __init__(self, function):
        self.function = function
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.function(*args)


class _FakeCudaDriver:
    def __init__(self, uuids: tuple[bytes, ...]):
        self.uuids = uuids
        self.init_calls = 0
        self.count_calls = 0
        self.uuid_calls = 0
        self.cuInit = _FakeFunction(self._init)
        self.cuDeviceGetCount = _FakeFunction(self._get_count)
        self.cuDeviceGet = _FakeFunction(self._get_device)
        self.cuDeviceGetUuid_v2 = _FakeFunction(self._get_uuid)

    def _init(self, flags: int) -> int:
        self.init_calls += 1
        return 0

    def _get_count(self, output) -> int:
        self.count_calls += 1
        ctypes.cast(output, ctypes.POINTER(ctypes.c_int))[0] = len(self.uuids)
        return 0

    def _get_device(self, output, ordinal: int) -> int:
        if ordinal < 0 or ordinal >= len(self.uuids):
            return 101
        ctypes.cast(output, ctypes.POINTER(ctypes.c_int))[0] = ordinal
        return 0

    def _get_uuid(self, output, device: int) -> int:
        self.uuid_calls += 1
        if device < 0 or device >= len(self.uuids):
            return 101
        target = ctypes.cast(output, ctypes.POINTER(cuda_identity._CUuuid)).contents
        for index, byte in enumerate(self.uuids[device]):
            target.bytes[index] = byte
        return 0


def _uuid_bytes(seed: int) -> bytes:
    return bytes((seed + offset) % 256 for offset in range(16))


@contextmanager
def _process_mask(mask: str | None):
    environment = dict(os.environ)
    if mask is None:
        environment.pop("CUDA_VISIBLE_DEVICES", None)
    else:
        environment["CUDA_VISIBLE_DEVICES"] = mask
    with patch.dict(os.environ, environment, clear=True):
        with patch.object(
            cuda_identity, "_INHERITED_CUDA_VISIBLE_DEVICES", mask
        ):
            yield


class LegacyCudaBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_discovery = cuda_identity._discovery
        self.previous_inherited_mask = (
            cuda_identity._INHERITED_CUDA_VISIBLE_DEVICES
        )
        cuda_identity._discovery = None
        cuda_identity._INHERITED_CUDA_VISIBLE_DEVICES = os.environ.get(
            "CUDA_VISIBLE_DEVICES"
        )
        self.addCleanup(self._restore_state)

    def _restore_state(self) -> None:
        cuda_identity._discovery = self.previous_discovery
        cuda_identity._INHERITED_CUDA_VISIBLE_DEVICES = (
            self.previous_inherited_mask
        )

    def test_runtime_metadata_resolves_visible_ordinal_and_preserves_mask(self) -> None:
        driver = _FakeCudaDriver((_uuid_bytes(0), _uuid_bytes(16)))
        inherited_mask = "GPU-first,GPU-second"
        with _process_mask(inherited_mask):
            with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
                binding = RuntimeSelection(
                    device_target="cuda", device_index=1
                ).to_runtime_metadata()["legacy_cuda_binding"]
                self.assertEqual(
                    os.environ.get("CUDA_VISIBLE_DEVICES"), inherited_mask
                )

        self.assertEqual(
            binding,
            {
                "schema_version": "legacy_cuda_binding.v1",
                "ordinal": 1,
                "cuda_visible_devices": inherited_mask,
                "gpu_uuid": "GPU-10111213-1415-1617-1819-1a1b1c1d1e1f",
            },
        )
        self.assertEqual(driver.init_calls, 1)
        self.assertEqual(driver.count_calls, 1)
        self.assertEqual(driver.uuid_calls, 2)

    def test_mask_drift_fails_closed_and_does_not_reenumerate(self) -> None:
        driver = _FakeCudaDriver((_uuid_bytes(32),))
        with _process_mask("GPU-original"):
            with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
                first = RuntimeSelection(
                    device_target="cuda", device_index=0
                ).to_runtime_metadata()["legacy_cuda_binding"]
                os.environ["CUDA_VISIBLE_DEVICES"] = "GPU-reordered"
                second = RuntimeSelection(
                    device_target="cuda", device_index=0
                ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertEqual(first["gpu_uuid"], "GPU-20212223-2425-2627-2829-2a2b2c2d2e2f")
        self.assertEqual(second["cuda_visible_devices"], "GPU-original")
        self.assertIsNone(second["gpu_uuid"])
        self.assertIn("changed after CUDA driver discovery", second["resolution_error"])
        self.assertEqual(driver.init_calls, 1)

    def test_mask_changed_after_import_fails_before_driver_probe(self) -> None:
        driver = _FakeCudaDriver((_uuid_bytes(48),))
        with _process_mask("GPU-imported"):
            os.environ["CUDA_VISIBLE_DEVICES"] = "GPU-changed-before-export"
            with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
                binding = RuntimeSelection(
                    device_target="cuda", device_index=0
                ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertEqual(binding["cuda_visible_devices"], "GPU-imported")
        self.assertIsNone(binding["gpu_uuid"])
        self.assertIn("changed after Fullmag import", binding["resolution_error"])
        self.assertEqual(driver.init_calls, 0)

    def test_repeated_export_with_same_mask_reuses_cached_enumeration(self) -> None:
        driver = _FakeCudaDriver((_uuid_bytes(64), _uuid_bytes(80)))
        with _process_mask("GPU-stable"):
            with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
                first = RuntimeSelection(
                    device_target="cuda", device_index=0
                ).to_runtime_metadata()["legacy_cuda_binding"]
                second = RuntimeSelection(
                    device_target="cuda", device_index=1
                ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertEqual(first["cuda_visible_devices"], "GPU-stable")
        self.assertEqual(second["cuda_visible_devices"], "GPU-stable")
        self.assertEqual(driver.init_calls, 1)
        self.assertEqual(driver.count_calls, 1)

    def test_cached_binding_is_not_reenumerated_after_process_fork(self) -> None:
        driver = _FakeCudaDriver((_uuid_bytes(96),))
        original_pid = os.getpid()
        with _process_mask("GPU-parent"):
            with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
                RuntimeSelection(
                    device_target="cuda", device_index=0
                ).to_runtime_metadata()
                with patch.object(cuda_identity.os, "getpid", return_value=original_pid + 1):
                    binding = RuntimeSelection(
                        device_target="cuda", device_index=0
                    ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertIsNone(binding["gpu_uuid"])
        self.assertIn("inherited across a process fork", binding["resolution_error"])
        self.assertEqual(binding["cuda_visible_devices"], "GPU-parent")
        self.assertEqual(driver.init_calls, 1)

    def test_unavailable_driver_is_exported_as_resolution_failure(self) -> None:
        inherited_mask = "GPU-visible"
        with _process_mask(inherited_mask):
            with patch.object(
                cuda_identity,
                "_load_cuda_driver",
                side_effect=OSError("driver unavailable"),
            ):
                binding = RuntimeSelection(
                    device_target="cuda", device_index=0
                ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertEqual(binding["schema_version"], "legacy_cuda_binding.v1")
        self.assertEqual(binding["ordinal"], 0)
        self.assertEqual(binding["cuda_visible_devices"], inherited_mask)
        self.assertIsNone(binding["gpu_uuid"])
        self.assertEqual(binding["resolution_error"], "driver unavailable")

    def test_out_of_range_ordinal_is_recorded_without_losing_discovery(self) -> None:
        driver = _FakeCudaDriver((_uuid_bytes(48),))
        with _process_mask(None):
            with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
                unavailable = RuntimeSelection(
                    device_target="cuda", device_index=1
                ).to_runtime_metadata()["legacy_cuda_binding"]
                available = RuntimeSelection(
                    device_target="cuda", device_index=0
                ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertIsNone(unavailable["gpu_uuid"])
        self.assertIn("outside the visible device range", unavailable["resolution_error"])
        self.assertEqual(available["gpu_uuid"], "GPU-30313233-3435-3637-3839-3a3b3c3d3e3f")
        self.assertEqual(driver.init_calls, 1)

    def test_oversized_visible_device_count_fails_closed(self) -> None:
        driver = _FakeCudaDriver((_uuid_bytes(112),) * 257)
        with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
            binding = RuntimeSelection(
                device_target="cuda", device_index=0
            ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertIsNone(binding["gpu_uuid"])
        self.assertIn("exceeds 256", binding["resolution_error"])
        self.assertEqual(driver.uuid_calls, 0)

    def test_duplicate_visible_device_uuids_fail_closed(self) -> None:
        duplicate = _uuid_bytes(128)
        driver = _FakeCudaDriver((duplicate, duplicate))
        with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
            binding = RuntimeSelection(
                device_target="cuda", device_index=0
            ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertIsNone(binding["gpu_uuid"])
        self.assertIn("duplicate visible device UUIDs", binding["resolution_error"])

    def test_missing_uuid_v2_symbol_does_not_fall_back_to_legacy_uuid(self) -> None:
        driver = _FakeCudaDriver((_uuid_bytes(144),))
        legacy_calls = 0

        def get_legacy_uuid(output, device):
            nonlocal legacy_calls
            legacy_calls += 1
            return 0

        driver.cuDeviceGetUuid = _FakeFunction(get_legacy_uuid)
        del driver.cuDeviceGetUuid_v2
        with patch.object(cuda_identity, "_load_cuda_driver", return_value=driver):
            binding = RuntimeSelection(
                device_target="cuda", device_index=0
            ).to_runtime_metadata()["legacy_cuda_binding"]

        self.assertIsNone(binding["gpu_uuid"])
        self.assertIn("cuDeviceGetUuid_v2", binding["resolution_error"])
        self.assertEqual(legacy_calls, 0)

    def test_cpu_auto_and_unindexed_gpu_metadata_do_not_probe(self) -> None:
        selections = (
            RuntimeSelection(device_target="cpu"),
            RuntimeSelection(device_target="auto"),
            RuntimeSelection(device_target="gpu"),
        )
        with patch.object(
            cuda_identity,
            "_load_cuda_driver",
            side_effect=AssertionError("unexpected CUDA driver probe"),
        ) as load_driver:
            for selection in selections:
                with self.subTest(device=selection.device_target):
                    self.assertNotIn(
                        "legacy_cuda_binding", selection.to_runtime_metadata()
                    )
        load_driver.assert_not_called()

    def test_invalid_device_indices_are_rejected(self) -> None:
        for index in (-1, True, 1.5):
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, "device_index"):
                    RuntimeSelection(device_target="cuda", device_index=index)

    def test_driver_library_loading_uses_platform_specific_system_path(self) -> None:
        fake_driver = object()
        with patch.object(sys, "platform", "win32"):
            with patch.object(
                cuda_identity.ctypes, "WinDLL", create=True, return_value=fake_driver
            ) as load_windows:
                self.assertIs(cuda_identity._load_cuda_driver(), fake_driver)
        load_windows.assert_called_once_with(
            "nvcuda.dll", winmode=cuda_identity._LOAD_LIBRARY_SEARCH_SYSTEM32
        )

        with patch.object(sys, "platform", "linux"):
            with patch.object(
                cuda_identity.ctypes, "CDLL", return_value=fake_driver
            ) as load_linux:
                self.assertIs(cuda_identity._load_cuda_driver(), fake_driver)
        load_linux.assert_called_once_with("libcuda.so.1")


if __name__ == "__main__":
    unittest.main()
