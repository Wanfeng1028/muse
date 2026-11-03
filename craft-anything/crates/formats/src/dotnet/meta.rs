//! ECMA-335 metadata: the `BSJB` root, stream headers, the four heaps and all 45 tables of the
//! `#~` (compressed) or `#-` (uncompressed, with pointer tables) stream, with coded indexes.
//! Every read is bounds-checked; a bad cell reads as 0 (a null index).

use crate::FormatError;
use crate::bytes::Reader;
use serde::Serialize;

/// Table ids (ECMA-335 II.22).
pub mod t {
    pub const MODULE: u8 = 0x00;
    pub const TYPE_REF: u8 = 0x01;
    pub const TYPE_DEF: u8 = 0x02;
    pub const FIELD_PTR: u8 = 0x03;
    pub const FIELD: u8 = 0x04;
    pub const METHOD_PTR: u8 = 0x05;
    pub const METHOD_DEF: u8 = 0x06;
    pub const PARAM_PTR: u8 = 0x07;
    pub const PARAM: u8 = 0x08;
    pub const INTERFACE_IMPL: u8 = 0x09;
    pub const MEMBER_REF: u8 = 0x0a;
    pub const CONSTANT: u8 = 0x0b;
    pub const CUSTOM_ATTRIBUTE: u8 = 0x0c;
    pub const FIELD_MARSHAL: u8 = 0x0d;
    pub const DECL_SECURITY: u8 = 0x0e;
    pub const CLASS_LAYOUT: u8 = 0x0f;
    pub const FIELD_LAYOUT: u8 = 0x10;
    pub const STAND_ALONE_SIG: u8 = 0x11;
    pub const EVENT_MAP: u8 = 0x12;
    pub const EVENT_PTR: u8 = 0x13;
    pub const EVENT: u8 = 0x14;
    pub const PROPERTY_MAP: u8 = 0x15;
    pub const PROPERTY_PTR: u8 = 0x16;
    pub const PROPERTY: u8 = 0x17;
    pub const METHOD_SEMANTICS: u8 = 0x18;
    pub const METHOD_IMPL: u8 = 0x19;
    pub const MODULE_REF: u8 = 0x1a;
    pub const TYPE_SPEC: u8 = 0x1b;
    pub const IMPL_MAP: u8 = 0x1c;
    pub const FIELD_RVA: u8 = 0x1d;
    pub const ENC_LOG: u8 = 0x1e;
    pub const ENC_MAP: u8 = 0x1f;
    pub const ASSEMBLY: u8 = 0x20;
    pub const ASSEMBLY_PROCESSOR: u8 = 0x21;
    pub const ASSEMBLY_OS: u8 = 0x22;
    pub const ASSEMBLY_REF: u8 = 0x23;
    pub const ASSEMBLY_REF_PROCESSOR: u8 = 0x24;
    pub const ASSEMBLY_REF_OS: u8 = 0x25;
    pub const FILE: u8 = 0x26;
    pub const EXPORTED_TYPE: u8 = 0x27;
    pub const MANIFEST_RESOURCE: u8 = 0x28;
    pub const NESTED_CLASS: u8 = 0x29;
    pub const GENERIC_PARAM: u8 = 0x2a;
    pub const METHOD_SPEC: u8 = 0x2b;
    pub const GENERIC_PARAM_CONSTRAINT: u8 = 0x2c;
}

pub const TABLE_COUNT: usize = 45;

pub const TABLE_NAMES: [&str; TABLE_COUNT] = [
    "Module",
    "TypeRef",
    "TypeDef",
    "FieldPtr",
    "Field",
    "MethodPtr",
    "MethodDef",
    "ParamPtr",
    "Param",
    "InterfaceImpl",
    "MemberRef",
    "Constant",
    "CustomAttribute",
    "FieldMarshal",
    "DeclSecurity",
    "ClassLayout",
    "FieldLayout",
    "StandAloneSig",
    "EventMap",
    "EventPtr",
    "Event",
    "PropertyMap",
    "PropertyPtr",
    "Property",
    "MethodSemantics",
    "MethodImpl",
    "ModuleRef",
    "TypeSpec",
    "ImplMap",
    "FieldRVA",
    "EncLog",
    "EncMap",
    "Assembly",
    "AssemblyProcessor",
    "AssemblyOS",
    "AssemblyRef",
    "AssemblyRefProcessor",
    "AssemblyRefOS",
    "File",
    "ExportedType",
    "ManifestResource",
    "NestedClass",
    "GenericParam",
    "MethodSpec",
    "GenericParamConstraint",
];

