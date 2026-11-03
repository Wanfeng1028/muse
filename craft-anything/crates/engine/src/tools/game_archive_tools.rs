//! Game archives: what's inside a game's packed files, and taking one out. Only the parts of the
//! file that describe its contents are read (an Unreal pak's footer and index), and a file taken
//! out is streamed, so a pak of many gigabytes is fine.

use super::native_common::{params_json, spec};
use super::static_input::{builder, format_err};
use super::web_common::{Image, encode_png};
use crate::tool::{CancelToken, Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Confidence, Coverage, ErrorCode, Limitation, Location, Subject, ToolError};
use craft_anything_formats::godot_pck;
use craft_anything_formats::unity_bundle;
use craft_anything_formats::unity_serialized;
use craft_anything_formats::unity_texture;
use craft_anything_formats::unreal_iostore;
use craft_anything_formats::unreal_pak::{self, Entry, Footer};
use craft_anything_formats::{pixels, unreal_texture};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

/// The largest index (or directory index, or compressed block) read into memory.
const MAX_INDEX: u64 = 512 << 20;
/// The largest compressed block taken (Unreal's default block is 64 KiB).
const MAX_BLOCK: u64 = 16 << 20;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "game_archives_list",
            "List a game's archives",
            "Find the packed files in a game's folder (absolute path): Unreal paks (.pak, checked by their footer) and IoStore containers (.utoc), Unity serialized files (.assets, level<n>, globalgamemanagers) and bundles (.bundle, data.unity3d), and Godot packs (.pck, or carried at the end of a program, checked by their mark, with how many files each declares), each with its size and the tool that lists it. Looks at most 8 folders deep and at 20000 entries.",
            "Find the files a game keeps its pictures, sounds and models in.",
            Toolset::Formats,
            Effects::EVIDENCE,
            Requires::Nothing,
            schema_of::<GameFolderParams>,
            game_archives_list,
        ),
        spec(
            "game_pak_list",
            "List an Unreal pak",
            "List what's inside an Unreal Engine .pak archive (absolute path): its version (1-11), mount point, compression methods, and every file with its size, stored size, compression and whether it's encrypted, paged and optionally filtered by a part of the path. Only the footer and index are read, so very large paks are fine. An encrypted index is reported, never guessed: listing it needs the game's own AES key. Says when the game also keeps IoStore containers (.utoc/.ucas) beside it.",
            "See which files are packed inside an Unreal game's .pak file.",
            Toolset::Formats,
            Effects::EVIDENCE,
            Requires::Nothing,
            schema_of::<ListParams>,
            game_pak_list,
        ),
        spec(
            "game_iostore_list",
            "List an Unreal IoStore container",
            "List what's inside an Unreal Engine IoStore container (absolute path of its .utoc table of contents, or of the .ucas beside it): its version, flags (compressed, encrypted, signed, indexed), compression methods, chunk and partition counts, and every named file with its size, stored size and compression, paged and optionally filtered by a part of the path. Unreal 5 games keep most of their assets this way. An encrypted container's names need the game's AES key, so they're counted, never guessed.",
            "See which files are packed inside an Unreal game's .utoc/.ucas files.",
            Toolset::Formats,
            Effects::EVIDENCE,
            Requires::Nothing,
            schema_of::<ListParams>,
            game_iostore_list,
        ),
        spec(
            "game_unity_list",
            "List a Unity assets file",
            "List the objects in a Unity serialized file (absolute path: a .assets file, level<n>, globalgamemanagers, sharedassets<n>.assets in <Game>_Data) or in a bundle (.bundle, data.unity3d: every serialized file inside it, each object naming its `file`, or only `file`'s): the format version, Unity version, build platform, how many objects of each class (GameObject, Texture2D, AudioClip, MonoBehaviour…), the other files it points to, and the objects with their path id, class, size and name (named assets, GameObjects and MonoBehaviours), paged and optionally filtered by class or name. Unity 5 and later.",
            "See which textures, sounds, models and objects a Unity game's .assets or .bundle file holds.",
            Toolset::Formats,
            Effects::EVIDENCE,
            Requires::Nothing,
            schema_of::<UnityListParams>,
            game_unity_list,
        ),
        spec(
            "game_unity_bundle_list",
            "List a Unity bundle",
            "List the files inside a Unity asset bundle in the UnityFS format (absolute path: a .bundle, data.unity3d or Addressables file): its format, Unity version, block compression (LZMA, LZ4), and each file with its size, and for each serialized file inside, its Unity version, object count and objects by class. Only the blocks that hold those files' headers are decompressed. Paged and optionally filtered by a part of the path.",
            "See what a Unity game's .bundle file holds.",
            Toolset::Formats,
            Effects::EVIDENCE,
            Requires::Nothing,
            schema_of::<ListParams>,
            game_unity_bundle_list,
        ),
        spec(
            "game_unity_asset_export",
            "Take an asset out of a Unity game",
            "Save one object of a Unity serialized file (absolute path of a .assets or level file, or of a bundle: then `file` picks the serialized file inside, the first by default) as a file anyone can open: a texture (Texture2D, by its path_id from game_unity_list) becomes a PNG at `output` (an absolute path that doesn't exist yet). Pixels are read inside the object or from the .resS file it streams from. Formats: Alpha8, R8, RGB24, RGBA32, ARGB32, BGRA32, RGB565, RGBA4444, ARGB4444, DXT1, DXT5, BC4, BC5, BC6H (tone-mapped to 8 bits; brighter than white clips) and BC7; others (crunched, ASTC, ETC…) are refused with their name. Unity 2017.3 and later.",
            "Save a picture from a Unity game as a PNG.",
            Toolset::Formats,
            Effects::EVIDENCE.union(Effects::WRITES_FILESYSTEM),
            Requires::Nothing,
            schema_of::<ExportParams>,
            game_unity_asset_export,
        ),
        spec(
            "game_unreal_texture_export",
            "Take a texture out of an Unreal game",
            "Save a texture of an Unreal Engine 4.26-4.27 game as a PNG, only when the person confirms they may unpack the game (permission: true; they made it or its rights holder allows it). path is the game's .pak (then `file` is the texture's .uasset path inside it, as game_pak_list shows it) or a .uasset already taken out, with its .uexp (and .ubulk) beside it. The largest mip the game ships is saved at `output` (an absolute path that doesn't exist yet). Formats: B8G8R8A8, R8G8B8A8, G8, A8, DXT1, DXT5, BC4, BC5, BC6H (tone-mapped to 8 bits) and BC7; others (ASTC…) are refused by name, as are Oodle-compressed and encrypted paks, Unreal 5 packages and packages written without property names.",
            "Save a picture from an Unreal game you may unpack as a PNG.",
            Toolset::Formats,
            Effects::EVIDENCE.union(Effects::WRITES_FILESYSTEM),
            Requires::Nothing,
            schema_of::<UnrealTextureParams>,
            game_unreal_texture_export,
        ),
        spec(
            "game_pak_extract",
            "Take files out of an Unreal pak",
            "Copy files out of an Unreal Engine .pak archive (absolute path). `file` is one file's path as game_pak_list shows it (any case) and `output` an absolute path that doesn't exist yet (its folders are made); the result has the size and SHA-256. A `file` ending in `/` (e.g. `Game/Content/UI/`) takes out every file under that folder into the folder `output`, keeping their layout, up to `limit` files per call: files already there are skipped, so calling again carries on. Stored and zlib-compressed files are supported and streamed. Encrypted files need the game's AES key and Oodle-compressed ones need Oodle (a commercial library the game ships), so both are refused with the reason.",
            "Take a file, or a whole folder, out of an Unreal game's .pak file.",
            Toolset::Formats,
            Effects::EVIDENCE.union(Effects::WRITES_FILESYSTEM),
            Requires::Nothing,
            schema_of::<ExtractParams>,
            game_pak_extract,
        ),
    ]
}

fn d_limit() -> usize {
    500
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ListParams {
    /// Absolute path of the archive (.pak, an IoStore container's .utoc or .ucas, a Unity .assets
    /// or level file, or a Unity bundle).
    pub path: String,
    /// Only files whose path contains this (any case).
    #[serde(default)]
    pub filter: Option<String>,
    /// First file of the page.
    #[serde(default)]
    pub offset: usize,
    /// Files per page (1–20000, default 500).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct UnityListParams {
    /// Absolute path of the .assets or level file, or of a bundle.
    pub path: String,
    /// For a bundle: only this serialized file inside it (as game_unity_bundle_list shows); every one by default.
    #[serde(default)]
    pub file: Option<String>,
    /// Only objects whose class or name contains this (any case).
    #[serde(default)]
    pub filter: Option<String>,
    /// First object of the page.
    #[serde(default)]
    pub offset: usize,
    /// Objects per page (1–20000, default 500).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExtractParams {
    /// Absolute path of the .pak file.
    pub path: String,
    /// The file to take out, as game_pak_list shows it (e.g. `Game/Content/Maps/Level.umap`; any case),
    /// or a folder ending in `/` (e.g. `Game/Content/UI/`) to take out every file under it.
    pub file: String,
    /// Where to write it: an absolute path that doesn't exist yet (its folders are made). For a
    /// folder, the folder to write into; files keep their layout under it.
    pub output: String,
    /// For a folder: the most files to take out in this call (at most 5000).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

fn read_at(file: &mut File, path: &Path, at: u64, len: u64) -> Result<Vec<u8>, ToolError> {
    if len > MAX_INDEX {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("the pak's index is {len} bytes; the limit is {MAX_INDEX}")));
    }
    let mut buf = vec![0; len as usize];
    file.seek(SeekFrom::Start(at)).and_then(|_| file.read_exact(&mut buf)).map_err(|e| ToolError::io(path.display(), e))?;
    Ok(buf)
}

/// An opened pak: its footer and the files its index lists.
struct Pak {
    file: File,
    path: PathBuf,
    len: u64,
    name: String,
    footer: Footer,
    /// None when the index is encrypted.
    mount_point: Option<String>,
    file_count: u64,
    files: Vec<Entry>,
    lims: Vec<Limitation>,
}

fn open_pak(ctx: &Ctx<'_>, raw: &str) -> Result<Pak, ToolError> {
    let path = PathBuf::from(raw);
    if !path.is_absolute() {
        return Err(ToolError::invalid(format!("{raw:?} is not an absolute path")).with_remediation("Pass the full path of the .pak file."));
    }
    let mut file = File::open(&path).map_err(|e| ToolError::io(path.display(), e))?;
    let len = file.metadata().map_err(|e| ToolError::io(path.display(), e))?.len();
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let tail_len = len.min(unreal_pak::FOOTER_READ as u64);
    let tail = read_at(&mut file, &path, len - tail_len, tail_len)?;
    let footer = unreal_pak::footer(&tail, len).map_err(|_| {
        ToolError::unsupported(format!(
            "{name} has no standard Unreal pak footer at its end: it's another kind of .pak, or the game changed the pak format (some do, to stop modding)."
        ))
        .with_remediation(
            "Unreal games keep their paks in <Game>/Content/Paks/. Chromium's .pak files (cef.pak, chrome_100_percent.pak) are a different format.",
        )
    })?;
    ctx.report(None, format!("Reading the index of {name}"));
    let index_bytes = read_at(&mut file, &path, footer.index_offset, footer.index_size)?;
    let mut lims = Vec::new();
    let (mount_point, file_count, files) = match unreal_pak::index(&index_bytes, &footer) {
        Ok(index) => {
            let files = match index.directory_index {
                Some((at, size)) => {
                    let dir = read_at(&mut file, &path, at, size)?;
                    unreal_pak::directory(&dir, &footer, &index, usize::MAX).map_err(|e| format_err(e, "an Unreal pak's directory index"))?
                }
                None if footer.version >= 10 => {
                    lims.push(Limitation::new("hashed_names", "This pak keeps its file names only as hashes, so the files are counted but not listed."));
                    Vec::new()
                }
                None => index.entries,
            };
            (Some(index.mount_point), index.file_count, files)
        }
        Err(craft_anything_formats::FormatError::Unsupported(why)) => {
            lims.push(Limitation::new(
                "encrypted_index",
                format!("{why}; listing it needs that key, which only the game has. Keys aren't searched for or guessed."),
            ));
            (None, 0, Vec::new())
        }
        Err(e) => return Err(format_err(e, "an Unreal pak's index")),
    };
    Ok(Pak { file, path, len, name, footer, mount_point, file_count, files, lims })
}

