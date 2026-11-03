//! Unity serialized files: `*.assets`, `level<n>`, `globalgamemanagers`, `sharedassets<n>.assets`
//! and the files inside asset bundles.
//!
//! A big-endian header (format version, metadata size, where the object data starts; 64-bit
//! fields from version 22) is followed by the metadata, in the file's own byte order: the Unity
//! version, the build platform, whether type trees are kept, the types (a class id each, with an
//! optional type tree), the objects (path id, where its bytes are, its type), script references
//! and the other files it points to. Object bytes are only read to find a name: most asset classes
//! start with `m_Name`, and GameObjects and MonoBehaviours keep it a little further in.
//!
//! Format versions 14 and up (Unity 5 onward) are read; older files are refused.

use crate::common::FormatError;
use serde::Serialize;

/// The oldest format version read (Unity 5.0).
pub const MIN_VERSION: u32 = 14;
/// Format versions above this aren't taken for a serialized file at all.
const MAX_VERSION: u32 = 30;
/// Bytes enough for any header.
pub const HEADER_READ: usize = 48;
/// Longest string accepted.
const MAX_STRING: usize = 4096;

/// What the header says.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct Header {
    pub version: u32,
    pub big_endian: bool,
    /// Where the metadata starts and how long it is.
    pub metadata_offset: u64,
    pub metadata_size: u64,
    /// Where object data starts (object offsets count from here).
    pub data_offset: u64,
    pub file_size: u64,
}

/// One object.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Object {
    pub path_id: i64,
    pub class_id: i32,
    /// Where its bytes are in the file.
    pub offset: u64,
    pub size: u32,
}

/// The metadata.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Metadata {
    pub unity_version: String,
    pub platform: i32,
    pub type_trees: bool,
    pub objects: Vec<Object>,
    /// The other files its objects point to.
    pub externals: Vec<String>,
}

/// A bounds-checked cursor in either byte order (shared with [`crate::unity_texture`]).
pub(crate) struct Cur<'a> {
    pub(crate) data: &'a [u8],
    pub(crate) pos: usize,
    pub(crate) big: bool,
}

impl<'a> Cur<'a> {
    pub(crate) fn take(&mut self, n: usize, what: &str) -> Result<&'a [u8], FormatError> {
        let end = self.pos.checked_add(n).filter(|e| *e <= self.data.len()).ok_or_else(|| FormatError::Truncated(what.to_string()))?;
        let s = &self.data[self.pos..end];
        self.pos = end;
        Ok(s)
    }
    fn arr<const N: usize>(&mut self, what: &str) -> Result<[u8; N], FormatError> {
        let mut a = [0; N];
        a.copy_from_slice(self.take(N, what)?);
        if !self.big {
            a.reverse();
        }
        Ok(a)
    }
    pub(crate) fn u8(&mut self, what: &str) -> Result<u8, FormatError> {
        Ok(self.take(1, what)?[0])
    }
    fn u16(&mut self, what: &str) -> Result<u16, FormatError> {
        Ok(u16::from_be_bytes(self.arr(what)?))
    }
    pub(crate) fn u32(&mut self, what: &str) -> Result<u32, FormatError> {
        Ok(u32::from_be_bytes(self.arr(what)?))
    }
    pub(crate) fn i32(&mut self, what: &str) -> Result<i32, FormatError> {
        Ok(self.u32(what)? as i32)
    }
    pub(crate) fn u64(&mut self, what: &str) -> Result<u64, FormatError> {
        Ok(u64::from_be_bytes(self.arr(what)?))
    }
    pub(crate) fn align4(&mut self) -> Result<(), FormatError> {
        let pad = (4 - self.pos % 4) % 4;
        self.take(pad, "alignment").map(|_| ())
    }
    /// A count that must be non-negative and fit what's left (`min_each` bytes each).
    pub(crate) fn count(&mut self, what: &str, min_each: usize) -> Result<usize, FormatError> {
        let n = usize::try_from(self.i32(what)?).map_err(|_| FormatError::Malformed(format!("negative {what}")))?;
        if n.saturating_mul(min_each.max(1)) > self.data.len() - self.pos {
            return Err(FormatError::Malformed(format!("{what} {n} doesn't fit")));
        }
        Ok(n)
    }
    fn cstr(&mut self, what: &str) -> Result<String, FormatError> {
        let rest = &self.data[self.pos..];
        let n = rest.iter().take(MAX_STRING + 1).position(|b| *b == 0).ok_or_else(|| FormatError::Malformed(format!("{what} has no end")))?;
        let s = String::from_utf8_lossy(&rest[..n]).into_owned();
        self.pos += n + 1;
        Ok(s)
    }
}

