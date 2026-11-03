//! Android binary XML (AXML): the compiled form of `AndroidManifest.xml` and `res/*.xml`.
//! Chunks, the string pool (UTF-8 and UTF-16), the resource-id map, namespaces, elements and
//! typed attribute values. Also the string pool and typed-value formatting that resource tables
//! share, and the manifest facts (package, SDK levels, permissions, components) on top.

use crate::FormatError;
use crate::bytes::Reader;
use serde::Serialize;

pub const RES_STRING_POOL: u16 = 0x0001;
pub const RES_XML: u16 = 0x0003;
const XML_START_NS: u16 = 0x0100;
const XML_END_NS: u16 = 0x0101;
const XML_START_ELEMENT: u16 = 0x0102;
const XML_END_ELEMENT: u16 = 0x0103;
const XML_CDATA: u16 = 0x0104;
const XML_RESOURCE_MAP: u16 = 0x0180;

/// Most strings decoded from one pool.
const MAX_STRINGS: usize = 1_000_000;
/// Longest string kept (characters).
const MAX_STRING: usize = 64 * 1024;
/// Most XML nodes decoded.
const MAX_NODES: usize = 200_000;
/// Deepest element nesting tracked.
const MAX_DEPTH: usize = 512;

pub const ANDROID_NS: &str = "http://schemas.android.com/apk/res/android";

/// A chunk header: type, header size, total size, at `off`.
pub fn chunk(r: &Reader<'_>, off: usize) -> Option<(u16, usize, usize)> {
    let t = r.u16_le(off)?;
    let h = usize::from(r.u16_le(off.checked_add(2)?)?);
    let s = r.u32_le(off.checked_add(4)?)? as usize;
    if h < 8 || s < h || off.checked_add(s)? > r.len() {
        return None;
    }
    Some((t, h, s))
}

/// A decoded string pool.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct StringPool {
    pub strings: Vec<String>,
    pub utf8: bool,
    /// Strings the pool declared (may exceed `strings.len()` when capped).
    pub declared: usize,
}

impl StringPool {
    pub fn get(&self, i: u32) -> Option<&str> {
        if i == u32::MAX {
            return None;
        }
        self.strings.get(i as usize).map(String::as_str)
    }

    /// Parse the pool whose chunk starts at `off`.
    pub fn parse(data: &[u8], off: usize) -> Result<StringPool, FormatError> {
        let r = Reader::new(data);
        let (t, _h, size) = chunk(&r, off).ok_or_else(|| FormatError::Truncated("string pool header".into()))?;
        if t != RES_STRING_POOL {
            return Err(FormatError::Malformed(format!("expected a string pool, found chunk type {t:#x}")));
        }
        let end = off + size;
        let count = r.u32_le(off + 8).ok_or_else(|| FormatError::Truncated("string pool".into()))? as usize;
        let flags = r.u32_le(off + 16).ok_or_else(|| FormatError::Truncated("string pool".into()))?;
        let strings_start = r.u32_le(off + 20).ok_or_else(|| FormatError::Truncated("string pool".into()))? as usize;
        let utf8 = flags & (1 << 8) != 0;
        let hdr = usize::from(r.u16_le(off + 2).unwrap_or(28));
        if count.saturating_mul(4) > size {
            return Err(FormatError::Malformed(format!("string pool declares {count} strings in {size} bytes")));
        }
        let base = off.checked_add(strings_start).ok_or_else(|| FormatError::Malformed("string data offset".into()))?;
        let mut strings = Vec::with_capacity(count.min(MAX_STRINGS).min(65_536));
        for i in 0..count.min(MAX_STRINGS) {
            let so = r.u32_le(off + hdr + i * 4).ok_or_else(|| FormatError::Truncated("string offsets".into()))? as usize;
            let at = base.saturating_add(so);
            let s = if at >= end {
                None
            } else if utf8 {
                utf8_string(&r, at, end)
            } else {
                utf16_string(&r, at, end)
            };
            strings.push(s.unwrap_or_default());
        }
        Ok(StringPool { strings, utf8, declared: count })
    }
}

