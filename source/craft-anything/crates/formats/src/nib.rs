//! Compiled Interface Builder documents: the `NIBArchive` format (objects, keys, values and class
//! tables with variable-length integers) and keyed-archive nibs, both read into one object model,
//! plus the derived graph: outlet and action connections and the view hierarchy.

use crate::FormatError;
use crate::bytes::Reader;
use crate::keyed_archive::{self, KeyedArchive};
use crate::plist::{self, Value as PValue};
use serde::Serialize;
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

/// Most objects, keys, values or classes read from one NIB archive.
pub const MAX_TABLE: usize = 2_000_000;

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(tag = "type", content = "value", rename_all = "snake_case")]
pub enum IbValue {
    Int(i64),
    Bool(bool),
    Float(f64),
    Data(Vec<u8>),
    Nil,
    Object(u64),
    /// A keyed-archive scalar, already JSON.
    Json(Json),
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct IbObject {
    pub index: u64,
    pub class: String,
    pub values: Vec<(String, IbValue)>,
}

/// One compiled document.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct IbDocument {
    /// `nib-archive` or `keyed-archive`.
    pub encoding: &'static str,
    pub format_version: Option<u32>,
    pub coder_version: Option<u32>,
    pub objects: Vec<IbObject>,
    pub warnings: Vec<String>,
}

/// True for the `NIBArchive` binary form.
pub fn is_nib_archive(data: &[u8]) -> bool {
    data.starts_with(b"NIBArchive")
}

/// Parse either encoding.
pub fn parse(data: &[u8]) -> Result<IbDocument, FormatError> {
    if is_nib_archive(data) {
        parse_nib_archive(data)
    } else if data.starts_with(b"bplist") || plist::looks_like_plist(data) {
        let v = plist::parse(data)?;
        let a = keyed_archive::from_plist(&v)?;
        Ok(from_keyed_archive(&a))
    } else {
        Err(FormatError::Malformed("neither a NIB archive nor a keyed archive".into()))
    }
}

/// NIB variable-length integer: 7 bits per byte, little-endian; a set high bit marks the last byte.
fn varint(r: &Reader<'_>, pos: &mut usize) -> Option<u64> {
    let mut v = 0u64;
    for i in 0..10u32 {
        let b = r.u8(*pos)?;
        *pos = pos.checked_add(1)?;
        v |= u64::from(b & 0x7f).checked_shl(7 * i)?;
        if b & 0x80 != 0 {
            return Some(v);
        }
    }
    None
}

fn table(r: &Reader<'_>, at: usize, what: &str) -> Result<(usize, usize), FormatError> {
    let n = r.u32_le(at).ok_or_else(|| FormatError::Truncated(format!("{what} count")))? as usize;
    let off = r.u32_le(at + 4).ok_or_else(|| FormatError::Truncated(format!("{what} offset")))? as usize;
    if n > MAX_TABLE || n > r.len() {
        return Err(FormatError::Malformed(format!("{n} {what} in a {}-byte file", r.len())));
    }
    if off > r.len() {
        return Err(FormatError::Truncated(format!("{what} table lies past the end")));
    }
    Ok((n, off))
}