/// Read the header (the first [`HEADER_READ`] bytes) of a file `file_len` bytes long. An error
/// when it isn't a serialized file this module reads.
pub fn header(data: &[u8], file_len: u64) -> Result<Header, FormatError> {
    let mut c = Cur { data, pos: 0, big: true };
    let mut metadata_size = u64::from(c.u32("metadata size")?);
    let mut file_size = u64::from(c.u32("file size")?);
    let version = c.u32("version")?;
    let mut data_offset = u64::from(c.u32("data offset")?);
    let endian = c.u8("byte order")?;
    c.take(3, "reserved")?;
    if !(1..=MAX_VERSION).contains(&version) || endian > 1 {
        return Err(FormatError::Malformed("not a Unity serialized file".into()));
    }
    if version < MIN_VERSION {
        return Err(FormatError::Unsupported(format!("serialized file version {version} (before Unity 5)")));
    }
    if version >= 22 {
        metadata_size = u64::from(c.u32("metadata size")?);
        file_size = c.u64("file size")?;
        data_offset = c.u64("data offset")?;
        c.u64("reserved")?;
    }
    let metadata_offset = c.pos as u64;
    if file_size != file_len || metadata_offset + metadata_size > data_offset || data_offset > file_size {
        return Err(FormatError::Malformed("not a Unity serialized file (its sizes don't match)".into()));
    }
    Ok(Header { version, big_endian: endian == 1, metadata_offset, metadata_size, data_offset, file_size })
}

/// Read the metadata (`data` is the file from its start through the metadata).
pub fn metadata(data: &[u8], h: &Header) -> Result<Metadata, FormatError> {
    let v = h.version;
    let mut c = Cur { data, pos: h.metadata_offset as usize, big: h.big_endian };
    let unity_version = c.cstr("Unity version")?;
    let platform = c.i32("platform")?;
    let type_trees = c.u8("type trees")? != 0;
    let mut classes = Vec::new();
    for _ in 0..c.count("types", 4)? {
        let class_id = c.i32("class id")?;
        if v >= 16 {
            c.u8("stripped")?;
        }
        if v >= 17 {
            c.u16("script type index")?;
        }
        if (v < 16 && class_id < 0) || (v >= 16 && class_id == 114) {
            c.take(16, "script id")?;
        }
        c.take(16, "type hash")?;
        if type_trees {
            let nodes = c.count("type tree nodes", 24)?;
            let strings = c.count("type tree strings", 1)?;
            c.take(nodes * if v >= 19 { 32 } else { 24 }, "type tree")?;
            c.take(strings, "type tree strings")?;
            if v >= 21 {
                let deps = c.count("type dependencies", 4)?;
                c.take(deps * 4, "type dependencies")?;
            }
        }
        classes.push(class_id);
    }
    let mut objects = Vec::new();
    for _ in 0..c.count("objects", 20)? {
        c.align4()?;
        let path_id = c.u64("path id")? as i64;
        let start = if v >= 22 { c.u64("object offset")? } else { u64::from(c.u32("object offset")?) };
        let size = c.u32("object size")?;
        let type_id = c.i32("object type")?;
        let class_id = if v < 16 {
            i32::from(c.u16("class id")?)
        } else {
            *usize::try_from(type_id).ok().and_then(|t| classes.get(t)).ok_or_else(|| FormatError::Malformed(format!("object type {type_id}")))?
        };
        if v < 17 {
            c.u16("script type index")?;
        }
        if v == 15 || v == 16 {
            c.u8("stripped")?;
        }
        objects.push(Object { path_id, class_id, offset: h.data_offset.saturating_add(start), size });
    }
    for _ in 0..c.count("script references", 12)? {
        c.i32("script file")?;
        c.align4()?;
        c.u64("script id")?;
    }
    let mut externals = Vec::new();
    for _ in 0..c.count("externals", 22)? {
        c.cstr("external")?;
        c.take(16 + 4, "external guid")?;
        externals.push(c.cstr("external path")?);
    }
    Ok(Metadata { unity_version, platform, type_trees, objects, externals })
}