fn utf8_len(r: &Reader<'_>, at: usize) -> Option<(usize, usize)> {
    let b0 = usize::from(r.u8(at)?);
    if b0 & 0x80 != 0 {
        let b1 = usize::from(r.u8(at + 1)?);
        Some((((b0 & 0x7f) << 8) | b1, 2))
    } else {
        Some((b0, 1))
    }
}

fn utf8_string(r: &Reader<'_>, at: usize, end: usize) -> Option<String> {
    let (_chars, n1) = utf8_len(r, at)?;
    let (bytes, n2) = utf8_len(r, at.checked_add(n1)?)?;
    let start = at.checked_add(n1 + n2)?;
    if start.checked_add(bytes)? > end {
        return None;
    }
    let b = r.slice(start, bytes.min(MAX_STRING * 4))?;
    Some(String::from_utf8_lossy(b).into_owned())
}

fn utf16_string(r: &Reader<'_>, at: usize, end: usize) -> Option<String> {
    let u0 = usize::from(r.u16_le(at)?);
    let (len, hdr) = if u0 & 0x8000 != 0 { (((u0 & 0x7fff) << 16) | usize::from(r.u16_le(at + 2)?), 4) } else { (u0, 2) };
    let start = at.checked_add(hdr)?;
    if start.checked_add(len.checked_mul(2)?)? > end {
        return None;
    }
    let n = len.min(MAX_STRING);
    let mut units = Vec::with_capacity(n);
    for i in 0..n {
        units.push(r.u16_le(start + i * 2)?);
    }
    Some(String::from_utf16_lossy(&units))
}

/// A typed value (`Res_value`): data type and 32-bit data.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct ResValue {
    pub data_type: u8,
    pub data: u32,
}

impl ResValue {
    pub fn type_name(&self) -> &'static str {
        match self.data_type {
            0x00 => "null",
            0x01 => "reference",
            0x02 => "attribute",
            0x03 => "string",
            0x04 => "float",
            0x05 => "dimension",
            0x06 => "fraction",
            0x07 => "dynamic-reference",
            0x08 => "dynamic-attribute",
            0x10 => "int-dec",
            0x11 => "int-hex",
            0x12 => "boolean",
            0x1c => "color-argb8",
            0x1d => "color-rgb8",
            0x1e => "color-argb4",
            0x1f => "color-rgb4",
            _ => "unknown",
        }
    }

    /// Human form; strings come from `pool`.
    pub fn format(&self, pool: &StringPool) -> String {
        let d = self.data;
        match self.data_type {
            0x00 => {
                if d == 1 {
                    "@empty".into()
                } else {
                    "@null".into()
                }
            }
            0x01 | 0x07 => {
                if d == 0 {
                    "@null".into()
                } else {
                    format!("@{d:#010x}")
                }
            }
            0x02 | 0x08 => format!("?{d:#010x}"),
            0x03 => pool.get(d).unwrap_or("").to_string(),
            0x04 => format!("{}", f32::from_bits(d)),
            0x05 => complex(d, &["px", "dp", "sp", "pt", "in", "mm"]),
            0x06 => complex(d, &["%", "%p"]),
            0x10 => (d as i32).to_string(),
            0x11 => format!("{d:#x}"),
            0x12 => (if d != 0 { "true" } else { "false" }).into(),
            0x1c..=0x1f => format!("#{d:08x}"),
            _ => format!("{d:#x} (type {:#x})", self.data_type),
        }
    }
}

fn complex(d: u32, units: &[&str]) -> String {
    const RADIX: [f64; 4] = [1.0, 1.0 / 128.0, 1.0 / 32768.0, 1.0 / 8_388_608.0];
    let mantissa = f64::from((d & 0xffff_ff00) as i32 >> 8);
    let radix = RADIX.get(((d >> 4) & 3) as usize).copied().unwrap_or(1.0);
    let mut v = mantissa * radix;
    let unit = units.get((d & 0xf) as usize).copied().unwrap_or("?");
    if units.len() == 2 {
        v *= 100.0;
    }
    let v = (v * 10_000.0).round() / 10_000.0;
    format!("{v}{unit}")
}