/// Parse a `NIBArchive` file.
pub fn parse_nib_archive(data: &[u8]) -> Result<IbDocument, FormatError> {
    if !is_nib_archive(data) {
        return Err(FormatError::Malformed("no NIBArchive header".into()));
    }
    let r = Reader::new(data);
    let fv = r.u32_le(10);
    let cv = r.u32_le(14);
    let (n_obj, o_obj) = table(&r, 18, "objects")?;
    let (n_key, o_key) = table(&r, 26, "keys")?;
    let (n_val, o_val) = table(&r, 34, "values")?;
    let (n_cls, o_cls) = table(&r, 42, "classes")?;
    let mut warnings = Vec::new();
    // Keys.
    let mut keys = Vec::with_capacity(n_key);
    let mut p = o_key;
    for _ in 0..n_key {
        let len = varint(&r, &mut p).ok_or_else(|| FormatError::Truncated("key table".into()))? as usize;
        let s = r.slice(p, len).ok_or_else(|| FormatError::Truncated("key name".into()))?;
        keys.push(String::from_utf8_lossy(s).into_owned());
        p += len;
    }
    // Classes.
    let mut classes = Vec::with_capacity(n_cls);
    let mut p = o_cls;
    for _ in 0..n_cls {
        let len = varint(&r, &mut p).ok_or_else(|| FormatError::Truncated("class table".into()))? as usize;
        let extra = varint(&r, &mut p).ok_or_else(|| FormatError::Truncated("class table".into()))? as usize;
        p = extra.checked_mul(4).and_then(|e| p.checked_add(e)).ok_or_else(|| FormatError::Malformed("class table".into()))?;
        let s = r.slice(p, len).ok_or_else(|| FormatError::Truncated("class name".into()))?;
        let end = s.iter().position(|&b| b == 0).unwrap_or(s.len());
        classes.push(String::from_utf8_lossy(s.get(..end).unwrap_or(s)).into_owned());
        p += len;
    }
    // Values.
    let mut values = Vec::with_capacity(n_val);
    let mut p = o_val;
    for i in 0..n_val {
        let k = varint(&r, &mut p).ok_or_else(|| FormatError::Truncated("value table".into()))? as usize;
        let ty = r.u8(p).ok_or_else(|| FormatError::Truncated("value type".into()))?;
        p += 1;
        let trunc = || FormatError::Truncated(format!("value {i}"));
        let v = match ty {
            0 => {
                let b = r.u8(p).ok_or_else(trunc)?;
                p += 1;
                IbValue::Int(i64::from(b as i8))
            }
            1 => {
                let b = r.u16_le(p).ok_or_else(trunc)?;
                p += 2;
                IbValue::Int(i64::from(b as i16))
            }
            2 => {
                let b = r.u32_le(p).ok_or_else(trunc)?;
                p += 4;
                IbValue::Int(i64::from(b as i32))
            }
            3 => {
                let b = r.u64_le(p).ok_or_else(trunc)?;
                p += 8;
                IbValue::Int(b as i64)
            }
            4 => IbValue::Bool(true),
            5 => IbValue::Bool(false),
            6 => {
                let b = r.u32_le(p).ok_or_else(trunc)?;
                p += 4;
                IbValue::Float(f64::from(f32::from_bits(b)))
            }
            7 => {
                let b = r.u64_le(p).ok_or_else(trunc)?;
                p += 8;
                IbValue::Float(f64::from_bits(b))
            }
            8 => {
                let len = varint(&r, &mut p).ok_or_else(trunc)? as usize;
                let d = r.slice(p, len).ok_or_else(trunc)?;
                p += len;
                IbValue::Data(d.to_vec())
            }
            9 => IbValue::Nil,
            10 => {
                let o = r.u32_le(p).ok_or_else(trunc)?;
                p += 4;
                IbValue::Object(u64::from(o))
            }
            other => return Err(FormatError::Malformed(format!("value {i} has unknown type {other}"))),
        };
        let key = keys.get(k).cloned().unwrap_or_else(|| {
            if warnings.len() < 50 {
                warnings.push(format!("value {i} names missing key {k}"));
            }
            format!("#key{k}")
        });
        values.push((key, v));
    }
    // Objects.
    let mut objects = Vec::with_capacity(n_obj);
    let mut p = o_obj;
    // Objects may share value ranges; cap the copies so overlapping ranges cannot explode.
    let mut budget = values.len().saturating_mul(4).max(1 << 16);
    for i in 0..n_obj {
        let c = varint(&r, &mut p).ok_or_else(|| FormatError::Truncated("object table".into()))? as usize;
        let start = varint(&r, &mut p).ok_or_else(|| FormatError::Truncated("object table".into()))? as usize;
        let count = varint(&r, &mut p).ok_or_else(|| FormatError::Truncated("object table".into()))? as usize;
        let class = classes.get(c).cloned().unwrap_or_else(|| format!("#class{c}"));
        let vals = match start.checked_add(count).and_then(|end| values.get(start..end)) {
            Some(v) if v.len() <= budget => {
                budget -= v.len();
                v.to_vec()
            }
            Some(_) => {
                if warnings.len() < 50 {
                    warnings.push(format!("object {i}: value budget exhausted (overlapping value ranges)"));
                }
                Vec::new()
            }
            None => {
                if warnings.len() < 50 {
                    warnings.push(format!("object {i} values {start}+{count} lie outside the value table"));
                }
                Vec::new()
            }
        };
        objects.push(IbObject { index: i as u64, class, values: vals });
    }
    Ok(IbDocument { encoding: "nib-archive", format_version: fv, coder_version: cv, objects, warnings })
}

