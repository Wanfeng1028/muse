//! Electron ASAR archives: a Chromium pickle holding a JSON directory tree, followed by file data.
//!
//! Layout: `u32 4` (size of the first pickle's payload), `u32 header_pickle_size`, then the header
//! pickle: `u32 payload_size`, `u32 json_len`, JSON. File data starts at `8 + header_pickle_size`;
//! each file's `offset` (a decimal string) is relative to that point.

use crate::bytes::Reader;
use serde_json::Value;

/// Headers bigger than this are refused (real ones are a few MiB at most).
pub const MAX_HEADER_BYTES: usize = 16 * 1024 * 1024;
/// Deepest directory nesting we walk.
pub const MAX_DEPTH: usize = 128;

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum AsarError {
    #[error("not an ASAR archive: {0}")]
    NotAsar(&'static str),
    #[error("ASAR header is {0} bytes; the limit is {MAX_HEADER_BYTES}")]
    HeaderTooLarge(usize),
    #[error("ASAR header JSON is invalid: {0}")]
    BadJson(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AsarKind {
    File,
    Directory,
    Link,
}

/// Per-file integrity block (Electron's ASAR integrity feature).
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct AsarIntegrity {
    pub algorithm: String,
    /// Lowercase hex digest of the whole file.
    pub hash: String,
    pub block_size: Option<u64>,
    pub blocks: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct AsarEntry {
    /// Slash-separated path inside the archive.
    pub path: String,
    pub kind: AsarKind,
    pub size: u64,
    /// Offset relative to the data area (files only, not for unpacked files).
    pub offset: Option<u64>,
    /// Stored next to the archive in `<name>.asar.unpacked/` rather than inside it.
    pub unpacked: bool,
    pub executable: bool,
    pub link: Option<String>,
    pub integrity: Option<AsarIntegrity>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Serialize)]
pub struct AsarArchive {
    pub json_bytes: usize,
    /// Absolute offset in the archive where file data starts.
    pub data_offset: u64,
    pub entries: Vec<AsarEntry>,
    pub truncated: bool,
    /// Entries skipped because their names could escape the tree (`..`, `/`, empty).
    pub rejected_names: Vec<String>,
}

impl AsarArchive {
    pub fn get(&self, path: &str) -> Option<&AsarEntry> {
        self.entries.iter().find(|e| e.path == path)
    }
}

/// Parse the header and list entries (at most `max_entries`).
pub fn parse(data: &[u8], max_entries: usize) -> Result<AsarArchive, AsarError> {
    let r = Reader::new(data);
    if r.u32_le(0) != Some(4) {
        return Err(AsarError::NotAsar("first pickle size is not 4"));
    }
    let header_pickle = r.u32_le(4).ok_or(AsarError::NotAsar("truncated"))? as usize;
    let json_len = r.u32_le(12).ok_or(AsarError::NotAsar("truncated"))? as usize;
    if json_len > MAX_HEADER_BYTES {
        return Err(AsarError::HeaderTooLarge(json_len));
    }
    if header_pickle < json_len.saturating_add(8) {
        return Err(AsarError::NotAsar("header sizes disagree"));
    }
    let json = r.slice(16, json_len).ok_or(AsarError::NotAsar("header runs past the end"))?;
    if json.first() != Some(&b'{') {
        return Err(AsarError::NotAsar("header is not a JSON object"));
    }
    let v: Value = serde_json::from_slice(json).map_err(|e| AsarError::BadJson(e.to_string()))?;
    let mut out = AsarArchive { json_bytes: json_len, data_offset: 8 + header_pickle as u64, ..Default::default() };
    let files = v.get("files").ok_or_else(|| AsarError::BadJson("no \"files\" object".into()))?;
    walk(files, "", 0, max_entries, &mut out);
    Ok(out)
}

fn walk(files: &Value, prefix: &str, depth: usize, max: usize, out: &mut AsarArchive) {
    let Some(map) = files.as_object() else { return };
    if depth > MAX_DEPTH {
        out.truncated = true;
        return;
    }
    for (name, node) in map {
        if out.entries.len() >= max {
            out.truncated = true;
            return;
        }
        if name.is_empty() || name == "." || name == ".." || name.contains('/') || name.contains('\\') || name.contains('\0') {
            out.rejected_names.push(format!("{prefix}{name}"));
            continue;
        }
        let path = format!("{prefix}{name}");
        if let Some(children) = node.get("files") {
            out.entries.push(AsarEntry {
                path: path.clone(),
                kind: AsarKind::Directory,
                size: 0,
                offset: None,
                unpacked: false,
                executable: false,
                link: None,
                integrity: None,
            });
            walk(children, &format!("{path}/"), depth + 1, max, out);
        } else if let Some(link) = node.get("link").and_then(Value::as_str) {
            out.entries.push(AsarEntry {
                path,
                kind: AsarKind::Link,
                size: 0,
                offset: None,
                unpacked: false,
                executable: false,
                link: Some(link.to_string()),
                integrity: None,
            });
        } else {
            let size = node.get("size").and_then(Value::as_u64).unwrap_or(0);
            let unpacked = node.get("unpacked").and_then(Value::as_bool).unwrap_or(false);
            let offset = node.get("offset").and_then(|o| o.as_str().and_then(|s| s.parse::<u64>().ok()).or_else(|| o.as_u64()));
            let integrity = node.get("integrity").map(|i| AsarIntegrity {
                algorithm: i.get("algorithm").and_then(Value::as_str).unwrap_or_default().to_string(),
                hash: i.get("hash").and_then(Value::as_str).unwrap_or_default().to_ascii_lowercase(),
                block_size: i.get("blockSize").and_then(Value::as_u64),
                blocks: i.get("blocks").and_then(Value::as_array).map_or(0, Vec::len),
            });
            out.entries.push(AsarEntry {
                path,
                kind: AsarKind::File,
                size,
                offset: if unpacked { None } else { offset },
                unpacked,
                executable: node.get("executable").and_then(Value::as_bool).unwrap_or(false),
                link: None,
                integrity,
            });
        }
    }
}

/// The bytes of a packed file, or `None` when it is unpacked, out of range or not a file.
pub fn file_bytes<'a>(data: &'a [u8], archive: &AsarArchive, entry: &AsarEntry) -> Option<&'a [u8]> {
    if entry.kind != AsarKind::File || entry.unpacked {
        return None;
    }
    let start = archive.data_offset.checked_add(entry.offset?)?;
    let start = usize::try_from(start).ok()?;
    let len = usize::try_from(entry.size).ok()?;
    Reader::new(data).slice(start, len)
}

/// True when the bytes start like an ASAR (pickle size 4, JSON object at 16).
pub fn looks_like_asar(data: &[u8]) -> bool {
    let r = Reader::new(data);
    r.u32_le(0) == Some(4) && data.get(16) == Some(&b'{')
}

fn insert_node(map: &mut serde_json::Map<String, Value>, parts: &[&str], leaf: Value) {
    match parts {
        [] => {}
        [last] => {
            map.insert((*last).to_string(), leaf);
        }
        [dir, rest @ ..] => {
            let entry = map.entry((*dir).to_string()).or_insert_with(|| serde_json::json!({"files": {}}));
            if let Some(next) = entry.get_mut("files").and_then(Value::as_object_mut) {
                insert_node(next, rest, leaf);
            }
        }
    }
}

/// Build an ASAR from (path, bytes) pairs. Used by tests and fixture builders.
pub fn build(files: &[(&str, &[u8])]) -> Vec<u8> {
    let mut root = serde_json::Map::new();
    let mut data = Vec::new();
    for (path, body) in files {
        let parts: Vec<&str> = path.split('/').filter(|p| !p.is_empty()).collect();
        insert_node(&mut root, &parts, serde_json::json!({"size": body.len(), "offset": data.len().to_string()}));
        data.extend_from_slice(body);
    }
    let json = serde_json::to_vec(&serde_json::json!({"files": root})).unwrap_or_default();
    let pad = (4 - json.len() % 4) % 4;
    let payload = json.len() + 4 + pad;
    let mut out = Vec::new();
    out.extend_from_slice(&4u32.to_le_bytes());
    out.extend_from_slice(&((payload + 4) as u32).to_le_bytes());
    out.extend_from_slice(&(payload as u32).to_le_bytes());
    out.extend_from_slice(&(json.len() as u32).to_le_bytes());
    out.extend_from_slice(&json);
    out.extend(std::iter::repeat_n(0u8, pad));
    out.extend_from_slice(&data);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip() {
        let a = build(&[("package.json", b"{\"main\":\"main.js\"}"), ("src/main.js", b"require('electron')")]);
        assert!(looks_like_asar(&a));
        let p = parse(&a, 100).unwrap();
        let main = p.get("src/main.js").unwrap();
        assert_eq!(file_bytes(&a, &p, main).unwrap(), b"require('electron')");
        assert_eq!(p.get("src").unwrap().kind, AsarKind::Directory);
    }

    #[test]
    fn rejects_escaping_names_and_bounds() {
        let json = br#"{"files":{"..":{"size":1,"offset":"0"},"a/b":{"size":1,"offset":"0"},"ok":{"size":99,"offset":"0"}}}"#;
        let mut a = 4u32.to_le_bytes().to_vec();
        a.extend_from_slice(&((json.len() + 8) as u32).to_le_bytes());
        a.extend_from_slice(&((json.len() + 4) as u32).to_le_bytes());
        a.extend_from_slice(&(json.len() as u32).to_le_bytes());
        a.extend_from_slice(json);
        let p = parse(&a, 10).unwrap();
        assert_eq!(p.rejected_names.len(), 2);
        let ok = p.get("ok").unwrap();
        assert!(file_bytes(&a, &p, ok).is_none(), "size runs past the end");
    }

    #[test]
    fn hostile_inputs_do_not_panic() {
        let a = build(&[("x/y/z.js", b"1"), ("q", b"22")]);
        for cut in 0..a.len() {
            if let Ok(p) = parse(&a[..cut], 10) {
                for e in &p.entries {
                    let _ = file_bytes(&a[..cut], &p, e);
                }
            }
        }
        let mut deep = String::from("{\"files\":");
        for _ in 0..300 {
            deep.push_str("{\"d\":{\"files\":");
        }
        let mut a = 4u32.to_le_bytes().to_vec();
        a.extend_from_slice(&((deep.len() + 8) as u32).to_le_bytes());
        a.extend_from_slice(&((deep.len() + 4) as u32).to_le_bytes());
        a.extend_from_slice(&(deep.len() as u32).to_le_bytes());
        a.extend_from_slice(deep.as_bytes());
        assert!(parse(&a, 10).is_err());
    }
}