/// One attribute of an element.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Attribute {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub namespace: Option<String>,
    pub name: String,
    /// The framework/app resource id of the attribute name, when the resource map gives one.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resource_id: Option<String>,
    /// Formatted value.
    pub value: String,
    pub value_type: &'static str,
    #[serde(skip)]
    pub raw: ResValue,
}

/// One XML node event.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Node {
    Start { depth: usize, name: String, namespace: Option<String>, line: u32, attributes: Vec<Attribute> },
    End { depth: usize, name: String },
    Text { depth: usize, text: String },
    Namespace { prefix: String, uri: String },
}

/// A decoded binary XML document.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct Document {
    pub nodes: Vec<Node>,
    #[serde(skip)]
    pub pool: StringPool,
    pub resource_ids: usize,
    pub namespaces: Vec<(String, String)>,
    pub truncated: bool,
    pub warnings: Vec<String>,
}

/// Names of common framework attributes by resource id, used when a name string was stripped.
pub fn framework_attr(id: u32) -> Option<&'static str> {
    Some(match id {
        0x0101_0000 => "theme",
        0x0101_0001 => "label",
        0x0101_0002 => "icon",
        0x0101_0003 => "name",
        0x0101_0006 => "permission",
        0x0101_0007 => "readPermission",
        0x0101_0008 => "writePermission",
        0x0101_0009 => "protectionLevel",
        0x0101_000e => "enabled",
        0x0101_000f => "debuggable",
        0x0101_0010 => "exported",
        0x0101_0018 => "authorities",
        0x0101_020c => "minSdkVersion",
        0x0101_021b => "versionCode",
        0x0101_021c => "versionName",
        0x0101_0270 => "targetSdkVersion",
        0x0101_0271 => "maxSdkVersion",
        0x0101_0280 => "allowBackup",
        _ => return None,
    })
}