/// Read a keyed-archive nib into the same object model.
pub fn from_keyed_archive(a: &KeyedArchive) -> IbDocument {
    let mut objects = Vec::new();
    for (i, o) in a.objects.iter().enumerate() {
        let PValue::Dict(d) = o else { continue };
        if d.iter().any(|(k, _)| k == "$classname") {
            continue;
        }
        let class = a.class_of(i as u64).unwrap_or_default();
        let mut values = Vec::new();
        for (k, v) in d {
            if k == "$class" {
                continue;
            }
            match v {
                PValue::Array(items) => {
                    for it in items {
                        values.push((k.clone(), kv(it)));
                    }
                }
                other => values.push((k.clone(), kv(other))),
            }
        }
        objects.push(IbObject { index: i as u64, class, values });
    }
    // Plain strings in the object table become NSString objects so labels resolve.
    for (i, o) in a.objects.iter().enumerate() {
        if let PValue::String(s) = o
            && s != "$null"
        {
            objects.push(IbObject { index: i as u64, class: "NSString".into(), values: vec![("NS.string".into(), IbValue::Json(json!(s)))] });
        }
    }
    objects.sort_by_key(|o| o.index);
    IbDocument { encoding: "keyed-archive", format_version: None, coder_version: a.version.and_then(|v| u32::try_from(v).ok()), objects, warnings: Vec::new() }
}

fn kv(v: &PValue) -> IbValue {
    if let Some(u) = keyed_archive::uid_of(v) {
        return IbValue::Object(u);
    }
    match v {
        PValue::Integer(i) => i64::try_from(*i).map(IbValue::Int).unwrap_or_else(|_| IbValue::Json(plist::int_json(*i))),
        PValue::Bool(b) => IbValue::Bool(*b),
        PValue::Real(f) => IbValue::Float(*f),
        PValue::Data(d) => IbValue::Data(d.clone()),
        other => IbValue::Json(other.to_json()),
    }
}