/// Coded index kinds (ECMA-335 II.24.2.6).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Coded {
    TypeDefOrRef,
    HasConstant,
    HasCustomAttribute,
    HasFieldMarshal,
    HasDeclSecurity,
    MemberRefParent,
    HasSemantics,
    MethodDefOrRef,
    MemberForwarded,
    Implementation,
    CustomAttributeType,
    ResolutionScope,
    TypeOrMethodDef,
}

/// `None` marks an unused tag value.
const NO: Option<u8> = None;

impl Coded {
    pub fn tables(self) -> &'static [Option<u8>] {
        use t::*;
        match self {
            Coded::TypeDefOrRef => &[Some(TYPE_DEF), Some(TYPE_REF), Some(TYPE_SPEC)],
            Coded::HasConstant => &[Some(FIELD), Some(PARAM), Some(PROPERTY)],
            Coded::HasCustomAttribute => &[
                Some(METHOD_DEF),
                Some(FIELD),
                Some(TYPE_REF),
                Some(TYPE_DEF),
                Some(PARAM),
                Some(INTERFACE_IMPL),
                Some(MEMBER_REF),
                Some(MODULE),
                Some(DECL_SECURITY),
                Some(PROPERTY),
                Some(EVENT),
                Some(STAND_ALONE_SIG),
                Some(MODULE_REF),
                Some(TYPE_SPEC),
                Some(ASSEMBLY),
                Some(ASSEMBLY_REF),
                Some(FILE),
                Some(EXPORTED_TYPE),
                Some(MANIFEST_RESOURCE),
                Some(GENERIC_PARAM),
                Some(GENERIC_PARAM_CONSTRAINT),
                Some(METHOD_SPEC),
            ],
            Coded::HasFieldMarshal => &[Some(FIELD), Some(PARAM)],
            Coded::HasDeclSecurity => &[Some(TYPE_DEF), Some(METHOD_DEF), Some(ASSEMBLY)],
            Coded::MemberRefParent => &[Some(TYPE_DEF), Some(TYPE_REF), Some(MODULE_REF), Some(METHOD_DEF), Some(TYPE_SPEC)],
            Coded::HasSemantics => &[Some(EVENT), Some(PROPERTY)],
            Coded::MethodDefOrRef => &[Some(METHOD_DEF), Some(MEMBER_REF)],
            Coded::MemberForwarded => &[Some(FIELD), Some(METHOD_DEF)],
            Coded::Implementation => &[Some(FILE), Some(ASSEMBLY_REF), Some(EXPORTED_TYPE)],
            Coded::CustomAttributeType => &[NO, NO, Some(METHOD_DEF), Some(MEMBER_REF), NO],
            Coded::ResolutionScope => &[Some(MODULE), Some(MODULE_REF), Some(ASSEMBLY_REF), Some(TYPE_REF)],
            Coded::TypeOrMethodDef => &[Some(TYPE_DEF), Some(METHOD_DEF)],
        }
    }

    pub fn tag_bits(self) -> u32 {
        let n = self.tables().len();
        let mut bits = 0u32;
        while (1usize << bits) < n {
            bits += 1;
        }
        bits
    }

    /// Split a coded value into (table, 1-based row). `None` for a null or unused tag.
    pub fn decode(self, v: u32) -> Option<(u8, u32)> {
        let bits = self.tag_bits();
        let mask = (1u32 << bits) - 1;
        let tag = usize::try_from(v & mask).ok()?;
        let row = v >> bits;
        let table = (*self.tables().get(tag)?)?;
        if row == 0 { None } else { Some((table, row)) }
    }
}

