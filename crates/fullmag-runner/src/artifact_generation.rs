//! Final-byte membership for a committed frequency-domain publication.
//! This proves content membership, never physics or runtime authentication.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};

pub const COMMIT_PATH: &str = "frequency_domain/generation.v1.json";
pub const IMMUTABLE_COMMIT_PATH: &str = "frequency_domain/generation.v2.json";
const GENERATION_DIRECTORY: &str = "frequency_domain/generations";
const SCHEMA: &str = "frequency_domain_artifact_generation.v1";
const IMMUTABLE_SCHEMA: &str = "frequency_domain_artifact_generation.v2";
const MAX_COMMIT_BYTES: u64 = 4 * 1024 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicationOwner {
    pub run_id: String,
    pub stage_id: String,
    pub stage_kind: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct GenerationMember {
    pub byte_length: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct GenerationBody {
    pub schema_version: String,
    /// Supplied by execution ownership; absence is not filled from the viewer.
    pub producer: Option<PublicationOwner>,
    pub members: BTreeMap<String, GenerationMember>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct GenerationCommit {
    pub generation_id: String,
    pub content: GenerationBody,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum GenerationLayout {
    MutableV1,
    ImmutableV2,
}

#[derive(Debug, Clone)]
pub struct GenerationCapture {
    pub commit: GenerationCommit,
    commit_digest: String,
    layout: GenerationLayout,
}

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

fn digest(bytes: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(bytes))
}

fn valid_digest(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|v| {
        v.len() == 64 && v.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

fn validate_relative(relative: &str) -> io::Result<PathBuf> {
    if relative.is_empty()
        || relative.contains(char::from(92))
        || relative.contains(':')
        || relative.as_bytes().contains(&0)
    {
        return Err(invalid("generation member path is not canonical relative"));
    }
    let path = Path::new(relative);
    if path.components().any(|c| !matches!(c, Component::Normal(_)))
        || path.to_string_lossy() != relative
        || relative.split('/').any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(invalid("generation member path escapes its publication"));
    }
    Ok(path.to_path_buf())
}

fn is_reserved_member_path(relative: &str) -> bool {
    [
        COMMIT_PATH,
        IMMUTABLE_COMMIT_PATH,
        "WRITER.owner.json",
        GENERATION_DIRECTORY,
    ]
    .iter()
    .any(|reserved| {
        relative == *reserved
            || relative
                .strip_prefix(*reserved)
                .is_some_and(|tail| tail.starts_with('/'))
    })
}

fn validate_member_path(relative: &str) -> io::Result<PathBuf> {
    let path = validate_relative(relative)?;
    if is_reserved_member_path(relative) {
        return Err(invalid("generation member uses a reserved publication path"));
    }
    Ok(path)
}
fn checked_path(root: &Path, relative: &str) -> io::Result<PathBuf> {
    if relative.is_empty() || (relative.contains('\\') || relative.contains(':') || relative.contains('\0')) {
        return Err(invalid("generation member path is not canonical relative"));
    }
    let path = Path::new(relative);
    if path.components().any(|c| !matches!(c, Component::Normal(_)))
        || path.to_string_lossy() != relative
        || relative.split('/').any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(invalid("generation member path escapes its publication"));
    }
    let canonical_root = fs::canonicalize(root)?;
    let mut candidate = canonical_root.clone();
    for part in path.components() {
        candidate.push(part.as_os_str());
        let metadata = fs::symlink_metadata(&candidate)?;
        if metadata.file_type().is_symlink() || is_reparse_point(&metadata) {
            return Err(invalid("generation member contains a symlink or reparse point"));
        }
    }
    let canonical = fs::canonicalize(&candidate)?;
    if !canonical.starts_with(&canonical_root) || !fs::metadata(&canonical)?.is_file() {
        return Err(invalid("generation member is not a regular in-root file"));
    }
    Ok(canonical)
}

#[cfg(windows)]
fn is_reparse_point(metadata: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    metadata.file_attributes() & 0x400 != 0
}
#[cfg(not(windows))]
fn is_reparse_point(_: &fs::Metadata) -> bool { false }

fn checked_directory(root: &Path, relative: &str) -> io::Result<PathBuf> {
    let path = validate_relative(relative)?;
    let canonical_root = fs::canonicalize(root)?;
    let mut candidate = canonical_root.clone();
    for part in path.components() {
        candidate.push(part.as_os_str());
        let metadata = fs::symlink_metadata(&candidate)?;
        if metadata.file_type().is_symlink() || is_reparse_point(&metadata) || !metadata.is_dir() {
            return Err(invalid("generation directory contains a link or non-directory"));
        }
    }
    let canonical = fs::canonicalize(&candidate)?;
    if !canonical.starts_with(&canonical_root) || !fs::metadata(&canonical)?.is_dir() {
        return Err(invalid("generation directory is not an in-root directory"));
    }
    Ok(canonical)
}

fn ensure_real_directory(path: &Path) -> io::Result<()> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            match fs::create_dir(path) {
                Ok(()) => fs::symlink_metadata(path)?,
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => fs::symlink_metadata(path)?,
                Err(error) => return Err(error),
            }
        }
        Err(error) => return Err(error),
    };
    if metadata.file_type().is_symlink() || is_reparse_point(&metadata) || !metadata.is_dir() {
        return Err(invalid("generation path traverses a link or non-directory"));
    }
    Ok(())
}

