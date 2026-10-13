//! Final-byte membership for a committed frequency-domain publication.
//! This proves content membership, never physics or runtime authentication.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};

pub const COMMIT_PATH: &str = "frequency_domain/generation.v1.json";
const SCHEMA: &str = "frequency_domain_artifact_generation.v1";
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

#[derive(Debug, Clone)]
pub struct GenerationCapture {
    pub commit: GenerationCommit,
    commit_digest: String,
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
    let mut members = BTreeMap::new();
    for relative in member_paths {
        if relative == COMMIT_PATH { return Err(invalid("commit cannot be its own member")); }
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

pub fn capture(root: &Path) -> io::Result<Option<GenerationCapture>> {
    match fs::symlink_metadata(root.join(COMMIT_PATH)) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
        Ok(_) => {}
    }
    let path = checked_path(root, COMMIT_PATH)?;
    if fs::metadata(&path)?.len() > MAX_COMMIT_BYTES {
        return Err(invalid("generation commit exceeds control-plane bound"));
    }
    let mut bytes = Vec::new();
    fs::File::open(path)?.take(MAX_COMMIT_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_COMMIT_BYTES { return Err(invalid("oversize generation commit")); }
    let commit: GenerationCommit = serde_json::from_slice(&bytes)?;
    if serde_json::to_vec_pretty(&commit)? != bytes {
        return Err(invalid("generation commit is not canonical or has duplicate fields"));
    }
    if commit.content.schema_version != SCHEMA
        || commit.content.members.is_empty()
        || generation_id(&commit.content)? != commit.generation_id
        || !valid_digest(&commit.generation_id)
        || commit.content.members.iter().any(|(p, m)| p == COMMIT_PATH || !valid_digest(&m.sha256))
        || commit.content.producer.as_ref().is_some_and(|o|
            [&o.run_id, &o.stage_id, &o.stage_kind].iter().any(|v| v.trim().is_empty()))
    { return Err(invalid("invalid generation commit")); }
    Ok(Some(GenerationCapture { commit, commit_digest: digest(&bytes) }))
}

impl GenerationCapture {
    pub fn ensure_current(&self, root: &Path) -> io::Result<()> {
        let current = capture(root)?.ok_or_else(|| invalid("generation commit disappeared"))?;
        if current.commit_digest != self.commit_digest || current.commit != self.commit {
            return Err(invalid("frequency-domain generation changed"));
        }
        Ok(())
    }

    /// Streaming membership check for metadata endpoints. This does not pin a
    /// later data-plane request; that request must verify its own served bytes.
    pub fn verify_member(&self, root: &Path, relative: &str) -> io::Result<GenerationMember> {
        let expected = self.commit.content.members.get(relative)
            .ok_or_else(|| invalid("artifact is not a member of the captured generation"))?;
        let path = checked_path(root, relative)?;
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
        let path = checked_path(root, relative)?;
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
    fn exact_members_bind_changed_same_length_csv_and_commit_replacement() {
        let tmp = Temp::new(); fixture(&tmp.0);
        let old = capture(&tmp.0).unwrap().unwrap();
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
        for path in ["../escape", "eigen//dispersion.csv", "eigen/./dispersion.csv", "C:/outside", "eigen\\outside", COMMIT_PATH] {
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
    }
}