/// Column types.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Col {
    U16,
    U32,
    Str,
    Guid,
    Blob,
    Idx(u8),
    Code(Coded),
}

/// Column layout of every table.
pub fn schema(table: u8) -> &'static [Col] {
    use Coded as C;
    use Col::*;
    use t::*;
    match table {
        MODULE => &[U16, Str, Guid, Guid, Guid],
        TYPE_REF => &[Code(C::ResolutionScope), Str, Str],
        TYPE_DEF => &[U32, Str, Str, Code(C::TypeDefOrRef), Idx(FIELD), Idx(METHOD_DEF)],
        FIELD_PTR => &[Idx(FIELD)],
        FIELD => &[U16, Str, Blob],
        METHOD_PTR => &[Idx(METHOD_DEF)],
        METHOD_DEF => &[U32, U16, U16, Str, Blob, Idx(PARAM)],
        PARAM_PTR => &[Idx(PARAM)],
        PARAM => &[U16, U16, Str],
        INTERFACE_IMPL => &[Idx(TYPE_DEF), Code(C::TypeDefOrRef)],
        MEMBER_REF => &[Code(C::MemberRefParent), Str, Blob],
        CONSTANT => &[U16, Code(C::HasConstant), Blob],
        CUSTOM_ATTRIBUTE => &[Code(C::HasCustomAttribute), Code(C::CustomAttributeType), Blob],
        FIELD_MARSHAL => &[Code(C::HasFieldMarshal), Blob],
        DECL_SECURITY => &[U16, Code(C::HasDeclSecurity), Blob],
        CLASS_LAYOUT => &[U16, U32, Idx(TYPE_DEF)],
        FIELD_LAYOUT => &[U32, Idx(FIELD)],
        STAND_ALONE_SIG => &[Blob],
        EVENT_MAP => &[Idx(TYPE_DEF), Idx(EVENT)],
        EVENT_PTR => &[Idx(EVENT)],
        EVENT => &[U16, Str, Code(C::TypeDefOrRef)],
        PROPERTY_MAP => &[Idx(TYPE_DEF), Idx(PROPERTY)],
        PROPERTY_PTR => &[Idx(PROPERTY)],
        PROPERTY => &[U16, Str, Blob],
        METHOD_SEMANTICS => &[U16, Idx(METHOD_DEF), Code(C::HasSemantics)],
        METHOD_IMPL => &[Idx(TYPE_DEF), Code(C::MethodDefOrRef), Code(C::MethodDefOrRef)],
        MODULE_REF => &[Str],
        TYPE_SPEC => &[Blob],
        IMPL_MAP => &[U16, Code(C::MemberForwarded), Str, Idx(MODULE_REF)],
        FIELD_RVA => &[U32, Idx(FIELD)],
        ENC_LOG => &[U32, U32],
        ENC_MAP => &[U32],
        ASSEMBLY => &[U32, U16, U16, U16, U16, U32, Blob, Str, Str],
        ASSEMBLY_PROCESSOR => &[U32],
        ASSEMBLY_OS => &[U32, U32, U32],
        ASSEMBLY_REF => &[U16, U16, U16, U16, U32, Blob, Str, Str, Blob],
        ASSEMBLY_REF_PROCESSOR => &[U32, Idx(ASSEMBLY_REF)],
        ASSEMBLY_REF_OS => &[U32, U32, U32, Idx(ASSEMBLY_REF)],
        FILE => &[U32, Str, Blob],
        EXPORTED_TYPE => &[U32, U32, Str, Str, Code(C::Implementation)],
        MANIFEST_RESOURCE => &[U32, U32, Str, Code(C::Implementation)],
        NESTED_CLASS => &[Idx(TYPE_DEF), Idx(TYPE_DEF)],
        GENERIC_PARAM => &[U16, U16, Code(C::TypeOrMethodDef), Str],
        METHOD_SPEC => &[Code(C::MethodDefOrRef), Blob],
        GENERIC_PARAM_CONSTRAINT => &[Idx(GENERIC_PARAM), Code(C::TypeDefOrRef)],
        _ => &[],
    }
}

/// A stream header.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct StreamInfo {
    pub name: String,
    pub offset: u32,
    pub size: u32,
}

