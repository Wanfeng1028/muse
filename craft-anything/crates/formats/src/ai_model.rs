//! AI model files: GGUF (versions 2 and 3) and safetensors. Only the header is read: metadata,
//! tensor names, shapes and types. Tensor data is never touched, so a caller may pass just the
//! start of a big file together with the file's real size.

use crate::FormatError;
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// Most metadata entries kept.
const MAX_METADATA: usize = 65_536;
/// Most tensors listed (all of them count toward the totals).
const MAX_TENSORS: usize = 200_000;
/// Longest text value kept, in characters.
const MAX_TEXT: usize = 1024;
/// Array elements shown as a sample.
const ARRAY_SAMPLE: usize = 8;
/// Deepest nesting of arrays inside arrays.
const MAX_ARRAY_DEPTH: u32 = 3;
/// Most dimensions a tensor may have.
const MAX_DIMS: u32 = 16;
/// Most warnings kept.
const MAX_WARNINGS: usize = 32;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelFormat {
    Gguf,
    Safetensors,
}

/// One tensor's description. Its data isn't read.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ModelTensor {
    pub name: String,
    pub dtype: String,
    pub shape: Vec<u64>,
    /// Elements in the tensor (saturates at the largest number we can hold).
    pub parameters: u64,
    /// Where its data starts, relative to the start of the data section.
    pub data_offset: u64,
    /// Size of its data, when the type has a fixed element size.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data_bytes: Option<u64>,
}

/// One metadata key and a bounded view of its value.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ModelMetadata {
    pub key: String,
    pub value_type: String,
    pub value: Value,
    /// Elements in an array value.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub count: Option<u64>,
    /// The value shown is only part of what the file holds.
    pub shortened: bool,
}

/// What a model file's header says.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ModelReport {
    pub format: ModelFormat,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<u32>,
    pub file_size: u64,
    /// Bytes from the start of the file to the end of the part we read as header.
    pub header_bytes: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub architecture: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    /// The tensor type most parameters use, when it is a quantized one.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub quantization: Option<String>,
    /// What the file's own `general.file_type` says.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file_type: Option<String>,
    /// Parameters across every tensor read (saturates).
    pub parameters: u64,
    /// Parameters per tensor type.
    pub parameters_by_type: BTreeMap<String, u64>,
    /// What the header claims; can be far more than exists in a hostile file.
    pub declared_tensors: u64,
    pub declared_metadata: u64,
    pub tensors_read: u64,
    pub metadata_read: u64,
    pub tensors: Vec<ModelTensor>,
    pub metadata: Vec<ModelMetadata>,
    /// The whole header was read and walked to its end.
    pub complete: bool,
    /// Tensors whose data would lie past the end of the file.
    pub tensors_past_end: u64,
    pub warnings: Vec<String>,
}

impl ModelReport {
    fn new(format: ModelFormat, file_size: u64) -> Self {
        ModelReport {
            format,
            version: None,
            file_size,
            header_bytes: 0,
            architecture: None,
            name: None,
            quantization: None,
            file_type: None,
            parameters: 0,
            parameters_by_type: BTreeMap::new(),
            declared_tensors: 0,
            declared_metadata: 0,
            tensors_read: 0,
            metadata_read: 0,
            tensors: Vec::new(),
            metadata: Vec::new(),
            complete: false,
            tensors_past_end: 0,
            warnings: Vec::new(),
        }
    }

    fn warn(&mut self, w: String) {
        if self.warnings.len() < MAX_WARNINGS {
            self.warnings.push(w);
        }
    }

    fn add_tensor(&mut self, t: ModelTensor) {
        self.tensors_read = self.tensors_read.saturating_add(1);
        self.parameters = self.parameters.saturating_add(t.parameters);
        let slot = self.parameters_by_type.entry(t.dtype.clone()).or_insert(0);
        *slot = slot.saturating_add(t.parameters);
        if self.tensors.len() < MAX_TENSORS {
            self.tensors.push(t);
        }
    }
}

/// Whether these bytes start like a model file we read.
pub fn looks_like_model(prefix: &[u8]) -> bool {
    prefix.starts_with(b"GGUF") || safetensors_header_len(prefix).is_some()
}

fn safetensors_header_len(prefix: &[u8]) -> Option<u64> {
    let len = u64::from_le_bytes(prefix.get(..8)?.try_into().ok()?);
    (prefix.get(8) == Some(&b'{') && len >= 2).then_some(len)
}

