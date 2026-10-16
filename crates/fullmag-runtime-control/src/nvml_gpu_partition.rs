//! Bounded NVML evidence for promoting an otherwise unknown GPU partition.
//!
//! `nvidia-smi` reports `N/A` for MIG mode on some physical devices. That
//! value is intentionally not interpreted here. A device may be promoted to
//! `FullDevice` only after a bounded child probe has proved all of the
//! following in one observation: the requested canonical `GPU-...` UUID
//! resolves, the returned UUID is an exact match, virtualization is bare metal
//! or passthrough, and MIG is disabled or explicitly unsupported. Probe,
//! interpreter, loader, and status failures remain inconclusive so callers
//! keep the fail-closed `Unknown` state.

use std::time::Instant;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum NvmlMigMode {
    Disabled,
    Enabled,
    NotSupported,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum NvmlVirtualizationMode {
    BareMetal,
    Passthrough,
    Vgpu,
    HostVgpu,
    HostVsga,
    Unknown,
}

/// Return `Some(true)` only for a complete physical-device proof, `Some(false)`
/// when NVML positively identifies a non-full device, and `None` when the
/// evidence is unavailable or incomplete. The latter is deliberately not an
/// error: generic host telemetry must remain usable while strict GPU readiness
/// rejects an unresolved partition.
pub(crate) fn full_device_probe(uuid: &str, deadline: Instant) -> Option<bool> {
    if !is_canonical_gpu_uuid(uuid) {
        return None;
    }

    #[cfg(unix)]
    {
        return probe_unix(uuid, deadline);
    }

    #[cfg(not(unix))]
    {
        // The Windows runtime has no NVML loader in this crate. Existing
        // parser evidence, including an explicit nvidia-smi Disabled value,
        // remains untouched; an Unknown value stays Unknown.
        let _ = (uuid, deadline);
        None
    }
}

fn is_canonical_gpu_uuid(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 40 || &bytes[..4] != b"GPU-" {
        return false;
    }
    for (index, byte) in bytes[4..].iter().enumerate() {
        if matches!(index, 8 | 13 | 18 | 23) {
            if *byte != b'-' {
                return false;
            }
        } else if !byte.is_ascii_hexdigit() {
            return false;
        }
    }
    true
}

fn verified_full_device(
    requested_uuid: &str,
    returned_uuid: &str,
    mig_mode: NvmlMigMode,
    virtualization_mode: NvmlVirtualizationMode,
) -> bool {
    is_canonical_gpu_uuid(requested_uuid)
        && requested_uuid == returned_uuid
        && matches!(
            virtualization_mode,
            NvmlVirtualizationMode::BareMetal | NvmlVirtualizationMode::Passthrough
        )
        && matches!(mig_mode, NvmlMigMode::Disabled | NvmlMigMode::NotSupported)
}

#[cfg(unix)]
const NVML_PROBE_SCRIPT: &str = r#"
import ctypes
import json
import sys

NVML_SUCCESS = 0


def symbol(library, name, restype, argtypes):
    function = getattr(library, name)
    function.restype = restype
    function.argtypes = argtypes
    return function


try:
    library = ctypes.CDLL("libnvidia-ml.so.1")
    init = symbol(library, "nvmlInit_v2", ctypes.c_uint, [])
    shutdown = symbol(library, "nvmlShutdown", ctypes.c_uint, [])
    get_handle = symbol(
        library,
        "nvmlDeviceGetHandleByUUID",
        ctypes.c_uint,
        [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)],
    )
    get_uuid = symbol(
        library,
        "nvmlDeviceGetUUID",
        ctypes.c_uint,
        [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char), ctypes.c_uint],
    )
    get_mig = symbol(
        library,
        "nvmlDeviceGetMigMode",
        ctypes.c_uint,
        [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)],
    )
    get_virtualization = symbol(
        library,
        "nvmlDeviceGetVirtualizationMode",
        ctypes.c_uint,
        [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)],
    )
except (AttributeError, OSError):
    raise SystemExit(2)

if len(sys.argv) != 2:
    raise SystemExit(2)

if init() != NVML_SUCCESS:
    raise SystemExit(3)

