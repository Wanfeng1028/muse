//! Property lists: binary (`bplist00`) and XML, parsed into one [`Value`] tree and projected to
//! normalised JSON. Bounded: object counts, nesting depth and total nodes are capped; shared
//! references in binary plists are expanded at most once per path (cycles are refused).

use crate::FormatError;
use crate::bytes::Reader;
use serde_json::{Map, Value as Json, json};

/// Deepest nesting accepted.
pub const MAX_DEPTH: usize = 256;
/// Most nodes produced by one parse (guards against reference blow-up in binary plists).
pub const MAX_NODES: usize = 2_000_000;

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Dict(Vec<(String, Value)>),
    Array(Vec<Value>),
    String(String),
    Integer(i128),
    Real(f64),
    Bool(bool),
    /// Seconds since 2001-01-01T00:00:00Z (binary), or the ISO text (XML).
    Date(DateValue),
    Data(Vec<u8>),
    /// A keyed-archive object reference.
    Uid(u64),
    Null,
}

#[derive(Debug, Clone, PartialEq)]
pub enum DateValue {
    Seconds(f64),
    Text(String),
}

impl Value {
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Dict(d) => d.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::String(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Value]> {
        match self {
            Value::Array(a) => Some(a),
            _ => None,
        }
    }

    pub fn as_uid(&self) -> Option<u64> {
        match self {
            Value::Uid(u) => Some(*u),
            _ => None,
        }
    }

    pub fn as_int(&self) -> Option<i128> {
        match self {
            Value::Integer(i) => Some(*i),
            _ => None,
        }
    }

    /// Normalised JSON: dicts keep key order, data becomes `{"$data": base64}`, dates
    /// `{"$date": iso}`, UIDs `{"$uid": n}`.
    pub fn to_json(&self) -> Json {
        self.to_json_depth(0)
    }

    fn to_json_depth(&self, depth: usize) -> Json {
        if depth > MAX_DEPTH {
            return json!({"$truncated": "too deep"});
        }
        match self {
            Value::Dict(d) => {
                let mut m = Map::new();
                for (k, v) in d {
                    m.insert(k.clone(), v.to_json_depth(depth + 1));
                }
                Json::Object(m)
            }
            Value::Array(a) => Json::Array(a.iter().map(|v| v.to_json_depth(depth + 1)).collect()),
            Value::String(s) => Json::String(s.clone()),
            Value::Integer(i) => int_json(*i),
            Value::Real(f) => serde_json::Number::from_f64(*f).map(Json::Number).unwrap_or_else(|| Json::String(f.to_string())),
            Value::Bool(b) => Json::Bool(*b),
            Value::Date(DateValue::Seconds(s)) => json!({"$date": apple_date_iso(*s)}),
            Value::Date(DateValue::Text(t)) => json!({"$date": t}),
            Value::Data(d) => json!({"$data": base64(d), "length": d.len()}),
            Value::Uid(u) => json!({"$uid": u}),
            Value::Null => Json::Null,
        }
    }
}

pub fn int_json(i: i128) -> Json {
    if let Ok(v) = i64::try_from(i) {
        Json::from(v)
    } else if let Ok(v) = u64::try_from(i) {
        Json::from(v)
    } else {
        Json::String(i.to_string())
    }
}

/// Standard base64 with padding.
pub fn base64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3).saturating_mul(4));
    for chunk in data.chunks(3) {
        let b0 = u32::from(chunk.first().copied().unwrap_or(0));
        let b1 = u32::from(chunk.get(1).copied().unwrap_or(0));
        let b2 = u32::from(chunk.get(2).copied().unwrap_or(0));
        let n = (b0 << 16) | (b1 << 8) | b2;
        let ch = |i: u32| T.get(((n >> i) & 63) as usize).copied().map(char::from).unwrap_or('A');
        out.push(ch(18));
        out.push(ch(12));
        out.push(if chunk.len() > 1 { ch(6) } else { '=' });
        out.push(if chunk.len() > 2 { ch(0) } else { '=' });
    }
    out
}