// ---------------------------------------------------------------------------------------------
// Graph

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Connection {
    pub index: u64,
    /// `outlet`, `outlet-collection` or `action`.
    pub kind: &'static str,
    pub class: String,
    pub label: Option<String>,
    pub source: Option<u64>,
    pub source_class: Option<String>,
    pub destination: Option<u64>,
    pub destination_class: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Graph {
    pub objects: Vec<Json>,
    pub objects_total: usize,
    pub connections: Vec<Connection>,
    pub connections_total: usize,
    /// parent → children view edges.
    pub hierarchy: Vec<Json>,
    pub class_counts: BTreeMap<String, usize>,
    pub root_objects: Vec<u64>,
}

fn is_string_class(c: &str) -> bool {
    matches!(c, "NSString" | "NSMutableString" | "NSLocalizableString" | "__NSCFString" | "NSStringKey")
}

fn is_array_class(c: &str) -> bool {
    matches!(c, "NSArray" | "NSMutableArray" | "NSSet" | "NSMutableSet" | "NSOrderedSet")
}

impl IbDocument {
    fn by_index(&self) -> BTreeMap<u64, &IbObject> {
        self.objects.iter().map(|o| (o.index, o)).collect()
    }
}

fn text_of(v: &IbValue) -> Option<String> {
    match v {
        IbValue::Data(d) => std::str::from_utf8(d).ok().map(|s| s.trim_end_matches('\0').to_string()),
        IbValue::Json(Json::String(s)) => Some(s.clone()),
        _ => None,
    }
}

fn string_of(map: &BTreeMap<u64, &IbObject>, idx: u64) -> Option<String> {
    let o = map.get(&idx)?;
    if !is_string_class(&o.class) {
        return None;
    }
    o.values.iter().find(|(k, _)| k == "NS.bytes" || k == "NS.string").and_then(|(_, v)| text_of(v))
}

fn first<'a>(o: &'a IbObject, keys: &[&str]) -> Option<&'a IbValue> {
    o.values.iter().find(|(k, _)| keys.contains(&k.as_str())).map(|(_, v)| v)
}

fn obj_ref(v: Option<&IbValue>) -> Option<u64> {
    match v {
        Some(IbValue::Object(o)) => Some(*o),
        _ => None,
    }
}

/// Array elements of an array-like object.
fn elements(o: &IbObject) -> Vec<u64> {
    o.values
        .iter()
        .filter(|(k, _)| k == "UINibEncoderEmptyKey" || k.starts_with("NS.object") || k == "NS.objects")
        .filter_map(|(_, v)| obj_ref(Some(v)))
        .collect()
}