try:
    requested_uuid = sys.argv[1].encode("ascii")
    handle = ctypes.c_void_p()
    handle_rc = get_handle(requested_uuid, ctypes.byref(handle))
    if handle_rc != NVML_SUCCESS or not handle.value:
        raise SystemExit(4)

    uuid_buffer = ctypes.create_string_buffer(96)
    uuid_rc = get_uuid(handle, uuid_buffer, 96)
    if uuid_rc != NVML_SUCCESS:
        raise SystemExit(5)

    current_mig = ctypes.c_uint(99)
    pending_mig = ctypes.c_uint(99)
    mig_rc = get_mig(handle, ctypes.byref(current_mig), ctypes.byref(pending_mig))

    virtualization_mode = ctypes.c_uint(99)
    virtualization_rc = get_virtualization(handle, ctypes.byref(virtualization_mode))

    print(
        json.dumps(
            {
                "uuid": uuid_buffer.value.decode("ascii"),
                "mig_status": mig_rc,
                "mig_current": current_mig.value,
                "virtualization_status": virtualization_rc,
                "virtualization_mode": virtualization_mode.value,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
finally:
    shutdown()
"#;

#[cfg(unix)]
const NVML_SUCCESS: u32 = 0;
#[cfg(unix)]
const NVML_ERROR_NOT_SUPPORTED: u32 = 3;
#[cfg(unix)]
const NVML_DEVICE_MIG_DISABLE: u32 = 0;
#[cfg(unix)]
const NVML_DEVICE_MIG_ENABLE: u32 = 1;
#[cfg(unix)]
const NVML_GPU_VIRTUALIZATION_MODE_NONE: u32 = 0;
#[cfg(unix)]
const NVML_GPU_VIRTUALIZATION_MODE_PASSTHROUGH: u32 = 1;
#[cfg(unix)]
const NVML_GPU_VIRTUALIZATION_MODE_VGPU: u32 = 2;
#[cfg(unix)]
const NVML_GPU_VIRTUALIZATION_MODE_HOST_VGPU: u32 = 3;
#[cfg(unix)]
const NVML_GPU_VIRTUALIZATION_MODE_HOST_VSGA: u32 = 4;

#[cfg(unix)]
#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct NvmlProbeRecord {
    uuid: String,
    mig_status: u32,
    mig_current: u32,
    virtualization_status: u32,
    virtualization_mode: u32,
}

#[cfg(unix)]
fn probe_unix(uuid: &str, deadline: Instant) -> Option<bool> {
    let record = run_bounded_probe(uuid, deadline)?;
    if record.uuid != uuid || !is_canonical_gpu_uuid(&record.uuid) {
        return None;
    }

    let virtualization_mode = if record.virtualization_status != NVML_SUCCESS {
        return None;
    } else {
        match record.virtualization_mode {
            NVML_GPU_VIRTUALIZATION_MODE_NONE => NvmlVirtualizationMode::BareMetal,
            NVML_GPU_VIRTUALIZATION_MODE_PASSTHROUGH => NvmlVirtualizationMode::Passthrough,
            NVML_GPU_VIRTUALIZATION_MODE_VGPU => NvmlVirtualizationMode::Vgpu,
            NVML_GPU_VIRTUALIZATION_MODE_HOST_VGPU => NvmlVirtualizationMode::HostVgpu,
            NVML_GPU_VIRTUALIZATION_MODE_HOST_VSGA => NvmlVirtualizationMode::HostVsga,
            _ => NvmlVirtualizationMode::Unknown,
        }
    };
    if matches!(
        virtualization_mode,
        NvmlVirtualizationMode::Vgpu
            | NvmlVirtualizationMode::HostVgpu
            | NvmlVirtualizationMode::HostVsga
    ) {
        return Some(false);
    }
    if matches!(virtualization_mode, NvmlVirtualizationMode::Unknown) {
        return None;
    }

    let mig_mode = match record.mig_status {
        NVML_SUCCESS => match record.mig_current {
            NVML_DEVICE_MIG_DISABLE => NvmlMigMode::Disabled,
            NVML_DEVICE_MIG_ENABLE => NvmlMigMode::Enabled,
            _ => NvmlMigMode::Unknown,
        },
        NVML_ERROR_NOT_SUPPORTED => NvmlMigMode::NotSupported,
        _ => NvmlMigMode::Unknown,
    };
    if matches!(mig_mode, NvmlMigMode::Enabled) {
        return Some(false);
    }
    if matches!(mig_mode, NvmlMigMode::Unknown) {
        return None;
    }

    Some(verified_full_device(
        uuid,
        &record.uuid,
        mig_mode,
        virtualization_mode,
    ))
}

#[cfg(unix)]
fn run_bounded_probe(uuid: &str, deadline: Instant) -> Option<NvmlProbeRecord> {
    if Instant::now() >= deadline {
        return None;
    }

    let mut command = std::process::Command::new("python3");
    crate::process_environment::remove_local_compute_operator_token(&mut command);
    command
        .args(["-I", "-c", NVML_PROBE_SCRIPT, uuid])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null());
    let mut child = command.spawn().ok()?;

    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                let output = child.wait_with_output().ok()?;
                if !status.success() {
                    return None;
                }
                return serde_json::from_slice(&output.stdout).ok();
            }
            Ok(None) if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
            Ok(None) => {
                let remaining = deadline.saturating_duration_since(Instant::now());
                std::thread::sleep(remaining.min(std::time::Duration::from_millis(10)));
            }
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{is_canonical_gpu_uuid, verified_full_device, NvmlMigMode, NvmlVirtualizationMode};

    const UUID: &str = "GPU-00112233-4455-6677-8899-aabbccddeeff";

    #[test]
    fn only_exact_bare_metal_or_passthrough_full_proof_promotes() {
        assert!(verified_full_device(
            UUID,
            UUID,
            NvmlMigMode::NotSupported,
            NvmlVirtualizationMode::BareMetal,
        ));
        assert!(verified_full_device(
            UUID,
            UUID,
            NvmlMigMode::Disabled,
            NvmlVirtualizationMode::Passthrough,
        ));
        assert!(!verified_full_device(
            UUID,
            UUID,
            NvmlMigMode::Enabled,
            NvmlVirtualizationMode::BareMetal,
        ));
        assert!(!verified_full_device(
            UUID,
            UUID,
            NvmlMigMode::NotSupported,
            NvmlVirtualizationMode::Vgpu,
        ));
        assert!(!verified_full_device(
            UUID,
            "GPU-ffeeddcc-bbaa-9988-7766-554433221100",
            NvmlMigMode::NotSupported,
            NvmlVirtualizationMode::BareMetal,
        ));
    }

    #[test]
    fn malformed_or_unknown_uuid_evidence_never_promotes() {
        assert!(!is_canonical_gpu_uuid("GPU-a"));
        assert!(!is_canonical_gpu_uuid(
            "MIG-00112233-4455-6677-8899-aabbccddeeff"
        ));
        assert!(!verified_full_device(
            "GPU-a",
            "GPU-a",
            NvmlMigMode::NotSupported,
            NvmlVirtualizationMode::BareMetal,
        ));
        assert!(!verified_full_device(
            UUID,
            UUID,
            NvmlMigMode::Unknown,
            NvmlVirtualizationMode::Unknown,
        ));
    }
}