/// Read a model header from the start of a file. `prefix` may be shorter than `file_size`.
pub fn parse(prefix: &[u8], file_size: u64) -> Result<ModelReport, FormatError> {
    if prefix.starts_with(b"GGUF") {
        return parse_gguf(prefix, file_size);
    }
    if safetensors_header_len(prefix).is_some() {
        return parse_safetensors(prefix, file_size);
    }
    if prefix.len() < 9 {
        return Err(FormatError::Truncated("model header".into()));
    }
    Err(FormatError::Unsupported("not a GGUF or safetensors file".into()))
}

/// A count in plain words: "7.2 billion".
pub fn plain_count(n: u64) -> String {
    let f = n as f64;
    if n >= 1_000_000_000_000 {
        format!("{:.1} trillion", f / 1e12)
    } else if n >= 1_000_000_000 {
        format!("{:.1} billion", f / 1e9)
    } else if n >= 1_000_000 {
        format!("{:.1} million", f / 1e6)
    } else if n >= 1_000 {
        format!("{:.1} thousand", f / 1e3)
    } else {
        n.to_string()
    }
}

fn shorten(s: String) -> (String, bool) {
    if s.chars().count() <= MAX_TEXT {
        return (s, false);
    }
    (s.chars().take(MAX_TEXT).collect(), true)
}

fn element_count(shape: &[u64]) -> (u64, bool) {
    let mut n: u64 = 1;
    for d in shape {
        match n.checked_mul(*d) {
            Some(v) => n = v,
            None => return (u64::MAX, true),
        }
    }
    (n, false)
}

// ---------------------------------------------------------------------------------------------
// GGUF

struct Cursor<'a> {
    d: &'a [u8],
    o: usize,
    le: bool,
}

impl<'a> Cursor<'a> {
    fn take(&mut self, n: usize) -> Option<&'a [u8]> {
        let end = self.o.checked_add(n)?;
        let s = self.d.get(self.o..end)?;
        self.o = end;
        Some(s)
    }
    fn u8(&mut self) -> Option<u8> {
        self.take(1)?.first().copied()
    }
    fn u16(&mut self) -> Option<u16> {
        let b: [u8; 2] = self.take(2)?.try_into().ok()?;
        Some(if self.le { u16::from_le_bytes(b) } else { u16::from_be_bytes(b) })
    }
    fn u32(&mut self) -> Option<u32> {
        let b: [u8; 4] = self.take(4)?.try_into().ok()?;
        Some(if self.le { u32::from_le_bytes(b) } else { u32::from_be_bytes(b) })
    }
    fn u64(&mut self) -> Option<u64> {
        let b: [u8; 8] = self.take(8)?.try_into().ok()?;
        Some(if self.le { u64::from_le_bytes(b) } else { u64::from_be_bytes(b) })
    }
    fn raw_str(&mut self) -> Option<&'a [u8]> {
        let n = usize::try_from(self.u64()?).ok()?;
        self.take(n)
    }
    fn string(&mut self) -> Option<String> {
        self.raw_str().map(|b| String::from_utf8_lossy(b).into_owned())
    }
    /// Skip a bounded string without building it, keeping only its first characters.
    fn short_string(&mut self) -> Option<(String, bool)> {
        let b = self.raw_str()?;
        // Four bytes per character at most; enough to fill MAX_TEXT.
        let cut = b.get(..b.len().min(MAX_TEXT * 4)).unwrap_or(b);
        let (s, short) = shorten(String::from_utf8_lossy(cut).into_owned());
        Some((s, short || cut.len() < b.len()))
    }
}

fn gguf_type_name(t: u32) -> &'static str {
    match t {
        0 => "u8",
        1 => "i8",
        2 => "u16",
        3 => "i16",
        4 => "u32",
        5 => "i32",
        6 => "f32",
        7 => "bool",
        8 => "string",
        9 => "array",
        10 => "u64",
        11 => "i64",
        12 => "f64",
        _ => "unknown",
    }
}

fn fixed_size(t: u32) -> Option<usize> {
    match t {
        0 | 1 | 7 => Some(1),
        2 | 3 => Some(2),
        4..=6 => Some(4),
        10..=12 => Some(8),
        _ => None,
    }
}

/// Read one scalar value of a fixed-size type or a string.
fn gguf_scalar(c: &mut Cursor<'_>, t: u32) -> Option<(Value, bool)> {
    Some(match t {
        0 => (json!(c.u8()?), false),
        1 => (json!(c.u8()? as i8), false),
        2 => (json!(c.u16()?), false),
        3 => (json!(c.u16()? as i16), false),
        4 => (json!(c.u32()?), false),
        5 => (json!(c.u32()? as i32), false),
        6 => (json!(f64::from(f32::from_bits(c.u32()?))), false),
        7 => (json!(c.u8()? != 0), false),
        8 => {
            let (s, short) = c.short_string()?;
            (json!(s), short)
        }
        10 => (json!(c.u64()?), false),
        11 => (json!(c.u64()? as i64), false),
        12 => (json!(f64::from_bits(c.u64()?)), false),
        _ => return None,
    })
}