fn ensure_directory_chain(root: &Path, relative: &str) -> io::Result<PathBuf> {
    let relative = validate_relative(relative)?;
    let mut current = fs::canonicalize(root)?;
    for part in relative.components() {
        current.push(part.as_os_str());
        ensure_real_directory(&current)?;
    }
    Ok(current)
}

fn create_private_staging(path: &Path) -> io::Result<()> {
    let mut builder = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    builder.create(path)?;
    let metadata = fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink() || is_reparse_point(&metadata) || !metadata.is_dir() {
        return Err(invalid("generation staging path is not a private directory"));
    }
    Ok(())
}

fn write_member_bytes(root: &Path, relative: &str, bytes: &[u8]) -> io::Result<()> {
    let relative_path = validate_member_path(relative)?;
    if let Some(parent) = relative_path.parent() {
        let mut current = root.to_path_buf();
        for part in parent.components() {
            current.push(part.as_os_str());
            ensure_real_directory(&current)?;
        }
    }
    let destination = root.join(relative_path);
    let mut file = fs::OpenOptions::new().write(true).create_new(true).open(destination)?;
    file.write_all(bytes)?;
    file.sync_all()
}

fn verify_members_at_directory(
    directory: &Path,
    expected_members: &BTreeMap<String, GenerationMember>,
) -> io::Result<()> {
    for (relative, expected) in expected_members {
        validate_member_path(relative)?;
        let path = checked_path(directory, relative)?;
        if fs::metadata(&path)?.len() != expected.byte_length
            || hash_file_with_budget(&path, expected.byte_length)? != *expected
        {
            return Err(invalid("immutable generation member differs from its content identity"));
        }
    }
    Ok(())
}

fn marker_path_if_present(root: &Path, relative: &str) -> io::Result<Option<PathBuf>> {
    let path = validate_relative(relative)?;
    let canonical_root = fs::canonicalize(root)?;
    let mut candidate = canonical_root;
    let parts = path.components().collect::<Vec<_>>();
    for (index, part) in parts.iter().enumerate() {
        candidate.push(part.as_os_str());
        let metadata = match fs::symlink_metadata(&candidate) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        };
        if metadata.file_type().is_symlink() || is_reparse_point(&metadata) {
            return Err(invalid("generation commit path contains a link or reparse point"));
        }
        if index + 1 < parts.len() && !metadata.is_dir() {
            return Err(invalid("generation commit parent is not a directory"));
        }
        if index + 1 == parts.len() && !metadata.is_file() {
            return Err(invalid("generation commit is not a regular file"));
        }
    }
    Ok(Some(candidate))
}

fn validate_publication_root(root: &Path) -> io::Result<bool> {
    match fs::symlink_metadata(root) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() || is_reparse_point(&metadata) || !metadata.is_dir() {
                return Err(invalid("publication root is redirected or not a directory"));
            }
            Ok(true)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error),
    }
}

pub(crate) fn ensure_legacy_publication_allowed(root: &Path) -> io::Result<()> {
    if !validate_publication_root(root)? {
        return Ok(());
    }
    if marker_path_if_present(root, IMMUTABLE_COMMIT_PATH)?.is_some() {
        return Err(invalid("v1 publisher cannot shadow the current immutable v2 generation"));
    }
    Ok(())
}

fn hash_file(path: &Path) -> io::Result<GenerationMember> {
    hash_file_with_budget(path, fs::metadata(path)?.len())
}

fn hash_file_with_budget(path: &Path, byte_budget: u64) -> io::Result<GenerationMember> {
    let mut file = fs::File::open(path)?.take(byte_budget.saturating_add(1));
    let mut hasher = Sha256::new();
    let mut byte_length = 0u64;
    let mut buffer = [0u8; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 { break; }
        byte_length = byte_length.checked_add(count as u64)
            .ok_or_else(|| invalid("generation member length overflow"))?;
        if byte_length > byte_budget { return Err(invalid("generation member grew during hashing")); }
        hasher.update(&buffer[..count]);
    }
    Ok(GenerationMember { byte_length, sha256: format!("sha256:{:x}", hasher.finalize()) })
}