/// Decode a binary XML file.
pub fn parse(data: &[u8]) -> Result<Document, FormatError> {
    let r = Reader::new(data);
    let (t, h, size) = chunk(&r, 0).ok_or_else(|| FormatError::Truncated("binary XML header".into()))?;
    if t != RES_XML {
        return Err(FormatError::Malformed(format!("not binary XML (chunk type {t:#x})")));
    }
    let mut doc = Document::default();
    let mut res_map: Vec<u32> = Vec::new();
    let mut pos = h;
    let mut depth = 0usize;
    let mut ns_stack: Vec<(String, String)> = Vec::new();
    while pos < size {
        let Some((ct, ch, cs)) = chunk(&r, pos) else {
            doc.warnings.push(format!("unreadable chunk at offset {pos}"));
            break;
        };
        match ct {
            RES_STRING_POOL => match StringPool::parse(data, pos) {
                Ok(p) => doc.pool = p,
                Err(e) => doc.warnings.push(format!("string pool: {e}")),
            },
            XML_RESOURCE_MAP => {
                let n = (cs - ch) / 4;
                res_map = (0..n.min(MAX_STRINGS)).filter_map(|i| r.u32_le(pos + ch + i * 4)).collect();
                doc.resource_ids = res_map.len();
            }
            XML_START_NS | XML_END_NS => {
                let prefix = r.u32_le(pos + 16).and_then(|i| doc.pool.get(i)).unwrap_or("").to_string();
                let uri = r.u32_le(pos + 20).and_then(|i| doc.pool.get(i)).unwrap_or("").to_string();
                if ct == XML_START_NS {
                    if doc.namespaces.len() < 256 {
                        doc.namespaces.push((prefix.clone(), uri.clone()));
                    }
                    if ns_stack.len() < MAX_DEPTH {
                        ns_stack.push((prefix.clone(), uri.clone()));
                    }
                    if doc.nodes.len() < MAX_NODES {
                        doc.nodes.push(Node::Namespace { prefix, uri });
                    }
                } else {
                    ns_stack.pop();
                }
            }
            XML_START_ELEMENT => {
                if doc.nodes.len() >= MAX_NODES {
                    doc.truncated = true;
                    break;
                }
                let line = r.u32_le(pos + 8).unwrap_or(0);
                let ext = pos + ch;
                let ns = r.u32_le(ext).and_then(|i| doc.pool.get(i)).map(str::to_string);
                let name = r.u32_le(ext + 4).and_then(|i| doc.pool.get(i)).unwrap_or("?").to_string();
                let a_start = usize::from(r.u16_le(ext + 8).unwrap_or(20));
                let a_size = usize::from(r.u16_le(ext + 10).unwrap_or(20)).max(20);
                let a_count = usize::from(r.u16_le(ext + 12).unwrap_or(0));
                let mut attributes = Vec::new();
                for i in 0..a_count {
                    let Some(a) = ext.checked_add(a_start).and_then(|x| x.checked_add(i * a_size)) else { break };
                    if a + 20 > pos + cs {
                        doc.warnings.push(format!("element {name}: attribute {i} runs past its chunk"));
                        break;
                    }
                    let ans = r.u32_le(a).and_then(|i| doc.pool.get(i)).map(str::to_string);
                    let name_idx = r.u32_le(a + 4).unwrap_or(u32::MAX);
                    let raw_str = r.u32_le(a + 8).unwrap_or(u32::MAX);
                    let vt = r.u8(a + 15).unwrap_or(0);
                    let vd = r.u32_le(a + 16).unwrap_or(0);
                    let rid = res_map.get(name_idx as usize).copied();
                    let mut aname = doc.pool.get(name_idx).unwrap_or("").to_string();
                    if aname.is_empty() {
                        aname = rid.and_then(framework_attr).map(str::to_string).unwrap_or_else(|| format!("attr_{name_idx}"));
                    }
                    let raw = ResValue { data_type: vt, data: vd };
                    let value = if vt == 0x03 || (raw_str != u32::MAX && vt == 0) {
                        doc.pool.get(if vt == 0x03 { vd } else { raw_str }).unwrap_or("").to_string()
                    } else {
                        raw.format(&doc.pool)
                    };
                    attributes.push(Attribute {
                        namespace: ans,
                        name: aname,
                        resource_id: rid.map(|x| format!("{x:#010x}")),
                        value,
                        value_type: raw.type_name(),
                        raw,
                    });
                }
                doc.nodes.push(Node::Start { depth, name, namespace: ns, line, attributes });
                depth = (depth + 1).min(MAX_DEPTH);
            }
            XML_END_ELEMENT => {
                depth = depth.saturating_sub(1);
                let name = r.u32_le(pos + ch + 4).and_then(|i| doc.pool.get(i)).unwrap_or("?").to_string();
                if doc.nodes.len() < MAX_NODES {
                    doc.nodes.push(Node::End { depth, name });
                }
            }
            XML_CDATA => {
                let text = r.u32_le(pos + ch).and_then(|i| doc.pool.get(i)).unwrap_or("").to_string();
                if doc.nodes.len() < MAX_NODES {
                    doc.nodes.push(Node::Text { depth, text });
                }
            }
            _ => {}
        }
        pos = match pos.checked_add(cs) {
            Some(p) => p,
            None => break,
        };
    }
    Ok(doc)
}

fn esc(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;")
}

impl Document {
    fn prefix_for(&self, uri: &str) -> Option<&str> {
        self.namespaces.iter().find(|(_, u)| u == uri).map(|(p, _)| p.as_str())
    }

    /// An XML text rendition (for reading, not byte-exact source).
    pub fn to_xml(&self, max_bytes: usize) -> String {
        let mut out = String::from("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n");
        let mut first = true;
        for n in &self.nodes {
            if out.len() > max_bytes {
                out.push_str("<!-- truncated -->\n");
                break;
            }
            match n {
                Node::Start { depth, name, attributes, .. } => {
                    out.push_str(&"  ".repeat((*depth).min(64)));
                    out.push('<');
                    out.push_str(name);
                    if first {
                        for (p, u) in &self.namespaces {
                            out.push_str(&format!(" xmlns:{p}=\"{}\"", esc(u)));
                        }
                        first = false;
                    }
                    for a in attributes {
                        let p = a.namespace.as_deref().and_then(|u| self.prefix_for(u)).map(|p| format!("{p}:")).unwrap_or_default();
                        out.push_str(&format!(" {p}{}=\"{}\"", a.name, esc(&a.value)));
                    }
                    out.push_str(">\n");
                }
                Node::End { depth, name } => {
                    out.push_str(&"  ".repeat((*depth).min(64)));
                    out.push_str(&format!("</{name}>\n"));
                }
                Node::Text { depth, text } => {
                    out.push_str(&"  ".repeat((*depth).min(64)));
                    out.push_str(&esc(text));
                    out.push('\n');
                }
                Node::Namespace { .. } => {}
            }
        }
        out
    }
}