/// Read a value: `(json, type name, element count, shortened)`.
fn gguf_value(c: &mut Cursor<'_>, t: u32, depth: u32) -> Option<(Value, String, Option<u64>, bool)> {
    if t != 9 {
        let (v, short) = gguf_scalar(c, t)?;
        return Some((v, gguf_type_name(t).to_string(), None, short));
    }
    if depth >= MAX_ARRAY_DEPTH {
        return None;
    }
    let elem = c.u32()?;
    let count = c.u64()?;
    let mut sample = Vec::new();
    let mut short = false;
    if let Some(size) = fixed_size(elem) {
        // Fixed-size elements: read the sample, then jump over the rest at once.
        let shown = count.min(ARRAY_SAMPLE as u64);
        for _ in 0..shown {
            sample.push(gguf_scalar(c, elem)?.0);
        }
        let rest = usize::try_from(count - shown).ok()?.checked_mul(size)?;
        c.take(rest)?;
    } else {
        // Strings and arrays consume at least eight bytes each, so the input bounds this loop.
        let mut i = 0u64;
        while i < count {
            let (v, _, _, s) = gguf_value(c, elem, depth + 1)?;
            short |= s;
            if sample.len() < ARRAY_SAMPLE {
                sample.push(v);
            }
            i += 1;
        }
    }
    short |= count > sample.len() as u64;
    Some((Value::Array(sample), format!("array<{}>", gguf_type_name(elem)), Some(count), short))
}

fn ggml_type_name(t: u32) -> String {
    let known = match t {
        0 => "F32",
        1 => "F16",
        2 => "Q4_0",
        3 => "Q4_1",
        6 => "Q5_0",
        7 => "Q5_1",
        8 => "Q8_0",
        9 => "Q8_1",
        10 => "Q2_K",
        11 => "Q3_K",
        12 => "Q4_K",
        13 => "Q5_K",
        14 => "Q6_K",
        15 => "Q8_K",
        16 => "IQ2_XXS",
        17 => "IQ2_XS",
        18 => "IQ3_XXS",
        19 => "IQ1_S",
        20 => "IQ4_NL",
        21 => "IQ3_S",
        22 => "IQ2_S",
        23 => "IQ4_XS",
        24 => "I8",
        25 => "I16",
        26 => "I32",
        27 => "I64",
        28 => "F64",
        29 => "IQ1_M",
        30 => "BF16",
        _ => return format!("type {t}"),
    };
    known.to_string()
}

/// Bytes per element of the types stored one element at a time.
fn ggml_element_bytes(t: u32) -> Option<u64> {
    match t {
        0 | 26 => Some(4),
        1 | 25 | 30 => Some(2),
        24 => Some(1),
        27 | 28 => Some(8),
        _ => None,
    }
}

fn is_plain_numeric(name: &str) -> bool {
    matches!(name, "F32" | "F16" | "F64" | "BF16" | "I8" | "I16" | "I32" | "I64" | "U8" | "U16" | "U32" | "U64" | "BOOL")
}

/// `general.file_type`, for the values whose meaning has stayed fixed.
fn gguf_file_type(n: u64) -> Option<&'static str> {
    Some(match n {
        0 => "all F32",
        1 => "mostly F16",
        2 => "mostly Q4_0",
        3 => "mostly Q4_1",
        7 => "mostly Q8_0",
        8 => "mostly Q5_0",
        9 => "mostly Q5_1",
        10 => "mostly Q2_K",
        11 => "mostly Q3_K small",
        12 => "mostly Q3_K medium",
        13 => "mostly Q3_K large",
        14 => "mostly Q4_K small",
        15 => "mostly Q4_K medium",
        16 => "mostly Q5_K small",
        17 => "mostly Q5_K medium",
        18 => "mostly Q6_K",
        _ => return None,
    })
}

fn dominant_quantization(by_type: &BTreeMap<String, u64>) -> Option<String> {
    by_type.iter().filter(|(_, n)| **n > 0).max_by_key(|(_, n)| **n).filter(|(t, _)| !is_plain_numeric(t)).map(|(t, _)| t.clone())
}