#[derive(Debug, Clone, Default)]
struct TableInfo {
    rows: u32,
    row_size: usize,
    /// Offset of the first row inside the tables stream.
    start: usize,
    /// (offset in row, width) per column.
    cols: Vec<(usize, usize)>,
}

/// Parsed metadata with bounds-checked access to heaps and table cells.
#[derive(Debug, Clone)]
pub struct Metadata<'a> {
    pub version: String,
    pub major: u16,
    pub minor: u16,
    pub streams: Vec<StreamInfo>,
    pub tables_stream: String,
    pub table_schema_version: (u8, u8),
    pub heap_sizes: u8,
    pub valid: u64,
    pub sorted: u64,
    pub warnings: Vec<String>,
    strings: &'a [u8],
    blob: &'a [u8],
    guid: &'a [u8],
    us: &'a [u8],
    tables_data: &'a [u8],
    tables: Vec<TableInfo>,
}

/// Most rows we accept in one table (a token row index has 24 bits).
pub const MAX_ROWS: u32 = 0x00ff_ffff;

impl<'a> Metadata<'a> {
    /// Parse the metadata root that starts at `md`.
    pub fn parse(md: &'a [u8]) -> Result<Metadata<'a>, FormatError> {
        let r = Reader::new(md);
        if r.u32_le(0) != Some(0x424a_5342) {
            return Err(FormatError::Malformed("metadata root has no BSJB signature".into()));
        }
        let major = r.u16_le(4).ok_or_else(|| FormatError::Truncated("metadata root".into()))?;
        let minor = r.u16_le(6).ok_or_else(|| FormatError::Truncated("metadata root".into()))?;
        let vlen = r.u32_le(12).ok_or_else(|| FormatError::Truncated("metadata root".into()))? as usize;
        if vlen > 256 {
            return Err(FormatError::Malformed(format!("version string of {vlen} bytes")));
        }
        let version = r.cstr(16, vlen).ok_or_else(|| FormatError::Truncated("metadata version".into()))?;
        let mut off = 16usize.checked_add(vlen).ok_or_else(|| FormatError::Malformed("version length".into()))?;
        let nstreams = r.u16_le(off + 2).ok_or_else(|| FormatError::Truncated("stream count".into()))?;
        if nstreams > 16 {
            return Err(FormatError::Malformed(format!("{nstreams} metadata streams")));
        }
        off += 4;
        let mut streams = Vec::new();
        let mut warnings = Vec::new();
        for _ in 0..nstreams {
            let so = r.u32_le(off).ok_or_else(|| FormatError::Truncated("stream header".into()))?;
            let ss = r.u32_le(off + 4).ok_or_else(|| FormatError::Truncated("stream header".into()))?;
            let name = r.cstr(off + 8, 32).ok_or_else(|| FormatError::Truncated("stream name".into()))?;
            let padded = (name.len() + 1 + 3) & !3;
            off = off.checked_add(8 + padded).ok_or_else(|| FormatError::Malformed("stream header".into()))?;
            streams.push(StreamInfo { name, offset: so, size: ss });
        }
        let get = |n: &str, warnings: &mut Vec<String>| -> &'a [u8] {
            let Some(s) = streams.iter().find(|s| s.name == n) else { return &[] };
            match r.slice(s.offset as usize, s.size as usize) {
                Some(b) => b,
                None => {
                    warnings.push(format!("stream {n} runs past the metadata; ignored"));
                    &[]
                }
            }
        };
        let strings = get("#Strings", &mut warnings);
        let blob = get("#Blob", &mut warnings);
        let guid = get("#GUID", &mut warnings);
        let us = get("#US", &mut warnings);
        let (tables_stream, tables_data) = if streams.iter().any(|s| s.name == "#~") {
            ("#~".to_string(), get("#~", &mut warnings))
        } else if streams.iter().any(|s| s.name == "#-") {
            ("#-".to_string(), get("#-", &mut warnings))
        } else {
            return Err(FormatError::Malformed("no metadata tables stream (#~ or #-)".into()));
        };
        let mut md = Metadata {
            version,
            major,
            minor,
            streams,
            tables_stream,
            table_schema_version: (0, 0),
            heap_sizes: 0,
            valid: 0,
            sorted: 0,
            warnings,
            strings,
            blob,
            guid,
            us,
            tables_data,
            tables: vec![TableInfo::default(); TABLE_COUNT],
        };
        md.parse_tables()?;
        Ok(md)
    }

