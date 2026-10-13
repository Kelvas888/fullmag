//! CUDA-visible ordinal-to-UUID observation through the CUDA Driver API.
//!
//! This module reports the UUID bytes associated with each ordinal visible to
//! the current CUDA process. It does not identify devices by NVML order, change
//! environment variables, create a CUDA context, or decide whether a device is
//! a member of Fullmag's physical-GPU policy. In particular, a v2 UUID may
//! identify a MIG compute instance; callers must enforce physical UUID policy
//! membership, and this inventory alone does not qualify MIG execution.

use std::collections::HashSet;
use std::ffi::c_void;

use anyhow::{anyhow, bail, Result};
use uuid::Uuid;

const MAX_VISIBLE_CUDA_DEVICES: i32 = 256;

type CuInit = unsafe extern "system" fn(flags: u32) -> i32;
type CuDeviceGetCount = unsafe extern "system" fn(count: *mut i32) -> i32;
type CuDeviceGet = unsafe extern "system" fn(device: *mut i32, ordinal: i32) -> i32;
type CuDeviceGetUuidV2 = unsafe extern "system" fn(uuid: *mut CuUuid, device: i32) -> i32;

// CUDA declares CUuuid as a 16-byte array in a C struct.
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct CuUuid {
    bytes: [u8; 16],
}

struct CudaDriver {
    // Keep the module loaded for as long as any resolved function pointer can be used.
    _library: DynamicLibrary,
    init: CuInit,
    device_get_count: CuDeviceGetCount,
    device_get: CuDeviceGet,
    device_get_uuid_v2: CuDeviceGetUuidV2,
}

impl CudaDriver {
    fn load() -> Result<Self> {
        let library = DynamicLibrary::open()?;

        // v2 is required: the legacy UUID entry point can alias a MIG device to
        // its parent GPU, which is not sufficient for identity checks.
        let init = unsafe { std::mem::transmute::<*mut c_void, CuInit>(library.symbol("cuInit")?) };
        let device_get_count = unsafe {
            std::mem::transmute::<*mut c_void, CuDeviceGetCount>(
                library.symbol("cuDeviceGetCount")?,
            )
        };
        let device_get = unsafe {
            std::mem::transmute::<*mut c_void, CuDeviceGet>(library.symbol("cuDeviceGet")?)
        };
        let device_get_uuid_v2 = unsafe {
            std::mem::transmute::<*mut c_void, CuDeviceGetUuidV2>(
                library.symbol("cuDeviceGetUuid_v2")?,
            )
        };

        Ok(Self {
            _library: library,
            init,
            device_get_count,
            device_get,
            device_get_uuid_v2,
        })
    }
}

/// Return canonical `GPU-<uuid>` values in the current CUDA-visible ordinal order.
///
/// The vector index is the CUDA ordinal observed in this process. The result is
/// a point-in-time identity observation only: callers remain responsible for
/// matching each UUID against the configured physical-GPU policy. No CUDA
/// context is created and no environment variable is read or changed here.
pub fn discover_cuda_device_uuids() -> Result<Vec<String>> {
    let driver = CudaDriver::load()?;

    // cuInit initializes the Driver API but does not create a CUDA context.
    check_cuda("cuInit", unsafe { (driver.init)(0) })?;

    let mut device_count = -1;
    check_cuda("cuDeviceGetCount", unsafe {
        (driver.device_get_count)(&mut device_count)
    })?;
    let device_count = checked_device_count(device_count)?;

    let mut seen = HashSet::with_capacity(device_count);
    let mut uuids = Vec::with_capacity(device_count);
    for ordinal in 0..device_count {
        let ordinal = ordinal as i32;
        let mut device = -1;
        check_cuda(&format!("cuDeviceGet(ordinal {ordinal})"), unsafe {
            (driver.device_get)(&mut device, ordinal)
        })?;

        let mut uuid = CuUuid::default();
        check_cuda(&format!("cuDeviceGetUuid_v2(ordinal {ordinal})"), unsafe {
            (driver.device_get_uuid_v2)(&mut uuid, device)
        })?;

        if !seen.insert(uuid.bytes) {
            bail!("CUDA returned a duplicate device UUID at ordinal {ordinal}");
        }
        uuids.push(format_gpu_uuid(uuid.bytes));
    }

    Ok(uuids)
}

fn checked_device_count(count: i32) -> Result<usize> {
    if count < 0 {
        bail!("CUDA returned an invalid negative device count: {count}");
    }
    if count > MAX_VISIBLE_CUDA_DEVICES {
        bail!(
            "CUDA reported {count} visible devices, above the safety limit of {MAX_VISIBLE_CUDA_DEVICES}"
        );
    }
    Ok(count as usize)
}

fn check_cuda(operation: &str, result: i32) -> Result<()> {
    if result == 0 {
        Ok(())
    } else {
        Err(anyhow!(
            "{operation} failed with CUDA driver status {result}"
        ))
    }
}