/// Classes whose first field is `m_Name` (they derive from Unity's NamedObject).
const NAMED: &[i32] = &[21, 28, 43, 48, 49, 72, 74, 83, 84, 89, 90, 91, 115, 117, 128, 134, 156, 187, 213, 221, 240, 319, 329, 687_078_895];

/// The object's name, from the first bytes of its data (`data`, in the file's byte order), for
/// the classes that keep one where it can be found without a type tree.
pub fn object_name(class_id: i32, h: &Header, data: &[u8]) -> Option<String> {
    let mut c = Cur { data, pos: 0, big: h.big_endian };
    match class_id {
        // GameObject: its components (a 12-byte reference each from Unity 5.5), its layer, its name.
        1 if h.version >= 17 => {
            let n = c.count("components", 12).ok()?;
            c.take(n * 12 + 4, "components").ok()?;
        }
        // MonoBehaviour: its GameObject and script references and its enabled flag come first.
        114 => {
            c.take(12 + 4 + 12, "behaviour").ok()?;
        }
        c_id if NAMED.contains(&c_id) => {}
        _ => return None,
    }
    let len = c.count("name", 1).ok()?;
    if len == 0 || len > 1024 {
        return None;
    }
    let name = String::from_utf8(c.take(len, "name").ok()?.to_vec()).ok()?;
    (!name.chars().any(char::is_control)).then_some(name)
}

/// Common Unity class ids by name.
const CLASSES: &[(i32, &str)] = &[
    (1, "GameObject"),
    (4, "Transform"),
    (20, "Camera"),
    (21, "Material"),
    (23, "MeshRenderer"),
    (28, "Texture2D"),
    (29, "OcclusionCullingSettings"),
    (30, "GraphicsSettings"),
    (33, "MeshFilter"),
    (43, "Mesh"),
    (47, "QualitySettings"),
    (48, "Shader"),
    (49, "TextAsset"),
    (50, "Rigidbody2D"),
    (54, "Rigidbody"),
    (55, "PhysicsManager"),
    (61, "BoxCollider2D"),
    (64, "MeshCollider"),
    (65, "BoxCollider"),
    (72, "ComputeShader"),
    (74, "AnimationClip"),
    (78, "TagManager"),
    (81, "AudioListener"),
    (82, "AudioSource"),
    (83, "AudioClip"),
    (84, "RenderTexture"),
    (89, "Cubemap"),
    (90, "Avatar"),
    (91, "AnimatorController"),
    (95, "Animator"),
    (104, "RenderSettings"),
    (108, "Light"),
    (111, "Animation"),
    (114, "MonoBehaviour"),
    (115, "MonoScript"),
    (117, "Texture3D"),
    (128, "Font"),
    (129, "PlayerSettings"),
    (134, "PhysicMaterial"),
    (135, "SphereCollider"),
    (136, "CapsuleCollider"),
    (137, "SkinnedMeshRenderer"),
    (141, "BuildSettings"),
    (142, "AssetBundle"),
    (147, "ResourceManager"),
    (150, "PreloadData"),
    (156, "TerrainData"),
    (157, "LightmapSettings"),
    (187, "Texture2DArray"),
    (196, "NavMeshSettings"),
    (198, "ParticleSystem"),
    (199, "ParticleSystemRenderer"),
    (212, "SpriteRenderer"),
    (213, "Sprite"),
    (221, "AnimatorOverrideController"),
    (222, "CanvasRenderer"),
    (223, "Canvas"),
    (224, "RectTransform"),
    (225, "CanvasGroup"),
    (238, "NavMeshData"),
    (240, "AudioMixer"),
    (258, "LightProbes"),
    (319, "AvatarMask"),
    (329, "VideoClip"),
    (1001, "PrefabInstance"),
    (687_078_895, "SpriteAtlas"),
];