/// Decode base64, ignoring whitespace; `None` on invalid characters.
pub fn base64_decode(text: &str) -> Option<Vec<u8>> {
    let mut out = Vec::with_capacity(text.len() / 4 * 3);
    let mut acc = 0u32;
    let mut bits = 0u32;
    for c in text.bytes() {
        let v = match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            b'=' => break,
            b' ' | b'\t' | b'\r' | b'\n' => continue,
            _ => return None,
        };
        acc = (acc << 6) | u32::from(v);
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((acc >> bits) as u8);
            acc &= (1 << bits) - 1;
        }
    }
    Some(out)
}

/// An Apple absolute time (seconds since 2001-01-01Z) as ISO-8601 UTC.
pub fn apple_date_iso(secs: f64) -> String {
    if !secs.is_finite() || secs.abs() > 1e13 {
        return format!("{secs}");
    }
    let unix = secs.floor() as i64 + 978_307_200;
    let days = unix.div_euclid(86_400);
    let rem = unix.rem_euclid(86_400);
    // Civil date from days since 1970-01-01.
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z", rem / 3600, rem % 3600 / 60, rem % 60)
}

/// True when the bytes look like a property list of either kind.
pub fn looks_like_plist(data: &[u8]) -> bool {
    data.starts_with(b"bplist00") || data.iter().take(1024).copied().collect::<Vec<u8>>().windows(6).any(|w| w == b"<plist")
}

/// Parse a binary or XML property list.
pub fn parse(data: &[u8]) -> Result<Value, FormatError> {
    if data.starts_with(b"bplist") { parse_binary(data) } else { parse_xml(data) }
}

// ---------------------------------------------------------------------------------------------
// Binary

struct Bin<'a> {
    r: Reader<'a>,
    offsets: Vec<usize>,
    ref_size: usize,
    nodes: usize,
}

/// Parse a `bplist00` binary property list.
pub fn parse_binary(data: &[u8]) -> Result<Value, FormatError> {
    if !data.starts_with(b"bplist") {
        return Err(FormatError::Malformed("not a binary plist".into()));
    }
    let len = data.len();
    if len < 8 + 32 {
        return Err(FormatError::Truncated("binary plist trailer".into()));
    }
    let r = Reader::new(data);
    let t = len - 32;
    let off_size = usize::from(r.u8(t + 6).unwrap_or(0));
    let ref_size = usize::from(r.u8(t + 7).unwrap_or(0));
    let num = r.u64_be(t + 8).unwrap_or(0);
    let top = r.u64_be(t + 16).unwrap_or(0);
    let table = r.u64_be(t + 24).unwrap_or(0);
    if !(1..=8).contains(&off_size) || !(1..=8).contains(&ref_size) {
        return Err(FormatError::Malformed("bad offset or reference size".into()));
    }
    let num = usize::try_from(num).map_err(|_| FormatError::Malformed("object count".into()))?;
    let table = usize::try_from(table).map_err(|_| FormatError::Malformed("offset table".into()))?;
    if num == 0 || num > len {
        return Err(FormatError::Malformed(format!("{num} objects in a {len}-byte file")));
    }
    let need = num.checked_mul(off_size).and_then(|n| n.checked_add(table)).ok_or_else(|| FormatError::Malformed("offset table".into()))?;
    if need > t || table < 8 {
        return Err(FormatError::Truncated("offset table runs past the trailer".into()));
    }
    let mut offsets = Vec::with_capacity(num);
    for i in 0..num {
        let o = read_be(&r, table + i * off_size, off_size).ok_or_else(|| FormatError::Truncated("offset table".into()))?;
        let o = usize::try_from(o).map_err(|_| FormatError::Malformed("object offset".into()))?;
        if o >= table {
            return Err(FormatError::Malformed(format!("object {i} lies outside the object area")));
        }
        offsets.push(o);
    }
    let top = usize::try_from(top).map_err(|_| FormatError::Malformed("top object".into()))?;
    let mut b = Bin { r, offsets, ref_size, nodes: 0 };
    let mut stack = Vec::new();
    b.object(top, &mut stack)
}