    fn parse_tables(&mut self) -> Result<(), FormatError> {
        let r = Reader::new(self.tables_data);
        let maj = r.u8(4).ok_or_else(|| FormatError::Truncated("tables header".into()))?;
        let min = r.u8(5).ok_or_else(|| FormatError::Truncated("tables header".into()))?;
        self.table_schema_version = (maj, min);
        self.heap_sizes = r.u8(6).ok_or_else(|| FormatError::Truncated("tables header".into()))?;
        self.valid = r.u64_le(8).ok_or_else(|| FormatError::Truncated("tables header".into()))?;
        self.sorted = r.u64_le(16).ok_or_else(|| FormatError::Truncated("tables header".into()))?;
        let mut off = 24usize;
        let mut rows = [0u32; 64];
        for (i, slot) in rows.iter_mut().enumerate() {
            if self.valid & (1u64 << i) != 0 {
                let n = r.u32_le(off).ok_or_else(|| FormatError::Truncated("table row counts".into()))?;
                if n > MAX_ROWS {
                    return Err(FormatError::TooLarge(format!("table {i:#x} claims {n} rows")));
                }
                *slot = n;
                off += 4;
            }
        }
        if self.valid >> TABLE_COUNT != 0 {
            self.warnings.push(format!("unknown tables present (valid mask {:#x}); later tables may be misread", self.valid));
        }
        // Extra data after the row counts.
        if self.heap_sizes & 0x40 != 0 {
            off += 4;
        }
        let str_w = if self.heap_sizes & 1 != 0 { 4 } else { 2 };
        let guid_w = if self.heap_sizes & 2 != 0 { 4 } else { 2 };
        let blob_w = if self.heap_sizes & 4 != 0 { 4 } else { 2 };
        let rows_of = |tb: u8| rows.get(usize::from(tb)).copied().unwrap_or(0);
        // List columns point into the pointer table when one is present.
        let idx_target = |tb: u8, owner: u8| -> u8 {
            let ptr = match tb {
                t::FIELD if owner == t::TYPE_DEF => t::FIELD_PTR,
                t::METHOD_DEF if owner == t::TYPE_DEF => t::METHOD_PTR,
                t::PARAM if owner == t::METHOD_DEF => t::PARAM_PTR,
                t::EVENT if owner == t::EVENT_MAP => t::EVENT_PTR,
                t::PROPERTY if owner == t::PROPERTY_MAP => t::PROPERTY_PTR,
                _ => return tb,
            };
            if rows_of(ptr) > 0 { ptr } else { tb }
        };
        let mut start = off;
        for tb in 0..TABLE_COUNT as u8 {
            let mut cols = Vec::new();
            let mut row_size = 0usize;
            for c in schema(tb) {
                let w = match *c {
                    Col::U16 => 2,
                    Col::U32 => 4,
                    Col::Str => str_w,
                    Col::Guid => guid_w,
                    Col::Blob => blob_w,
                    Col::Idx(target) => {
                        if rows_of(idx_target(target, tb)) > 0xffff {
                            4
                        } else {
                            2
                        }
                    }
                    Col::Code(k) => {
                        let max = k.tables().iter().flatten().map(|&x| rows_of(x)).max().unwrap_or(0);
                        if u64::from(max) < (1u64 << (16 - k.tag_bits())) { 2 } else { 4 }
                    }
                };
                cols.push((row_size, w));
                row_size += w;
            }
            let n = rows_of(tb);
            let bytes = (n as usize).checked_mul(row_size).ok_or_else(|| FormatError::TooLarge("table size".into()))?;
            if let Some(info) = self.tables.get_mut(usize::from(tb)) {
                *info = TableInfo { rows: n, row_size, start, cols };
            }
            start = start.checked_add(bytes).ok_or_else(|| FormatError::TooLarge("table size".into()))?;
        }
        if start > self.tables_data.len() {
            // Keep the tables that fit; mark the rest empty.
            let len = self.tables_data.len();
            let mut cut = false;
            for (i, info) in self.tables.iter_mut().enumerate() {
                let end = info.start.saturating_add((info.rows as usize).saturating_mul(info.row_size));
                if end > len && info.rows > 0 {
                    let fit = len.saturating_sub(info.start).checked_div(info.row_size.max(1)).unwrap_or(0);
                    let fit = u32::try_from(fit).unwrap_or(0).min(info.rows);
                    if !cut {
                        self.warnings.push(format!(
                            "the tables stream ends early; {} keeps {fit} of {} rows and later tables are empty",
                            TABLE_NAMES.get(i).unwrap_or(&"?"),
                            info.rows
                        ));
                    }
                    info.rows = if cut { 0 } else { fit };
                    cut = true;
                } else if cut {
                    info.rows = 0;
                }
            }
        }
        Ok(())
    }

