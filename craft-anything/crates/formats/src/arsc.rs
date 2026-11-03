//! Android compiled resource tables (`resources.arsc`): the global string pool, packages, type
//! and key string pools, type specs, and typed entries per configuration (locale, density,
//! orientation, SDK level…). Simple and complex (bag) entries, sparse and 16-bit offset tables.

use crate::FormatError;
use crate::axml::{ResValue, StringPool, chunk};
use crate::bytes::Reader;
use serde::Serialize;

const RES_TABLE: u16 = 0x0002;
const RES_PACKAGE: u16 = 0x0200;
const RES_TYPE: u16 = 0x0201;
const RES_TYPE_SPEC: u16 = 0x0202;
const RES_LIBRARY: u16 = 0x0203;
const NO_ENTRY: u32 = 0xffff_ffff;
const MAX_PACKAGES: usize = 64;
const MAX_BAG: usize = 4096;

/// Limits for one table.
#[derive(Debug, Clone, Copy)]
pub struct Limits {
    /// Most entries decoded across all types and configurations.
    pub max_entries: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Limits { max_entries: 2_000_000 }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct TypeInfo {
    pub id: u8,
    pub name: String,
    pub entry_count: u32,
    /// Configuration qualifiers that have values for this type ("default" for none).
    pub configs: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Package {
    pub id: u32,
    pub name: String,
    pub types: Vec<TypeInfo>,
    pub keys: usize,
    /// Shared-library package references (id → name).
    pub libraries: Vec<(u32, String)>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct BagItem {
    pub name: String,
    pub value: String,
    pub value_type: &'static str,
}

/// One value of one resource in one configuration.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Entry {
    /// `0xPPTTEEEE`
    pub id: String,
    pub package: String,
    #[serde(rename = "type")]
    pub type_name: String,
    pub key: String,
    /// Qualifier string, e.g. `fr`, `es-rMX`, `night-xhdpi`, or `default`.
    pub config: String,
    /// `language[-rREGION]`, empty for the default locale.
    pub locale: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub value: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub value_type: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub bag: Vec<BagItem>,
    #[serde(skip)]
    pub raw: Option<ResValue>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct Table {
    pub packages: Vec<Package>,
    pub global_strings: usize,
    pub entries: Vec<Entry>,
    pub truncated: bool,
    pub warnings: Vec<String>,
}

fn utf16_fixed(r: &Reader<'_>, off: usize, chars: usize) -> String {
    let units: Vec<u16> = (0..chars).map_while(|i| r.u16_le(off + i * 2)).take_while(|&u| u != 0).collect();
    String::from_utf16_lossy(&units)
}

fn ascii2(b: &[u8]) -> String {
    b.iter().take_while(|&&c| c != 0).map(|&c| if c.is_ascii_graphic() { c as char } else { '?' }).collect()
}

/// A packed 2-byte language or region code (3-letter codes are packed into 15 bits).
fn unpack_code(b: &[u8], base: u8) -> String {
    let (b0, b1) = (b.first().copied().unwrap_or(0), b.get(1).copied().unwrap_or(0));
    if b0 & 0x80 != 0 {
        let first = b1 & 0x1f;
        let second = ((b1 & 0xe0) >> 5) | ((b0 & 0x03) << 3);
        let third = (b0 & 0x7c) >> 2;
        [first, second, third].iter().map(|c| (c.wrapping_add(base)) as char).collect()
    } else {
        ascii2(&[b0, b1])
    }
}

/// Qualifier string and locale for a `ResTable_config` at `off`.
pub fn config_qualifiers(r: &Reader<'_>, off: usize) -> (String, String) {
    let size = r.u32_le(off).unwrap_or(0) as usize;
    let get8 = |o: usize| if o < size { r.u8(off + o) } else { None };
    let get16 = |o: usize| if o + 1 < size { r.u16_le(off + o) } else { None };
    let mut q: Vec<String> = Vec::new();
    if let Some(mcc) = get16(4).filter(|&v| v != 0) {
        q.push(format!("mcc{mcc}"));
    }
    if let Some(mnc) = get16(6).filter(|&v| v != 0) {
        q.push(format!("mnc{mnc}"));
    }
    let lang = if size >= 12 { r.slice(off + 8, 2).map(|b| unpack_code(b, b'a')).unwrap_or_default() } else { String::new() };
    let region = if size >= 12 { r.slice(off + 10, 2).map(|b| unpack_code(b, b'0')).unwrap_or_default() } else { String::new() };
    let mut locale = lang.clone();
    if !region.is_empty() {
        locale.push_str(&format!("-r{region}"));
    }
    if !locale.is_empty() {
        q.push(locale.clone());
    }
    if let Some(sl) = get8(28) {
        match sl & 0xc0 {
            0x40 => q.push("ldltr".into()),
            0x80 => q.push("ldrtl".into()),
            _ => {}
        }
    }
    if let Some(sw) = get16(30).filter(|&v| v != 0) {
        q.push(format!("sw{sw}dp"));
    }
    if let Some(w) = get16(32).filter(|&v| v != 0) {
        q.push(format!("w{w}dp"));
    }
    if let Some(h) = get16(34).filter(|&v| v != 0) {
        q.push(format!("h{h}dp"));
    }
    if let Some(sl) = get8(28) {
        match sl & 0x0f {
            1 => q.push("small".into()),
            2 => q.push("normal".into()),
            3 => q.push("large".into()),
            4 => q.push("xlarge".into()),
            _ => {}
        }
        match sl & 0x30 {
            0x10 => q.push("notlong".into()),
            0x20 => q.push("long".into()),
            _ => {}
        }
    }
    match get8(12) {
        Some(1) => q.push("port".into()),
        Some(2) => q.push("land".into()),
        Some(3) => q.push("square".into()),
        _ => {}
    }
    if let Some(ui) = get8(29) {
        match ui & 0x0f {
            2 => q.push("desk".into()),
            3 => q.push("car".into()),
            4 => q.push("television".into()),
            5 => q.push("appliance".into()),
            6 => q.push("watch".into()),
            7 => q.push("vrheadset".into()),
            _ => {}
        }
        match ui & 0x30 {
            0x10 => q.push("notnight".into()),
            0x20 => q.push("night".into()),
            _ => {}
        }
    }
    if let Some(d) = get16(14).filter(|&v| v != 0) {
        q.push(match d {
            120 => "ldpi".into(),
            160 => "mdpi".into(),
            213 => "tvdpi".into(),
            240 => "hdpi".into(),
            320 => "xhdpi".into(),
            480 => "xxhdpi".into(),
            640 => "xxxhdpi".into(),
            0xfffe => "anydpi".into(),
            0xffff => "nodpi".into(),
            d => format!("{d}dpi"),
        });
    }
    match get8(13) {
        Some(1) => q.push("notouch".into()),
        Some(3) => q.push("finger".into()),
        _ => {}
    }
    match get8(16) {
        Some(1) => q.push("nokeys".into()),
        Some(2) => q.push("qwerty".into()),
        Some(3) => q.push("12key".into()),
        _ => {}
    }
    match get8(17) {
        Some(1) => q.push("nonav".into()),
        Some(2) => q.push("dpad".into()),
        Some(3) => q.push("trackball".into()),
        Some(4) => q.push("wheel".into()),
        _ => {}
    }
    if let (Some(w), Some(h)) = (get16(20), get16(22))
        && w != 0
        && h != 0
    {
        q.push(format!("{w}x{h}"));
    }
    if let Some(v) = get16(24).filter(|&v| v != 0) {
        q.push(format!("v{v}"));
    }
    let s = if q.is_empty() { "default".to_string() } else { q.join("-") };
    (s, locale)
}

struct Pkg<'a> {
    name: &'a str,
    id: u32,
    types: &'a StringPool,
    keys: &'a StringPool,
}

fn type_name(p: &Pkg<'_>, id: u8) -> String {
    p.types.get(u32::from(id).wrapping_sub(1)).map(str::to_string).unwrap_or_else(|| format!("type{id}"))
}

/// Parse a resource table.
pub fn parse(data: &[u8], limits: Limits) -> Result<Table, FormatError> {
    let r = Reader::new(data);
    let (t, h, size) = chunk(&r, 0).ok_or_else(|| FormatError::Truncated("resource table header".into()))?;
    if t != RES_TABLE {
        return Err(FormatError::Malformed(format!("not a resource table (chunk type {t:#x})")));
    }
    let mut table = Table::default();
    let mut global = StringPool::default();
    let mut pos = h;
    while pos < size {
        let Some((ct, _ch, cs)) = chunk(&r, pos) else {
            table.warnings.push(format!("unreadable chunk at offset {pos}"));
            break;
        };
        match ct {
            crate::axml::RES_STRING_POOL => match StringPool::parse(data, pos) {
                Ok(p) => {
                    table.global_strings = p.declared;
                    global = p;
                }
                Err(e) => table.warnings.push(format!("global string pool: {e}")),
            },
            RES_PACKAGE => {
                if table.packages.len() >= MAX_PACKAGES {
                    table.warnings.push("too many packages; the rest were skipped".into());
                } else {
                    parse_package(data, pos, cs, &global, &mut table, limits);
                }
            }
            _ => {}
        }
        pos = match pos.checked_add(cs) {
            Some(p) => p,
            None => break,
        };
    }
    Ok(table)
}

fn parse_package(data: &[u8], pos: usize, cs: usize, global: &StringPool, table: &mut Table, limits: Limits) {
    let r = Reader::new(data);
    let hsize = usize::from(r.u16_le(pos + 2).unwrap_or(0));
    let id = r.u32_le(pos + 8).unwrap_or(0);
    let name = utf16_fixed(&r, pos + 12, 128);
    let type_strings = r.u32_le(pos + 268).unwrap_or(0) as usize;
    let key_strings = r.u32_le(pos + 276).unwrap_or(0) as usize;
    let end = pos + cs;
    let types = if type_strings != 0 { StringPool::parse(data, pos + type_strings).unwrap_or_default() } else { StringPool::default() };
    let keys = if key_strings != 0 { StringPool::parse(data, pos + key_strings).unwrap_or_default() } else { StringPool::default() };
    let mut package = Package { id, name: name.clone(), types: Vec::new(), keys: keys.declared, libraries: Vec::new() };
    let p = Pkg { name: &name, id, types: &types, keys: &keys };
    let mut c = pos.saturating_add(hsize.max(8));
    while c < end {
        let Some((ct, ch, sz)) = chunk(&r, c) else {
            table.warnings.push(format!("package {name}: unreadable chunk at offset {c}"));
            break;
        };
        match ct {
            RES_TYPE_SPEC => {
                let tid = r.u8(c + 8).unwrap_or(0);
                let count = r.u32_le(c + 12).unwrap_or(0);
                if !package.types.iter().any(|t| t.id == tid) && package.types.len() < 256 {
                    package.types.push(TypeInfo { id: tid, name: type_name(&p, tid), entry_count: count, configs: Vec::new() });
                }
            }
            RES_TYPE => {
                let tid = r.u8(c + 8).unwrap_or(0);
                let (cfg, _) = config_qualifiers(&r, c + 20);
                match package.types.iter_mut().find(|t| t.id == tid) {
                    Some(t) => {
                        if !t.configs.contains(&cfg) && t.configs.len() < 4096 {
                            t.configs.push(cfg);
                        }
                    }
                    None => {
                        if package.types.len() < 256 {
                            package.types.push(TypeInfo { id: tid, name: type_name(&p, tid), entry_count: r.u32_le(c + 12).unwrap_or(0), configs: vec![cfg] })
                        }
                    }
                }
                parse_type(&r, c, ch, sz, &p, global, table, limits);
            }
            RES_LIBRARY => {
                let n = r.u32_le(c + 8).unwrap_or(0) as usize;
                for i in 0..n.min(256) {
                    let e = c + ch + i * 260;
                    if let Some(lid) = r.u32_le(e) {
                        package.libraries.push((lid, utf16_fixed(&r, e + 4, 128)));
                    }
                }
            }
            _ => {}
        }
        c = match c.checked_add(sz) {
            Some(x) => x,
            None => break,
        };
    }
    table.packages.push(package);
}

#[allow(clippy::too_many_arguments)]
fn parse_type(r: &Reader<'_>, c: usize, ch: usize, sz: usize, p: &Pkg<'_>, global: &StringPool, table: &mut Table, limits: Limits) {
    let tid = r.u8(c + 8).unwrap_or(0);
    let flags = r.u8(c + 9).unwrap_or(0);
    let count = r.u32_le(c + 12).unwrap_or(0) as usize;
    let entries_start = r.u32_le(c + 16).unwrap_or(0) as usize;
    let (cfg, locale) = config_qualifiers(r, c + 20);
    let end = c + sz;
    let tname = type_name(p, tid);
    let sparse = flags & 0x01 != 0;
    let off16 = flags & 0x02 != 0;
    // (entry index, offset from entries_start)
    let mut slots: Vec<(u32, usize)> = Vec::new();
    let table_bytes = if sparse || off16 { count.saturating_mul(if sparse { 4 } else { 2 }) } else { count.saturating_mul(4) };
    if c.saturating_add(ch).saturating_add(table_bytes) > end {
        table.warnings.push(format!("{tname} ({cfg}): entry table runs past its chunk"));
        return;
    }
    for i in 0..count {
        let at = c + ch;
        if sparse {
            let (Some(idx), Some(o)) = (r.u16_le(at + i * 4), r.u16_le(at + i * 4 + 2)) else { break };
            slots.push((u32::from(idx), usize::from(o) * 4));
        } else if off16 {
            let Some(o) = r.u16_le(at + i * 2) else { break };
            if o != 0xffff {
                slots.push((i as u32, usize::from(o) * 4));
            }
        } else {
            let Some(o) = r.u32_le(at + i * 4) else { break };
            if o != NO_ENTRY {
                slots.push((i as u32, o as usize));
            }
        }
    }
    for (idx, o) in slots {
        if table.entries.len() >= limits.max_entries {
            table.truncated = true;
            return;
        }
        let Some(e) = c.checked_add(entries_start).and_then(|x| x.checked_add(o)) else { continue };
        if e.saturating_add(8) > end {
            continue;
        }
        let esize = usize::from(r.u16_le(e).unwrap_or(0));
        let eflags = r.u16_le(e + 2).unwrap_or(0);
        let id = (p.id << 24) | (u32::from(tid) << 16) | (idx & 0xffff);
        let mut entry = Entry {
            id: format!("{id:#010x}"),
            package: p.name.to_string(),
            type_name: tname.clone(),
            key: String::new(),
            config: cfg.clone(),
            locale: locale.clone(),
            value: None,
            value_type: None,
            parent: None,
            bag: Vec::new(),
            raw: None,
        };
        if eflags & 0x08 != 0 {
            // Compact entry: key index in the size field, type in the high byte of flags.
            entry.key = p.keys.get(u32::from(r.u16_le(e).unwrap_or(0))).unwrap_or("").to_string();
            let v = ResValue { data_type: (eflags >> 8) as u8, data: r.u32_le(e + 4).unwrap_or(0) };
            entry.value = Some(v.format(global));
            entry.value_type = Some(v.type_name());
            entry.raw = Some(v);
        } else {
            entry.key = r.u32_le(e + 4).and_then(|k| p.keys.get(k)).unwrap_or("").to_string();
            if eflags & 0x01 != 0 {
                let parent = r.u32_le(e + 8).unwrap_or(0);
                if parent != 0 {
                    entry.parent = Some(format!("@{parent:#010x}"));
                }
                let n = r.u32_le(e + 12).unwrap_or(0) as usize;
                let mut m = e.saturating_add(esize.max(16));
                for _ in 0..n.min(MAX_BAG) {
                    if m.saturating_add(12) > end {
                        break;
                    }
                    let name = r.u32_le(m).unwrap_or(0);
                    let v = ResValue { data_type: r.u8(m + 7).unwrap_or(0), data: r.u32_le(m + 8).unwrap_or(0) };
                    entry.bag.push(BagItem { name: format!("@{name:#010x}"), value: v.format(global), value_type: v.type_name() });
                    m += 12;
                }
            } else {
                let v_at = e.saturating_add(esize.max(8));
                if v_at.saturating_add(8) <= end {
                    let v = ResValue { data_type: r.u8(v_at + 3).unwrap_or(0), data: r.u32_le(v_at + 4).unwrap_or(0) };
                    entry.value = Some(v.format(global));
                    entry.value_type = Some(v.type_name());
                    entry.raw = Some(v);
                }
            }
        }
        table.entries.push(entry);
    }
}

impl Table {
    /// String resources grouped by locale (`""` = default): (locale, key, value).
    pub fn strings_by_locale(&self) -> std::collections::BTreeMap<String, Vec<(String, String)>> {
        let mut out: std::collections::BTreeMap<String, Vec<(String, String)>> = Default::default();
        for e in self.entries.iter().filter(|e| e.type_name == "string") {
            if let Some(v) = &e.value {
                out.entry(e.locale.clone()).or_default().push((e.key.clone(), v.clone()));
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::android as fx;

    #[test]
    fn decodes_table() {
        let t = parse(&fx::resources_arsc(), Limits::default()).unwrap();
        assert!(t.warnings.is_empty(), "{:?}", t.warnings);
        assert_eq!(t.packages.len(), 1);
        let p = &t.packages[0];
        assert_eq!(p.id, 0x7f);
        assert_eq!(p.name, fx::PACKAGE);
        assert_eq!(p.types[0].name, "string");
        assert_eq!(p.types[0].configs, vec!["default", "fr"]);
        let by = t.strings_by_locale();
        assert_eq!(by[""], vec![("app_name".to_string(), "Notes".to_string()), ("greeting".to_string(), "Hello".to_string())]);
        assert_eq!(by["fr"], vec![("app_name".to_string(), "Notes FR".to_string()), ("greeting".to_string(), "Bonjour".to_string())]);
        let app = t.entries.iter().find(|e| e.key == "app_name" && e.locale.is_empty()).unwrap();
        assert_eq!(app.id, "0x7f010000");
        let style = t.entries.iter().find(|e| e.type_name == "style").unwrap();
        assert_eq!(style.key, "AppTheme");
        assert_eq!(style.parent.as_deref(), Some("@0x01030005"));
        assert_eq!(style.bag[0].value, "#ff336699");
        assert_eq!(style.config, "night-xhdpi-v21");
    }

    #[test]
    fn qualifiers() {
        let mut cfg = vec![0u8; 64];
        cfg[0] = 64;
        cfg[8] = b'e';
        cfg[9] = b's';
        cfg[10] = b'M';
        cfg[11] = b'X';
        cfg[12] = 2;
        let (q, l) = config_qualifiers(&Reader::new(&cfg), 0);
        assert_eq!(q, "es-rMX-land");
        assert_eq!(l, "es-rMX");
    }

    #[test]
    fn hostile() {
        let s = fx::resources_arsc();
        for m in craft_anything_testkit::mutations(&s) {
            let _ = parse(&m, Limits { max_entries: 1000 });
        }
        for len in 0..s.len() {
            let _ = parse(&s[..len], Limits::default());
        }
        for seed in 0..64 {
            let mut n = craft_anything_testkit::noise(seed, 1024);
            n[0] = 2;
            n[1] = 0;
            n[2] = 12;
            n[3] = 0;
            n[4..8].copy_from_slice(&1024u32.to_le_bytes());
            n[12] = 0;
            n[13] = 2;
            let _ = parse(&n, Limits::default());
        }
    }
}