/// A path as people see it: "../../../Game/Content/…" without the climb to the game's root.
fn shown_path(path: &str) -> &str {
    path.trim_start_matches("../")
}

fn shown(e: &Entry) -> &str {
    shown_path(&e.path)
}

/// The items whose path contains the filter (any case).
fn matching<'a, T>(items: &'a [T], path: impl Fn(&T) -> &str, filter: Option<&str>) -> Vec<&'a T> {
    let needle = filter.map(str::to_lowercase).filter(|f| !f.is_empty());
    items.iter().filter(|i| needle.as_deref().is_none_or(|n| path(i).to_lowercase().contains(n))).collect()
}

/// How many items use each compression method.
fn by_compression<'a>(methods: impl Iterator<Item = &'a str>) -> BTreeMap<&'a str, u64> {
    let mut out = BTreeMap::new();
    for m in methods {
        *out.entry(m).or_default() += 1;
    }
    out
}

fn game_pak_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListParams = parse_params(params)?;
    let Pak { path, name, footer, mount_point, file_count, files, mut lims, .. } = open_pak(ctx, &p.path)?;
    let matching = matching(&files, |e| e.path.as_str(), p.filter.as_deref());
    let page: Vec<Value> = matching
        .iter()
        .skip(p.offset)
        .take(p.limit.clamp(1, 20_000))
        .map(|e| json!({"path": shown(e), "size": e.uncompressed_size, "stored_size": e.size, "compression": e.compression, "encrypted": e.encrypted, "offset": e.offset}))
        .collect();
    let by_compression = by_compression(files.iter().map(|e| e.compression.as_str()));
    let encrypted_files = files.iter().filter(|e| e.encrypted).count();
    if encrypted_files > 0 {
        lims.push(Limitation::new("encrypted_files", format!("{encrypted_files} file(s) are encrypted; their contents need the game's AES key.")));
    }
    let stem = path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let iostore = path.with_file_name(format!("{stem}.utoc")).is_file();
    let guid = footer.encryption_key_guid.as_deref().filter(|g| g.bytes().any(|b| b != b'0'));
    let result = json!({
        "version": footer.version,
        "mount_point": mount_point,
        "encrypted_index": footer.encrypted_index,
        "encryption_key_guid": guid,
        "compression_methods": footer.compression_methods,
        "file_count": file_count,
        "listed": files.len(),
        "by_compression": by_compression,
        "encrypted_files": encrypted_files,
        "size": files.iter().map(|e| e.uncompressed_size).sum::<u64>(),
        "stored_size": files.iter().map(|e| e.size).sum::<u64>(),
        "iostore": iostore.then(|| format!("{stem}.utoc / {stem}.ucas")),
        "matching": matching.len(),
        "offset": p.offset,
        "files": page,
    });
    let summary = if footer.encrypted_index {
        format!("{name}: an Unreal pak (version {}) whose index is encrypted; its files can't be listed without the game's key.", footer.version)
    } else {
        let iostore_note = if iostore { " Most of the game's assets are in its IoStore files (.utoc/.ucas) beside it." } else { "" };
        format!("{name}: an Unreal pak (version {}) with {file_count} file(s).{iostore_note}", footer.version)
    };
    let shown_count = page.len() as u64;
    let b = builder(ctx, "game_pak_list", Subject { kind: "archive".into(), sha256: None, name: Some(name) }, params_json(&p))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(Coverage::page(shown_count, matching.len() as u64, p.offset as u64))
        .location(Location::new("path", p.path.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

fn game_iostore_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListParams = parse_params(params)?;
    let mut path = PathBuf::from(&p.path);
    if !path.is_absolute() {
        return Err(ToolError::invalid(format!("{:?} is not an absolute path", p.path)).with_remediation("Pass the full path of the .utoc file."));
    }
    // The table of contents sits beside its data file, with the same name.
    if path.extension().is_some_and(|x| x.eq_ignore_ascii_case("ucas")) {
        path.set_extension("utoc");
    }
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let len = std::fs::metadata(&path).map_err(|e| ToolError::io(path.display(), e))?.len();
    if len > MAX_INDEX {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{name} is {len} bytes; the limit is {MAX_INDEX}")));
    }
    ctx.report(None, format!("Reading {name}"));
    let data = std::fs::read(&path).map_err(|e| ToolError::io(path.display(), e))?;
    if !data.starts_with(unreal_iostore::MAGIC) {
        return Err(ToolError::unsupported(format!("{name} isn't an IoStore table of contents."))
            .with_remediation("Pass the .utoc file (or the .ucas beside it) from <Game>/Content/Paks/."));
    }
    let toc = unreal_iostore::toc(&data).map_err(|e| format_err(e, "an IoStore table of contents"))?;
    let h = &toc.header;
    let mut lims = Vec::new();
    let (mount_point, files, file_count) = if !h.flags.encrypted && (!h.flags.indexed || h.version < 2) {
        (None, Vec::new(), None)
    } else {
        match unreal_iostore::files(&toc, usize::MAX) {
            Ok((mount, files, total)) => (Some(mount), files, Some(total)),
            Err(craft_anything_formats::FormatError::Unsupported(why)) => {
                lims.push(Limitation::new(
                    "encrypted_index",
                    format!("{why}; naming its files needs that key, which only the game has. Keys aren't searched for or guessed."),
                ));
                (None, Vec::new(), Some(0))
            }
            Err(e) => return Err(format_err(e, "an IoStore directory index")),
        }
    };
    if !h.flags.indexed || h.version < 2 {
        lims.push(Limitation::new("not_indexed", "This container has no directory index, so its chunks are counted but not named."));
    }
    let matching = matching(&files, |f| f.path.as_str(), p.filter.as_deref());
    let page: Vec<Value> = matching
        .iter()
        .skip(p.offset)
        .take(p.limit.clamp(1, 20_000))
        .map(|f| json!({"path": shown_path(&f.path), "size": f.size, "stored_size": f.stored_size, "compression": f.compression, "chunk": f.chunk}))
        .collect();
    let guid = Some(h.encryption_key_guid.as_str()).filter(|g| g.bytes().any(|b| b != b'0'));
    let (size, stored_size) = match file_count {
        Some(_) => (Value::from(files.iter().map(|f| f.size).sum::<u64>()), Value::from(files.iter().map(|f| f.stored_size).sum::<u64>())),
        None => (Value::Null, Value::Null),
    };
    let result = json!({
        "version": h.version,
        "mount_point": mount_point,
        "flags": h.flags,
        "encryption_key_guid": guid,
        "compression_methods": toc.methods,
        "chunk_count": h.chunk_count,
        "block_size": h.block_size,
        "partition_count": h.partition_count,
        "file_count": file_count,
        "by_compression": by_compression(files.iter().map(|f| f.compression.as_str())),
        "size": size,
        "stored_size": stored_size,
        "matching": file_count.map(|_| matching.len()),
        "offset": p.offset,
        "files": page,
    });
    let summary = if h.flags.encrypted {
        format!(
            "{name}: an Unreal IoStore container (version {}, {} chunks) whose names are encrypted; its files can't be named without the game's key.",
            h.version, h.chunk_count
        )
    } else if !h.flags.indexed || h.version < 2 {
        format!(
            "{name}: an Unreal IoStore container (version {}, {} chunks) with no directory index; its chunks are counted but not named.",
            h.version, h.chunk_count
        )
    } else {
        format!("{name}: an Unreal IoStore container (version {}) with {} named file(s) in {} chunks.", h.version, file_count.unwrap_or(0), h.chunk_count)
    };
    let shown_count = page.len() as u64;
    let coverage = match file_count {
        Some(_) => Coverage::page(shown_count, matching.len() as u64, p.offset as u64),
        None => Coverage::default(),
    };
    let b = builder(ctx, "game_iostore_list", Subject { kind: "archive".into(), sha256: None, name: Some(name) }, params_json(&p))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(coverage)
        .location(Location::new("path", path.display().to_string()));
    Ok(ToolOutput::evidence(b.build()?))
}

/// Bytes read at an object's start to find its name (enough for a GameObject with many components).
const NAME_READ: u64 = 1024;

fn game_unity_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: UnityListParams = parse_params(params)?;
    let name = Path::new(&p.path).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let first = Serialized::open(&p.path, p.file.as_deref())?;
    // A bundle is read file by file: every serialized file inside it, or only the one asked for.
    let (inner, inside) = match &first {
        Serialized::Bundle { nodes, .. } if p.file.is_none() => {
            let all: Vec<String> = nodes.iter().filter(|n| n.flags & 4 != 0).map(|n| n.path.clone()).collect();
            let inside = all.len();
            (all.into_iter().take(MAX_COUNTED).collect::<Vec<_>>(), inside)
        }
        Serialized::Bundle { node, .. } => (vec![node.path.clone()], 1),
        Serialized::File { .. } => (Vec::new(), 0),
    };
    let mut sources = vec![(inner.first().cloned(), first)];
    for f in inner.iter().skip(1) {
        sources.push((Some(f.clone()), Serialized::open(&p.path, Some(f))?));
    }
    let (mut srcs, mut files) = (Vec::new(), Vec::new());
    for (file, mut src) in sources {
        ctx.cancel.check()?;
        let shown = file.clone().unwrap_or_else(|| name.clone());
        let head = src.read(0, src.len().min(unity_serialized::HEADER_READ as u64))?;
        let h = unity_serialized::header(&head, src.len()).map_err(|e| match e {
            craft_anything_formats::FormatError::Unsupported(why) => ToolError::unsupported(format!("{shown} is a Unity {why}, which isn't read here.")),
            _ => ToolError::unsupported(format!("{shown} isn't a Unity serialized file."))
                .with_remediation("Pass a .assets file, level<n> or globalgamemanagers from the game's <Game>_Data folder, or a bundle."),
        })?;
        ctx.report(None, format!("Reading {shown}"));
        let meta = src.read(0, h.metadata_offset + h.metadata_size)?;
        let m = unity_serialized::metadata(&meta, &h).map_err(|e| format_err(e, "a Unity serialized file"))?;
        srcs.push(src);
        files.push((file, h, m));
    }
    let mut name_of = |i: usize, o: &unity_serialized::Object| -> Option<String> {
        let (_, h, _) = files.get(i)?;
        let bytes = srcs.get_mut(i)?.read(o.offset, u64::from(o.size).min(NAME_READ)).ok()?;
        unity_serialized::object_name(o.class_id, h, &bytes)
    };
    let objects = || files.iter().enumerate().flat_map(|(i, (_, _, m))| m.objects.iter().map(move |o| (i, o)));
    // Names are read for the page shown, or for every object when filtering (a name can match).
    let needle = p.filter.as_deref().map(str::to_lowercase).filter(|f| !f.is_empty());
    let rows: Vec<(usize, &unity_serialized::Object, String, Option<String>)> = match &needle {
        Some(n) => objects()
            .map(|(i, o)| (i, o, unity_serialized::class_name(o.class_id), name_of(i, o)))
            .filter(|(_, _, class, obj)| class.to_lowercase().contains(n) || obj.as_deref().is_some_and(|x| x.to_lowercase().contains(n)))
            .collect(),
        None => objects().map(|(i, o)| (i, o, unity_serialized::class_name(o.class_id), None)).collect(),
    };
    let page: Vec<Value> = rows
        .iter()
        .skip(p.offset)
        .take(p.limit.clamp(1, 20_000))
        .map(|(i, o, class, obj)| {
            let obj = if needle.is_some() { obj.clone() } else { name_of(*i, o) };
            let mut row = json!({"path_id": o.path_id, "class": class, "name": obj, "size": o.size, "offset": o.offset});
            if let Some(file) = files.get(*i).and_then(|(f, ..)| f.as_ref()) {
                row["file"] = json!(file);
            }
            row
        })
        .collect();
    let classes: Vec<String> = objects().map(|(_, o)| unity_serialized::class_name(o.class_id)).collect();
    let mut by_class: Vec<(&str, u64)> = by_compression(classes.iter().map(String::as_str)).into_iter().collect();
    by_class.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(b.0)));
    let object_count = classes.len();
    let Some((_, h, m)) = files.first() else { return Err(damaged("no serialized file was read")) };
    let platform = unity_serialized::platform_name(m.platform);
    let version = known_version(&m.unity_version, Path::new(&p.path));
    let mut result = json!({
        "format_version": h.version,
        "unity_version": version,
        "platform": platform,
        "type_trees": m.type_trees,
        "object_count": object_count,
        "by_class": by_class.iter().take(40).map(|(c, n)| json!({"class": c, "count": n})).collect::<Vec<_>>(),
        "externals": files.iter().flat_map(|(_, _, m)| &m.externals).take(100).collect::<Vec<_>>(),
        "matching": rows.len(),
        "offset": p.offset,
        "objects": page,
    });
    let mut lims = Vec::new();
    let summary = if inner.is_empty() {
        format!("{name}: a Unity {version} file for {platform} with {object_count} object(s).")
    } else {
        result["serialized_files"] = json!(inner);
        if inside > inner.len() {
            lims.push(Limitation::new(
                "files_unread",
                format!("Only the first {} of the bundle's {inside} serialized files were read; pass `file` for the others.", inner.len()),
            ));
        }
        format!("{name}: a Unity {version} bundle for {platform}; {} serialized file(s) with {object_count} object(s).", inner.len())
    };
    let shown_count = page.len() as u64;
    let b = builder(ctx, "game_unity_list", Subject { kind: "archive".into(), sha256: None, name: Some(name) }, params_json(&p))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(Coverage::page(shown_count, rows.len() as u64, p.offset as u64))
        .location(Location::new("path", p.path.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

/// Whether a Unity version was left out when the file was built (it then reads `0.0.0`).
fn stripped(version: &str) -> bool {
    unity_serialized::version_numbers(version).is_none_or(|v| v == (0, 0))
}

/// The Unity version that wrote a file. Bundles built with the version stripped don't say; the
/// game's globalgamemanagers, in the `<Game>_Data` folder above them, does.
fn known_version(version: &str, path: &Path) -> String {
    if !stripped(version) {
        return version.to_string();
    }
    let from_game = path.ancestors().skip(1).take(8).find_map(|dir| {
        let ggm = dir.join("globalgamemanagers");
        let mut file = File::open(&ggm).ok()?;
        let len = file.metadata().ok()?.len();
        let head = read_at(&mut file, &ggm, 0, len.min(unity_serialized::HEADER_READ as u64)).ok()?;
        let h = unity_serialized::header(&head, len).ok()?;
        let meta = read_at(&mut file, &ggm, 0, h.metadata_offset + h.metadata_size).ok()?;
        Some(unity_serialized::metadata(&meta, &h).ok()?.unity_version)
    });
    from_game.filter(|v| !stripped(v)).unwrap_or_else(|| version.to_string())
}

/// Most bytes decompressed from a bundle in one read (metadata, or a texture's pixels).
const MAX_BUNDLE_READ: u64 = 256 << 20;
/// Serialized files inside a bundle whose objects are counted.
const MAX_COUNTED: usize = 16;

/// The bundle block decompressed last (its index and bytes), so many small reads (objects'
/// names) decompress each block once.
type BlockCache = Option<(usize, Vec<u8>)>;

/// A range of a bundle's uncompressed data, decompressing only the blocks it touches.
fn bundle_range(
    file: &mut File,
    path: &Path,
    h: &unity_bundle::Header,
    blocks: &[unity_bundle::Block],
    start: u64,
    len: u64,
    cache: &mut BlockCache,
) -> Result<Vec<u8>, ToolError> {
    if len > MAX_BUNDLE_READ {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{len} bytes would be decompressed; the limit is {MAX_BUNDLE_READ}")));
    }
    let end = start.saturating_add(len);
    let (mut out, mut ustart, mut cstart) = (Vec::new(), 0u64, h.data_offset);
    for (i, b) in blocks.iter().enumerate() {
        let uend = ustart + u64::from(b.uncompressed_size);
        if uend > start && ustart < end {
            if cache.as_ref().is_none_or(|(at, _)| *at != i) {
                let raw = read_at(file, path, cstart, u64::from(b.compressed_size))?;
                let data =
                    unity_bundle::decompress(u32::from(b.flags & 0x3f), &raw, b.uncompressed_size).map_err(|e| format_err(e, "a Unity bundle's data"))?;
                *cache = Some((i, data));
            }
            let data = cache.as_ref().map_or(&[][..], |(_, d)| d.as_slice());
            let from = start.saturating_sub(ustart) as usize;
            let to = (end.min(uend) - ustart) as usize;
            out.extend_from_slice(data.get(from..to).unwrap_or_default());
        }
        if uend >= end {
            break;
        }
        ustart = uend;
        cstart += u64::from(b.compressed_size);
    }
    Ok(out)
}

/// The Unity version, object count and top classes of a serialized file inside a bundle.
fn bundle_objects(
    file: &mut File,
    path: &Path,
    h: &unity_bundle::Header,
    blocks: &[unity_bundle::Block],
    node: &unity_bundle::Node,
) -> Result<Value, ToolError> {
    let mut cache = None;
    let head = bundle_range(file, path, h, blocks, node.offset, (unity_serialized::HEADER_READ as u64).min(node.size), &mut cache)?;
    let sh = unity_serialized::header(&head, node.size).map_err(|e| format_err(e, "a Unity serialized file"))?;
    let meta = bundle_range(file, path, h, blocks, node.offset, sh.metadata_offset + sh.metadata_size, &mut cache)?;
    let m = unity_serialized::metadata(&meta, &sh).map_err(|e| format_err(e, "a Unity serialized file"))?;
    let classes: Vec<String> = m.objects.iter().map(|o| unity_serialized::class_name(o.class_id)).collect();
    let mut by_class: Vec<(&str, u64)> = by_compression(classes.iter().map(String::as_str)).into_iter().collect();
    by_class.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(b.0)));
    Ok(json!({
        "unity_version": m.unity_version,
        "object_count": m.objects.len(),
        "by_class": by_class.iter().take(12).map(|(c, n)| json!({"class": c, "count": n})).collect::<Vec<_>>(),
    }))
}