    /// Row count of a table.
    pub fn rows(&self, table: u8) -> u32 {
        self.tables.get(usize::from(table)).map(|t| t.rows).unwrap_or(0)
    }

    /// Row counts by table name, for tables that have rows.
    pub fn row_counts(&self) -> Vec<(&'static str, u32)> {
        TABLE_NAMES.iter().enumerate().filter_map(|(i, n)| self.tables.get(i).filter(|t| t.rows > 0).map(|t| (*n, t.rows))).collect()
    }

    /// One cell (1-based row). 0 when out of range.
    pub fn cell(&self, table: u8, row: u32, col: usize) -> u32 {
        let Some(info) = self.tables.get(usize::from(table)) else { return 0 };
        if row == 0 || row > info.rows {
            return 0;
        }
        let Some(&(co, w)) = info.cols.get(col) else { return 0 };
        let Some(off) = ((row - 1) as usize).checked_mul(info.row_size).and_then(|x| x.checked_add(info.start)).and_then(|x| x.checked_add(co)) else {
            return 0;
        };
        let r = Reader::new(self.tables_data);
        match w {
            2 => r.u16_le(off).map(u32::from).unwrap_or(0),
            4 => r.u32_le(off).unwrap_or(0),
            _ => 0,
        }
    }

    /// A coded-index cell, decoded.
    pub fn coded(&self, table: u8, row: u32, col: usize) -> Option<(u8, u32)> {
        match schema(table).get(col) {
            Some(Col::Code(k)) => k.decode(self.cell(table, row, col)),
            _ => None,
        }
    }

    /// A string from `#Strings`.
    pub fn string(&self, idx: u32) -> String {
        Reader::new(self.strings).cstr(idx as usize, 1024).unwrap_or_default()
    }

    /// A string cell.
    pub fn str_cell(&self, table: u8, row: u32, col: usize) -> String {
        self.string(self.cell(table, row, col))
    }