fn parse_gguf(prefix: &[u8], file_size: u64) -> Result<ModelReport, FormatError> {
    let header = prefix.get(..24).ok_or_else(|| FormatError::Truncated("GGUF header".into()))?;
    let v = header.get(4..8).and_then(|b| <[u8; 4]>::try_from(b).ok()).ok_or_else(|| FormatError::Truncated("GGUF header".into()))?;
    let (le, version) = {
        let little = u32::from_le_bytes(v);
        let big = u32::from_be_bytes(v);
        if little <= 0xffff { (true, little) } else { (false, big) }
    };
    if !matches!(version, 2 | 3) {
        return Err(FormatError::Unsupported(format!("GGUF version {version}; versions 2 and 3 are read")));
    }
    let mut c = Cursor { d: prefix, o: 8, le };
    let (Some(tensor_count), Some(kv_count)) = (c.u64(), c.u64()) else {
        return Err(FormatError::Truncated("GGUF header".into()));
    };
    let mut r = ModelReport::new(ModelFormat::Gguf, file_size);
    r.version = Some(version);
    r.declared_tensors = tensor_count;
    r.declared_metadata = kv_count;

    let mut alignment = 32u64;
    let mut file_type = None;
    let mut ended_early = false;
    let mut i = 0u64;
    while i < kv_count {
        let parsed = (|| {
            let key = c.string()?;
            let t = c.u32()?;
            let (value, value_type, count, shortened) = gguf_value(&mut c, t, 0)?;
            Some(ModelMetadata { key, value_type, value, count, shortened })
        })();
        let Some(entry) = parsed else {
            ended_early = true;
            break;
        };
        r.metadata_read = r.metadata_read.saturating_add(1);
        match entry.key.as_str() {
            "general.architecture" => r.architecture = entry.value.as_str().map(str::to_string),
            "general.name" => r.name = entry.value.as_str().map(str::to_string),
            "general.alignment" => match entry.value.as_u64() {
                Some(a) if a.is_power_of_two() => alignment = a,
                _ => r.warn("general.alignment isn't a power of two; assuming 32".into()),
            },
            "general.file_type" => file_type = entry.value.as_u64(),
            _ => {}
        }
        if r.metadata.len() < MAX_METADATA {
            r.metadata.push(entry);
        }
        i += 1;
    }

    let mut last_data_end = 0u64;
    if !ended_early {
        let mut i = 0u64;
        while i < tensor_count {
            let parsed = (|| {
                let name = c.string()?;
                let dims = c.u32()?;
                if dims > MAX_DIMS {
                    return None;
                }
                let mut shape = Vec::new();
                for _ in 0..dims {
                    shape.push(c.u64()?);
                }
                let ty = c.u32()?;
                let offset = c.u64()?;
                Some((name, shape, ty, offset))
            })();
            let Some((name, shape, ty, data_offset)) = parsed else {
                ended_early = true;
                break;
            };
            let (parameters, overflow) = element_count(&shape);
            if overflow {
                r.warn(format!("{name}: its shape multiplies past what a number can hold"));
            }
            let data_bytes = ggml_element_bytes(ty).and_then(|b| parameters.checked_mul(b));
            last_data_end = last_data_end.max(data_offset.saturating_add(data_bytes.unwrap_or(0)));
            let (name, _) = shorten(name);
            r.add_tensor(ModelTensor { name, dtype: ggml_type_name(ty), shape, parameters, data_offset, data_bytes });
            i += 1;
        }
    }

    r.header_bytes = c.o as u64;
    r.complete = !ended_early;
    if ended_early {
        if (prefix.len() as u64) < file_size {
            r.warn(format!("Only the first {} bytes were read and the header goes on past them.", prefix.len()));
        } else {
            r.warn("The header stops before everything it declares: the file is cut short or damaged.".into());
        }
    } else {
        // Tensor data starts at the next alignment boundary.
        let start = (c.o as u64).checked_next_multiple_of(alignment);
        match start {
            Some(start) => {
                r.tensors_past_end = r
                    .tensors
                    .iter()
                    .filter(|t| t.parameters > 0 && start.saturating_add(t.data_offset).saturating_add(t.data_bytes.unwrap_or(0)) > file_size)
                    .count() as u64;
                if start.saturating_add(last_data_end) > file_size {
                    r.warn("The tensor table describes more data than the file holds: it is cut short, or the table is false.".into());
                }
            }
            None => r.warn("The tensor data's start can't be worked out.".into()),
        }
    }
    r.file_type = file_type.map(|n| gguf_file_type(n).map_or_else(|| format!("type {n}"), str::to_string));
    r.quantization = dominant_quantization(&r.parameters_by_type);
    Ok(r)
}

// ---------------------------------------------------------------------------------------------
// safetensors