fn read_be(r: &Reader<'_>, off: usize, n: usize) -> Option<u64> {
    let s = r.slice(off, n)?;
    Some(s.iter().fold(0u64, |acc, &b| (acc << 8) | u64::from(b)))
}

impl Bin<'_> {
    fn count(&self, at: usize, low: u8) -> Result<(usize, usize), FormatError> {
        if low != 0xf {
            return Ok((usize::from(low), at + 1));
        }
        let m = self.r.u8(at + 1).ok_or_else(|| FormatError::Truncated("length".into()))?;
        if m & 0xf0 != 0x10 {
            return Err(FormatError::Malformed("bad extended length marker".into()));
        }
        let n = 1usize << (m & 0x0f).min(3);
        let v = read_be(&self.r, at + 2, n).ok_or_else(|| FormatError::Truncated("length".into()))?;
        let v = usize::try_from(v).map_err(|_| FormatError::Malformed("length".into()))?;
        Ok((v, at + 2 + n))
    }

    fn reference(&self, at: usize, i: usize) -> Result<usize, FormatError> {
        let off = i.checked_mul(self.ref_size).and_then(|x| x.checked_add(at)).ok_or_else(|| FormatError::Malformed("reference".into()))?;
        let v = read_be(&self.r, off, self.ref_size).ok_or_else(|| FormatError::Truncated("object reference".into()))?;
        usize::try_from(v).map_err(|_| FormatError::Malformed("reference".into()))
    }

    fn object(&mut self, idx: usize, stack: &mut Vec<usize>) -> Result<Value, FormatError> {
        self.nodes += 1;
        if self.nodes > MAX_NODES {
            return Err(FormatError::TooLarge(format!("more than {MAX_NODES} plist nodes")));
        }
        if stack.len() >= MAX_DEPTH {
            return Err(FormatError::Malformed("nesting too deep".into()));
        }
        if stack.contains(&idx) {
            return Err(FormatError::Malformed(format!("object {idx} contains itself")));
        }
        let at = *self.offsets.get(idx).ok_or_else(|| FormatError::Malformed(format!("reference to missing object {idx}")))?;
        let m = self.r.u8(at).ok_or_else(|| FormatError::Truncated("object marker".into()))?;
        let (hi, lo) = (m >> 4, m & 0x0f);
        let v = match hi {
            0x0 => match lo {
                0x0 => Value::Null,
                0x8 => Value::Bool(false),
                0x9 => Value::Bool(true),
                _ => Value::Null,
            },
            0x1 => {
                let n = 1usize << lo.min(4);
                let bytes = self.r.slice(at + 1, n).ok_or_else(|| FormatError::Truncated("integer".into()))?;
                let v = match n {
                    8 => i128::from(i64::from_be_bytes(bytes.try_into().map_err(|_| FormatError::Truncated("integer".into()))?)),
                    16 => i128::from_be_bytes(bytes.try_into().map_err(|_| FormatError::Truncated("integer".into()))?),
                    _ => i128::from(bytes.iter().fold(0u64, |acc, &b| (acc << 8) | u64::from(b))),
                };
                Value::Integer(v)
            }
            0x2 => {
                let v = match lo {
                    2 => self.r.u32_be(at + 1).map(|b| f64::from(f32::from_bits(b))),
                    3 => self.r.u64_be(at + 1).map(f64::from_bits),
                    _ => None,
                };
                Value::Real(v.ok_or_else(|| FormatError::Truncated("real".into()))?)
            }
            0x3 => Value::Date(DateValue::Seconds(self.r.u64_be(at + 1).map(f64::from_bits).ok_or_else(|| FormatError::Truncated("date".into()))?)),
            0x4 => {
                let (n, s) = self.count(at, lo)?;
                Value::Data(self.r.slice(s, n).ok_or_else(|| FormatError::Truncated("data".into()))?.to_vec())
            }
            0x5 => {
                let (n, s) = self.count(at, lo)?;
                Value::String(String::from_utf8_lossy(self.r.slice(s, n).ok_or_else(|| FormatError::Truncated("string".into()))?).into_owned())
            }
            0x6 => {
                let (n, s) = self.count(at, lo)?;
                let bytes = self
                    .r
                    .slice(s, n.checked_mul(2).ok_or_else(|| FormatError::Malformed("string".into()))?)
                    .ok_or_else(|| FormatError::Truncated("string".into()))?;
                let units: Vec<u16> = bytes.as_chunks::<2>().0.iter().map(|c| u16::from_be_bytes(*c)).collect();
                Value::String(String::from_utf16_lossy(&units))
            }
            0x8 => {
                let n = usize::from(lo) + 1;
                Value::Uid(read_be(&self.r, at + 1, n).ok_or_else(|| FormatError::Truncated("uid".into()))?)
            }
            0xa | 0xc => {
                let (n, s) = self.count(at, lo)?;
                if n > self.offsets.len().saturating_mul(4).max(16) || s.saturating_add(n.saturating_mul(self.ref_size)) > self.r.len() {
                    return Err(FormatError::Malformed("array larger than the file".into()));
                }
                stack.push(idx);
                let mut out = Vec::with_capacity(n);
                for i in 0..n {
                    let child = self.reference(s, i)?;
                    out.push(self.object(child, stack)?);
                }
                stack.pop();
                Value::Array(out)
            }
            0xd => {
                let (n, s) = self.count(at, lo)?;
                if s.saturating_add(n.saturating_mul(self.ref_size).saturating_mul(2)) > self.r.len() {
                    return Err(FormatError::Malformed("dictionary larger than the file".into()));
                }
                stack.push(idx);
                let mut out = Vec::with_capacity(n);
                for i in 0..n {
                    let k = self.reference(s, i)?;
                    let v = self.reference(s, i + n)?;
                    let key = match self.object(k, stack)? {
                        Value::String(s) => s,
                        other => format!("{:?}", other.to_json()),
                    };
                    out.push((key, self.object(v, stack)?));
                }
                stack.pop();
                Value::Dict(out)
            }
            _ => return Err(FormatError::Malformed(format!("unknown object marker {m:#04x}"))),
        };
        Ok(v)
    }
}