// ---------------------------------------------------------------------------------------------
// Manifest facts

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct IntentFilter {
    pub actions: Vec<String>,
    pub categories: Vec<String>,
    /// scheme://host/path pieces from `<data>`.
    pub data: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct Component {
    /// activity, activity-alias, service, receiver, provider
    pub kind: String,
    pub name: String,
    /// The explicit `android:exported` value, when set.
    pub exported_attribute: Option<bool>,
    /// Effective: explicit value, or implied by intent filters (only before API 31).
    pub exported: bool,
    pub permission: Option<String>,
    /// A provider's separate read and write permissions.
    pub read_permission: Option<String>,
    pub write_permission: Option<String>,
    /// The explicit `android:enabled` value, when set.
    pub enabled: Option<bool>,
    pub authorities: Option<String>,
    pub intent_filters: Vec<IntentFilter>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct DeclaredPermission {
    pub name: String,
    pub protection_level: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct Manifest {
    pub package: Option<String>,
    pub version_code: Option<String>,
    pub version_name: Option<String>,
    pub min_sdk: Option<String>,
    pub target_sdk: Option<String>,
    pub max_sdk: Option<String>,
    pub uses_permissions: Vec<String>,
    pub declared_permissions: Vec<DeclaredPermission>,
    pub uses_features: Vec<String>,
    pub application: ApplicationFlags,
    pub components: Vec<Component>,
    pub uses_libraries: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct ApplicationFlags {
    pub name: Option<String>,
    pub label: Option<String>,
    /// Guards every component that doesn't name its own.
    pub permission: Option<String>,
    /// The explicit `android:enabled` value, when set.
    pub enabled: Option<bool>,
    pub debuggable: Option<bool>,
    pub allow_backup: Option<bool>,
    pub uses_cleartext_traffic: Option<bool>,
    pub network_security_config: Option<String>,
    pub extract_native_libs: Option<bool>,
    pub test_only: Option<bool>,
}

fn attr<'a>(attrs: &'a [Attribute], name: &str) -> Option<&'a Attribute> {
    attrs.iter().find(|a| a.name == name && a.namespace.as_deref().is_none_or(|n| n == ANDROID_NS))
}

fn sval(attrs: &[Attribute], name: &str) -> Option<String> {
    attr(attrs, name).map(|a| a.value.clone())
}

fn bval(attrs: &[Attribute], name: &str) -> Option<bool> {
    attr(attrs, name).and_then(|a| match a.value.as_str() {
        "true" => Some(true),
        "false" => Some(false),
        _ => None,
    })
}

fn qualify(package: &Option<String>, name: &str) -> String {
    match package {
        Some(p) if name.starts_with('.') => format!("{p}{name}"),
        Some(p) if !name.contains('.') && !name.is_empty() => format!("{p}.{name}"),
        _ => name.to_string(),
    }
}

/// Facts from a decoded `AndroidManifest.xml`.
pub fn manifest(doc: &Document) -> Manifest {
    let mut m = Manifest::default();
    let mut stack: Vec<String> = Vec::new();
    let mut current: Option<Component> = None;
    let mut filter: Option<IntentFilter> = None;
    for n in &doc.nodes {
        match n {
            Node::Start { name, attributes: a, .. } => {
                let parent = stack.last().map(String::as_str).unwrap_or("");
                match (parent, name.as_str()) {
                    (_, "manifest") => {
                        m.package = a.iter().find(|x| x.name == "package").map(|x| x.value.clone());
                        m.version_code = sval(a, "versionCode");
                        m.version_name = sval(a, "versionName");
                    }
                    ("manifest", "uses-sdk") => {
                        m.min_sdk = sval(a, "minSdkVersion");
                        m.target_sdk = sval(a, "targetSdkVersion");
                        m.max_sdk = sval(a, "maxSdkVersion");
                    }
                    ("manifest", "uses-permission" | "uses-permission-sdk-23") => {
                        if let Some(p) = sval(a, "name")
                            && m.uses_permissions.len() < 4096
                        {
                            m.uses_permissions.push(p);
                        }
                    }
                    ("manifest", "permission") => {
                        if let Some(p) = sval(a, "name")
                            && m.declared_permissions.len() < 4096
                        {
                            m.declared_permissions.push(DeclaredPermission { name: p, protection_level: sval(a, "protectionLevel") });
                        }
                    }
                    ("manifest", "uses-feature") => {
                        if let Some(p) = sval(a, "name")
                            && m.uses_features.len() < 4096
                        {
                            m.uses_features.push(p);
                        }
                    }
                    ("manifest", "application") => {
                        m.application = ApplicationFlags {
                            name: sval(a, "name").map(|n| qualify(&m.package, &n)),
                            label: sval(a, "label"),
                            permission: sval(a, "permission"),
                            enabled: bval(a, "enabled"),
                            debuggable: bval(a, "debuggable"),
                            allow_backup: bval(a, "allowBackup"),
                            uses_cleartext_traffic: bval(a, "usesCleartextTraffic"),
                            network_security_config: sval(a, "networkSecurityConfig"),
                            extract_native_libs: bval(a, "extractNativeLibs"),
                            test_only: bval(a, "testOnly"),
                        };
                    }
                    ("application", "uses-library") => {
                        if let Some(p) = sval(a, "name")
                            && m.uses_libraries.len() < 1024
                        {
                            m.uses_libraries.push(p);
                        }
                    }
                    ("application", k @ ("activity" | "activity-alias" | "service" | "receiver" | "provider")) => {
                        current = Some(Component {
                            kind: k.to_string(),
                            name: qualify(&m.package, &sval(a, "name").unwrap_or_default()),
                            exported_attribute: bval(a, "exported"),
                            exported: false,
                            permission: sval(a, "permission"),
                            read_permission: sval(a, "readPermission"),
                            write_permission: sval(a, "writePermission"),
                            enabled: bval(a, "enabled"),
                            authorities: sval(a, "authorities"),
                            intent_filters: Vec::new(),
                        });
                    }
                    (_, "intent-filter") if current.is_some() => filter = Some(IntentFilter::default()),
                    ("intent-filter", "action") => {
                        if let (Some(f), Some(v)) = (filter.as_mut(), sval(a, "name")) {
                            f.actions.push(v);
                        }
                    }
                    ("intent-filter", "category") => {
                        if let (Some(f), Some(v)) = (filter.as_mut(), sval(a, "name")) {
                            f.categories.push(v);
                        }
                    }
                    ("intent-filter", "data") => {
                        if let Some(f) = filter.as_mut() {
                            let parts: Vec<String> = ["scheme", "host", "port", "path", "pathPrefix", "pathPattern", "mimeType"]
                                .iter()
                                .filter_map(|k| sval(a, k).map(|v| format!("{k}={v}")))
                                .collect();
                            if !parts.is_empty() {
                                f.data.push(parts.join(" "));
                            }
                        }
                    }
                    _ => {}
                }
                if stack.len() < MAX_DEPTH {
                    stack.push(name.clone());
                }
            }
            Node::End { name, .. } => {
                stack.pop();
                match name.as_str() {
                    "intent-filter" => {
                        if let (Some(c), Some(f)) = (current.as_mut(), filter.take())
                            && c.intent_filters.len() < 256
                        {
                            c.intent_filters.push(f);
                        }
                    }
                    "activity" | "activity-alias" | "service" | "receiver" | "provider" => {
                        if let Some(c) = current.take()
                            && m.components.len() < 20_000
                        {
                            m.components.push(c);
                        }
                    }
                    _ => {}
                }
            }
            _ => {}
        }
    }
    let target: Option<u32> = m.target_sdk.as_deref().and_then(|s| s.parse().ok());
    for c in &mut m.components {
        // Providers were exported by default up to API 16, intent filters or not.
        let implied = if c.kind == "provider" { target.is_none_or(|t| t <= 16) } else { !c.intent_filters.is_empty() && target.is_none_or(|t| t < 31) };
        c.exported = c.exported_attribute.unwrap_or(implied);
    }
    m
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::android as fx;

    #[test]
    fn decodes_manifest() {
        let doc = parse(&fx::manifest_axml()).unwrap();
        assert!(doc.warnings.is_empty(), "{:?}", doc.warnings);
        let m = manifest(&doc);
        assert_eq!(m.package.as_deref(), Some(fx::PACKAGE));
        assert_eq!(m.version_code.as_deref(), Some("42"));
        assert_eq!(m.version_name.as_deref(), Some("1.2.3"));
        assert_eq!(m.min_sdk.as_deref(), Some("24"));
        assert_eq!(m.target_sdk.as_deref(), Some("34"));
        assert_eq!(m.uses_permissions, vec!["android.permission.INTERNET", "android.permission.CAMERA"]);
        assert_eq!(m.declared_permissions[0].name, "com.example.notes.permission.SYNC");
        assert_eq!(m.declared_permissions[0].protection_level.as_deref(), Some("0x2"));
        assert_eq!(m.application.debuggable, Some(true));
        assert_eq!(m.application.allow_backup, Some(false));
        assert_eq!(m.application.label.as_deref(), Some("@0x7f010000"));
        assert_eq!(m.components.len(), 3);
        let main = &m.components[0];
        assert_eq!(main.name, "com.example.notes.MainActivity");
        assert!(main.exported);
        assert_eq!(main.intent_filters[0].actions, vec!["android.intent.action.MAIN"]);
        assert_eq!(main.intent_filters[0].categories, vec!["android.intent.category.LAUNCHER"]);
        assert_eq!(main.intent_filters[0].data, vec!["scheme=notes host=open"]);
        assert_eq!(m.components[1].kind, "service");
        assert!(!m.components[1].exported);
        assert_eq!(m.components[2].kind, "provider");
        assert_eq!(m.components[2].authorities.as_deref(), Some("com.example.notes.files"));
        let xml = doc.to_xml(1 << 20);
        assert!(xml.contains("<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\""), "{xml}");
        assert!(xml.contains("android:name=\"android.permission.INTERNET\""), "{xml}");
    }

    #[test]
    fn values_format() {
        let p = StringPool { strings: vec!["x".into()], utf8: false, declared: 1 };
        assert_eq!(ResValue { data_type: 0x05, data: (16 << 8) | 1 }.format(&p), "16dp");
        assert_eq!(ResValue { data_type: 0x12, data: 0xffff_ffff }.format(&p), "true");
        assert_eq!(ResValue { data_type: 0x1c, data: 0xff00_ff00 }.format(&p), "#ff00ff00");
        assert_eq!(ResValue { data_type: 0x10, data: (-5i32) as u32 }.format(&p), "-5");
        assert_eq!(ResValue { data_type: 0x03, data: 0 }.format(&p), "x");
        assert_eq!(ResValue { data_type: 0x04, data: 1.5f32.to_bits() }.format(&p), "1.5");
    }

    #[test]
    fn hostile() {
        let s = fx::manifest_axml();
        for m in craft_anything_testkit::mutations(&s) {
            if let Ok(d) = parse(&m) {
                let _ = manifest(&d);
                let _ = d.to_xml(4096);
            }
        }
        for len in 0..s.len() {
            let _ = parse(&s[..len]);
        }
        for seed in 0..64 {
            let mut n = craft_anything_testkit::noise(seed, 512);
            n[0] = 3;
            n[1] = 0;
            n[2] = 8;
            n[3] = 0;
            n[4..8].copy_from_slice(&512u32.to_le_bytes());
            let _ = parse(&n);
        }
    }
}