fn format_gpu_uuid(bytes: [u8; 16]) -> String {
    format!("GPU-{}", Uuid::from_bytes(bytes).hyphenated())
}

#[cfg(unix)]
struct DynamicLibrary {
    handle: *mut c_void,
}

#[cfg(unix)]
impl DynamicLibrary {
    fn open() -> Result<Self> {
        let name = std::ffi::CString::new("libcuda.so.1").expect("static library name");
        let handle = unsafe { libc::dlopen(name.as_ptr(), libc::RTLD_NOW | libc::RTLD_LOCAL) };
        if handle.is_null() {
            let detail = last_dl_error().unwrap_or_else(|| "no loader detail".to_owned());
            bail!("could not load libcuda.so.1: {detail}");
        }
        Ok(Self { handle })
    }

    fn symbol(&self, name: &str) -> Result<*mut c_void> {
        let name_c = std::ffi::CString::new(name).expect("static CUDA symbol name");
        unsafe {
            // POSIX requires clearing dlerror before using it to detect dlsym failure.
            let _ = libc::dlerror();
            let symbol = libc::dlsym(self.handle, name_c.as_ptr());
            if let Some(detail) = last_dl_error() {
                bail!("could not resolve CUDA driver symbol {name}: {detail}");
            }
            if symbol.is_null() {
                bail!("CUDA driver symbol {name} resolved to a null address");
            }
            Ok(symbol)
        }
    }
}

#[cfg(unix)]
fn last_dl_error() -> Option<String> {
    let error = unsafe { libc::dlerror() };
    if error.is_null() {
        None
    } else {
        Some(
            unsafe { std::ffi::CStr::from_ptr(error) }
                .to_string_lossy()
                .into_owned(),
        )
    }
}

#[cfg(unix)]
impl Drop for DynamicLibrary {
    fn drop(&mut self) {
        unsafe {
            libc::dlclose(self.handle);
        }
    }
}

#[cfg(windows)]
struct DynamicLibrary {
    handle: *mut c_void,
}

#[cfg(windows)]
impl DynamicLibrary {
    fn open() -> Result<Self> {
        const LOAD_LIBRARY_SEARCH_SYSTEM32: u32 = 0x0000_0800;

        let name: Vec<u16> = "nvcuda.dll"
            .encode_utf16()
            .chain(std::iter::once(0))
            .collect();
        let handle = unsafe {
            load_library_ex_w(
                name.as_ptr(),
                std::ptr::null_mut(),
                LOAD_LIBRARY_SEARCH_SYSTEM32,
            )
        };
        if handle.is_null() {
            return Err(anyhow!(
                "could not load nvcuda.dll from System32: {}",
                std::io::Error::last_os_error()
            ));
        }
        Ok(Self { handle })
    }

    fn symbol(&self, name: &str) -> Result<*mut c_void> {
        let name = std::ffi::CString::new(name).expect("static CUDA symbol name");
        let symbol = unsafe { get_proc_address(self.handle, name.as_ptr()) };
        if symbol.is_null() {
            return Err(anyhow!(
                "could not resolve CUDA driver symbol {}: {}",
                name.to_string_lossy(),
                std::io::Error::last_os_error()
            ));
        }
        Ok(symbol)
    }
}

#[cfg(windows)]
#[link(name = "kernel32")]
extern "system" {
    #[link_name = "LoadLibraryExW"]
    fn load_library_ex_w(file_name: *const u16, file: *mut c_void, flags: u32) -> *mut c_void;
    #[link_name = "GetProcAddress"]
    fn get_proc_address(module: *mut c_void, proc_name: *const std::ffi::c_char) -> *mut c_void;
    #[link_name = "FreeLibrary"]
    fn free_library(module: *mut c_void) -> i32;
}

#[cfg(windows)]
impl Drop for DynamicLibrary {
    fn drop(&mut self) {
        unsafe {
            free_library(self.handle);
        }
    }
}

#[cfg(not(any(unix, windows)))]
struct DynamicLibrary;

#[cfg(not(any(unix, windows)))]
impl DynamicLibrary {
    fn open() -> Result<Self> {
        bail!("CUDA device identity discovery is unsupported on this platform");
    }

    fn symbol(&self, _name: &str) -> Result<*mut c_void> {
        bail!("CUDA device identity discovery is unsupported on this platform");
    }
}

#[cfg(test)]
mod tests {
    use super::{checked_device_count, format_gpu_uuid};

    #[test]
    fn formats_uuid_as_canonical_nvidia_identity() {
        assert_eq!(
            format_gpu_uuid([
                0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd,
                0xee, 0xff,
            ]),
            "GPU-00112233-4455-6677-8899-aabbccddeeff"
        );
    }

    #[test]
    fn bounds_cuda_visible_device_count() {
        assert_eq!(checked_device_count(0).unwrap(), 0);
        assert_eq!(checked_device_count(256).unwrap(), 256);
        assert!(checked_device_count(-1).is_err());
        assert!(checked_device_count(257).is_err());
    }
}