// ---------------------------------------------------------------------------------------------
// XML

#[derive(Debug, Clone, PartialEq)]
enum Tok {
    Open(String),
    Close(String),
    Empty(String),
    Text(String),
}

fn decode_entities(s: &str) -> String {
    if !s.contains('&') {
        return s.to_string();
    }
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(p) = rest.find('&') {
        out.push_str(rest.get(..p).unwrap_or(""));
        let after = rest.get(p..).unwrap_or("");
        let Some(end) = after.find(';').filter(|&e| e <= 12) else {
            out.push('&');
            rest = after.get(1..).unwrap_or("");
            continue;
        };
        let ent = after.get(1..end).unwrap_or("");
        let rep = match ent {
            "lt" => Some('<'),
            "gt" => Some('>'),
            "amp" => Some('&'),
            "quot" => Some('"'),
            "apos" => Some('\''),
            e if e.starts_with("#x") || e.starts_with("#X") => u32::from_str_radix(e.get(2..).unwrap_or(""), 16).ok().and_then(char::from_u32),
            e if e.starts_with('#') => e.get(1..).and_then(|d| d.parse::<u32>().ok()).and_then(char::from_u32),
            _ => None,
        };
        match rep {
            Some(c) => {
                out.push(c);
                rest = after.get(end + 1..).unwrap_or("");
            }
            None => {
                out.push('&');
                rest = after.get(1..).unwrap_or("");
            }
        }
    }
    out.push_str(rest);
    out
}