fn generation_id(body: &GenerationBody) -> io::Result<String> {
    Ok(digest(&serde_json::to_vec(body)?))
}

/// Exclusive final publication. A crash leaves a lease for explicit recovery;
/// readers still reject mismatching bytes instead of accepting partial output.
pub(crate) struct PublicationLease {
    path: PathBuf,
    token: String,
}
impl PublicationLease {
    pub(crate) fn acquire(root: &Path) -> io::Result<Self> {
        fs::create_dir_all(root)?;
        let path = root.join(".frequency-domain-publication.lease");
        let token = format!("{}:{}", std::process::id(), uuid::Uuid::new_v4());
        let mut file = fs::OpenOptions::new().write(true).create_new(true).open(&path)?;
        file.write_all(token.as_bytes())?;
        file.sync_all()?;
        Ok(Self { path, token })
    }
}
impl Drop for PublicationLease {
    fn drop(&mut self) {
        // Do not remove a replaced lease belonging to a different publisher.
        if fs::read(&self.path).ok().as_deref() == Some(self.token.as_bytes()) {
            let _ = fs::remove_file(&self.path);
        }
    }
}

/// Construct from this invocation's member list; never scan stale directory files.
pub(crate) fn publish(
    root: &Path,
    producer: Option<PublicationOwner>,
    member_paths: impl IntoIterator<Item = String>,
) -> io::Result<()> {
    if producer.as_ref().is_some_and(|owner| {
        [&owner.run_id, &owner.stage_id, &owner.stage_kind].iter().any(|v| v.trim().is_empty())
    }) { return Err(invalid("incomplete generation producer identity")); }
    ensure_legacy_publication_allowed(root)?;
    let mut members = BTreeMap::new();
    for relative in member_paths {
        validate_member_path(&relative)?;
        let member = hash_file(&checked_path(root, &relative)?)?;
        if members.insert(relative, member).is_some() {
            return Err(invalid("duplicate generation member"));
        }
    }
    if members.is_empty() { return Err(invalid("empty generation publication")); }
    let content = GenerationBody { schema_version: SCHEMA.into(), producer, members };
    let commit = GenerationCommit { generation_id: generation_id(&content)?, content };
    // No claim that a mutable directory is an immutable snapshot. Every reader
    // validates the exact consumed bytes against this final commit.
    for (relative, expected) in &commit.content.members {
        if hash_file(&checked_path(root, relative)?)? != *expected {
            return Err(invalid("generation member changed before publication"));
        }
    }
    if serde_json::to_vec_pretty(&commit)?.len() as u64 > MAX_COMMIT_BYTES {
        return Err(invalid("generation commit exceeds control-plane bound"));
    }
    fs::create_dir_all(root.join("frequency_domain"))?;
    let parent_metadata = fs::symlink_metadata(root.join("frequency_domain"))?;
    if parent_metadata.file_type().is_symlink() || is_reparse_point(&parent_metadata) {
        return Err(invalid("generation commit directory is redirected"));
    }
    crate::autosave_zarr::write_json_atomic(&root.join(COMMIT_PATH), &commit)
        .map_err(invalid)
}