/// Derive objects, connections and the view hierarchy. Caps bound each list.
pub fn graph(doc: &IbDocument, max_objects: usize, max_connections: usize) -> Graph {
    let map = doc.by_index();
    let class_of = |i: u64| map.get(&i).map(|o| o.class.clone());
    let mut class_counts = BTreeMap::new();
    for o in &doc.objects {
        *class_counts.entry(o.class.clone()).or_insert(0usize) += 1;
    }
    let render = |v: &IbValue| -> Json {
        match v {
            IbValue::Object(i) => match string_of(&map, *i) {
                Some(s) => json!({"string": s, "ref": i}),
                None => json!({"ref": i, "class": class_of(*i)}),
            },
            IbValue::Data(d) => match std::str::from_utf8(d) {
                Ok(s) if s.chars().all(|c| !c.is_control() || c == '\n' || c == '\0') => json!(s.trim_end_matches('\0')),
                _ => json!({"data_length": d.len()}),
            },
            IbValue::Int(i) => json!(i),
            IbValue::Bool(b) => json!(b),
            IbValue::Float(f) => serde_json::Number::from_f64(*f).map(Json::Number).unwrap_or(Json::Null),
            IbValue::Nil => Json::Null,
            IbValue::Json(j) => j.clone(),
        }
    };
    let objects: Vec<Json> = doc
        .objects
        .iter()
        .filter(|o| !is_string_class(&o.class))
        .take(max_objects)
        .map(|o| {
            let vals: Vec<Json> = o.values.iter().take(256).map(|(k, v)| json!({"key": k, "value": render(v)})).collect();
            json!({"index": o.index, "class": o.class, "values": vals, "value_count": o.values.len()})
        })
        .collect();
    let objects_total = doc.objects.iter().filter(|o| !is_string_class(&o.class)).count();
    let mut connections = Vec::new();
    let mut connections_total = 0usize;
    for o in &doc.objects {
        let c = o.class.as_str();
        let kind = if c.contains("OutletCollection") {
            "outlet-collection"
        } else if c.contains("Outlet") {
            "outlet"
        } else if c.contains("EventConnection") || c.contains("ControlConnector") || c.contains("ActionConnection") {
            "action"
        } else if c.ends_with("Connector") || c.ends_with("Connection") {
            "outlet"
        } else {
            continue;
        };
        connections_total += 1;
        if connections.len() >= max_connections {
            continue;
        }
        let label = first(o, &["UILabel", "NSLabel", "label"]).and_then(|v| match v {
            IbValue::Object(i) => string_of(&map, *i),
            other => text_of(other),
        });
        let source = obj_ref(first(o, &["UISource", "NSSource", "source"]));
        let destination = obj_ref(first(o, &["UIDestination", "NSDestination", "destination"]));
        connections.push(Connection {
            index: o.index,
            kind,
            class: o.class.clone(),
            label,
            source,
            source_class: source.and_then(class_of),
            destination,
            destination_class: destination.and_then(class_of),
        });
    }
    let mut hierarchy = Vec::new();
    for o in &doc.objects {
        let Some(sub) = obj_ref(first(o, &["UISubviews", "NSSubviews"])) else { continue };
        let Some(arr) = map.get(&sub) else { continue };
        let children: Vec<Json> = if is_array_class(&arr.class) || !elements(arr).is_empty() {
            elements(arr).into_iter().take(4096).map(|c| json!({"index": c, "class": class_of(c)})).collect()
        } else {
            vec![json!({"index": sub, "class": arr.class})]
        };
        if hierarchy.len() < max_objects {
            hierarchy.push(json!({"parent": o.index, "parent_class": o.class, "children": children}));
        }
    }
    let root_objects = doc
        .objects
        .iter()
        .find_map(|o| obj_ref(first(o, &["UINibTopLevelObjectsKey", "IBDocument.RootObjects", "NSRoot"])))
        .and_then(|a| map.get(&a).map(|arr| elements(arr)))
        .unwrap_or_default();
    Graph { objects, objects_total, connections, connections_total, hierarchy, class_counts, root_objects }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::apple as fx;

    #[test]
    fn decodes_a_nib_archive() {
        let d = parse(&fx::nib_archive()).unwrap();
        assert_eq!(d.encoding, "nib-archive");
        assert_eq!(d.coder_version, Some(10));
        let g = graph(&d, 1000, 1000);
        assert!(g.class_counts.contains_key("UILabel"));
        let outlet = g.connections.iter().find(|c| c.kind == "outlet").unwrap();
        assert_eq!(outlet.label.as_deref(), Some("titleLabel"));
        assert_eq!(outlet.destination_class.as_deref(), Some("UILabel"));
        let action = g.connections.iter().find(|c| c.kind == "action").unwrap();
        assert_eq!(action.label.as_deref(), Some("save:"));
        assert_eq!(action.source_class.as_deref(), Some("UIButton"));
        let h = &g.hierarchy[0];
        assert_eq!(h["parent_class"], "UIView");
        assert_eq!(h["children"].as_array().unwrap().len(), 2);
        assert_eq!(g.root_objects.len(), 2);
        let capped = graph(&d, 1, 0);
        assert_eq!(capped.objects.len(), 1);
        assert_eq!(capped.connections_total, 2);
    }

    #[test]
    fn keyed_archive_nib() {
        let d = parse(&fx::keyed_nib()).unwrap();
        assert_eq!(d.encoding, "keyed-archive");
        let g = graph(&d, 100, 100);
        let c = g.connections.first().unwrap();
        assert_eq!(c.label.as_deref(), Some("window"));
        assert_eq!(c.destination_class.as_deref(), Some("NSWindow"));
    }

    #[test]
    fn hostile_inputs() {
        let s = fx::nib_archive();
        for m in craft_anything_testkit::mutations(&s) {
            if let Ok(d) = parse(&m) {
                let _ = graph(&d, 100, 100);
            }
        }
        for i in 0..s.len() {
            let _ = parse(&s[..i]);
        }
        for seed in 0..100 {
            let mut n = b"NIBArchive".to_vec();
            n.extend(craft_anything_testkit::noise(seed, 80));
            if let Ok(d) = parse(&n) {
                let _ = graph(&d, 10, 10);
            }
        }
    }
}