fn tokenize(text: &str) -> Result<Vec<Tok>, FormatError> {
    let mut toks = Vec::new();
    let mut rest = text;
    while !rest.is_empty() {
        if toks.len() > MAX_NODES {
            return Err(FormatError::TooLarge("too many XML tokens".into()));
        }
        match rest.find('<') {
            None => {
                if !rest.trim().is_empty() {
                    toks.push(Tok::Text(decode_entities(rest)));
                }
                break;
            }
            Some(p) => {
                let t = rest.get(..p).unwrap_or("");
                if !t.is_empty() {
                    toks.push(Tok::Text(decode_entities(t)));
                }
                rest = rest.get(p..).unwrap_or("");
            }
        }
        if let Some(r) = rest.strip_prefix("<!--") {
            let e = r.find("-->").ok_or_else(|| FormatError::Truncated("comment".into()))?;
            rest = r.get(e + 3..).unwrap_or("");
            continue;
        }
        if let Some(r) = rest.strip_prefix("<![CDATA[") {
            let e = r.find("]]>").ok_or_else(|| FormatError::Truncated("CDATA".into()))?;
            toks.push(Tok::Text(r.get(..e).unwrap_or("").to_string()));
            rest = r.get(e + 3..).unwrap_or("");
            continue;
        }
        if rest.starts_with("<?") || rest.starts_with("<!") {
            let e = rest.find('>').ok_or_else(|| FormatError::Truncated("declaration".into()))?;
            rest = rest.get(e + 1..).unwrap_or("");
            continue;
        }
        let e = rest.find('>').ok_or_else(|| FormatError::Truncated("tag".into()))?;
        let inner = rest.get(1..e).unwrap_or("").trim();
        rest = rest.get(e + 1..).unwrap_or("");
        if let Some(name) = inner.strip_prefix('/') {
            toks.push(Tok::Close(name.trim().to_string()));
        } else if let Some(body) = inner.strip_suffix('/') {
            toks.push(Tok::Empty(body.split_whitespace().next().unwrap_or("").to_string()));
        } else {
            toks.push(Tok::Open(inner.split_whitespace().next().unwrap_or("").to_string()));
        }
    }
    Ok(toks)
}

struct Xml {
    toks: Vec<Tok>,
    pos: usize,
    nodes: usize,
}

impl Xml {
    fn next(&mut self) -> Option<Tok> {
        let t = self.toks.get(self.pos).cloned();
        self.pos += 1;
        t
    }

    fn peek(&self) -> Option<&Tok> {
        self.toks.get(self.pos)
    }

    /// Text up to the closing tag `name`.
    fn text_until(&mut self, name: &str) -> Result<String, FormatError> {
        let mut s = String::new();
        loop {
            match self.next() {
                Some(Tok::Text(t)) => s.push_str(&t),
                Some(Tok::Close(n)) if n == name => return Ok(s),
                Some(other) => return Err(FormatError::Malformed(format!("unexpected {other:?} inside <{name}>"))),
                None => return Err(FormatError::Truncated(format!("<{name}> is not closed"))),
            }
        }
    }

    fn skip_text(&mut self) {
        while matches!(self.peek(), Some(Tok::Text(_))) {
            self.pos += 1;
        }
    }