/// Publish an immutable v2 generation from this invocation's exact member bytes.
///
/// Members are written into a unique private sibling directory and published
/// without replacement. The v2 current pointer is atomically replaced last.
/// This additive API is not yet used by the production artifact writer.
/// It does not claim power-loss durability for every filesystem/platform.
pub fn publish_immutable(
    root: &Path,
    producer: Option<PublicationOwner>,
    member_bytes: impl IntoIterator<Item = (String, Vec<u8>)>,
) -> io::Result<GenerationCommit> {
    validate_publication_root(root)?;
    if producer.as_ref().is_some_and(|owner| {
        [&owner.run_id, &owner.stage_id, &owner.stage_kind].iter().any(|value| value.trim().is_empty())
    }) {
        return Err(invalid("incomplete generation producer identity"));
    }


    let mut payloads = BTreeMap::new();
    let mut members = BTreeMap::new();
    for (relative, bytes) in member_bytes {
        validate_member_path(&relative)?;
        let byte_length = u64::try_from(bytes.len())
            .map_err(|_| invalid("generation member length exceeds u64"))?;
        let member = GenerationMember { byte_length, sha256: digest(&bytes) };
        if members.insert(relative.clone(), member).is_some() {
            return Err(invalid("duplicate generation member"));
        }
        payloads.insert(relative, bytes);
    }
    if members.is_empty() {
        return Err(invalid("empty generation publication"));
    }

    let content = GenerationBody {
        schema_version: IMMUTABLE_SCHEMA.into(),
        producer,
        members,
    };
    let commit = GenerationCommit {
        generation_id: generation_id(&content)?,
        content,
    };
    if !valid_digest(&commit.generation_id)
        || serde_json::to_vec_pretty(&commit)?.len() as u64 > MAX_COMMIT_BYTES
    {
        return Err(invalid("invalid or oversized immutable generation commit"));
    }

    validate_publication_root(root)?;
    let _lease = PublicationLease::acquire(root)?;
    validate_publication_root(root)?;
    let root = fs::canonicalize(root)?;
    if marker_path_if_present(&root, IMMUTABLE_COMMIT_PATH)?.is_some() {
        capture_from_marker(
            &root,
            IMMUTABLE_COMMIT_PATH,
            IMMUTABLE_SCHEMA,
            GenerationLayout::ImmutableV2,
        )?;
    }
    let generations_directory = ensure_directory_chain(&root, GENERATION_DIRECTORY)?;

    let generation_name = commit.generation_id.strip_prefix("sha256:")
        .ok_or_else(|| invalid("immutable generation ID is not a SHA-256 digest"))?;
    let destination = generations_directory.join(generation_name);
    let generation_relative = format!("{GENERATION_DIRECTORY}/{generation_name}");

    match fs::symlink_metadata(&destination) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() || is_reparse_point(&metadata) || !metadata.is_dir() {
                return Err(invalid("immutable generation destination is not a regular directory"));
            }
            let existing = checked_directory(&root, &generation_relative)?;
            verify_members_at_directory(&existing, &commit.content.members)?;
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            let staging = generations_directory.join(format!(
                ".stage-{}-{}",
                std::process::id(),
                uuid::Uuid::new_v4()
            ));
            create_private_staging(&staging)?;
            for (relative, bytes) in &payloads {
                write_member_bytes(&staging, relative, bytes)?;
            }
            verify_members_at_directory(&staging, &commit.content.members)?;

            fullmag_session::publish_directory(&staging, &destination).map_err(|error| {
                match error.downcast::<fullmag_session::PublicationUncertain>() {
                    Ok(uncertain) => io::Error::new(io::ErrorKind::Other, uncertain),
                    Err(error) => match error.downcast::<fullmag_session::WriterReleaseUnconfirmed>() {
                        Ok(unconfirmed) => io::Error::new(io::ErrorKind::Other, unconfirmed),
                        Err(error) => io::Error::new(io::ErrorKind::Other, error),
                    },
                }
            })?;

            // Revalidate after the no-replace rename. Any failure leaves the
            // published directory as an orphan and the current pointer intact.
            let published = checked_directory(&root, &generation_relative)?;
            verify_members_at_directory(&published, &commit.content.members)?;
        }
        Err(error) => return Err(error),
    }

    #[cfg(test)]
    if fail_v2_before_marker() {
        return Err(invalid("injected failure after immutable directory publication"));
    }

    crate::autosave_zarr::write_json_atomic(&root.join(IMMUTABLE_COMMIT_PATH), &commit)
        .map_err(invalid)?;
    Ok(commit)
}
fn capture_from_marker(
    root: &Path,
    relative: &str,
    expected_schema: &str,
    layout: GenerationLayout,
) -> io::Result<GenerationCapture> {
    let path = checked_path(root, relative)?;
    if fs::metadata(&path)?.len() > MAX_COMMIT_BYTES {
        return Err(invalid("generation commit exceeds control-plane bound"));
    }
    let mut bytes = Vec::new();
    fs::File::open(path)?.take(MAX_COMMIT_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_COMMIT_BYTES {
        return Err(invalid("oversize generation commit"));
    }
    let commit: GenerationCommit = serde_json::from_slice(&bytes)?;
    if serde_json::to_vec_pretty(&commit)? != bytes {
        return Err(invalid("generation commit is not canonical or has duplicate fields"));
    }
    if commit.content.schema_version != expected_schema
        || commit.content.members.is_empty()
        || generation_id(&commit.content)? != commit.generation_id
        || !valid_digest(&commit.generation_id)
        || commit.content.members.iter().any(|(path, member)| {
            validate_member_path(path).is_err() || !valid_digest(&member.sha256)
        })
        || commit.content.producer.as_ref().is_some_and(|owner| {
            [&owner.run_id, &owner.stage_id, &owner.stage_kind]
                .iter()
                .any(|value| value.trim().is_empty())
        })
    {
        return Err(invalid("invalid generation commit"));
    }
    Ok(GenerationCapture {
        commit,
        commit_digest: digest(&bytes),
        layout,
    })
}

pub fn capture(root: &Path) -> io::Result<Option<GenerationCapture>> {
    let canonical_root = match fs::canonicalize(root) {
        Ok(root) => root,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    if marker_path_if_present(&canonical_root, IMMUTABLE_COMMIT_PATH)?.is_some() {
        return capture_from_marker(
            &canonical_root,
            IMMUTABLE_COMMIT_PATH,
            IMMUTABLE_SCHEMA,
            GenerationLayout::ImmutableV2,
        ).map(Some);
    }
    if marker_path_if_present(&canonical_root, COMMIT_PATH)?.is_some() {
        return capture_from_marker(
            &canonical_root,
            COMMIT_PATH,
            SCHEMA,
            GenerationLayout::MutableV1,
        ).map(Some);
    }
    Ok(None)
}
impl GenerationCapture {
    /// Whether this capture resolves members inside a content-addressed v2 generation.
    pub fn is_immutable(&self) -> bool {
        self.layout == GenerationLayout::ImmutableV2
    }

    fn checked_member_path(&self, root: &Path, relative: &str) -> io::Result<PathBuf> {
        validate_member_path(relative)?;
        match self.layout {
            GenerationLayout::MutableV1 if self.commit.content.schema_version == SCHEMA => {
                checked_path(root, relative)
            }
            GenerationLayout::ImmutableV2 if self.commit.content.schema_version == IMMUTABLE_SCHEMA => {
                let generation_name = self.commit.generation_id.strip_prefix("sha256:")
                    .filter(|value| valid_digest(&self.commit.generation_id) && value.len() == 64)
                    .ok_or_else(|| invalid("immutable generation ID is invalid"))?;
                let physical = format!("{GENERATION_DIRECTORY}/{generation_name}/{relative}");
                checked_path(root, &physical)
            }
            _ => Err(invalid("generation capture layout does not match its schema")),
        }
    }
    pub fn ensure_current(&self, root: &Path) -> io::Result<()> {
        let current = capture(root)?.ok_or_else(|| invalid("generation commit disappeared"))?;
        if current.commit_digest != self.commit_digest || current.commit != self.commit || current.layout != self.layout {
            return Err(invalid("frequency-domain generation changed"));
        }
        Ok(())
    }

    /// Streaming membership check for metadata endpoints. This does not pin a
    /// later data-plane request; that request must verify its own served bytes.
    pub fn verify_member(&self, root: &Path, relative: &str) -> io::Result<GenerationMember> {
        let expected = self.commit.content.members.get(relative)
            .ok_or_else(|| invalid("artifact is not a member of the captured generation"))?;
        let path = self.checked_member_path(root, relative)?;
        if fs::metadata(&path)?.len() != expected.byte_length {
            return Err(invalid("frequency-domain generation member length changed"));
        }
        let measured = hash_file_with_budget(&path, expected.byte_length)?;
        if measured != *expected {
            return Err(invalid("frequency-domain generation member changed"));
        }
        self.ensure_current(root)?;
        Ok(measured)
    }

    /// Returns the very bytes whose membership was verified, not a second read.
    pub fn read_member(&self, root: &Path, relative: &str) -> io::Result<Vec<u8>> {
        let maximum = self.commit.content.members.get(relative)
            .ok_or_else(|| invalid("artifact is not a member of the captured generation"))?.byte_length;
        self.read_member_bounded(root, relative, maximum)
    }

    /// Reject oversized control-plane members before allocating their contents.
    pub fn read_member_bounded(&self, root: &Path, relative: &str, maximum: u64) -> io::Result<Vec<u8>> {
        let expected = self.commit.content.members.get(relative)
            .ok_or_else(|| invalid("artifact is not a member of the captured generation"))?;
        if expected.byte_length > maximum {
            return Err(invalid("generation member exceeds reader byte budget"));
        }
        let path = self.checked_member_path(root, relative)?;
        let file = fs::File::open(path)?;
        if file.metadata()?.len() != expected.byte_length {
            return Err(invalid("frequency-domain generation member length changed"));
        }
        let read_limit = expected.byte_length.checked_add(1)
            .ok_or_else(|| invalid("generation member length cannot be bounded"))?;
        let reserve = usize::try_from(read_limit)
            .map_err(|_| invalid("generation member exceeds addressable memory"))?;
        let mut bytes = Vec::new();
        bytes.try_reserve_exact(reserve)
            .map_err(|error| invalid(format!("cannot allocate bounded generation member: {error}")))?;
        file.take(read_limit).read_to_end(&mut bytes)?;
        if bytes.len() as u64 != expected.byte_length || digest(&bytes) != expected.sha256 {
            return Err(invalid("frequency-domain generation member changed"));
        }
        self.ensure_current(root)?;
        Ok(bytes)
    }
}

#[cfg(test)]
std::thread_local! {
    static FAIL_V2_BEFORE_MARKER: std::cell::Cell<bool> = std::cell::Cell::new(false);
}

#[cfg(test)]
fn fail_v2_before_marker() -> bool {
    FAIL_V2_BEFORE_MARKER.with(|flag| flag.replace(false))
}
#[cfg(test)]
mod tests {
    use super::*;
    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!("fullmag-generation-{}", uuid::Uuid::new_v4()));
            fs::create_dir_all(root.join("frequency_domain")).unwrap();
            fs::create_dir_all(root.join("eigen")).unwrap();
            Self(root)
        }
    }
    impl Drop for Temp { fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); } }
    fn fixture(root: &Path) {
        fs::write(root.join("eigen/spectrum.json"), b"one").unwrap();
        fs::write(root.join("eigen/dispersion.csv"), b"two").unwrap();
        publish(root, None, ["eigen/spectrum.json".into(), "eigen/dispersion.csv".into()]).unwrap();
    }
    #[test]
    fn immutable_v2_keeps_history_bytes_and_enforces_current_capture_fence() {
        let tmp = Temp::new();
        let first = publish_immutable(
            &tmp.0,
            None,
            vec![("eigen/result.json".into(), b"first".to_vec())],
        ).unwrap();
        assert_eq!(first.content.schema_version, "frequency_domain_artifact_generation.v2");
        let first_capture = capture(&tmp.0).unwrap().unwrap();
        assert!(first_capture.is_immutable());
        let first_name = first.generation_id.strip_prefix("sha256:").unwrap();
        let first_path = tmp.0.join(GENERATION_DIRECTORY).join(first_name).join("eigen/result.json");

        let second = publish_immutable(
            &tmp.0,
            None,
            vec![("eigen/result.json".into(), b"second".to_vec())],
        ).unwrap();
        assert_ne!(first.generation_id, second.generation_id);
        assert_eq!(fs::read(&first_path).unwrap(), b"first");
        let second_capture = capture(&tmp.0).unwrap().unwrap();
        assert!(second_capture.is_immutable());
        assert_eq!(second_capture.read_member(&tmp.0, "eigen/result.json").unwrap(), b"second");
        assert!(first_capture.ensure_current(&tmp.0).is_err());
    }

    #[test]
    fn v1_publisher_cannot_shadow_valid_or_corrupt_v2_pointer() {
        let tmp = Temp::new();
        fixture(&tmp.0);
        let v1_pointer = fs::read(tmp.0.join(COMMIT_PATH)).unwrap();
        publish_immutable(
            &tmp.0,
            None,
            vec![("eigen/v2.json".into(), b"v2".to_vec())],
        ).unwrap();

        assert!(publish(
            &tmp.0,
            None,
            ["eigen/spectrum.json".into(), "eigen/dispersion.csv".into()],
        ).is_err());
        assert_eq!(fs::read(tmp.0.join(COMMIT_PATH)).unwrap(), v1_pointer);
        assert!(capture(&tmp.0).unwrap().unwrap().is_immutable());

        fs::write(tmp.0.join(IMMUTABLE_COMMIT_PATH), b"not-json").unwrap();
        assert!(publish(
            &tmp.0,
            None,
            ["eigen/spectrum.json".into(), "eigen/dispersion.csv".into()],
        ).is_err());
        assert_eq!(fs::read(tmp.0.join(COMMIT_PATH)).unwrap(), v1_pointer);
        assert!(capture(&tmp.0).is_err());
    }
    #[test]
    fn corrupt_v2_marker_does_not_fall_back_to_valid_v1() {
        let tmp = Temp::new();
        fixture(&tmp.0);
        fs::write(tmp.0.join(IMMUTABLE_COMMIT_PATH), b"not-json").unwrap();
        assert!(capture(&tmp.0).is_err());
    }

    #[test]
    fn immutable_v2_does_not_replace_a_corrupt_current_pointer() {
        let tmp = Temp::new();
        let marker = tmp.0.join(IMMUTABLE_COMMIT_PATH);
        fs::write(&marker, b"not-json").unwrap();
        let original = fs::read(&marker).unwrap();

        assert!(publish_immutable(
            &tmp.0,
            None,
            vec![("eigen/result.json".into(), b"replacement".to_vec())],
        )
        .is_err());
        assert_eq!(fs::read(marker).unwrap(), original);
        assert!(!tmp.0.join(GENERATION_DIRECTORY).exists());
        assert!(!tmp.0.join(".frequency-domain-publication.lease").exists());
    }

    #[cfg(unix)]
    #[test]
    fn immutable_v2_rejects_a_symlink_root_before_mutation() {
        let tmp = Temp::new();
        let linked_root = tmp.0.join("root-link");
        std::os::unix::fs::symlink(&tmp.0, &linked_root).unwrap();

        assert!(publish_immutable(
            &linked_root,
            None,
            vec![("eigen/result.json".into(), b"payload".to_vec())],
        )
        .is_err());
        assert!(!tmp.0.join(".frequency-domain-publication.lease").exists());
        assert!(!tmp.0.join(GENERATION_DIRECTORY).exists());
        assert!(!tmp.0.join(IMMUTABLE_COMMIT_PATH).exists());
    }

    #[test]
    fn immutable_v2_rejects_missing_and_reserved_members() {
        let tmp = Temp::new();
        let captured = {
            publish_immutable(
                &tmp.0,
                None,
                vec![("eigen/present.json".into(), b"present".to_vec())],
            ).unwrap();
            capture(&tmp.0).unwrap().unwrap()
        };
        assert!(captured.read_member(&tmp.0, "eigen/missing.json").is_err());
        let generation_name = captured.commit.generation_id.strip_prefix("sha256:").unwrap();
        let member = tmp.0.join(GENERATION_DIRECTORY).join(generation_name).join("eigen/present.json");
        fs::remove_file(member).unwrap();
        assert!(captured.verify_member(&tmp.0, "eigen/present.json").is_err());

        let other = Temp::new();
        for path in [
            COMMIT_PATH,
            IMMUTABLE_COMMIT_PATH,
            "frequency_domain/generation.v1.json/child",
            "frequency_domain/generation.v2.json/child",
            "WRITER.owner.json/child",
            GENERATION_DIRECTORY,
            "frequency_domain/generations/fake/payload.json",
            "WRITER.owner.json",
        ] {
            assert!(publish_immutable(&other.0, None, vec![(path.into(), b"x".to_vec())]).is_err());
        }
        assert!(capture(&other.0).unwrap().is_none());
        assert!(!other.0.join(GENERATION_DIRECTORY).exists());
    }

    #[test]
    fn immutable_v2_verifies_existing_target_without_replacing_bytes_or_pointer() {
        let tmp = Temp::new();
        let commit = publish_immutable(
            &tmp.0,
            None,
            vec![("eigen/result.json".into(), b"expected".to_vec())],
        ).unwrap();
        let pointer = fs::read(tmp.0.join(IMMUTABLE_COMMIT_PATH)).unwrap();
        let generation_name = commit.generation_id.strip_prefix("sha256:").unwrap();
        let member = tmp.0.join(GENERATION_DIRECTORY).join(generation_name).join("eigen/result.json");
        fs::write(&member, b"tampered").unwrap();

        assert!(publish_immutable(
            &tmp.0,
            None,
            vec![("eigen/result.json".into(), b"expected".to_vec())],
        ).is_err());
        assert_eq!(fs::read(member).unwrap(), b"tampered");
        assert_eq!(fs::read(tmp.0.join(IMMUTABLE_COMMIT_PATH)).unwrap(), pointer);
    }

    #[test]
    fn immutable_v2_keeps_directory_orphan_when_failure_precedes_marker() {
        let tmp = Temp::new();
        let bytes = b"orphan".to_vec();
        FAIL_V2_BEFORE_MARKER.with(|flag| flag.set(true));
        assert!(publish_immutable(
            &tmp.0,
            None,
            vec![("eigen/result.json".into(), bytes.clone())],
        ).is_err());
        assert!(!tmp.0.join(IMMUTABLE_COMMIT_PATH).exists());

        let members = BTreeMap::from([(
            "eigen/result.json".to_string(),
            GenerationMember { byte_length: bytes.len() as u64, sha256: digest(&bytes) },
        )]);
        let body = GenerationBody {
            schema_version: IMMUTABLE_SCHEMA.into(),
            producer: None,
            members,
        };
        let generation_name = generation_id(&body).unwrap().strip_prefix("sha256:").unwrap().to_string();
        let orphan = tmp.0.join(GENERATION_DIRECTORY).join(generation_name).join("eigen/result.json");
        assert_eq!(fs::read(orphan).unwrap(), bytes);

        let recovered = publish_immutable(
            &tmp.0,
            None,
            vec![("eigen/result.json".into(), bytes.clone())],
        ).unwrap();
        assert_eq!(capture(&tmp.0).unwrap().unwrap().read_member(&tmp.0, "eigen/result.json").unwrap(), bytes);
        assert!(recovered.generation_id.starts_with("sha256:"));
    }
    #[test]
    fn exact_members_bind_changed_same_length_csv_and_commit_replacement() {
        let tmp = Temp::new(); fixture(&tmp.0);
        let old = capture(&tmp.0).unwrap().unwrap();
        assert!(!old.is_immutable());
        assert_eq!(old.read_member(&tmp.0, "eigen/dispersion.csv").unwrap(), b"two");
        assert_eq!(old.verify_member(&tmp.0, "eigen/dispersion.csv").unwrap().byte_length, 3);
        assert!(old.read_member_bounded(&tmp.0, "eigen/dispersion.csv", 2).is_err());
        assert_eq!(old.read_member_bounded(&tmp.0, "eigen/dispersion.csv", 3).unwrap(), b"two");
        let mut tampered = old.clone();
        tampered.commit.content.producer = Some(PublicationOwner {
            run_id: "different-run".into(), stage_id: "different-stage".into(), stage_kind: "eigenmodes".into(),
        });
        assert!(tampered.ensure_current(&tmp.0).is_err());
        fs::write(tmp.0.join("eigen/dispersion.csv"), b"new").unwrap();
        assert!(old.read_member(&tmp.0, "eigen/dispersion.csv").is_err());
        assert!(old.verify_member(&tmp.0, "eigen/dispersion.csv").is_err());
        publish(&tmp.0, None, ["eigen/spectrum.json".into(), "eigen/dispersion.csv".into()]).unwrap();
        let new = capture(&tmp.0).unwrap().unwrap();
        assert_ne!(old.commit.generation_id, new.commit.generation_id);
        assert!(old.ensure_current(&tmp.0).is_err());
        assert_eq!(new.read_member(&tmp.0, "eigen/dispersion.csv").unwrap(), b"new");
    }
    #[test]
    fn publication_lease_rejects_concurrent_writers_and_releases_its_own_token() {
        let tmp = Temp::new();
        let first = PublicationLease::acquire(&tmp.0).unwrap();
        assert_eq!(PublicationLease::acquire(&tmp.0).err().unwrap().kind(), io::ErrorKind::AlreadyExists);
        drop(first);
        let second = PublicationLease::acquire(&tmp.0).unwrap();
        fs::write(&second.path, b"replacement-owner").unwrap();
        drop(second);
        assert_eq!(fs::read(tmp.0.join(".frequency-domain-publication.lease")).unwrap(), b"replacement-owner");
    }
    #[test]
    fn legacy_and_unbound_publications_do_not_invent_owners() {
        let tmp = Temp::new(); assert!(capture(&tmp.0).unwrap().is_none()); fixture(&tmp.0);
        assert!(capture(&tmp.0).unwrap().unwrap().commit.content.producer.is_none());
    }
    #[test]
    fn bad_members_and_interrupted_publication_preserve_commit() {
        let tmp = Temp::new(); fixture(&tmp.0);
        let old = fs::read(tmp.0.join(COMMIT_PATH)).unwrap();
        for path in ["../escape", "eigen//dispersion.csv", "eigen/./dispersion.csv", "C:/outside", "eigen\\outside", COMMIT_PATH, IMMUTABLE_COMMIT_PATH, GENERATION_DIRECTORY, "frequency_domain/generations/id/payload"] {
            assert!(publish(&tmp.0, None, [path.into()]).is_err());
            assert_eq!(fs::read(tmp.0.join(COMMIT_PATH)).unwrap(), old);
        }
        assert!(publish(&tmp.0, None, ["missing".into()]).is_err());
        assert_eq!(fs::read(tmp.0.join(COMMIT_PATH)).unwrap(), old);
        let captured = capture(&tmp.0).unwrap().unwrap();
        assert!(captured.read_member(&tmp.0, "metadata.json").is_err());
    }
    #[cfg(unix)]
    #[test]
    fn symlink_members_are_rejected() {
        let tmp = Temp::new(); fixture(&tmp.0);
        std::os::unix::fs::symlink(tmp.0.join("eigen/dispersion.csv"), tmp.0.join("eigen/link")).unwrap();
        assert!(publish(&tmp.0, None, ["eigen/link".into()]).is_err());

        let other = Temp::new();
        std::os::unix::fs::symlink(other.0.join("eigen"), other.0.join("frequency_domain/generations")).unwrap();
        assert!(publish_immutable(
            &other.0,
            None,
            vec![("eigen/payload.json".into(), b"payload".to_vec())],
        ).is_err());
    }
}
