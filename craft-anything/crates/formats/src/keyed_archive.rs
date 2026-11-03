//! Keyed archives (`NSKeyedArchiver` property lists): the `$objects` table with UID references
//! resolved into a projected tree. Each object is expanded once; later references and cycles
//! become `{"$ref": index}` so the projection is linear in the archive size.

use crate::FormatError;
use crate::plist::{self, Value};
use serde::Serialize;
use serde_json::{Map, Value as Json, json};
use std::collections::HashSet;

const MAX_PROJECT_DEPTH: usize = 96;
const MAX_PROJECT_NODES: usize = 500_000;

#[derive(Debug, Clone)]
pub struct KeyedArchive {
    pub archiver: String,
    pub version: Option<i128>,
    /// `$top` entries: name and object index.
    pub top: Vec<(String, u64)>,
    pub objects: Vec<Value>,
}

/// One row of the object table.
#[derive(Debug, Clone, Serialize)]
pub struct ObjectRow {
    pub index: usize,
    pub class: Option<String>,
    /// `string`, `integer`, `object`, … for non-object rows.
    pub kind: &'static str,
    pub keys: Vec<String>,
    /// Indexes this object references.
    pub references: Vec<u64>,
}

/// True when a parsed plist is a keyed archive.
pub fn is_keyed_archive(v: &Value) -> bool {
    v.get("$objects").and_then(Value::as_array).is_some() && v.get("$top").is_some()
}

/// Read the archive structure from a parsed plist.
pub fn from_plist(v: &Value) -> Result<KeyedArchive, FormatError> {
    let objects = v.get("$objects").and_then(Value::as_array).ok_or_else(|| FormatError::Malformed("no $objects array (not a keyed archive)".into()))?;
    let top = match v.get("$top") {
        Some(Value::Dict(d)) => d.iter().filter_map(|(k, v)| uid_of(v).map(|u| (k.clone(), u))).collect(),
        _ => return Err(FormatError::Malformed("no $top dictionary".into())),
    };
    Ok(KeyedArchive {
        archiver: v.get("$archiver").and_then(Value::as_str).unwrap_or("").to_string(),
        version: v.get("$version").and_then(Value::as_int),
        top,
        objects: objects.to_vec(),
    })
}

/// Parse bytes (binary or XML plist) as a keyed archive.
pub fn parse(data: &[u8]) -> Result<KeyedArchive, FormatError> {
    from_plist(&plist::parse(data)?)
}

/// A UID, also in its XML form `{"CF$UID": n}`.
pub fn uid_of(v: &Value) -> Option<u64> {
    match v {
        Value::Uid(u) => Some(*u),
        Value::Dict(d) if d.len() == 1 => d.first().filter(|(k, _)| k == "CF$UID").and_then(|(_, v)| v.as_int()).and_then(|i| u64::try_from(i).ok()),
        _ => None,
    }
}

fn kind_of(v: &Value) -> &'static str {
    match v {
        Value::Dict(_) => "object",
        Value::Array(_) => "array",
        Value::String(s) if s == "$null" => "null",
        Value::String(_) => "string",
        Value::Integer(_) => "integer",
        Value::Real(_) => "real",
        Value::Bool(_) => "boolean",
        Value::Date(_) => "date",
        Value::Data(_) => "data",
        Value::Uid(_) => "uid",
        Value::Null => "null",
    }
}

impl KeyedArchive {
    pub fn object(&self, idx: u64) -> Option<&Value> {
        usize::try_from(idx).ok().and_then(|i| self.objects.get(i))
    }

    /// The class name of an object (`$class` → `$classname`).
    pub fn class_of(&self, idx: u64) -> Option<String> {
        let o = self.object(idx)?;
        let c = o.get("$class").and_then(uid_of)?;
        self.object(c)?.get("$classname").and_then(Value::as_str).map(str::to_string)
    }

    /// The table of objects.
    pub fn rows(&self) -> Vec<ObjectRow> {
        self.objects
            .iter()
            .enumerate()
            .map(|(i, o)| {
                let (keys, references) = match o {
                    Value::Dict(d) => {
                        let mut refs = Vec::new();
                        for (_, v) in d {
                            collect_uids(v, &mut refs, 0);
                        }
                        (d.iter().map(|(k, _)| k.clone()).collect(), refs)
                    }
                    _ => (Vec::new(), Vec::new()),
                };
                ObjectRow { index: i, class: self.class_of(i as u64), kind: kind_of(o), keys, references }
            })
            .collect()
    }

    /// The root to project: `name` in `$top`, else `root`, else the first entry.
    pub fn root(&self, name: Option<&str>) -> Option<(String, u64)> {
        match name {
            Some(n) => self.top.iter().find(|(k, _)| k == n).cloned(),
            None => self.top.iter().find(|(k, _)| k == "root").or_else(|| self.top.first()).cloned(),
        }
    }

    /// Project the object graph below `idx` into JSON.
    pub fn project(&self, idx: u64) -> Json {
        let mut p = Projector { a: self, expanded: HashSet::new(), nodes: 0 };
        p.uid(idx, 0)
    }
}