    fn value(&mut self, depth: usize) -> Result<Value, FormatError> {
        self.nodes += 1;
        if depth > MAX_DEPTH || self.nodes > MAX_NODES {
            return Err(FormatError::TooLarge("plist nesting or size limit".into()));
        }
        self.skip_text();
        match self.next() {
            Some(Tok::Empty(n)) => Ok(match n.as_str() {
                "true" => Value::Bool(true),
                "false" => Value::Bool(false),
                "dict" => Value::Dict(Vec::new()),
                "array" => Value::Array(Vec::new()),
                "string" | "key" => Value::String(String::new()),
                "data" => Value::Data(Vec::new()),
                other => return Err(FormatError::Malformed(format!("unexpected <{other}/>"))),
            }),
            Some(Tok::Open(n)) => match n.as_str() {
                "string" => Ok(Value::String(self.text_until("string")?)),
                "integer" => {
                    let t = self.text_until("integer")?;
                    let t = t.trim();
                    let v = if let Some(h) = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")) {
                        i128::from_str_radix(h, 16).ok()
                    } else {
                        t.parse::<i128>().ok()
                    };
                    v.map(Value::Integer).ok_or_else(|| FormatError::Malformed(format!("bad integer {t:?}")))
                }
                "real" => {
                    let t = self.text_until("real")?;
                    t.trim().parse::<f64>().map(Value::Real).map_err(|_| FormatError::Malformed(format!("bad real {t:?}")))
                }
                "date" => Ok(Value::Date(DateValue::Text(self.text_until("date")?.trim().to_string()))),
                "data" => {
                    let t = self.text_until("data")?;
                    base64_decode(&t).map(Value::Data).ok_or_else(|| FormatError::Malformed("bad base64 in <data>".into()))
                }
                "true" => {
                    self.text_until("true")?;
                    Ok(Value::Bool(true))
                }
                "false" => {
                    self.text_until("false")?;
                    Ok(Value::Bool(false))
                }
                "array" => {
                    let mut out = Vec::new();
                    loop {
                        self.skip_text();
                        if matches!(self.peek(), Some(Tok::Close(c)) if c == "array") {
                            self.pos += 1;
                            return Ok(Value::Array(out));
                        }
                        if self.peek().is_none() {
                            return Err(FormatError::Truncated("<array> is not closed".into()));
                        }
                        out.push(self.value(depth + 1)?);
                    }
                }
                "dict" => {
                    let mut out = Vec::new();
                    loop {
                        self.skip_text();
                        match self.next() {
                            Some(Tok::Close(c)) if c == "dict" => return Ok(Value::Dict(out)),
                            Some(Tok::Open(k)) if k == "key" => {
                                let key = self.text_until("key")?;
                                let v = self.value(depth + 1)?;
                                out.push((key, v));
                            }
                            Some(Tok::Empty(k)) if k == "key" => {
                                let v = self.value(depth + 1)?;
                                out.push((String::new(), v));
                            }
                            Some(other) => return Err(FormatError::Malformed(format!("expected <key> in <dict>, found {other:?}"))),
                            None => return Err(FormatError::Truncated("<dict> is not closed".into())),
                        }
                    }
                }
                other => Err(FormatError::Malformed(format!("unknown plist element <{other}>"))),
            },
            Some(other) => Err(FormatError::Malformed(format!("expected a value, found {other:?}"))),
            None => Err(FormatError::Truncated("expected a value".into())),
        }
    }
}

/// Decode a UTF-16 XML property list after its byte-order mark into UTF-8 text.
/// Surrogate pairs join normally; a lone surrogate fails as malformed rather
/// than turning into replacement characters that tokenize into garbage element
/// names.
fn decode_utf16_xml(data: &[u8], big_endian: bool) -> Result<String, FormatError> {
    let r = Reader::new(data);
    let mut units = Vec::with_capacity(data.len() / 2);
    let mut off = 0;
    while let Some(unit) = if big_endian { r.u16_be(off) } else { r.u16_le(off) } {
        units.push(unit);
        off += 2;
    }
    String::from_utf16(&units).map_err(|_| FormatError::Malformed("invalid UTF-16 in XML plist".into()))
}