/// The major and minor numbers of a Unity version string (`2022.3.62f2` → (2022, 3)).
pub fn version_numbers(unity_version: &str) -> Option<(u32, u32)> {
    let mut parts = unity_version.split(|c: char| !c.is_ascii_digit()).filter(|p| !p.is_empty());
    Some((parts.next()?.parse().ok()?, parts.next()?.parse().ok()?))
}

/// A class id's name, or `class <id>` for one not in the table.
pub fn class_name(id: i32) -> String {
    CLASSES.iter().find(|(c, _)| *c == id).map_or_else(|| format!("class {id}"), |(_, n)| (*n).to_string())
}

/// Build platforms by id.
const PLATFORMS: &[(i32, &str)] = &[
    (2, "macOS"),
    (5, "Windows (32-bit)"),
    (9, "iOS"),
    (13, "Android"),
    (19, "Windows (64-bit)"),
    (20, "WebGL"),
    (24, "Linux (64-bit)"),
    (31, "PlayStation 4"),
    (33, "Xbox One"),
    (38, "Nintendo Switch"),
];

/// A build platform's name, or `platform <id>`.
pub fn platform_name(id: i32) -> String {
    PLATFORMS.iter().find(|(p, _)| *p == id).map_or_else(|| format!("platform {id}"), |(_, n)| (*n).to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_a_version_22_file_and_names_its_objects() {
        let file = craft_anything_testkit::games::unity_assets();
        let h = header(&file[..HEADER_READ], file.len() as u64).unwrap();
        assert_eq!((h.version, h.big_endian, h.metadata_offset), (22, false, 48));
        let m = metadata(&file[..(h.metadata_offset + h.metadata_size) as usize], &h).unwrap();
        assert_eq!((m.unity_version.as_str(), platform_name(m.platform).as_str(), m.type_trees), ("2022.3.62f1", "Windows (64-bit)", false));
        assert_eq!(m.externals, ["library/unity default resources"]);
        let rows: Vec<(i64, String, Option<String>)> = m
            .objects
            .iter()
            .map(|o| (o.path_id, class_name(o.class_id), object_name(o.class_id, &h, &file[o.offset as usize..o.offset as usize + o.size as usize])))
            .collect();
        assert_eq!(
            rows,
            [
                (1, "GameObject".into(), Some("Player".into())),
                (2, "Texture2D".into(), Some("Grass".into())),
                (3, "MonoBehaviour".into(), Some("PlayerController".into())),
                (4, "Transform".into(), None),
            ]
        );
    }

    #[test]
    fn refuses_what_it_cannot_read() {
        let file = craft_anything_testkit::games::unity_assets();
        assert!(header(&file[..HEADER_READ], file.len() as u64 + 1).is_err(), "sizes must match the file");
        assert!(header(&[0; HEADER_READ], 100).is_err());
        let mut old = file.clone();
        old[8..12].copy_from_slice(&9u32.to_be_bytes());
        assert!(matches!(header(&old[..HEADER_READ], old.len() as u64), Err(FormatError::Unsupported(_))));
        // Cut-off metadata never panics.
        let h = header(&file[..HEADER_READ], file.len() as u64).unwrap();
        for cut in 48..(h.metadata_offset + h.metadata_size) as usize {
            let _ = metadata(&file[..cut], &h);
        }
        assert_eq!(object_name(1, &h, &[0xff; 8]), None, "a broken GameObject has no name");
        assert_eq!(class_name(-5), "class -5");
    }
}