fn game_unity_bundle_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListParams = parse_params(params)?;
    let path = PathBuf::from(&p.path);
    if !path.is_absolute() {
        return Err(ToolError::invalid(format!("{:?} is not an absolute path", p.path)).with_remediation("Pass the full path of the bundle."));
    }
    let mut file = File::open(&path).map_err(|e| ToolError::io(path.display(), e))?;
    let len = file.metadata().map_err(|e| ToolError::io(path.display(), e))?.len();
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let head = read_at(&mut file, &path, 0, len.min(unity_bundle::HEADER_READ as u64))?;
    let h = unity_bundle::header(&head, len).map_err(|e| match e {
        craft_anything_formats::FormatError::Unsupported(why) => ToolError::unsupported(format!("{name} is a {why} bundle, which isn't read here.")),
        _ => ToolError::unsupported(format!("{name} isn't a UnityFS bundle."))
            .with_remediation("Unity bundles are usually .bundle files under <Game>_Data/StreamingAssets, or data.unity3d."),
    })?;
    ctx.report(None, format!("Reading {name}"));
    let table = read_at(&mut file, &path, h.table_offset, u64::from(h.table_size))?;
    let (blocks, nodes) = unity_bundle::table(&table, &h).map_err(|e| format_err(e, "a Unity bundle's block table"))?;
    let mut lims = Vec::new();
    let mut counted = BTreeMap::new();
    for node in nodes.iter().filter(|n| n.flags & 4 != 0).take(MAX_COUNTED) {
        ctx.cancel.check()?;
        match bundle_objects(&mut file, &path, &h, &blocks, node) {
            Ok(v) => {
                counted.insert(node.path.as_str(), v);
            }
            Err(e) => lims.push(Limitation::new("objects_unread", format!("{}'s objects couldn't be read: {}", node.path, e.message))),
        }
    }
    let serialized_total = nodes.iter().filter(|n| n.flags & 4 != 0).count();
    if serialized_total > MAX_COUNTED {
        lims.push(Limitation::new(
            "files_unread",
            format!(
                "Only the first {MAX_COUNTED} of the bundle's {serialized_total} serialized files were read; pass `file` to game_unity_list for the others."
            ),
        ));
    }
    let matching = matching(&nodes, |n| n.path.as_str(), p.filter.as_deref());
    let page: Vec<Value> = matching
        .iter()
        .skip(p.offset)
        .take(p.limit.clamp(1, 20_000))
        .map(|n| json!({"path": n.path, "size": n.size, "offset": n.offset, "serialized": n.flags & 4 != 0, "objects": counted.get(n.path.as_str())}))
        .collect();
    let block_compression = by_compression(blocks.iter().map(|b| unity_bundle::compression_name(u32::from(b.flags & 0x3f))));
    let result = json!({
        "format_version": h.format_version,
        "unity_version": h.unity_revision,
        "table_compression": unity_bundle::compression_name(h.flags & 0x3f),
        "block_count": blocks.len(),
        "block_compression": block_compression,
        "size": blocks.iter().map(|b| u64::from(b.uncompressed_size)).sum::<u64>(),
        "stored_size": len,
        "file_count": nodes.len(),
        "matching": matching.len(),
        "offset": p.offset,
        "files": page,
    });
    let objects: usize = counted.values().filter_map(|v| v["object_count"].as_u64()).sum::<u64>() as usize;
    let at_least = if serialized_total > MAX_COUNTED { "at least " } else { "" };
    let summary = format!("{name}: a Unity {} bundle with {} file(s) and {at_least}{objects} object(s).", h.unity_revision, nodes.len());
    let shown_count = page.len() as u64;
    let b = builder(ctx, "game_unity_bundle_list", Subject { kind: "archive".into(), sha256: None, name: Some(name) }, params_json(&p))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(Coverage::page(shown_count, matching.len() as u64, p.offset as u64))
        .location(Location::new("path", p.path.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExportParams {
    /// Absolute path of the .assets or level file, or of a bundle.
    pub path: String,
    /// For a bundle: the serialized file inside it (as game_unity_bundle_list shows); the first by default.
    #[serde(default)]
    pub file: Option<String>,
    /// The object's path id (game_unity_list shows them).
    pub path_id: i64,
    /// Where to write it: an absolute path that doesn't exist yet (its folders are made).
    pub output: String,
}

/// The largest picture taken out, in pixels (8192 × 8192).
const MAX_PIXELS: u64 = 8192 * 8192;

/// A serialized file to read objects from: a file of its own, or one inside a bundle.
enum Serialized {
    File {
        file: File,
        path: PathBuf,
        len: u64,
    },
    Bundle {
        file: File,
        path: PathBuf,
        header: Box<unity_bundle::Header>,
        blocks: Vec<unity_bundle::Block>,
        nodes: Vec<unity_bundle::Node>,
        node: unity_bundle::Node,
        cache: BlockCache,
    },
}

impl Serialized {
    fn open(raw: &str, inner: Option<&str>) -> Result<Self, ToolError> {
        let path = PathBuf::from(raw);
        if !path.is_absolute() {
            return Err(ToolError::invalid(format!("{raw:?} is not an absolute path")).with_remediation("Pass the full path of the .assets file or bundle."));
        }
        let mut file = File::open(&path).map_err(|e| ToolError::io(path.display(), e))?;
        let len = file.metadata().map_err(|e| ToolError::io(path.display(), e))?.len();
        let head = read_at(&mut file, &path, 0, len.min(unity_bundle::HEADER_READ as u64))?;
        if !head.starts_with(unity_bundle::MAGIC) {
            return Ok(Serialized::File { file, path, len });
        }
        let header = unity_bundle::header(&head, len).map_err(|e| format_err(e, "a Unity bundle"))?;
        let table = read_at(&mut file, &path, header.table_offset, u64::from(header.table_size))?;
        let (blocks, nodes) = unity_bundle::table(&table, &header).map_err(|e| format_err(e, "a Unity bundle's block table"))?;
        let node = match inner {
            Some(want) => nodes.iter().find(|n| n.path.eq_ignore_ascii_case(want.trim())),
            None => nodes.iter().find(|n| n.flags & 4 != 0),
        }
        .cloned()
        .ok_or_else(|| {
            ToolError::new(ErrorCode::NotFound, "That serialized file isn't in the bundle.").with_remediation("game_unity_bundle_list shows the files inside.")
        })?;
        Ok(Serialized::Bundle { file, path, header: Box::new(header), blocks, nodes, node, cache: None })
    }

    /// The serialized file's size.
    fn len(&self) -> u64 {
        match self {
            Serialized::File { len, .. } => *len,
            Serialized::Bundle { node, .. } => node.size,
        }
    }

    /// Bytes of the serialized file.
    fn read(&mut self, offset: u64, len: u64) -> Result<Vec<u8>, ToolError> {
        if offset.checked_add(len).is_none_or(|end| end > self.len()) {
            return Err(damaged("an object lies outside its file"));
        }
        match self {
            Serialized::File { file, path, .. } => read_at(file, path, offset, len),
            Serialized::Bundle { file, path, header, blocks, node, cache, .. } => bundle_range(file, path, header, blocks, node.offset + offset, len, cache),
        }
    }

    /// Bytes of the file an object streams its data from (a `.resS` beside the file, or a file in
    /// the same bundle). Only the stream path's last part is used, so it can't point elsewhere.
    fn stream(&mut self, stream_path: &str, offset: u64, len: u64) -> Result<Vec<u8>, ToolError> {
        let name = stream_path.rsplit(['/', '\\']).next().unwrap_or(stream_path);
        match self {
            Serialized::File { path, .. } => {
                let other = path.with_file_name(name);
                let mut file = File::open(&other).map_err(|e| ToolError::io(other.display(), e))?;
                read_at(&mut file, &other, offset, len)
            }
            Serialized::Bundle { file, path, header, blocks, nodes, cache, .. } => {
                let node = nodes.iter().find(|n| n.path == name).ok_or_else(|| damaged(format!("{name} isn't in the bundle")))?;
                if offset.checked_add(len).is_none_or(|end| end > node.size) {
                    return Err(damaged(format!("data lies outside {name}")));
                }
                bundle_range(file, path, header, blocks, node.offset + offset, len, cache)
            }
        }
    }
}

fn game_unity_asset_export(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ExportParams = parse_params(params)?;
    let out = new_output(&p.output)?;
    let mut src = Serialized::open(&p.path, p.file.as_deref())?;
    let head = src.read(0, src.len().min(unity_serialized::HEADER_READ as u64))?;
    let h = unity_serialized::header(&head, src.len()).map_err(|e| format_err(e, "a Unity serialized file"))?;
    let meta = src.read(0, h.metadata_offset + h.metadata_size)?;
    let m = unity_serialized::metadata(&meta, &h).map_err(|e| format_err(e, "a Unity serialized file"))?;
    let object = m.objects.iter().find(|o| o.path_id == p.path_id).ok_or_else(|| {
        ToolError::new(ErrorCode::NotFound, format!("There's no object with path id {}.", p.path_id))
            .with_remediation("game_unity_list (or game_unity_bundle_list for a bundle) shows the objects and their path ids.")
    })?;
    if object.class_id != 28 {
        return Err(ToolError::unsupported(format!(
            "{} objects can't be taken out yet; textures (Texture2D) can.",
            unity_serialized::class_name(object.class_id)
        )));
    }
    ctx.report(None, format!("Reading texture {}", p.path_id));
    let version = known_version(&m.unity_version, Path::new(&p.path));
    if stripped(&version) {
        return Err(ToolError::unsupported("This file doesn't say which Unity version wrote it, so its textures' layout isn't known.")
            .with_remediation("Pass a bundle that's inside the game's <Game>_Data folder, beside its globalgamemanagers file."));
    }
    let bytes = src.read(object.offset, u64::from(object.size))?;
    let t = unity_texture::parse(&bytes, &version, h.big_endian).map_err(|e| format_err(e, "a Unity texture"))?;
    let format = unity_texture::format_name(t.format);
    if u64::from(t.width) * u64::from(t.height) > MAX_PIXELS {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{} is {}×{}; the limit is 8192×8192", t.name, t.width, t.height)));
    }
    let need = unity_texture::mip0_size(t.format, t.width, t.height)
        .ok_or_else(|| ToolError::unsupported(format!("{} is a {format} texture, which isn't decoded here.", t.name)))? as u64;
    let pixels = match (&t.inline, &t.stream) {
        (Some((start, len)), _) => bytes.get(*start..*start + *len).map(<[u8]>::to_vec).unwrap_or_default(),
        (None, Some(s)) => src.stream(&s.path, s.offset, need.min(u64::from(s.size)))?,
        (None, None) => Vec::new(),
    };
    let rgba = unity_texture::decode(t.format, t.width, t.height, &pixels).map_err(|e| format_err(e, "a Unity texture's pixels"))?;
    let png = encode_png(&Image { width: t.width, height: t.height, rgba })?;
    crate::project::write_atomic(&out, &png)?;
    let sha256 = craft_anything_evidence::sha256_hex(&png);
    let result = json!({
        "path_id": p.path_id,
        "name": t.name,
        "class": "Texture2D",
        "width": t.width,
        "height": t.height,
        "format": format,
        "streamed_from": t.stream.as_ref().map(|s| s.path.clone()),
        "output": out.display().to_string(),
        "size": png.len(),
        "sha256": sha256,
    });
    let name = Path::new(&p.path).file_name().map(|n| n.to_string_lossy().into_owned());
    let b = builder(ctx, "game_unity_asset_export", Subject { kind: "archive".into(), sha256: None, name }, params_json(&p))
        .result(result)
        .summary(format!("Saved texture \"{}\" ({}×{}, {format}) as {}.", t.name, t.width, t.height, out.display()))
        .confidence(Confidence::Observed)
        .coverage(Coverage::complete(1))
        .location(Location::new("path", out.display().to_string()));
    Ok(ToolOutput::evidence(b.build()?))
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct UnrealTextureParams {
    /// Absolute path of the game's .pak, or of a .uasset already taken out (its .uexp and .ubulk beside it).
    pub path: String,
    /// For a pak: the texture's .uasset path inside it, as game_pak_list shows it.
    #[serde(default)]
    pub file: Option<String>,
    /// Where to write the PNG: an absolute path that doesn't exist yet (its folders are made).
    pub output: String,
    /// The person made this game or has its rights holder's permission to unpack its files.
    #[serde(default)]
    pub permission: bool,
}

/// Where a package's files come from.
enum PackageSource {
    /// Inside a pak: the entries named `<stem>.<extension>` (`stem` lower case, as shown).
    Pak { pak: Box<Pak>, stem: String },
    /// Loose files: `<stem>.<extension>` on disk.
    Loose { stem: PathBuf },
}

impl PackageSource {
    /// One of the package's files, or None when it has none with that extension.
    fn part(&mut self, extension: &str, cancel: &CancelToken) -> Result<Option<Vec<u8>>, ToolError> {
        match self {
            PackageSource::Pak { pak, stem } => {
                let want = format!("{stem}.{extension}");
                let Some(entry) = pak.files.iter().find(|e| shown(e).to_lowercase() == want).cloned() else { return Ok(None) };
                entry_bytes(pak, &entry, cancel).map(Some)
            }
            PackageSource::Loose { stem } => {
                let file = stem.with_extension(extension);
                if !file.is_file() {
                    return Ok(None);
                }
                let len = std::fs::metadata(&file).map_err(|e| ToolError::io(file.display(), e))?.len();
                let mut f = File::open(&file).map_err(|e| ToolError::io(file.display(), e))?;
                read_at(&mut f, &file, 0, len).map(Some)
            }
        }
    }
}

fn game_unreal_texture_export(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: UnrealTextureParams = parse_params(params)?;
    if !p.permission {
        return Err(ToolError::new(
            ErrorCode::ConsentRequired,
            "Unpacking a game's files needs your confirmation that you may: you made the game, or its rights holder allows it.",
        )
        .with_remediation("If that's so, ask again with permission set to true."));
    }
    let out = new_output(&p.output)?;
    let raw = PathBuf::from(&p.path);
    if !raw.is_absolute() {
        return Err(ToolError::invalid(format!("{:?} is not an absolute path", p.path)).with_remediation("Pass the full path of the .pak or .uasset file."));
    }
    let cancel = ctx.cancel.clone();
    let loose = raw.extension().is_some_and(|x| x.eq_ignore_ascii_case("uasset"));
    let (mut source, shown_name) = if loose {
        let name = raw.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
        (PackageSource::Loose { stem: raw.with_extension("") }, name)
    } else {
        let pak = open_pak(ctx, &p.path)?;
        if pak.footer.encrypted_index {
            return Err(ToolError::unsupported(format!("{}'s index is encrypted, so its files can't be found without the game's AES key.", pak.name)));
        }
        let file = p.file.as_deref().map(str::trim).filter(|f| !f.is_empty()).ok_or_else(|| {
            ToolError::invalid("file is needed for a pak: the texture's .uasset path inside it")
                .with_remediation("game_pak_list shows the paths; filter it by .uasset.")
        })?;
        let lower = file.trim_start_matches("../").to_lowercase();
        let stem = lower.strip_suffix(".uasset").or_else(|| lower.strip_suffix(".uexp")).unwrap_or(&lower).to_string();
        (PackageSource::Pak { pak: Box::new(pak), stem }, file.to_string())
    };
    ctx.report(None, format!("Reading {shown_name}"));
    let missing = |ext: &str| {
        ToolError::new(ErrorCode::NotFound, format!("There's no .{ext} for {shown_name}."))
            .with_remediation("A cooked texture is a .uasset with a .uexp beside it; game_pak_list shows what the pak holds.")
    };
    let uasset = source.part("uasset", &cancel)?.ok_or_else(|| missing("uasset"))?;
    let uexp = source.part("uexp", &cancel)?.ok_or_else(|| missing("uexp"))?;
    let package = unreal_texture::package(&uasset).map_err(|e| format_err(e, "an Unreal package"))?;
    let export = package.exports.iter().find(|e| e.class == "Texture2D").ok_or_else(|| {
        let classes: Vec<&str> = package.exports.iter().map(|e| e.class.as_str()).collect();
        ToolError::unsupported(format!("{shown_name} isn't a texture (it holds {}).", classes.join(", ")))
    })?;
    let start = export.serial_offset.checked_sub(package.header_size).ok_or_else(|| damaged("a texture's data lies before its .uexp"))?;
    let data = usize::try_from(start)
        .ok()
        .and_then(|s| uexp.get(s..s.checked_add(usize::try_from(export.serial_size).ok()?)?))
        .ok_or_else(|| damaged("a texture's data lies outside its .uexp"))?;
    let texture = unreal_texture::texture(data, &package.names).map_err(|e| format_err(e, "an Unreal texture"))?;
    let layout = unreal_texture::layout(&texture.pixel_format)
        .ok_or_else(|| ToolError::unsupported(format!("{} is a {} texture, which isn't decoded here.", export.name, texture.pixel_format)))?;
    // The largest mip whose pixels the game ships (bigger ones can be stripped or kept elsewhere).
    let mut other: BTreeMap<&str, Option<Vec<u8>>> = BTreeMap::new();
    let mut chosen = None;
    for (index, mip) in texture.mips.iter().enumerate() {
        if u64::from(mip.width) * u64::from(mip.height) > MAX_PIXELS {
            continue;
        }
        let bytes = match &mip.data {
            unreal_texture::MipData::Inline(s, n) => data.get(*s..s.saturating_add(*n)).map(<[u8]>::to_vec),
            unreal_texture::MipData::File { extension, offset, length } => {
                if !other.contains_key(extension) {
                    let part = source.part(extension, &cancel)?;
                    other.insert(*extension, part);
                }
                other.get(extension).and_then(Option::as_ref).and_then(|f| {
                    let s = usize::try_from(*offset).ok()?;
                    f.get(s..s.checked_add(usize::try_from(*length).ok()?)?).map(<[u8]>::to_vec)
                })
            }
            unreal_texture::MipData::Missing => None,
        };
        if let Some(bytes) = bytes {
            let from = match &mip.data {
                unreal_texture::MipData::File { extension, .. } => *extension,
                _ => "uexp",
            };
            chosen = Some((index, mip.clone(), bytes, from));
            break;
        }
    }
    let (index, mip, bytes, from) = chosen.ok_or_else(|| {
        ToolError::unsupported(format!("None of {}'s mips are stored where they can be read, or they're larger than 8192×8192.", export.name))
    })?;
    let rgba = pixels::decode(layout, mip.width, mip.height, &bytes).map_err(|e| format_err(e, "an Unreal texture's pixels"))?;
    let png = encode_png(&Image { width: mip.width, height: mip.height, rgba })?;
    crate::project::write_atomic(&out, &png)?;
    let mut lims = Vec::new();
    if (mip.width, mip.height) != (texture.width, texture.height) {
        lims.push(Limitation::new(
            "smaller_than_full",
            format!("The game ships this texture at most {}×{}; its full {}×{} isn't stored.", mip.width, mip.height, texture.width, texture.height),
        ));
    }
    let result = json!({
        "name": export.name,
        "pixel_format": texture.pixel_format,
        "width": texture.width,
        "height": texture.height,
        "saved": {"width": mip.width, "height": mip.height, "mip": index, "from": from},
        "output": out.display().to_string(),
        "size": png.len(),
        "sha256": craft_anything_evidence::sha256_hex(&png),
    });
    let b = builder(ctx, "game_unreal_texture_export", Subject { kind: "archive".into(), sha256: None, name: Some(shown_name) }, params_json(&p))
        .result(result)
        .summary(format!("Saved texture \"{}\" ({}×{}, {}) as {}.", export.name, mip.width, mip.height, texture.pixel_format, out.display()))
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .location(Location::new("path", out.display().to_string()));
    Ok(ToolOutput::evidence(b.build()?))
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GameFolderParams {
    /// Absolute path of the game's folder.
    pub path: String,
}

/// Folders deep and entries looked at when searching a game's folder.
const MAX_DEPTH: usize = 8;
const MAX_ENTRIES: usize = 20_000;

/// Where a Godot pack starts in this file, when one does: at its start, or where a trailer at its
/// end says, as long as the pack's mark is really there.
fn godot_start(path: &Path) -> Option<u64> {
    let mut f = File::open(path).ok()?;
    let len = f.metadata().ok()?.len();
    let mark_at =
        |f: &mut File, at: u64| len.checked_sub(at).filter(|left| *left >= 4).and_then(|_| read_at(f, path, at, 4).ok()).is_some_and(|m| m == godot_pck::MAGIC);
    if mark_at(&mut f, 0) {
        return Some(0);
    }
    let tail = read_at(&mut f, path, len.checked_sub(godot_pck::TRAILER_SIZE)?, godot_pck::TRAILER_SIZE).ok()?;
    let start = godot_pck::trailer_start(&tail, len)?;
    mark_at(&mut f, start).then_some(start)
}

/// How many files a Godot pack declares (from its header and, for later formats, one more read).
fn godot_declared_files(path: &Path) -> Option<u64> {
    let start = godot_start(path)?;
    let mut f = File::open(path).ok()?;
    let len = f.metadata().ok()?.len();
    let head = read_at(&mut f, path, start, len.checked_sub(start)?.min(godot_pck::HEADER_READ as u64)).ok()?;
    let directory = start.checked_add(godot_pck::header(&head).ok()?.directory_offset?)?;
    if directory.checked_add(4)? > len {
        return None;
    }
    let count = read_at(&mut f, path, directory, 4).ok()?;
    Some(u64::from(u32::from_le_bytes(count.try_into().ok()?)))
}

/// What kind of archive a file is, and the tool that lists it; None when it isn't one.
fn archive_kind(path: &Path) -> Option<(&'static str, &'static str)> {
    let name = path.file_name()?.to_string_lossy().to_lowercase();
    let ext = path.extension().map(|e| e.to_string_lossy().to_lowercase()).unwrap_or_default();
    let head = |n: u64| -> Option<Vec<u8>> {
        let mut f = File::open(path).ok()?;
        let len = f.metadata().ok()?.len();
        let at = if n > 0 { 0 } else { len.saturating_sub(unreal_pak::FOOTER_READ as u64) };
        let n = if n > 0 { n.min(len) } else { len - at };
        read_at(&mut f, path, at, n).ok()
    };
    match ext.as_str() {
        // Chromium's .pak files share the extension: an Unreal pak has its footer.
        "pak" => {
            let len = std::fs::metadata(path).ok()?.len();
            unreal_pak::footer(&head(0)?, len).ok().map(|_| ("unreal_pak", "game_pak_list"))
        }
        "utoc" => Some(("unreal_iostore", "game_iostore_list")),
        "bundle" | "unity3d" => head(8).filter(|h| h.starts_with(unity_bundle::MAGIC)).map(|_| ("unity_bundle", "game_unity_bundle_list")),
        "assets" => Some(("unity_assets", "game_unity_list")),
        "pck" => head(godot_pck::MAGIC.len() as u64).filter(|h| h.starts_with(godot_pck::MAGIC)).map(|_| ("godot_pck", "core_packed_files_list")),
        // A Godot game can carry its pack at the end of its program.
        "exe" | "x86_64" | "x86_32" | "x86" | "arm64" | "arm32" => godot_start(path).map(|_| ("godot_pck", "core_packed_files_list")),
        "" if name == "globalgamemanagers" || name.strip_prefix("level").is_some_and(|n| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit())) => {
            Some(("unity_assets", "game_unity_list"))
        }
        _ => None,
    }
}

fn game_archives_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: GameFolderParams = parse_params(params)?;
    let root = PathBuf::from(&p.path);
    if !root.is_absolute() || !root.is_dir() {
        return Err(ToolError::invalid(format!("{:?} isn't a folder", p.path)).with_remediation("Pass the full path of the game's folder."));
    }
    ctx.report(None, format!("Looking through {}", root.display()));
    let (mut archives, mut seen, mut stack) = (Vec::new(), 0usize, vec![(root.clone(), 0usize)]);
    while let Some((dir, depth)) = stack.pop() {
        ctx.cancel.check()?;
        let Ok(entries) = std::fs::read_dir(&dir) else { continue };
        for entry in entries.flatten() {
            seen += 1;
            if seen > MAX_ENTRIES {
                break;
            }
            let Ok(kind) = entry.file_type() else { continue };
            let path = entry.path();
            if kind.is_dir() && depth < MAX_DEPTH {
                stack.push((path, depth + 1));
            } else if kind.is_file()
                && let Some((archive, tool)) = archive_kind(&path)
            {
                let size = entry.metadata().map(|m| m.len()).unwrap_or(0);
                let shown = path.strip_prefix(&root).unwrap_or(&path).display().to_string();
                let mut row = json!({"path": path.display().to_string(), "name": shown, "kind": archive, "size": size, "list_tool": tool});
                if archive == "godot_pck" {
                    row["declared_files"] = json!(godot_declared_files(&path));
                }
                archives.push(row);
            }
        }
        if seen > MAX_ENTRIES {
            break;
        }
    }
    archives.sort_by(|a, b| a["kind"].as_str().cmp(&b["kind"].as_str()).then(b["size"].as_u64().cmp(&a["size"].as_u64())));
    let has = |prefix: &str| archives.iter().any(|a| a["kind"].as_str().is_some_and(|k| k.starts_with(prefix)));
    let found: Vec<(&str, &str)> = [("unreal", "Unreal"), ("unity", "Unity"), ("godot", "Godot")].into_iter().filter(|(id, _)| has(id)).collect();
    let engine = match found.as_slice() {
        [] => "none",
        [(id, _)] => id,
        _ => "mixed",
    };
    let truncated = seen > MAX_ENTRIES;
    let name = root.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let summary = if found.is_empty() {
        format!("{name}: no Unreal, Unity or Godot archives found.")
    } else {
        format!("{name}: {} {} archive(s).", archives.len(), found.iter().map(|(_, title)| *title).collect::<Vec<_>>().join(" and "))
    };
    let mut lims = Vec::new();
    if truncated {
        lims.push(Limitation::new("entries_capped", format!("Only the first {MAX_ENTRIES} files and folders were looked at.")));
    }
    let shown_count = archives.len() as u64;
    let b = builder(ctx, "game_archives_list", Subject { kind: "folder".into(), sha256: None, name: Some(name) }, params_json(&p))
        .result(json!({"folder": root.display().to_string(), "engine": engine, "archives": archives, "truncated": truncated}))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(if truncated { super::static_input::partial(shown_count) } else { Coverage::complete(shown_count) })
        .location(Location::new("path", p.path.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

fn damaged(what: impl Into<String>) -> ToolError {
    ToolError::new(ErrorCode::NotSupported, format!("The pak looks damaged: {}", what.into()))
        .with_remediation("Check the game's files (Steam: Verify integrity).")
}

/// A new output file's path: absolute, not there yet, in a folder that is.
fn new_output(raw: &str) -> Result<PathBuf, ToolError> {
    let out = PathBuf::from(raw);
    if !out.is_absolute() {
        return Err(ToolError::invalid("output must be an absolute path"));
    }
    if out.exists() {
        return Err(ToolError::invalid(format!("{} already exists", out.display())).with_remediation("Pick a new file name; nothing is overwritten."));
    }
    let dir = out.parent().ok_or_else(|| ToolError::invalid(format!("{} has no folder", out.display())))?;
    std::fs::create_dir_all(dir).map_err(|e| ToolError::io(dir.display(), e))?;
    Ok(out)
}

/// `rel` (a pak path, `/`-separated) under `root`, or None when a part could climb out or name a drive.
fn inside(root: &Path, rel: &str) -> Option<PathBuf> {
    let mut out = root.to_path_buf();
    for part in rel.split('/') {
        if part.is_empty() || part == "." || part == ".." || part.contains(['\\', ':']) {
            return None;
        }
        out.push(part);
    }
    Some(out)
}

/// Whether a pak entry can be read here, and whether it's zlib-compressed.
fn readable(e: &Entry) -> Result<bool, ToolError> {
    let file = shown(e);
    if e.encrypted {
        return Err(ToolError::unsupported(format!("{file} is encrypted with the game's AES key; it can't be taken out without it.")));
    }
    let method = e.compression.to_lowercase();
    if method != "none" && method != "zlib" {
        let oodle = if method.contains("oodle") { " Oodle is a commercial library the game ships; Craft Anything doesn't run it." } else { "" };
        return Err(ToolError::unsupported(format!("{file} is compressed with {}, which isn't supported here.{oodle}", e.compression)));
    }
    Ok(method == "zlib")
}

/// A pak entry's bytes, in memory.
fn entry_bytes(pak: &mut Pak, e: &Entry, cancel: &CancelToken) -> Result<Vec<u8>, ToolError> {
    let zlib = readable(e)?;
    if e.uncompressed_size > MAX_INDEX {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{} is {} bytes; the limit is {MAX_INDEX}", shown(e), e.uncompressed_size)));
    }
    let mut sink = Sink { file: Vec::with_capacity(e.uncompressed_size as usize), hash: Default::default(), written: 0 };
    copy_entry(pak, e, zlib, &mut sink, Path::new(&e.path), cancel)?;
    Ok(sink.file)
}

/// Where a file being taken out goes: its bytes, counted and hashed as they're written.
struct Sink<W: Write> {
    file: W,
    hash: sha2::Sha256,
    written: u64,
}

impl<W: Write> Sink<W> {
    fn put(&mut self, bytes: &[u8], out: &Path) -> Result<(), ToolError> {
        use sha2::Digest;
        self.file.write_all(bytes).map_err(|e| ToolError::io(out.display(), e))?;
        self.hash.update(bytes);
        self.written += bytes.len() as u64;
        Ok(())
    }
}

/// Copy `e` out of the pak into `sink`: stored bytes as they are, zlib blocks inflated.
fn copy_entry<W: Write>(pak: &mut Pak, e: &Entry, zlib: bool, sink: &mut Sink<W>, out: &Path, cancel: &CancelToken) -> Result<(), ToolError> {
    if zlib {
        for &(start, end) in &e.blocks {
            cancel.check()?;
            if start > end || end > pak.len || end - start > MAX_BLOCK {
                return Err(damaged(format!("a block of {} lies outside it", shown(e))));
            }
            let raw = read_at(&mut pak.file, &pak.path, start, end - start)?;
            let room = e.uncompressed_size.saturating_sub(sink.written);
            let block = craft_anything_formats::firmware::inflate(&raw, true, room, true)
                .map_err(|err| damaged(format!("a block of {} didn't inflate ({err})", shown(e))))?;
            sink.put(&block.data.unwrap_or_default(), out)?;
        }
    } else {
        if e.data_start.checked_add(e.size).is_none_or(|end| end > pak.len) {
            return Err(damaged(format!("{} lies outside it", shown(e))));
        }
        pak.file.seek(SeekFrom::Start(e.data_start)).map_err(|err| ToolError::io(pak.path.display(), err))?;
        let mut buf = vec![0u8; 1 << 20];
        let mut left = e.size;
        while left > 0 {
            cancel.check()?;
            let n = left.min(buf.len() as u64) as usize;
            pak.file.read_exact(&mut buf[..n]).map_err(|err| ToolError::io(pak.path.display(), err))?;
            sink.put(&buf[..n], out)?;
            left -= n as u64;
        }
    }
    if sink.written != e.uncompressed_size {
        return Err(damaged(format!("{} came out as {} bytes; its entry says {}", shown(e), sink.written, e.uncompressed_size)));
    }
    Ok(())
}

fn game_pak_extract(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ExtractParams = parse_params(params)?;
    if p.file.trim().ends_with('/') {
        return extract_folder(ctx, p);
    }
    let out = new_output(&p.output)?;
    let mut pak = open_pak(ctx, &p.path)?;
    if pak.footer.encrypted_index {
        return Err(encrypted_index(&pak));
    }
    let want = p.file.trim().trim_start_matches("../").to_lowercase();
    let entry = pak.files.iter().find(|e| shown(e).to_lowercase() == want).cloned().ok_or_else(|| {
        ToolError::new(ErrorCode::NotFound, format!("There's no {} in {}.", p.file.trim(), pak.name))
            .with_remediation("game_pak_list shows the paths inside; its filter narrows them.")
    })?;
    let file = shown(&entry).to_string();
    ctx.report(None, format!("Taking {file} out of {}", pak.name));
    let (size, sha256) = take_out(&mut pak, &entry, &out, &ctx.cancel.clone())?;
    let result = json!({"file": file, "output": out.display().to_string(), "size": size, "sha256": sha256, "compression": entry.compression});
    let b = builder(ctx, "game_pak_extract", Subject { kind: "archive".into(), sha256: None, name: Some(pak.name.clone()) }, params_json(&p))
        .result(result)
        .summary(format!("Took {file} ({size} bytes) out of {} into {}.", pak.name, out.display()))
        .confidence(Confidence::Observed)
        .coverage(Coverage::complete(1))
        .location(Location::new("path", out.display().to_string()));
    Ok(ToolOutput::evidence(b.build()?))
}

fn encrypted_index(pak: &Pak) -> ToolError {
    ToolError::unsupported(format!("{}'s index is encrypted, so its files can't be found without the game's AES key.", pak.name))
}

/// Write `e` into the new file `out`; returns its size and SHA-256. A failed copy leaves nothing behind.
fn take_out(pak: &mut Pak, e: &Entry, out: &Path, cancel: &CancelToken) -> Result<(u64, String), ToolError> {
    let zlib = readable(e)?;
    let target = std::fs::OpenOptions::new().write(true).create_new(true).open(out).map_err(|err| ToolError::io(out.display(), err))?;
    let mut sink = Sink { file: target, hash: Default::default(), written: 0 };
    if let Err(err) = copy_entry(pak, e, zlib, &mut sink, out, cancel) {
        drop(sink);
        let _ = std::fs::remove_file(out);
        return Err(err);
    }
    use sha2::Digest;
    Ok((sink.written, hex::encode(sink.hash.finalize())))
}

const MAX_FOLDER_FILES: usize = 5000;

/// Every file under a pak folder into `output`, keeping the layout; files already there are skipped.
fn extract_folder(ctx: &mut Ctx<'_>, p: ExtractParams) -> Result<ToolOutput, ToolError> {
    let root = PathBuf::from(&p.output);
    if !root.is_absolute() {
        return Err(ToolError::invalid("output must be an absolute path"));
    }
    let mut pak = open_pak(ctx, &p.path)?;
    if pak.footer.encrypted_index {
        return Err(encrypted_index(&pak));
    }
    let prefix = shown_path(p.file.trim()).to_string();
    let under: Vec<Entry> = pak.files.iter().filter(|e| shown(e).get(..prefix.len()).is_some_and(|head| head.eq_ignore_ascii_case(&prefix))).cloned().collect();
    if under.is_empty() {
        return Err(ToolError::new(ErrorCode::NotFound, format!("There are no files under {prefix} in {}.", pak.name))
            .with_remediation("game_pak_list shows the paths inside; its filter narrows them."));
    }
    let limit = p.limit.clamp(1, MAX_FOLDER_FILES);
    let cancel = ctx.cancel.clone();
    let (mut taken, mut there, mut bytes, mut looked) = (0usize, 0usize, 0u64, 0usize);
    let mut refused = Vec::new();
    for e in &under {
        if taken == limit {
            break;
        }
        cancel.check()?;
        looked += 1;
        let file = shown(e);
        let Some(out) = file.get(prefix.len()..).and_then(|rel| inside(&root, rel)) else {
            refused.push(format!("{file}: its path would leave the folder"));
            continue;
        };
        if out.exists() {
            there += 1;
            continue;
        }
        if taken % 100 == 0 {
            ctx.report(Some(looked as f32 / under.len() as f32), format!("Taking {file} out of {}", pak.name));
        }
        let made = out.parent().map_or(Ok(()), std::fs::create_dir_all).map_err(|err| ToolError::io(out.display(), err));
        match made.and_then(|()| take_out(&mut pak, e, &out, &cancel)) {
            Ok((size, _)) => {
                taken += 1;
                bytes += size;
            }
            Err(err) if err.code == ErrorCode::Cancelled => return Err(err),
            Err(err) => refused.push(format!("{file}: {}", err.message)),
        }
    }
    let left = under.len() - looked;
    let more = if left > 0 { format!(" {left} more are left: call again with the same folder to carry on.") } else { String::new() };
    let summary = format!(
        "Took {taken} files ({bytes} bytes) under {prefix} out of {} into {}; {there} were already there and {} couldn't be taken out.{more}",
        pak.name,
        root.display(),
        refused.len()
    );
    let result = json!({
        "folder": prefix, "output": root.display().to_string(), "files": under.len(), "taken": taken, "bytes": bytes,
        "already_there": there, "refused": refused.len(), "refused_examples": refused.iter().take(20).collect::<Vec<_>>(), "left": left,
    });
    let b = builder(ctx, "game_pak_extract", Subject { kind: "archive".into(), sha256: None, name: Some(pak.name.clone()) }, params_json(&p))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Observed)
        .coverage(Coverage::page(looked as u64, under.len() as u64, 0))
        .location(Location::new("path", root.display().to_string()));
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use crate::{CallOptions, Caller, Engine};
    use serde_json::json;

    fn pak() -> Vec<u8> {
        craft_anything_testkit::games::unreal_pak(&[
            ("/", "Game.uproject", b"{}", false),
            ("Game/Content/Maps/", "Level.umap", b"level bytes", true),
            ("Game/Content/Maps/", "Level.uexp", b"more", false),
        ])
    }

    #[test]
    fn a_file_that_isnt_a_pak_is_named() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("cef.pak", b"not an unreal archive at all, just bytes that go on for a while");
        let err = e.call("game_pak_list", json!({"path": p}), CallOptions::new(Caller::Mcp)).unwrap_err();
        assert!(err.message.contains("no standard Unreal pak footer"), "{err:?}");
        let err = e.call("game_pak_list", json!({"path": "relative.pak"}), CallOptions::new(Caller::Mcp)).unwrap_err();
        assert!(err.message.contains("absolute"), "{err:?}");
    }

    #[test]
    fn lists_an_unreal_pak_with_paging_and_a_filter() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("Game-Windows.pak", &pak());
        let call = |params: serde_json::Value| e.call("game_pak_list", params, CallOptions::new(Caller::Mcp)).unwrap().to_json();
        let v = call(json!({"path": p}));
        let r = &v["result"];
        assert_eq!((r["version"].as_i64(), r["file_count"].as_u64(), r["mount_point"].as_str()), (Some(11), Some(3), Some("../../../")));
        let paths: Vec<&str> = r["files"].as_array().unwrap().iter().map(|f| f["path"].as_str().unwrap()).collect();
        assert_eq!(paths, ["Game.uproject", "Game/Content/Maps/Level.umap", "Game/Content/Maps/Level.uexp"]);
        assert_eq!((r["files"][1]["size"].as_u64(), r["files"][1]["compression"].as_str()), (Some(11), Some("Zlib")));
        assert_eq!((r["size"].as_u64(), r["by_compression"]["none"].as_u64()), (Some(17), Some(2)));
        assert!(v["summary"].as_str().unwrap().contains("version 11) with 3 file(s)"), "{v}");

        let v = call(json!({"path": p, "filter": "MAPS", "offset": 1, "limit": 1}));
        assert_eq!((v["result"]["matching"].as_u64(), v["result"]["files"][0]["path"].as_str()), (Some(2), Some("Game/Content/Maps/Level.uexp")));
        assert_eq!(v["coverage"]["status"], "complete", "the last page");
        let v = call(json!({"path": p, "filter": "maps", "limit": 1}));
        assert_eq!((v["result"]["files"][0]["path"].as_str(), v["coverage"]["status"].as_str()), (Some("Game/Content/Maps/Level.umap"), Some("partial")));
    }

    #[test]
    fn lists_an_iostore_container() {
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        let utoc = dir.path().join("Game-Windows.utoc");
        std::fs::write(&utoc, craft_anything_testkit::games::unreal_utoc(0x9, u32::MAX)).unwrap();
        let call = |params: serde_json::Value| e.call("game_iostore_list", params, CallOptions::new(Caller::Mcp));
        // The .ucas beside it finds its table of contents.
        let v = call(json!({"path": dir.path().join("Game-Windows.ucas")})).unwrap().to_json();
        let r = &v["result"];
        assert_eq!((r["version"].as_u64(), r["file_count"].as_u64(), r["chunk_count"].as_u64()), (Some(8), Some(3), Some(3)));
        let rows: Vec<(&str, u64, &str)> = r["files"]
            .as_array()
            .unwrap()
            .iter()
            .map(|f| (f["path"].as_str().unwrap(), f["stored_size"].as_u64().unwrap(), f["compression"].as_str().unwrap()))
            .collect();
        assert_eq!(rows, [("Game/B.uasset", 8, "Oodle"), ("Game/Maps/A.uasset", 50_000, "Oodle"), ("Game/Maps/A.ubulk", 5, "none")]);
        assert_eq!(r["by_compression"]["Oodle"].as_u64(), Some(2));
        let v = call(json!({"path": utoc, "filter": "ubulk"})).unwrap().to_json();
        assert_eq!(v["result"]["matching"].as_u64(), Some(1));

        // Encrypted names are counted, not shown.
        std::fs::write(&utoc, craft_anything_testkit::games::unreal_utoc(0xb, u32::MAX)).unwrap();
        let v = call(json!({"path": utoc})).unwrap().to_json();
        assert!(v["summary"].as_str().unwrap().contains("names are encrypted"), "{v}");
        assert_eq!((v["result"]["files"].as_array().map(Vec::len), v["result"]["chunk_count"].as_u64()), (Some(0), Some(3)));
        // Unencrypted containers without a directory index still return header metadata and the not_indexed limitation, with unknown file totals and coverage.
        std::fs::write(&utoc, craft_anything_testkit::games::unreal_utoc(0x1, u32::MAX)).unwrap();
        let v = call(json!({"path": utoc})).unwrap().to_json();
        assert!(v["summary"].as_str().unwrap().contains("no directory index"), "{v}");
        assert_eq!((v["result"]["flags"]["indexed"].as_bool(), v["result"]["chunk_count"].as_u64()), (Some(false), Some(3)));
        assert!(v["result"]["file_count"].is_null());
        assert!(v["result"]["size"].is_null());
        assert!(v["result"]["stored_size"].is_null());
        assert!(v["result"]["matching"].is_null());
        assert_eq!(v["coverage"]["status"].as_str(), Some("unknown"));
        assert_eq!(v["limitations"][0]["code"].as_str(), Some("not_indexed"));
        let pak = craft_anything_testkit::temp_file("x.utoc", b"not a table of contents");
        assert!(call(json!({"path": pak})).unwrap_err().message.contains("isn't an IoStore"));
    }

    #[test]
    fn lists_a_unity_assets_file() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("sharedassets0.assets", &craft_anything_testkit::games::unity_assets());
        let call = |params: serde_json::Value| e.call("game_unity_list", params, CallOptions::new(Caller::Mcp));
        let v = call(json!({"path": p})).unwrap().to_json();
        let r = &v["result"];
        assert_eq!(
            (r["format_version"].as_u64(), r["unity_version"].as_str(), r["platform"].as_str()),
            (Some(22), Some("2022.3.62f1"), Some("Windows (64-bit)"))
        );
        let rows: Vec<(&str, Option<&str>)> = r["objects"].as_array().unwrap().iter().map(|o| (o["class"].as_str().unwrap(), o["name"].as_str())).collect();
        assert_eq!(rows, [("GameObject", Some("Player")), ("Texture2D", Some("Grass")), ("MonoBehaviour", Some("PlayerController")), ("Transform", None)]);
        assert_eq!(r["by_class"][0]["count"].as_u64(), Some(1));
        assert!(v["summary"].as_str().unwrap().contains("Unity 2022.3.62f1 file for Windows (64-bit) with 4 object(s)"), "{v}");
        // The filter matches a class or a name.
        for (filter, want) in [("texture", "Grass"), ("controller", "PlayerController")] {
            let v = call(json!({"path": p, "filter": filter})).unwrap().to_json();
            assert_eq!((v["result"]["matching"].as_u64(), v["result"]["objects"][0]["name"].as_str()), (Some(1), Some(want)), "{filter}");
        }
        let mut bundle = b"UnityFS".to_vec();
        bundle.resize(64, 0);
        let bundle = craft_anything_testkit::temp_file("data.unity3d", &bundle);
        assert!(call(json!({"path": bundle})).unwrap_err().message.contains("Unity bundle"));
    }

    #[test]
    fn lists_and_saves_the_textures_of_a_bundles_serialized_files() {
        use craft_anything_testkit::games::{unity_assets, unity_bundle_files, unity_serialized_file, unity_texture2d};
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        // A scene bundle: its level, then its shared assets with a DXT1 texture in the bundle's .resS.
        let red = [0x00, 0xf8, 0x1f, 0x00, 0, 0, 0, 0];
        let stream = ("archive:/CAB-scene/BuildPlayer-Level.sharedAssets.resS", 0, 8);
        let shared = unity_serialized_file("2022.3.62f1", &[(1, vec![0; 16]), (28, unity_texture2d("2022.3.62f1", "Wall", 4, 4, 10, None, Some(stream)))]);
        let bundle = unity_bundle_files(&[
            ("BuildPlayer-Level", &unity_assets(), true),
            ("BuildPlayer-Level.sharedAssets", &shared, true),
            ("BuildPlayer-Level.sharedAssets.resS", &red, false),
        ]);
        let path = dir.path().join("scene.bundle");
        std::fs::write(&path, bundle).unwrap();
        let call = |tool: &str, params: serde_json::Value| e.call(tool, params, CallOptions::new(Caller::Mcp));
        let v = call("game_unity_list", json!({"path": path})).unwrap().to_json();
        let r = &v["result"];
        assert_eq!((r["object_count"].as_u64(), r["serialized_files"].as_array().map(Vec::len)), (Some(6), Some(2)), "{v}");
        assert!(v["summary"].as_str().unwrap().contains("2 serialized file(s) with 6 object(s)"), "{v}");
        // Textures from every serialized file, each naming the file it's in.
        let v = call("game_unity_list", json!({"path": path, "filter": "texture2d"})).unwrap().to_json();
        let rows: Vec<(&str, &str, i64)> = v["result"]["objects"]
            .as_array()
            .unwrap()
            .iter()
            .map(|o| (o["file"].as_str().unwrap(), o["name"].as_str().unwrap(), o["path_id"].as_i64().unwrap()))
            .collect();
        assert_eq!(rows, [("BuildPlayer-Level", "Grass", 2), ("BuildPlayer-Level.sharedAssets", "Wall", 2)]);
        let v = call("game_unity_list", json!({"path": path, "file": "BuildPlayer-Level.sharedAssets"})).unwrap().to_json();
        assert_eq!(v["result"]["object_count"].as_u64(), Some(2));
        // The row's file and path id save the picture, its pixels read from the bundle's .resS.
        let out = dir.path().join("wall.png");
        let v = call("game_unity_asset_export", json!({"path": path, "file": rows[1].0, "path_id": rows[1].2, "output": out})).unwrap().to_json();
        assert_eq!(v["result"]["name"].as_str(), Some("Wall"), "{v}");
        let png = crate::tools::web_common::decode_png(&std::fs::read(&out).unwrap()).unwrap();
        assert!(png.rgba.as_chunks::<4>().0.iter().all(|p| *p == [255, 0, 0, 255]));
    }

    #[test]
    fn a_bundle_built_without_its_unity_version_uses_the_games() {
        use craft_anything_testkit::games::{unity_bundle_with, unity_serialized_file, unity_texture2d};
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        let data = dir.path().join("Game_Data");
        let aa = data.join("StreamingAssets/aa");
        std::fs::create_dir_all(&aa).unwrap();
        // The bundle's file says 0.0.0; its texture has the 2022.3 layout the game's own files name.
        let tex = unity_texture2d("2022.3.62f1", "Wall", 1, 1, 4, Some(&[255, 0, 0, 255]), None);
        let bundle = aa.join("walls.bundle");
        std::fs::write(&bundle, unity_bundle_with(&unity_serialized_file("0.0.0", &[(28, tex)]), b"")).unwrap();
        let export =
            |out: &str| e.call("game_unity_asset_export", json!({"path": bundle, "path_id": 1, "output": dir.path().join(out)}), CallOptions::new(Caller::Mcp));
        let err = export("a.png").unwrap_err();
        assert!(err.message.contains("doesn't say which Unity version"), "{err:?}");
        std::fs::write(data.join("globalgamemanagers"), unity_serialized_file("2022.3.62f1", &[])).unwrap();
        assert_eq!(export("b.png").unwrap().to_json()["result"]["name"].as_str(), Some("Wall"));
        let v = e.call("game_unity_list", json!({"path": bundle}), CallOptions::new(Caller::Mcp)).unwrap().to_json();
        assert_eq!(v["result"]["unity_version"].as_str(), Some("2022.3.62f1"), "{v}");
    }

    #[test]
    fn lists_a_unity_bundle_and_counts_its_objects() {
        let e = Engine::new(crate::testing::session());
        let call = |params: serde_json::Value| e.call("game_unity_bundle_list", params, CallOptions::new(Caller::Mcp));
        let p = craft_anything_testkit::temp_file("level.bundle", &craft_anything_testkit::games::unity_bundle());
        let v = call(json!({"path": p})).unwrap().to_json();
        let r = &v["result"];
        assert_eq!((r["format_version"].as_u64(), r["table_compression"].as_str(), r["file_count"].as_u64()), (Some(8), Some("LZ4"), Some(2)));
        let rows: Vec<(&str, bool)> =
            r["files"].as_array().unwrap().iter().map(|f| (f["path"].as_str().unwrap(), f["serialized"].as_bool().unwrap())).collect();
        assert_eq!(rows, [("CAB-0123456789abcdef", true), ("CAB-0123456789abcdef.resS", false)]);
        // The serialized file's objects are counted from its metadata.
        let objects = &r["files"][0]["objects"];
        assert_eq!((objects["object_count"].as_u64(), objects["unity_version"].as_str()), (Some(4), Some("2022.3.62f1")), "{v}");
        assert!(v["summary"].as_str().unwrap().contains("2 file(s) and 4 object(s)"), "{v}");
        let v = call(json!({"path": p, "filter": "ress"})).unwrap().to_json();
        assert_eq!(v["result"]["matching"].as_u64(), Some(1));
        let not = craft_anything_testkit::temp_file("x.bundle", b"UnityWeb and some more bytes");
        assert!(call(json!({"path": not})).unwrap_err().message.contains("isn't a UnityFS bundle"));
    }

    #[test]
    fn a_bundle_listing_says_when_it_read_only_some_serialized_files() {
        use craft_anything_testkit::games::{unity_bundle_files, unity_serialized_file};
        let e = Engine::new(crate::testing::session());
        let serialized = unity_serialized_file("2022.3.62f1", &[(1, vec![0; 16])]);
        let names: Vec<String> = (1..=17).map(|i| format!("member-{i:02}")).collect();
        let members: Vec<(&str, &[u8], bool)> = names.iter().map(|s| (s.as_str(), serialized.as_slice(), true)).collect();
        let p = craft_anything_testkit::temp_file("many.bundle", &unity_bundle_files(&members));
        let v = e.call("game_unity_bundle_list", json!({"path": p, "limit": 500}), CallOptions::new(Caller::Mcp)).unwrap().to_json();
        assert_eq!(v["limitations"][0]["code"], "files_unread", "{v}");
        assert!(v["summary"].as_str().unwrap().contains("at least 16 object(s)"), "{v}");
    }

    #[test]
    fn saves_unity_textures_as_png() {
        use craft_anything_testkit::games::{unity_bundle_with, unity_serialized_file, unity_texture2d};
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        // 2×1 RGBA32 inline (stored bottom row first), and a 4×4 DXT1 block streamed from the .resS.
        let inline = unity_texture2d("2022.3.62f1", "Pair", 2, 1, 4, Some(&[255, 0, 0, 255, 0, 0, 255, 255]), None);
        let block = [0x00, 0xf8, 0x1f, 0x00, 0, 0, 0, 0]; // all red
        let streamed = unity_texture2d("2022.3.62f1", "Block", 4, 4, 10, None, Some(("sharedassets0.assets.resS", 16, 8)));
        let crunched = unity_texture2d("2022.3.62f1", "Fancy", 4, 4, 28, Some(&[0; 16]), None);
        let assets = unity_serialized_file("2022.3.62f1", &[(28, inline), (28, streamed), (1, vec![0; 16]), (28, crunched)]);
        std::fs::write(dir.path().join("sharedassets0.assets"), &assets).unwrap();
        let mut ress = vec![0u8; 16];
        ress.extend_from_slice(&block);
        std::fs::write(dir.path().join("sharedassets0.assets.resS"), &ress).unwrap();
        let call = |path: &std::path::Path, id: i64, out: &str| {
            e.call("game_unity_asset_export", json!({"path": path, "path_id": id, "output": dir.path().join(out)}), CallOptions::new(Caller::Mcp))
        };
        let file = dir.path().join("sharedassets0.assets");
        let decode = |out: &str| crate::tools::web_common::decode_png(&std::fs::read(dir.path().join(out)).unwrap()).unwrap();
        let v = call(&file, 1, "pair.png").unwrap().to_json();
        assert_eq!((v["result"]["name"].as_str(), v["result"]["format"].as_str()), (Some("Pair"), Some("RGBA32")));
        assert_eq!(decode("pair.png").rgba, [255, 0, 0, 255, 0, 0, 255, 255]);
        let v = call(&file, 2, "block.png").unwrap().to_json();
        assert_eq!(v["result"]["streamed_from"].as_str(), Some("sharedassets0.assets.resS"));
        assert!(decode("block.png").rgba.as_chunks::<4>().0.iter().all(|p| *p == [255, 0, 0, 255]));
        assert!(call(&file, 3, "x.png").unwrap_err().message.contains("GameObject objects can't be taken out yet"));
        assert!(call(&file, 4, "x.png").unwrap_err().message.contains("DXT1Crunched"));
        assert!(call(&file, 9, "x.png").unwrap_err().message.contains("no object with path id 9"));
        assert!(call(&file, 1, "pair.png").unwrap_err().message.contains("already exists"));
        assert!(!dir.path().join("x.png").exists(), "nothing written on a refusal");

        // The same texture inside a bundle, its pixels in the bundle's .resS.
        let in_bundle = unity_texture2d("2022.3.62f1", "Block", 4, 4, 10, None, Some(("archive:/CAB-0123456789abcdef/CAB-0123456789abcdef.resS", 16, 8)));
        let bundle = unity_bundle_with(&unity_serialized_file("2022.3.62f1", &[(28, vec![0; 8]), (28, in_bundle)]), &ress);
        let b = dir.path().join("level.bundle");
        std::fs::write(&b, bundle).unwrap();
        let v = call(&b, 2, "from-bundle.png").unwrap().to_json();
        assert_eq!(v["result"]["width"].as_u64(), Some(4), "{v}");
        assert!(decode("from-bundle.png").rgba.as_chunks::<4>().0.iter().all(|p| *p == [255, 0, 0, 255]));
    }

    #[test]
    fn saves_unreal_textures_only_with_permission() {
        use craft_anything_testkit::games::{unreal_pak, unreal_texture_package};
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        // A 4×4 red mip in the .ubulk (BGRA) and a 2×2 one inline; the .uexp is zlib-compressed in the pak.
        let (uasset, uexp) = unreal_texture_package("T_Icon", "PF_B8G8R8A8", 2, 2, &[0; 16], Some((4, 4, 64)));
        let ubulk: Vec<u8> = [0u8, 0, 255, 255].repeat(16);
        let pak =
            unreal_pak(&[("Game/UI/", "T_Icon.uasset", &uasset, false), ("Game/UI/", "T_Icon.uexp", &uexp, true), ("Game/UI/", "T_Icon.ubulk", &ubulk, false)]);
        let pak_path = dir.path().join("Game-Windows.pak");
        std::fs::write(&pak_path, pak).unwrap();
        let call = |params: serde_json::Value| e.call("game_unreal_texture_export", params, CallOptions::new(Caller::Mcp));
        let out = |name: &str| dir.path().join(name);

        let err = call(json!({"path": pak_path, "file": "Game/UI/T_Icon.uasset", "output": out("a.png")})).unwrap_err();
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::ConsentRequired, "{err:?}");
        assert!(!out("a.png").exists());

        let v = call(json!({"path": pak_path, "file": "game/ui/t_icon.uasset", "output": out("a.png"), "permission": true})).unwrap().to_json();
        assert_eq!(
            (v["result"]["name"].as_str(), v["result"]["saved"]["from"].as_str(), v["result"]["saved"]["width"].as_u64()),
            (Some("T_Icon"), Some("ubulk"), Some(4)),
            "{v}"
        );
        let png = crate::tools::web_common::decode_png(&std::fs::read(out("a.png")).unwrap()).unwrap();
        assert!(png.rgba.as_chunks::<4>().0.iter().all(|p| *p == [255, 0, 0, 255]), "BGRA red comes out red");

        // Loose files taken out earlier work too; without the .ubulk the inline mip is saved, and said to be smaller.
        std::fs::write(dir.path().join("T_Icon.uasset"), &uasset).unwrap();
        std::fs::write(dir.path().join("T_Icon.uexp"), &uexp).unwrap();
        let v = call(json!({"path": dir.path().join("T_Icon.uasset"), "output": out("b.png"), "permission": true})).unwrap().to_json();
        assert_eq!((v["result"]["saved"]["from"].as_str(), v["result"]["saved"]["width"].as_u64()), (Some("uexp"), Some(2)));
        assert_eq!(v["limitations"][0]["code"], "smaller_than_full");

        assert!(
            call(json!({"path": pak_path, "file": "Game/UI/Nope.uasset", "output": out("c.png"), "permission": true}))
                .unwrap_err()
                .message
                .contains("There's no .uasset")
        );
        assert!(call(json!({"path": pak_path, "output": out("c.png"), "permission": true})).unwrap_err().message.contains("file is needed"));
    }

    #[test]
    fn finds_a_games_archives() {
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        let paks = dir.path().join("Game/Content/Paks");
        std::fs::create_dir_all(&paks).unwrap();
        std::fs::write(paks.join("Game-Windows.pak"), pak()).unwrap();
        std::fs::write(paks.join("Game-Windows.utoc"), craft_anything_testkit::games::unreal_utoc(0x9, u32::MAX)).unwrap();
        std::fs::write(dir.path().join("cef.pak"), b"a Chromium resource pack, not an Unreal one at all").unwrap();
        let data = dir.path().join("Game_Data");
        std::fs::create_dir_all(data.join("StreamingAssets")).unwrap();
        std::fs::write(data.join("sharedassets0.assets"), craft_anything_testkit::games::unity_assets()).unwrap();
        std::fs::write(data.join("level0"), craft_anything_testkit::games::unity_assets()).unwrap();
        std::fs::write(data.join("StreamingAssets/ui.bundle"), craft_anything_testkit::games::unity_bundle()).unwrap();
        std::fs::write(data.join("sharedassets0.assets.resS"), b"pixels").unwrap();
        let v = e.call("game_archives_list", json!({"path": dir.path()}), CallOptions::new(Caller::Mcp)).unwrap().to_json();
        let r = &v["result"];
        assert_eq!(r["engine"], "mixed");
        let mut kinds: Vec<(String, String)> = r["archives"]
            .as_array()
            .unwrap()
            .iter()
            .map(|a| (a["kind"].as_str().unwrap().to_string(), a["name"].as_str().unwrap().replace('\\', "/")))
            .collect();
        kinds.sort();
        assert_eq!(
            kinds,
            [
                ("unity_assets".into(), "Game_Data/level0".into()),
                ("unity_assets".into(), "Game_Data/sharedassets0.assets".into()),
                ("unity_bundle".into(), "Game_Data/StreamingAssets/ui.bundle".into()),
                ("unreal_iostore".into(), "Game/Content/Paks/Game-Windows.utoc".into()),
                ("unreal_pak".into(), "Game/Content/Paks/Game-Windows.pak".into()),
            ],
            "Chromium's pak and the .resS aren't archives"
        );
        assert!(e.call("game_archives_list", json!({"path": "relative"}), CallOptions::new(Caller::Mcp)).is_err());
    }

    #[test]
    fn finds_godot_packs_on_their_own_and_inside_a_program() {
        use craft_anything_testkit::games::{GodotFile, godot_embedded, godot_pck};
        let list = |dir: &std::path::Path| -> serde_json::Value {
            Engine::new(crate::testing::session()).call("game_archives_list", json!({"path": dir}), CallOptions::new(Caller::Mcp)).unwrap().to_json()
        };
        let files = [GodotFile { path: "res://a", data: b"x", flags: 0, md5: [0; 16] }, GodotFile { path: "res://b", data: b"yy", flags: 0, md5: [0; 16] }];

        for format in [1, 2, 3] {
            let dir = tempfile::tempdir().unwrap();
            std::fs::write(dir.path().join("game.pck"), godot_pck(format, 2, &files)).unwrap();
            std::fs::write(dir.path().join("other.pck"), b"not a pack").unwrap();
            let v = list(dir.path());
            let r = &v["result"];
            assert_eq!(r["engine"], "godot");
            assert_eq!(r["archives"].as_array().unwrap().len(), 1, "only a real pack counts");
            assert_eq!(r["archives"][0]["kind"], "godot_pck");
            assert_eq!(r["archives"][0]["list_tool"], "core_packed_files_list");
            assert_eq!(r["archives"][0]["declared_files"], 2, "format {format}");
            assert!(v["summary"].as_str().unwrap().contains("1 Godot archive"));
        }

        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("game.exe"), godot_embedded(b"MZ a program", &godot_pck(3, 2, &files))).unwrap();
        std::fs::write(dir.path().join("plain.exe"), b"MZ a program without a pack").unwrap();
        std::fs::write(dir.path().join("tiny.x86_64"), b"x").unwrap();
        let r = list(dir.path());
        let r = &r["result"];
        assert_eq!(r["archives"].as_array().unwrap().len(), 1);
        assert!(r["archives"][0]["name"].as_str().unwrap().ends_with("game.exe"));
        assert_eq!(r["archives"][0]["declared_files"], 2);

        // A pack cut short keeps its place, without a count.
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("cut.pck"), &godot_pck(3, 2, &files)[..50]).unwrap();
        let r = list(dir.path());
        assert!(r["result"]["archives"][0]["declared_files"].is_null());
    }

    #[test]
    fn takes_stored_and_zlib_files_out() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("Game-Windows.pak", &pak());
        let dir = tempfile::tempdir().unwrap();
        let call =
            |file: &str, out: &std::path::Path| e.call("game_pak_extract", json!({"path": p, "file": file, "output": out}), CallOptions::new(Caller::Mcp));
        for (file, want) in
            [("game/content/maps/LEVEL.umap", b"level bytes".as_slice()), ("Game/Content/Maps/Level.uexp", b"more"), ("../../../Game.uproject", b"{}")]
        {
            let out = dir.path().join(file.rsplit('/').next().unwrap());
            let v = call(file, &out).unwrap().to_json();
            assert_eq!(std::fs::read(&out).unwrap(), want, "{file}");
            assert_eq!(v["result"]["sha256"].as_str(), Some(craft_anything_evidence::sha256_hex(want).as_str()));
        }
        // Nothing is overwritten, a missing file is named, and nothing half-written stays.
        let taken = dir.path().join("LEVEL.umap");
        assert!(call("Game/Content/Maps/Level.umap", &taken).unwrap_err().message.contains("already exists"));
        let missing = dir.path().join("missing.bin");
        assert!(call("Game/Nope.uasset", &missing).unwrap_err().message.contains("There's no"));
        assert!(!missing.exists());
        // A missing folder is made.
        let deep = dir.path().join("a").join("b").join("Level.uexp");
        call("Game/Content/Maps/Level.uexp", &deep).unwrap();
        assert_eq!(std::fs::read(&deep).unwrap(), b"more");
    }

    #[test]
    fn takes_a_folder_out_a_page_at_a_time() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("Game-Windows.pak", &pak());
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("Original");
        let call = |limit: usize| {
            e.call("game_pak_extract", json!({"path": p, "file": "game/content/", "output": out, "limit": limit}), CallOptions::new(Caller::Mcp))
                .unwrap()
                .to_json()
        };
        let first = call(1);
        assert_eq!((first["result"]["taken"].as_u64(), first["result"]["left"].as_u64()), (Some(1), Some(1)));
        // Calling again skips what's there and carries on.
        let second = call(500);
        assert_eq!((second["result"]["taken"].as_u64(), second["result"]["already_there"].as_u64()), (Some(1), Some(1)));
        assert_eq!(std::fs::read(out.join("Maps").join("Level.umap")).unwrap(), b"level bytes");
        assert_eq!(std::fs::read(out.join("Maps").join("Level.uexp")).unwrap(), b"more");
        assert!(!dir.path().join("Game.uproject").exists() && !out.join("Game.uproject").exists());
        let none = e.call("game_pak_extract", json!({"path": p, "file": "Game/Nope/", "output": out}), CallOptions::new(Caller::Mcp));
        assert!(none.unwrap_err().message.contains("no files under"));
    }

    #[test]
    fn a_pak_path_never_leaves_the_folder() {
        let root = std::path::Path::new("/out");
        assert_eq!(super::inside(root, "Maps/Level.umap"), Some(root.join("Maps").join("Level.umap")));
        for bad in ["../x", "Maps/../../x", "C:/x", "a\\..\\b", "", "a//b", "./x"] {
            assert_eq!(super::inside(root, bad), None, "{bad}");
        }
    }
}