/// Parse an XML property list.
pub fn parse_xml(data: &[u8]) -> Result<Value, FormatError> {
    // Apple's Core Foundation reader accepts XML plists in UTF-16 as well as
    // UTF-8: it recognises both byte-order marks. `from_utf8_lossy` turns a
    // UTF-16 byte stream into NUL-separated text, so the encoding is settled
    // here, before tokenizing.
    let text = match data {
        [0xFF, 0xFE, rest @ ..] => decode_utf16_xml(rest, false)?,
        [0xFE, 0xFF, rest @ ..] => decode_utf16_xml(rest, true)?,
        _ => String::from_utf8_lossy(data).into_owned(),
    };
    let toks = tokenize(&text)?;
    let mut x = Xml { toks, pos: 0, nodes: 0 };
    x.skip_text();
    match x.peek() {
        Some(Tok::Open(n)) if n == "plist" => {
            x.pos += 1;
            let v = x.value(0)?;
            Ok(v)
        }
        Some(Tok::Open(_)) | Some(Tok::Empty(_)) => x.value(0),
        _ => Err(FormatError::Malformed("no <plist> element".into())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::apple as fx;

    #[test]
    fn xml_and_binary_agree() {
        let sample = fx::sample_plist();
        let x = parse(fx::to_xml(&sample).as_bytes()).unwrap();
        let b = parse(&fx::to_bplist(&sample)).unwrap();
        assert_eq!(x.get("CFBundleIdentifier").and_then(Value::as_str), Some("com.example.notes"));
        assert_eq!(b.get("CFBundleIdentifier").and_then(Value::as_str), Some("com.example.notes"));
        assert_eq!(b.get("Count").and_then(Value::as_int), Some(-42));
        assert_eq!(x.get("Count").and_then(Value::as_int), Some(-42));
        let j = b.to_json();
        assert_eq!(j["Nested"]["List"][1], "two & <three>");
        assert_eq!(x.to_json()["Nested"]["List"][1], "two & <three>");
        assert_eq!(j["Blob"]["$data"], "AAEC");
        assert_eq!(x.to_json()["Blob"]["$data"], "AAEC");
        assert_eq!(j["Flag"], true);
        assert_eq!(j["Pi"], 3.5);
        assert_eq!(j["When"]["$date"], "2001-01-02T00:00:00Z");
    }

    #[test]
    fn base64_round_trip() {
        for n in 0..20 {
            let d: Vec<u8> = (0..n).map(|i| (i * 37) as u8).collect();
            assert_eq!(base64_decode(&base64(&d)).unwrap(), d);
        }
        assert_eq!(apple_date_iso(0.0), "2001-01-01T00:00:00Z");
    }

    #[test]
    fn hostile_inputs() {
        let sample = fx::sample_plist();
        let b = fx::to_bplist(&sample);
        let x = fx::to_xml(&sample).into_bytes();
        for m in craft_anything_testkit::mutations(&b).into_iter().chain(craft_anything_testkit::mutations(&x)) {
            let _ = parse(&m);
        }
        for i in 0..b.len() {
            let _ = parse(&b[..i]);
        }
        for seed in 0..200 {
            let mut n = b"bplist00".to_vec();
            n.extend(craft_anything_testkit::noise(seed, 64));
            let _ = parse(&n);
        }
        // A self-referencing array must be refused, not loop.
        let mut cyc = b"bplist00".to_vec();
        cyc.extend_from_slice(&[0xa1, 0x00]); // array of one ref -> object 0
        let table = cyc.len();
        cyc.push(8);
        let mut trailer = vec![0u8; 6];
        trailer.extend_from_slice(&[1, 1]);
        trailer.extend_from_slice(&1u64.to_be_bytes());
        trailer.extend_from_slice(&0u64.to_be_bytes());
        trailer.extend_from_slice(&(table as u64).to_be_bytes());
        cyc.extend(trailer);
        assert!(parse(&cyc).is_err());
        let deep = "<plist>".to_string() + &"<array>".repeat(1000) + &"</array>".repeat(1000) + "</plist>";
        assert!(parse(deep.as_bytes()).is_err());
    }

    #[test]
    fn xml_plist_utf16_byte_orders_parse() {
        // Apple's Core Foundation reader accepts UTF-16 XML plists with either
        // byte-order mark; the reader used to lossy-decode them as UTF-8 and
        // reject the NUL-separated text (issue #333).
        let xml = "<?xml version=\"1.0\" encoding=\"UTF-16\"?><!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\"><plist version=\"1.0\"><dict><key>Message</key><string>hello</string></dict></plist>";
        let units: Vec<u16> = xml.encode_utf16().collect();
        let mut le = vec![0xFF, 0xFE];
        le.extend(units.iter().copied().flat_map(u16::to_le_bytes));
        let mut be = vec![0xFE, 0xFF];
        be.extend(units.iter().copied().flat_map(u16::to_be_bytes));
        for data in [&le[..], &be[..]] {
            let v = parse(data).unwrap_or_else(|e| panic!("UTF-16 XML plist should parse: {e}"));
            assert_eq!(v.get("Message").and_then(Value::as_str), Some("hello"));
        }
    }
}