fn collect_uids(v: &Value, out: &mut Vec<u64>, depth: usize) {
    if depth > 16 || out.len() > 10_000 {
        return;
    }
    if let Some(u) = uid_of(v) {
        out.push(u);
        return;
    }
    match v {
        Value::Array(a) => a.iter().for_each(|x| collect_uids(x, out, depth + 1)),
        Value::Dict(d) => d.iter().for_each(|(_, x)| collect_uids(x, out, depth + 1)),
        _ => {}
    }
}

struct Projector<'a> {
    a: &'a KeyedArchive,
    expanded: HashSet<u64>,
    nodes: usize,
}

impl Projector<'_> {
    fn reference(&self, idx: u64, why: &str) -> Json {
        let mut m = Map::new();
        m.insert("$ref".into(), json!(idx));
        if let Some(c) = self.a.class_of(idx) {
            m.insert("$class".into(), json!(c));
        }
        if !why.is_empty() {
            m.insert("$note".into(), json!(why));
        }
        Json::Object(m)
    }

    fn value(&mut self, v: &Value, depth: usize) -> Json {
        if let Some(u) = uid_of(v) {
            return self.uid(u, depth + 1);
        }
        match v {
            Value::Array(items) => Json::Array(items.iter().map(|x| self.value(x, depth + 1)).collect()),
            other => other.to_json(),
        }
    }

    fn list(&mut self, v: Option<&Value>, depth: usize) -> Vec<Json> {
        v.and_then(Value::as_array).map(|a| a.iter().map(|x| self.value(x, depth)).collect()).unwrap_or_default()
    }

    fn uid(&mut self, idx: u64, depth: usize) -> Json {
        self.nodes += 1;
        let Some(obj) = self.a.object(idx) else {
            return json!({"$ref": idx, "$note": "missing object"});
        };
        match obj {
            Value::String(s) if s == "$null" => return Json::Null,
            Value::Dict(_) => {}
            other => return other.to_json(),
        }
        if self.expanded.contains(&idx) {
            return self.reference(idx, "");
        }
        if depth > MAX_PROJECT_DEPTH || self.nodes > MAX_PROJECT_NODES {
            return self.reference(idx, "projection limit");
        }
        self.expanded.insert(idx);
        let class = self.a.class_of(idx);
        let c = class.as_deref().unwrap_or("");
        match c {
            "NSArray" | "NSMutableArray" | "NSSet" | "NSMutableSet" | "NSOrderedSet" | "NSMutableOrderedSet" => {
                let items = self.list(obj.get("NS.objects"), depth);
                return json!({"$class": c, "$index": idx, "items": items});
            }
            "NSDictionary" | "NSMutableDictionary" => {
                let keys = self.list(obj.get("NS.keys"), depth);
                let vals = self.list(obj.get("NS.objects"), depth);
                let mut m = Map::new();
                for (k, v) in keys.into_iter().zip(vals) {
                    let key = match k {
                        Json::String(s) => s,
                        other => other.to_string(),
                    };
                    m.insert(key, v);
                }
                return json!({"$class": c, "$index": idx, "entries": m});
            }
            "NSString" | "NSMutableString" => {
                if let Some(s) = obj.get("NS.string") {
                    return self.value(s, depth);
                }
                if let Some(Value::Data(b)) = obj.get("NS.bytes") {
                    return json!(String::from_utf8_lossy(b));
                }
            }
            "NSData" | "NSMutableData" => {
                if let Some(d) = obj.get("NS.data") {
                    return self.value(d, depth);
                }
            }
            "NSDate" => {
                if let Some(Value::Real(t)) = obj.get("NS.time") {
                    return json!({"$date": plist::apple_date_iso(*t)});
                }
            }
            _ => {}
        }
        let mut m = Map::new();
        if let Some(c) = &class {
            m.insert("$class".into(), json!(c));
        }
        m.insert("$index".into(), json!(idx));
        if let Value::Dict(d) = obj {
            for (k, v) in d {
                if k == "$class" {
                    continue;
                }
                let pv = self.value(v, depth);
                m.insert(k.clone(), pv);
            }
        }
        Json::Object(m)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::apple as fx;

    #[test]
    fn projects_a_keyed_archive() {
        let a = parse(&fx::keyed_archive()).unwrap();
        assert_eq!(a.archiver, "NSKeyedArchiver");
        let (name, root) = a.root(None).unwrap();
        assert_eq!(name, "root");
        assert_eq!(a.class_of(root).as_deref(), Some("NoteDocument"));
        let p = a.project(root);
        assert_eq!(p["title"], "Groceries");
        assert_eq!(p["tags"]["items"][0], "food");
        assert_eq!(p["tags"]["items"][1], "weekly");
        // the self reference becomes a $ref, not a loop
        assert_eq!(p["owner"]["$ref"], root);
        let rows = a.rows();
        assert!(rows.iter().any(|r| r.class.as_deref() == Some("NSArray")));
        // XML form too
        let xml = fx::to_xml(&fx::keyed_archive_value());
        let b = parse(xml.as_bytes()).unwrap();
        assert_eq!(b.project(b.root(None).unwrap().1)["title"], "Groceries");
    }

    #[test]
    fn hostile_inputs() {
        let s = fx::keyed_archive();
        for m in craft_anything_testkit::mutations(&s) {
            if let Ok(a) = parse(&m) {
                for (_, r) in a.top.clone() {
                    let _ = a.project(r);
                }
                let _ = a.rows();
            }
        }
    }
}