fn safetensors_element_bytes(dtype: &str) -> Option<u64> {
    match dtype {
        "BOOL" | "U8" | "I8" => Some(1),
        "U16" | "I16" | "F16" | "BF16" => Some(2),
        "U32" | "I32" | "F32" => Some(4),
        "U64" | "I64" | "F64" | "C64" => Some(8),
        _ => None,
    }
}

fn parse_safetensors(prefix: &[u8], file_size: u64) -> Result<ModelReport, FormatError> {
    let declared = safetensors_header_len(prefix).ok_or_else(|| FormatError::Malformed("not a safetensors header".into()))?;
    let end = declared.checked_add(8).ok_or_else(|| FormatError::Malformed("the header length overflows".into()))?;
    if end > file_size {
        return Err(FormatError::Malformed(format!("the header claims {declared} bytes, more than the file holds")));
    }
    if end > prefix.len() as u64 {
        return Err(FormatError::TooLarge(format!("the header is {declared} bytes and only {} were read", prefix.len())));
    }
    let body = usize::try_from(end).ok().and_then(|e| prefix.get(8..e)).ok_or_else(|| FormatError::Truncated("safetensors header".into()))?;
    let json: Value = serde_json::from_slice(body).map_err(|e| FormatError::Malformed(format!("the header isn't JSON: {e}")))?;
    let obj = json.as_object().ok_or_else(|| FormatError::Malformed("the header isn't a JSON object".into()))?;

    let mut r = ModelReport::new(ModelFormat::Safetensors, file_size);
    r.header_bytes = end;
    r.declared_tensors = obj.keys().filter(|k| k.as_str() != "__metadata__").count() as u64;
    let data_room = file_size - end;
    let mut bad = 0u64;
    for (key, v) in obj {
        if key == "__metadata__" {
            let Some(m) = v.as_object() else {
                r.warn("__metadata__ isn't an object".into());
                continue;
            };
            r.declared_metadata = m.len() as u64;
            for (mk, mv) in m {
                r.metadata_read = r.metadata_read.saturating_add(1);
                if r.metadata.len() >= MAX_METADATA {
                    continue;
                }
                let text = mv.as_str().map_or_else(|| mv.to_string(), str::to_string);
                match mk.as_str() {
                    "architecture" | "modelspec.architecture" if r.architecture.is_none() => r.architecture = Some(text.clone()),
                    "name" | "modelspec.title" if r.name.is_none() => r.name = Some(text.clone()),
                    _ => {}
                }
                let (shown, shortened) = shorten(text);
                r.metadata.push(ModelMetadata { key: mk.clone(), value_type: "string".into(), value: json!(shown), count: None, shortened });
            }
            continue;
        }
        let dtype = v.get("dtype").and_then(Value::as_str);
        let shape: Option<Vec<u64>> = v.get("shape").and_then(Value::as_array).and_then(|a| a.iter().map(Value::as_u64).collect());
        let offsets: Option<Vec<u64>> = v.get("data_offsets").and_then(Value::as_array).and_then(|a| a.iter().map(Value::as_u64).collect());
        let (Some(dtype), Some(shape), Some([from, to])) = (dtype, shape, offsets.as_deref().and_then(|o| <[u64; 2]>::try_from(o).ok())) else {
            bad = bad.saturating_add(1);
            r.warn(format!("{key}: not a tensor entry (it needs dtype, shape and data_offsets)"));
            continue;
        };
        let (parameters, overflow) = element_count(&shape);
        if overflow {
            r.warn(format!("{key}: its shape multiplies past what a number can hold"));
        }
        let data_bytes = to.checked_sub(from);
        match data_bytes {
            None => r.warn(format!("{key}: its data ends before it starts")),
            Some(n) => {
                if let Some(size) = safetensors_element_bytes(dtype)
                    && parameters.checked_mul(size) != Some(n)
                {
                    r.warn(format!("{key}: its shape and type don't fit the {n} bytes it says it holds"));
                }
            }
        }
        if to > data_room {
            r.tensors_past_end = r.tensors_past_end.saturating_add(1);
        }
        let (name, _) = shorten(key.clone());
        r.add_tensor(ModelTensor { name, dtype: dtype.to_string(), shape, parameters, data_offset: from, data_bytes });
    }
    r.tensors.sort_by_key(|t| t.data_offset);
    if r.tensors_past_end > 0 {
        r.warn(format!("{} tensor(s) point past the end of the file: it is cut short, or the header is false.", r.tensors_past_end));
    }
    r.complete = bad == 0;
    r.quantization = dominant_quantization(&r.parameters_by_type);
    Ok(r)
}