    /// A blob from `#Blob` (empty when out of range).
    pub fn blob(&self, idx: u32) -> &'a [u8] {
        let r = Reader::new(self.blob);
        let Some((len, n)) = compressed_u32(self.blob, idx as usize) else { return &[] };
        r.slice((idx as usize).saturating_add(n), len as usize).unwrap_or(&[])
    }

    pub fn blob_cell(&self, table: u8, row: u32, col: usize) -> &'a [u8] {
        self.blob(self.cell(table, row, col))
    }

    /// A GUID (1-based index) as text.
    pub fn guid(&self, idx: u32) -> Option<String> {
        if idx == 0 {
            return None;
        }
        let g = Reader::new(self.guid).slice(((idx - 1) as usize).checked_mul(16)?, 16)?;
        let r = Reader::new(g);
        Some(format!(
            "{:08x}-{:04x}-{:04x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
            r.u32_le(0)?,
            r.u16_le(4)?,
            r.u16_le(6)?,
            g.get(8)?,
            g.get(9)?,
            g.get(10)?,
            g.get(11)?,
            g.get(12)?,
            g.get(13)?,
            g.get(14)?,
            g.get(15)?
        ))
    }

    /// A user string (`ldstr`) from `#US`, at most `max` characters.
    pub fn user_string(&self, idx: u32, max: usize) -> Option<String> {
        let (len, n) = compressed_u32(self.us, idx as usize)?;
        let bytes = Reader::new(self.us).slice((idx as usize).checked_add(n)?, len as usize)?;
        let chars = bytes.len() / 2;
        let units: Vec<u16> = (0..chars.min(max)).filter_map(|i| Reader::new(bytes).u16_le(i * 2)).collect();
        Some(String::from_utf16_lossy(&units))
    }

    /// The range of child rows `[start, end)` a list column gives, resolved through the pointer
    /// table when present. Returns child row numbers.
    pub fn list(&self, owner: u8, row: u32, col: usize, child: u8, cap: usize) -> Vec<u32> {
        let ptr = match child {
            t::FIELD => t::FIELD_PTR,
            t::METHOD_DEF => t::METHOD_PTR,
            t::PARAM => t::PARAM_PTR,
            t::EVENT => t::EVENT_PTR,
            t::PROPERTY => t::PROPERTY_PTR,
            _ => child,
        };
        let use_ptr = ptr != child && self.rows(ptr) > 0;
        let target_rows = if use_ptr { self.rows(ptr) } else { self.rows(child) };
        let start = self.cell(owner, row, col);
        let end = if row < self.rows(owner) { self.cell(owner, row + 1, col) } else { target_rows.saturating_add(1) };
        if start == 0 || start > end {
            return Vec::new();
        }
        let end = end.min(target_rows.saturating_add(1));
        (start..end).take(cap).map(|i| if use_ptr { self.cell(ptr, i, 0) } else { i }).filter(|&i| i != 0 && i <= self.rows(child)).collect()
    }

    /// Bytes of the `#US` heap length (for statistics).
    pub fn heap_sizes_bytes(&self) -> [(&'static str, usize); 4] {
        [("#Strings", self.strings.len()), ("#Blob", self.blob.len()), ("#GUID", self.guid.len()), ("#US", self.us.len())]
    }
}

/// ECMA-335 compressed unsigned integer at `off`: (value, bytes used).
pub fn compressed_u32(data: &[u8], off: usize) -> Option<(u32, usize)> {
    let b0 = *data.get(off)?;
    if b0 & 0x80 == 0 {
        Some((u32::from(b0), 1))
    } else if b0 & 0xc0 == 0x80 {
        let b1 = *data.get(off.checked_add(1)?)?;
        Some(((u32::from(b0 & 0x3f) << 8) | u32::from(b1), 2))
    } else if b0 & 0xe0 == 0xc0 {
        let b = data.get(off.checked_add(1)?..off.checked_add(4)?)?;
        Some(((u32::from(b0 & 0x1f) << 24) | (u32::from(*b.first()?) << 16) | (u32::from(*b.get(1)?) << 8) | u32::from(*b.get(2)?), 4))
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn coded_indexes_and_compression() {
        assert_eq!(Coded::TypeDefOrRef.tag_bits(), 2);
        assert_eq!(Coded::HasCustomAttribute.tag_bits(), 5);
        assert_eq!(Coded::CustomAttributeType.tag_bits(), 3);
        assert_eq!(Coded::TypeDefOrRef.decode((5 << 2) | 1), Some((t::TYPE_REF, 5)));
        assert_eq!(Coded::CustomAttributeType.decode(1 << 3), None);
        assert_eq!(compressed_u32(&[0x03], 0), Some((3, 1)));
        assert_eq!(compressed_u32(&[0x80, 0x80], 0), Some((0x80, 2)));
        assert_eq!(compressed_u32(&[0xc0, 0x00, 0x40, 0x00], 0), Some((0x4000, 4)));
        assert_eq!(compressed_u32(&[0xff], 0), None);
        assert_eq!(compressed_u32(&[0xc0, 0], 0), None);
        for tb in 0..TABLE_COUNT as u8 {
            assert!(!schema(tb).is_empty(), "{tb}");
        }
    }
}
