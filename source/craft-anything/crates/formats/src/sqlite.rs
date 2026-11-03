//! Read-only parser for the SQLite 3 database file format (clean-room, from the public
//! on-disk documentation). It reads the 100-byte database header, b-tree pages (interior and
//! leaf, table and index), the record / serial-type encoding and the `sqlite_schema` table, and
//! can count a table's rows and read a page of them. Nothing is executed and nothing is written.
//!
//! Everything is bounded: inputs are capped, b-tree descent carries a depth limit and a
//! visited-page set to stop cycles, the number of pages walked and rows read is capped, cell
//! payloads (including overflow chains) are capped, and every read is bounds-checked. No input
//! can cause a panic.

use crate::FormatError;
use serde::Serialize;

/// Largest database file we read into memory (256 MiB).
pub const MAX_INPUT: usize = 256 << 20;
/// Longest text value decoded (bytes of source); longer values are truncated with a marker.
const MAX_TEXT: usize = 4096;
/// Largest assembled cell payload we follow across overflow pages.
const MAX_CELL_SIZE: usize = 8 << 20;
/// Most columns decoded from a single record.
const MAX_COLUMNS: usize = 4096;
/// Most overflow pages followed for one cell.
const MAX_OVERFLOW_PAGES: usize = 4096;
/// Most pages visited while counting or reading one table's b-tree.
const MAX_PAGES_WALKED: usize = 500_000;
/// Deepest b-tree descent (SQLite trees are shallow; this only guards hostile files).
const MAX_DEPTH: usize = 64;
/// Hard cap on rows returned in one read.
pub const MAX_ROWS: usize = 100_000;
/// Most schema objects listed.
const MAX_SCHEMA_OBJECTS: usize = 100_000;

const MAGIC: &[u8; 16] = b"SQLite format 3\0";

/// The 100-byte database header.
#[derive(Debug, Clone, Serialize)]
pub struct Header {
    /// Page size in bytes (512..=65536, a power of two).
    pub page_size: u32,
    /// File-format write version: 1 = legacy (rollback journal), 2 = WAL.
    pub write_version: u8,
    /// File-format read version: 1 = legacy, 2 = WAL.
    pub read_version: u8,
    /// Bytes reserved at the end of every page (usually 0).
    pub reserved_space: u8,
    /// Incremented on every change; used to spot stale caches.
    pub file_change_counter: u32,
    /// Database size in pages recorded in the header (valid only when it matches the file).
    pub db_size_pages: u32,
    /// Page number of the first freelist trunk page (0 when the freelist is empty).
    pub freelist_trunk: u32,
    /// Total number of freelist pages.
    pub freelist_pages: u32,
    pub schema_cookie: u32,
    /// Schema layer format number (1..=4).
    pub schema_format: u32,
    pub default_cache_size: u32,
    /// Page number of the largest root b-tree page (auto/incremental vacuum), else 0.
    pub largest_root_page: u32,
    /// `utf-8`, `utf-16le`, `utf-16be` or `unknown`.
    pub text_encoding: &'static str,
    pub user_version: u32,
    /// Non-zero when incremental-vacuum mode is on.
    pub incremental_vacuum: u32,
    pub application_id: u32,
    pub version_valid_for: u32,
    /// SQLITE_VERSION_NUMBER of the library that last wrote the file (e.g. 3045001 = 3.45.1).
    pub sqlite_version_number: u32,
    /// Human form of `sqlite_version_number`, e.g. `3.45.1`.
    pub sqlite_version: String,
    /// True when the file declares WAL mode (write or read version == 2).
    pub wal_mode: bool,
}

/// One row of the `sqlite_schema` table: a table, index, view or trigger.
#[derive(Debug, Clone, Serialize)]
pub struct SchemaObject {
    /// `table`, `index`, `view` or `trigger`.
    pub obj_type: String,
    pub name: String,
    /// The table this object belongs to (for an index/trigger it's the parent table).
    pub tbl_name: String,
    /// Root b-tree page (0 for views and triggers, which have no b-tree).
    pub rootpage: u32,
    /// The original CREATE statement, truncated to a sane length.
    pub sql: String,
    /// Columns parsed from the CREATE statement (tables only, best effort).
    pub columns: Vec<Column>,
}

/// A column declared in a CREATE TABLE statement (parsed from SQL text, best effort).
#[derive(Debug, Clone, Serialize)]
pub struct Column {
    pub name: String,
    /// Declared type, or empty when none was given.
    pub type_name: String,
}

/// A whole-database overview: header fields, integrity notes and the schema.
#[derive(Debug, Clone, Serialize)]
pub struct Overview {
    pub header: Header,
    /// File length in bytes.
    pub file_size: u64,
    /// Page count derived from the file length.
    pub page_count_from_size: u64,
    /// Non-fatal observations about consistency.
    pub integrity_notes: Vec<String>,
    pub schema: Vec<SchemaObject>,
    /// True when the schema listing hit the object cap.
    pub schema_truncated: bool,
}

/// A decoded cell value, rendered honestly: BLOBs are never dumped whole.
#[derive(Debug, Clone, PartialEq)]
pub enum CellValue {
    Null,
    Int(i64),
    Real(f64),
    Text { text: String, truncated: bool },
    Blob { len: usize, sha256_prefix: String },
    PartialBlob { len: usize },
    NotRead,
}

impl Serialize for CellValue {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        match self {
            CellValue::Null => s.serialize_none(),
            CellValue::Int(v) => s.serialize_i64(*v),
            CellValue::Real(v) => s.serialize_f64(*v),
            CellValue::Text { text, truncated } => {
                if *truncated {
                    let mut m = s.serialize_map(Some(2))?;
                    m.serialize_entry("text", text)?;
                    m.serialize_entry("truncated", &true)?;
                    m.end()
                } else {
                    s.serialize_str(text)
                }
            }
            CellValue::Blob { len, sha256_prefix } => {
                let mut m = s.serialize_map(Some(2))?;
                m.serialize_entry("blob_len", len)?;
                m.serialize_entry("sha256_prefix", sha256_prefix)?;
                m.end()
            }
            CellValue::PartialBlob { len } => {
                let mut m = s.serialize_map(Some(2))?;
                m.serialize_entry("blob_len", len)?;
                m.serialize_entry("truncated", &true)?;
                m.end()
            }
            CellValue::NotRead => {
                let mut m = s.serialize_map(Some(1))?;
                m.serialize_entry("not_read", &true)?;
                m.end()
            }
        }
    }
}

/// One table row.
#[derive(Debug, Clone, Serialize)]
pub struct Row {
    /// Absent for WITHOUT ROWID tables.
    pub rowid: Option<i64>,
    pub values: Vec<CellValue>,
}

/// A page of rows read from one table.
#[derive(Debug, Clone, Serialize)]
pub struct RowPage {
    pub rows: Vec<Row>,
    /// Rows skipped before the page (the requested offset, clamped to what exists).
    pub offset: usize,
    /// True when reading stopped at the row cap or a budget and more rows may exist.
    pub truncated: bool,
    /// Non-fatal observations (corruption skipped, overflow capped, …).
    pub notes: Vec<String>,
}

/// A table's row count.
#[derive(Debug, Clone, Serialize)]
pub struct RowCount {
    pub count: u64,
    /// True when the walk hit a budget, so the count is a lower bound.
    pub bounded: bool,
}

/// Accumulator for a bounded b-tree row walk: the rows gathered so far, a visited-page set to
/// stop cycles, the remaining page-walk budget, how many rows are wanted, and any notes.
struct RowWalk {
    index_tree: bool,
    visited: Vec<u32>,
    budget: usize,
    out: Vec<Row>,
    notes: Vec<String>,
    /// Stop once this many rows are collected (0 = no limit, used for the schema walk).
    want: usize,
}

impl RowWalk {
    fn new(want: usize) -> Self {
        RowWalk { index_tree: false, visited: Vec::new(), budget: MAX_PAGES_WALKED, out: Vec::new(), notes: Vec::new(), want }
    }
}

/// A parsed SQLite database, holding a borrow of the file bytes.
pub struct SqliteDb<'a> {
    data: &'a [u8],
    header: Header,
    usable: usize,
}

/// True when `data` starts with the SQLite 3 magic string.
pub fn is_sqlite(data: &[u8]) -> bool {
    data.len() >= 16 && data.get(..16) == Some(MAGIC.as_slice())
}

fn read_u32_be(data: &[u8], off: usize) -> Option<u32> {
    let b: [u8; 4] = data.get(off..off.checked_add(4)?)?.try_into().ok()?;
    Some(u32::from_be_bytes(b))
}

fn read_u16_be(data: &[u8], off: usize) -> Option<u16> {
    let b: [u8; 2] = data.get(off..off.checked_add(2)?)?.try_into().ok()?;
    Some(u16::from_be_bytes(b))
}

/// A SQLite big-endian varint (up to 9 bytes): (value, bytes consumed).
fn varint(data: &[u8], off: usize) -> Option<(u64, usize)> {
    let mut result: u64 = 0;
    let mut i = 0usize;
    while i < 9 {
        let b = *data.get(off.checked_add(i)?)?;
        if i == 8 {
            result = (result << 8) | u64::from(b);
            return Some((result, 9));
        }
        result = (result << 7) | u64::from(b & 0x7f);
        if b & 0x80 == 0 {
            return Some((result, i + 1));
        }
        i += 1;
    }
    None
}

fn version_string(n: u32) -> String {
    // SQLITE_VERSION_NUMBER = major*1_000_000 + minor*1_000 + patch.
    let major = n / 1_000_000;
    let minor = (n / 1_000) % 1_000;
    let patch = n % 1_000;
    format!("{major}.{minor}.{patch}")
}

impl<'a> SqliteDb<'a> {
    /// Parse the database header. Fails only when the magic or page size is wrong.
    pub fn parse(data: &'a [u8]) -> Result<SqliteDb<'a>, FormatError> {
        if data.len() > MAX_INPUT {
            return Err(FormatError::TooLarge(format!("{} bytes; the limit is {MAX_INPUT}", data.len())));
        }
        if !is_sqlite(data) {
            return Err(FormatError::Unsupported("missing the \"SQLite format 3\" signature".into()));
        }
        if data.len() < 100 {
            return Err(FormatError::Truncated("the 100-byte header does not fit".into()));
        }
        let raw_ps = read_u16_be(data, 16).unwrap_or(0);
        let page_size: u32 = if raw_ps == 1 { 65_536 } else { u32::from(raw_ps) };
        if page_size < 512 || !page_size.is_power_of_two() {
            return Err(FormatError::Malformed(format!("page size {page_size} is not a power of two in 512..=65536")));
        }
        let write_version = *data.get(18).unwrap_or(&0);
        let read_version = *data.get(19).unwrap_or(&0);
        let reserved_space = *data.get(20).unwrap_or(&0);
        let usable = (page_size as usize).saturating_sub(reserved_space as usize);
        if usable < 480 {
            return Err(FormatError::Malformed(format!("usable page size {usable} is too small")));
        }
        let text_encoding = match read_u32_be(data, 56).unwrap_or(0) {
            1 => "utf-8",
            2 => "utf-16le",
            3 => "utf-16be",
            0 => "utf-8", // a fresh database leaves this 0; UTF-8 is the default.
            _ => "unknown",
        };
        let sqlite_version_number = read_u32_be(data, 96).unwrap_or(0);
        let header = Header {
            page_size,
            write_version,
            read_version,
            reserved_space,
            file_change_counter: read_u32_be(data, 24).unwrap_or(0),
            db_size_pages: read_u32_be(data, 28).unwrap_or(0),
            freelist_trunk: read_u32_be(data, 32).unwrap_or(0),
            freelist_pages: read_u32_be(data, 36).unwrap_or(0),
            schema_cookie: read_u32_be(data, 40).unwrap_or(0),
            schema_format: read_u32_be(data, 44).unwrap_or(0),
            default_cache_size: read_u32_be(data, 48).unwrap_or(0),
            largest_root_page: read_u32_be(data, 52).unwrap_or(0),
            text_encoding,
            user_version: read_u32_be(data, 60).unwrap_or(0),
            incremental_vacuum: read_u32_be(data, 64).unwrap_or(0),
            application_id: read_u32_be(data, 68).unwrap_or(0),
            version_valid_for: read_u32_be(data, 92).unwrap_or(0),
            sqlite_version_number,
            sqlite_version: version_string(sqlite_version_number),
            wal_mode: write_version == 2 || read_version == 2,
        };
        Ok(SqliteDb { data, header, usable })
    }

    pub fn header(&self) -> &Header {
        &self.header
    }

    fn page_size(&self) -> usize {
        self.header.page_size as usize
    }

    /// Total pages implied by the file length.
    fn page_count(&self) -> u64 {
        (self.data.len() as u64) / (self.header.page_size as u64)
    }

    /// Byte offset of page `pageno` (1-based).
    fn page_base(&self, pageno: u32) -> Option<usize> {
        let p = (pageno as usize).checked_sub(1)?;
        p.checked_mul(self.page_size())
    }

    /// Byte offset where the b-tree page header begins (page 1 follows the 100-byte db header).
    fn btree_header_off(&self, pageno: u32) -> Option<usize> {
        let base = self.page_base(pageno)?;
        if pageno == 1 { base.checked_add(100) } else { Some(base) }
    }

    /// Build the whole-database overview, including the schema.
    pub fn overview(&self) -> Overview {
        let (schema, schema_truncated) = self.schema();
        let file_size = self.data.len() as u64;
        let page_count_from_size = self.page_count();
        let mut notes = Vec::new();
        if !self.data.len().is_multiple_of(self.page_size()) {
            notes.push("The file length is not a whole number of pages; it may be truncated or a header is stale.".into());
        }
        if self.header.db_size_pages != 0 && u64::from(self.header.db_size_pages) != page_count_from_size {
            notes.push(format!(
                "Header records {} pages but the file holds {page_count_from_size}; a -wal file may hold newer pages, or the header is stale.",
                self.header.db_size_pages
            ));
        }
        if self.header.wal_mode {
            notes.push("The database is in WAL mode: the newest committed rows may live in a -wal sidecar, not in this file.".into());
        }
        if self.header.freelist_pages > 0 {
            notes.push(format!("{} page(s) are on the freelist (deleted content may linger there; it is not read).", self.header.freelist_pages));
        }
        Overview { header: self.header.clone(), file_size, page_count_from_size, integrity_notes: notes, schema, schema_truncated }
    }

    /// Walk the `sqlite_schema` b-tree (rooted at page 1) and return its objects.
    pub fn schema(&self) -> (Vec<SchemaObject>, bool) {
        let mut out = Vec::new();
        let mut w = RowWalk::new(MAX_SCHEMA_OBJECTS);
        self.collect_table_rows(&mut w, 1, 0);
        let truncated = w.out.len() >= MAX_SCHEMA_OBJECTS;
        for row in w.out {
            // sqlite_schema columns: type, name, tbl_name, rootpage, sql.
            let get_text = |i: usize| match row.values.get(i) {
                Some(CellValue::Text { text, .. }) => text.clone(),
                _ => String::new(),
            };
            let obj_type = get_text(0);
            let name = get_text(1);
            let tbl_name = get_text(2);
            let rootpage = match row.values.get(3) {
                Some(CellValue::Int(v)) if *v >= 0 => *v as u32,
                _ => 0,
            };
            let sql = get_text(4);
            let columns = if obj_type == "table" { parse_create_columns(&sql) } else { Vec::new() };
            out.push(SchemaObject { obj_type, name, tbl_name, rootpage, sql, columns });
        }
        (out, truncated)
    }

    /// Find a schema object (table/index/view/trigger) by name (case-insensitive).
    pub fn find_object(&self, name: &str) -> Option<SchemaObject> {
        let (schema, _) = self.schema();
        schema.into_iter().find(|o| o.name.eq_ignore_ascii_case(name))
    }

    fn without_rowid_table(&self, rootpage: u32) -> Option<SchemaObject> {
        self.schema().0.into_iter().find(|obj| obj.obj_type == "table" && obj.rootpage == rootpage && is_without_rowid(&obj.sql))
    }

    /// Count the rows of the table rooted at `rootpage`, including interior index records.
    pub fn count_rows(&self, rootpage: u32) -> RowCount {
        let mut count: u64 = 0;
        let mut visited = Vec::new();
        let mut budget = MAX_PAGES_WALKED;
        let index_tree = self.btree_header_off(rootpage).and_then(|hdr| self.data.get(hdr)).is_some_and(|ptype| matches!(*ptype, 0x02 | 0x0a));
        let bounded = !self.count_leaf_cells(rootpage, 0, &mut visited, &mut budget, &mut count, index_tree);
        RowCount { count, bounded }
    }

    /// Read a page of rows from the table rooted at `rootpage`.
    pub fn read_rows(&self, rootpage: u32, offset: usize, limit: usize) -> RowPage {
        let limit = limit.min(MAX_ROWS);
        // Collect offset+limit rows, then drop the leading `offset`.
        let want = offset.saturating_add(limit);
        let mut w = RowWalk::new(want);
        let table = self.without_rowid_table(rootpage);
        w.index_tree = table.is_some();
        self.collect_table_rows(&mut w, rootpage, 0);
        if let Some(table) = table {
            if let Some(order) = without_rowid_order(&table) {
                for row in &mut w.out {
                    row.values = order.iter().map(|&i| row.values.get(i).cloned().unwrap_or(CellValue::Null)).collect();
                }
            } else {
                w.notes.push("Could not determine the primary-key column order; values remain in storage order.".into());
            }
        }
        let hit_cap = w.out.len() >= want && want > 0;
        let skipped = offset.min(w.out.len());
        let mut page: Vec<Row> = w.out.into_iter().skip(offset).take(limit).collect();
        let (schema, _) = self.schema();
        if let Some(table) = schema.iter().find(|o| o.obj_type == "table" && o.rootpage == rootpage) {
            let defaults: Vec<_> = column_definitions(&table.sql).into_iter().map(|(_, rest)| column_default(rest)).collect();
            let mut unsupported = vec![false; defaults.len()];
            for row in &mut page {
                for ((value, supported), disclosed) in defaults.iter().zip(&mut unsupported).skip(row.values.len()) {
                    row.values.push(value.clone());
                    if !supported {
                        *disclosed = true;
                    }
                }
            }
            for (i, disclosed) in unsupported.into_iter().enumerate() {
                if disclosed {
                    w.notes.push(format!("Column {} has an unsupported DEFAULT expression; missing values were filled as NULL.", i + 1));
                }
            }
            if let Some(index) = rowid_alias_index(&table.sql) {
                for row in &mut page {
                    if let (Some(rowid), Some(value @ CellValue::Null)) = (row.rowid, row.values.get_mut(index)) {
                        *value = CellValue::Int(rowid);
                    }
                }
            }
        }
        RowPage { rows: page, offset: skipped, truncated: hit_cap, notes: w.notes }
    }

    /// Recursively count rows. Returns false when a budget stopped the walk.
    fn count_leaf_cells(&self, pageno: u32, depth: usize, visited: &mut Vec<u32>, budget: &mut usize, count: &mut u64, index_tree: bool) -> bool {
        if depth > MAX_DEPTH || *budget == 0 {
            return false;
        }
        if visited.contains(&pageno) || pageno == 0 {
            return true; // a cycle or a null pointer: stop, but not a budget failure.
        }
        visited.push(pageno);
        *budget -= 1;
        let Some(hdr) = self.btree_header_off(pageno) else { return true };
        let ptype = *self.data.get(hdr).unwrap_or(&0);
        let ncells = read_u16_be(self.data, hdr.saturating_add(3)).unwrap_or(0) as usize;
        match ptype {
            0x0d if !index_tree => {
                *count = count.saturating_add(ncells as u64);
                true
            }
            0x0a if index_tree => {
                *count = count.saturating_add(ncells as u64);
                true
            }
            0x05 | 0x02 if (ptype == 0x02) == index_tree => {
                if index_tree {
                    *count = count.saturating_add(ncells as u64);
                }
                let mut ok = true;
                // Child pointers live in each cell; the right-most pointer is in the header.
                for i in 0..ncells {
                    if *budget == 0 {
                        return false;
                    }
                    if let Some(child) = self.interior_child(pageno, hdr, i) {
                        ok &= self.count_leaf_cells(child, depth + 1, visited, budget, count, index_tree);
                    }
                }
                if let Some(right) = read_u32_be(self.data, hdr.saturating_add(8)) {
                    ok &= self.count_leaf_cells(right, depth + 1, visited, budget, count, index_tree);
                }
                ok
            }
            _ => true, // not a table page; ignore.
        }
    }

    /// Recursively gather rows in key order, stopping once `want` are collected.
    fn collect_table_rows(&self, w: &mut RowWalk, pageno: u32, depth: usize) {
        if depth > MAX_DEPTH || w.budget == 0 || (w.want != 0 && w.out.len() >= w.want) {
            return;
        }
        if w.visited.contains(&pageno) || pageno == 0 {
            return;
        }
        w.visited.push(pageno);
        w.budget -= 1;
        let Some(hdr) = self.btree_header_off(pageno) else { return };
        let Some(base) = self.page_base(pageno) else { return };
        let ptype = *self.data.get(hdr).unwrap_or(&0);
        let ncells = read_u16_be(self.data, hdr.saturating_add(3)).unwrap_or(0) as usize;
        let cell_ptr_base = hdr.saturating_add(if ptype == 0x05 || ptype == 0x02 { 12 } else { 8 });
        match ptype {
            0x0d | 0x0a if (ptype == 0x0a) == w.index_tree => {
                for i in 0..ncells {
                    if w.want != 0 && w.out.len() >= w.want {
                        return;
                    }
                    let Some(ptr) = read_u16_be(self.data, cell_ptr_base.saturating_add(i * 2)) else { continue };
                    let cell_off = base.saturating_add(ptr as usize);
                    let row = if w.index_tree { self.read_index_cell(cell_off, &mut w.notes) } else { self.read_table_leaf_cell(cell_off, &mut w.notes) };
                    match row {
                        Some(row) => w.out.push(row),
                        None => w.notes.push(format!("Skipped an unreadable row on page {pageno}.")),
                    }
                }
            }
            0x05 | 0x02 if (ptype == 0x02) == w.index_tree => {
                for i in 0..ncells {
                    if (w.want != 0 && w.out.len() >= w.want) || w.budget == 0 {
                        return;
                    }
                    if let Some(child) = self.interior_child(pageno, hdr, i) {
                        self.collect_table_rows(w, child, depth + 1);
                    }
                    if w.index_tree {
                        if w.want != 0 && w.out.len() >= w.want {
                            return;
                        }
                        let row = read_u16_be(self.data, cell_ptr_base.saturating_add(i * 2))
                            .and_then(|ptr| base.checked_add(ptr as usize))
                            .and_then(|off| off.checked_add(4))
                            .and_then(|off| self.read_index_cell(off, &mut w.notes));
                        match row {
                            Some(row) => w.out.push(row),
                            None => w.notes.push(format!("Skipped an unreadable row on page {pageno}.")),
                        }
                    }
                }
                if let Some(right) = read_u32_be(self.data, hdr.saturating_add(8)) {
                    self.collect_table_rows(w, right, depth + 1);
                }
            }
            _ => {}
        }
    }

    /// The left-child page number of cell `i` on an interior page.
    fn interior_child(&self, pageno: u32, hdr: usize, i: usize) -> Option<u32> {
        let base = self.page_base(pageno)?;
        let cell_ptr_base = hdr.checked_add(12)?;
        let ptr = read_u16_be(self.data, cell_ptr_base.checked_add(i.checked_mul(2)?)?)?;
        let cell_off = base.checked_add(ptr as usize)?;
        read_u32_be(self.data, cell_off)
    }

    /// Decode one table-leaf cell into a row, following overflow pages if needed.
    fn read_table_leaf_cell(&self, cell_off: usize, notes: &mut Vec<String>) -> Option<Row> {
        let (payload_len, n1) = varint(self.data, cell_off)?;
        let (rowid, n2) = varint(self.data, cell_off.checked_add(n1)?)?;
        let body_off = cell_off.checked_add(n1)?.checked_add(n2)?;
        let payload_len = usize::try_from(payload_len).ok()?;
        let payload = self.assemble_payload(body_off, payload_len, true, notes)?;
        let values = parse_record(&payload);
        let rowid = i64::from_le_bytes(rowid.to_le_bytes());
        Some(Row { rowid: Some(rowid), values })
    }

    /// Index cells hold a whole row, without a rowid, using the index local-payload formula.
    fn read_index_cell(&self, cell_off: usize, notes: &mut Vec<String>) -> Option<Row> {
        let (payload_len, n) = varint(self.data, cell_off)?;
        let payload_len = usize::try_from(payload_len).ok()?;
        let payload = self.assemble_payload(cell_off.checked_add(n)?, payload_len, false, notes)?;
        Some(Row { rowid: None, values: parse_record(&payload) })
    }

    /// Assemble a cell payload: the local part plus any overflow-page chain, capped.
    fn assemble_payload(&self, local_off: usize, payload_len: usize, is_table_leaf: bool, notes: &mut Vec<String>) -> Option<Vec<u8>> {
        let usable = self.usable;
        // Maximum bytes stored on the page before spilling to overflow.
        let x = if is_table_leaf { usable.saturating_sub(35) } else { ((usable.saturating_sub(12)) * 64 / 255).saturating_sub(23) };
        let local = if payload_len <= x {
            payload_len
        } else {
            let m = ((usable.saturating_sub(12)) * 32 / 255).saturating_sub(23);
            let surplus = payload_len.saturating_sub(m);
            let denom = usable.saturating_sub(4).max(1);
            let k = m.saturating_add(surplus % denom);
            if k <= x { k } else { m }
        };
        let mut out = Vec::new();
        let first = self.data.get(local_off..local_off.checked_add(local)?)?;
        out.extend_from_slice(first);
        if local < payload_len {
            // The 4 bytes after the local part point at the first overflow page.
            let next_off = local_off.checked_add(local)?;
            let mut next = read_u32_be(self.data, next_off).unwrap_or(0);
            let per_page = usable.saturating_sub(4);
            let mut pages = 0usize;
            while next != 0 && out.len() < payload_len.min(MAX_CELL_SIZE) {
                if pages >= MAX_OVERFLOW_PAGES {
                    notes.push("An overflow chain was cut at the page cap; a value is partial.".into());
                    break;
                }
                pages += 1;
                let Some(pbase) = self.page_base(next) else { break };
                let Some(chunk) = self.data.get(pbase.checked_add(4)?..pbase.checked_add(4)?.checked_add(per_page).unwrap_or(pbase)) else {
                    break;
                };
                let remaining = payload_len.min(MAX_CELL_SIZE).saturating_sub(out.len());
                let take = remaining.min(chunk.len());
                out.extend_from_slice(chunk.get(..take)?);
                next = read_u32_be(self.data, pbase).unwrap_or(0);
            }
        }
        if out.len() < payload_len {
            notes.push("A cell payload was only partially read; some values are truncated or not read.".into());
        }
        Some(out)
    }
}

/// Decode a SQLite record (the "payload") into column values.
fn parse_record(payload: &[u8]) -> Vec<CellValue> {
    let mut out = Vec::new();
    let Some((hdr_len, n)) = varint(payload, 0) else { return out };
    let hdr_len = hdr_len as usize;
    if hdr_len > payload.len() || hdr_len < n {
        return out;
    }
    // First read the serial types from the header region.
    let mut types = Vec::new();
    let mut p = n;
    while p < hdr_len {
        let Some((st, used)) = varint(payload, p) else { break };
        types.push(st);
        p = match p.checked_add(used) {
            Some(v) => v,
            None => break,
        };
        if types.len() >= MAX_COLUMNS {
            break;
        }
    }
    // Then read each value from the body region.
    let mut body = hdr_len;
    for st in types {
        let (val, size) = decode_serial(st, payload, body);
        out.push(val);
        body = body.saturating_add(size);
    }
    out
}

/// Decode one serial-typed value at `off`; returns the value and its byte size.
fn decode_serial(serial: u64, data: &[u8], off: usize) -> (CellValue, usize) {
    let size = match serial {
        1..=4 => serial as usize,
        5 => 6,
        6 | 7 => 8,
        n if n >= 12 => usize::try_from((n - 12) / 2).unwrap_or(usize::MAX),
        _ => 0,
    };
    if off > data.len() || (off == data.len() && size != 0) {
        return (CellValue::NotRead, size);
    }
    if serial < 12 && size > data.len().saturating_sub(off) {
        return (CellValue::NotRead, size);
    }
    match serial {
        0 => (CellValue::Null, 0),
        1 => (int_be(data, off, 1), 1),
        2 => (int_be(data, off, 2), 2),
        3 => (int_be(data, off, 3), 3),
        4 => (int_be(data, off, 4), 4),
        5 => (int_be(data, off, 6), 6),
        6 => (int_be(data, off, 8), 8),
        7 => {
            let bytes: Option<[u8; 8]> = data.get(off..off.saturating_add(8)).and_then(|s| s.try_into().ok());
            (bytes.map(|b| CellValue::Real(f64::from_be_bytes(b))).unwrap_or(CellValue::Null), 8)
        }
        8 => (CellValue::Int(0), 0),
        9 => (CellValue::Int(1), 0),
        10 | 11 => (CellValue::Null, 0), // reserved for internal use.
        n if n >= 12 && n % 2 == 0 => {
            let len = size;
            let slice = data.get(off..off.saturating_add(len).min(data.len())).unwrap_or(&[]);
            let value = if slice.len() < len { CellValue::PartialBlob { len } } else { blob_value(slice, len) };
            (value, len)
        }
        _ => {
            // Odd and >= 13: text of (n-13)/2 bytes (encoding handled by the caller's DB header;
            // decoded here as UTF-8 lossily, which is correct for the common case).
            let len = size;
            let slice = data.get(off..off.saturating_add(len).min(data.len())).unwrap_or(&[]);
            let mut value = text_value(slice);
            if slice.len() < len
                && let CellValue::Text { truncated, .. } = &mut value
            {
                *truncated = true;
            }
            (value, len)
        }
    }
}

fn int_be(data: &[u8], off: usize, len: usize) -> CellValue {
    let Some(slice) = data.get(off..off.saturating_add(len)) else { return CellValue::Null };
    let mut v: i64 = if slice.first().is_some_and(|b| b & 0x80 != 0) { -1 } else { 0 };
    for &b in slice {
        v = (v << 8) | i64::from(b);
    }
    CellValue::Int(v)
}

fn text_value(slice: &[u8]) -> CellValue {
    let truncated = slice.len() > MAX_TEXT;
    let take = slice.get(..MAX_TEXT.min(slice.len())).unwrap_or(slice);
    CellValue::Text { text: String::from_utf8_lossy(take).into_owned(), truncated }
}

fn blob_value(slice: &[u8], len: usize) -> CellValue {
    use sha2::Digest as _;
    let digest = sha2::Sha256::digest(slice);
    let prefix: String = digest.iter().take(8).map(|b| format!("{b:02x}")).collect();
    CellValue::Blob { len, sha256_prefix: prefix }
}

fn is_without_rowid(sql: &str) -> bool {
    let Some(close) = sql.rfind(')') else { return false };
    sql_tokens(close.checked_add(1).and_then(|start| sql.get(start..)).unwrap_or(""))
        .windows(2)
        .any(|pair| pair.first().is_some_and(|s| s.eq_ignore_ascii_case("WITHOUT")) && pair.get(1).is_some_and(|s| s.eq_ignore_ascii_case("ROWID")))
}

/// Output-column positions in the stored record: PK columns first, then all remaining columns.
fn without_rowid_order(table: &SchemaObject) -> Option<Vec<usize>> {
    let open = table.sql.find('(')?;
    let close = table.sql.rfind(')')?;
    let body = table.sql.get(open.checked_add(1)?..close)?;
    let mut stored = Vec::new();
    for segment in split_top_level(body) {
        let tokens = sql_tokens(segment);
        let Some(pk) = tokens
            .windows(2)
            .position(|pair| pair.first().is_some_and(|s| s.eq_ignore_ascii_case("PRIMARY")) && pair.get(1).is_some_and(|s| s.eq_ignore_ascii_case("KEY")))
        else {
            continue;
        };
        let table_constraint = tokens.first().is_some_and(|s| s.eq_ignore_ascii_case("PRIMARY") || s.eq_ignore_ascii_case("CONSTRAINT"));
        let names: Vec<&str> = if table_constraint {
            let tail = tokens.get(pk.checked_add(3)?..)?;
            let end = tail.iter().position(|s| *s == ")")?;
            tail.get(..end)?.split(|s| *s == ",").filter_map(|part| part.first().copied()).collect()
        } else {
            vec![*tokens.first()?]
        };
        for token in names {
            let (name, _) = take_identifier(token);
            let position = table.columns.iter().position(|column| column.name.eq_ignore_ascii_case(&name))?;
            if !stored.contains(&position) {
                stored.push(position);
            }
        }
    }
    if stored.is_empty() {
        return None;
    }
    for i in 0..table.columns.len() {
        if !stored.contains(&i) {
            stored.push(i);
        }
    }
    (0..table.columns.len()).map(|i| stored.iter().position(|&column| column == i)).collect()
}

/// Parse column names and types from a CREATE TABLE statement (best effort, bounded).
pub fn parse_create_columns(sql: &str) -> Vec<Column> {
    column_definitions(sql).into_iter().map(|(column, _)| column).collect()
}

fn column_definitions(sql: &str) -> Vec<(Column, &str)> {
    let mut cols = Vec::new();
    // Take the text inside the outermost parentheses.
    let Some(open) = sql.find('(') else { return cols };
    let inner = &sql[open + 1..];
    let mut depth = 1usize;
    let mut end = inner.len();
    for token in sql_tokens(inner) {
        match token {
            "(" => depth = depth.saturating_add(1),
            ")" => depth = depth.saturating_sub(1),
            _ => {}
        }
        if depth == 0 {
            end = (token.as_ptr() as usize).saturating_sub(inner.as_ptr() as usize);
            break;
        }
    }
    let body = inner.get(..end).unwrap_or("");
    for seg in split_top_level(body) {
        if cols.len() >= MAX_COLUMNS {
            break;
        }
        let seg = seg.trim();
        if seg.is_empty() {
            continue;
        }
        // Skip table-level constraints.
        let first_word = seg.split([' ', '\t', '\n', '(']).next().unwrap_or("").to_ascii_uppercase();
        if matches!(first_word.as_str(), "CONSTRAINT" | "PRIMARY" | "UNIQUE" | "CHECK" | "FOREIGN" | "KEY") {
            continue;
        }
        let (name, rest) = take_identifier(seg);
        if name.is_empty() {
            continue;
        }
        let type_name = extract_type(rest.trim());
        cols.push((Column { name, type_name }, rest));
    }
    cols
}

/// Identify the single INTEGER primary key, excluding the column-level DESC exception.
fn rowid_alias_index(sql: &str) -> Option<usize> {
    let tokens = sql_tokens(sql);
    let is = |token: &&str, word: &str| token.eq_ignore_ascii_case(word);
    let open = tokens.iter().position(|t| *t == "(")?;
    let mut depth = 0usize;
    let close = tokens.iter().enumerate().skip(open).find_map(|(i, t)| {
        match *t {
            "(" => depth = depth.saturating_add(1),
            ")" => depth = depth.saturating_sub(1),
            _ => {}
        }
        (depth == 0).then_some(i)
    })?;
    let tail = tokens.get(close.saturating_add(1)..)?;
    if tail.windows(2).any(|w| w.first().is_some_and(|t| is(t, "WITHOUT")) && w.get(1).is_some_and(|t| is(t, "ROWID"))) {
        return None;
    }
    let columns = parse_create_columns(sql);
    let mut key = None;
    let mut column = 0usize;
    let body_start = open.saturating_add(1);
    let mut start = body_start;
    depth = 0;
    for i in body_start..=close {
        let token = *tokens.get(i)?;
        if i == close || (token == "," && depth == 0) {
            let mut segment = tokens.get(start..i)?;
            start = i.saturating_add(1);
            if segment.first().is_some_and(|t| is(t, "CONSTRAINT")) {
                segment = segment.get(2..)?;
            }
            if segment.first().is_some_and(|t| is(t, "PRIMARY")) {
                if key.is_some() || !segment.get(1).is_some_and(|t| is(t, "KEY")) || segment.get(2) != Some(&"(") {
                    return None;
                }
                let end = segment.iter().position(|t| *t == ")")?;
                let members = segment.get(3..end)?;
                if members.contains(&",") {
                    return None;
                }
                let (name, _) = take_identifier(members.first()?);
                key = Some(columns.iter().position(|c| c.name.eq_ignore_ascii_case(&name))?);
            } else if !segment.first().is_some_and(|t| ["UNIQUE", "CHECK", "FOREIGN"].iter().any(|word| is(t, word))) {
                let mut nesting = 0usize;
                for (j, t) in segment.iter().enumerate().skip(1) {
                    match *t {
                        "(" => nesting = nesting.saturating_add(1),
                        ")" => nesting = nesting.saturating_sub(1),
                        _ => {}
                    }
                    if nesting == 0 && is(t, "PRIMARY") && segment.get(j.saturating_add(1)).is_some_and(|t| is(t, "KEY")) {
                        if key.is_some() || segment.get(j.saturating_add(2)).is_some_and(|t| is(t, "DESC")) {
                            return None;
                        }
                        key = Some(column);
                    }
                }
                column = column.saturating_add(1);
            }
        } else {
            match token {
                "(" => depth = depth.saturating_add(1),
                ")" => depth = depth.saturating_sub(1),
                _ => {}
            }
        }
    }
    let index = key?;
    columns.get(index)?.type_name.eq_ignore_ascii_case("INTEGER").then_some(index)
}

/// Keep quoted text intact so defaults and constraint names cannot become SQL keywords.
fn sql_tokens(mut sql: &str) -> Vec<&str> {
    let mut tokens = Vec::new();
    while !sql.is_empty() {
        sql = sql.trim_start();
        if sql.is_empty() {
            break;
        }
        if sql.starts_with("--") {
            sql = sql.get(sql.find('\n').unwrap_or(sql.len())..).unwrap_or("");
            continue;
        }
        if sql.starts_with("/*") {
            sql = sql.get(2..).and_then(|s| s.find("*/").and_then(|end| s.get(end.saturating_add(2)..))).unwrap_or("");
            continue;
        }
        let mut chars = sql.char_indices().peekable();
        let Some((_, first)) = chars.next() else { break };
        let mut end = first.len_utf8();
        if matches!(first, '\'' | '"' | '`' | '[') {
            let quote = if first == '[' { ']' } else { first };
            while let Some((i, c)) = chars.next() {
                end = i.saturating_add(c.len_utf8());
                if c == quote {
                    if first != '[' && chars.peek().is_some_and(|(_, c)| *c == quote) {
                        if let Some((i, c)) = chars.next() {
                            end = i.saturating_add(c.len_utf8());
                        }
                    } else {
                        break;
                    }
                }
            }
        } else if !matches!(first, '(' | ')' | ',' | '/') {
            end = sql.find(|c: char| c.is_whitespace() || matches!(c, '(' | ')' | ',' | '\'' | '"' | '`' | '[' | '/')).unwrap_or(sql.len());
        }
        tokens.push(sql.get(..end).unwrap_or(""));
        sql = sql.get(end..).unwrap_or("");
    }
    tokens
}

/// Missing trailing fields use literal defaults; expressions remain explicitly unknown.
fn column_default(rest: &str) -> (CellValue, bool) {
    let tokens = sql_tokens(rest);
    let mut depth = 0usize;
    for (i, token) in tokens.iter().enumerate() {
        if depth == 0 && token.eq_ignore_ascii_case("DEFAULT") {
            return tokens.get(i.saturating_add(1)..).and_then(literal_default).map(|v| (v, true)).unwrap_or((CellValue::Null, false));
        }
        match *token {
            "(" => depth = depth.saturating_add(1),
            ")" => depth = depth.saturating_sub(1),
            _ => {}
        }
    }
    (CellValue::Null, true)
}

fn literal_default(tokens: &[&str]) -> Option<CellValue> {
    let token = *tokens.first()?;
    if token.eq_ignore_ascii_case("NULL") {
        return Some(CellValue::Null);
    }
    if token.eq_ignore_ascii_case("TRUE") || token.eq_ignore_ascii_case("FALSE") {
        return Some(CellValue::Int(i64::from(token.eq_ignore_ascii_case("TRUE"))));
    }
    if token.starts_with('\'') && token.ends_with('\'') && token.len() >= 2 {
        return Some(text_value(token.get(1..token.len().checked_sub(1)?)?.replace("''", "'").as_bytes()));
    }
    if token.eq_ignore_ascii_case("X") {
        let quoted = *tokens.get(1)?;
        if !quoted.starts_with('\'') || !quoted.ends_with('\'') || quoted.len() < 2 {
            return None;
        }
        let hex = quoted.get(1..quoted.len().checked_sub(1)?)?;
        if !hex.len().is_multiple_of(2) {
            return None;
        }
        let bytes: Option<Vec<u8>> = hex
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| {
                let high = char::from(*pair.first()?).to_digit(16)?;
                let low = char::from(*pair.get(1)?).to_digit(16)?;
                Some((high * 16 + low) as u8)
            })
            .collect();
        let bytes = bytes?;
        return Some(blob_value(&bytes, bytes.len()));
    }
    let number = if matches!(token, "+" | "-") {
        let value = *tokens.get(1)?;
        format!("{token}{value}")
    } else {
        token.to_owned()
    };
    if !number.bytes().all(|b| b.is_ascii_digit() || matches!(b, b'+' | b'-' | b'.' | b'e' | b'E')) {
        return None;
    }
    if let Ok(n) = number.parse::<i64>() {
        return Some(CellValue::Int(n));
    }
    number.parse::<f64>().ok().filter(|n| n.is_finite()).map(CellValue::Real)
}

/// Split on top-level commas (ignoring commas inside parentheses).
fn split_top_level(s: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut depth = 0i32;
    let mut start = 0usize;
    let mut in_quote: Option<char> = None;
    for (i, c) in s.char_indices() {
        if let Some(q) = in_quote {
            if c == q {
                in_quote = None;
            }
            continue;
        }
        match c {
            '\'' | '"' | '`' => in_quote = Some(c),
            '[' => depth += 1,
            ']' => depth -= 1,
            '(' => depth += 1,
            ')' => depth -= 1,
            ',' if depth == 0 => {
                out.push(s.get(start..i).unwrap_or(""));
                start = i + 1;
            }
            _ => {}
        }
        if out.len() >= MAX_COLUMNS {
            return out;
        }
    }
    out.push(s.get(start..).unwrap_or(""));
    out
}

/// Take the leading column identifier (handling "quoted", `back-ticked`, [bracketed] names).
fn take_identifier(seg: &str) -> (String, &str) {
    let seg = seg.trim_start();
    let mut chars = seg.char_indices();
    match chars.next() {
        Some((_, q @ ('"' | '`'))) => {
            // Quoted: read to the closing quote (doubled quote = literal, kept simple).
            for (i, c) in chars {
                if c == q {
                    let name = seg.get(1..i).unwrap_or("").replace(&format!("{q}{q}"), &q.to_string());
                    return (name, seg.get(i + 1..).unwrap_or(""));
                }
            }
            (seg.get(1..).unwrap_or("").to_string(), "")
        }
        Some((_, '[')) => {
            if let Some(close) = seg.find(']') {
                return (seg.get(1..close).unwrap_or("").to_string(), seg.get(close + 1..).unwrap_or(""));
            }
            (seg.get(1..).unwrap_or("").to_string(), "")
        }
        Some(_) => {
            let endp = seg.find([' ', '\t', '\n', '(', ',']).unwrap_or(seg.len());
            (seg.get(..endp).unwrap_or("").to_string(), seg.get(endp..).unwrap_or(""))
        }
        None => (String::new(), ""),
    }
}

/// The type name is the run of tokens before the first column-constraint keyword.
fn extract_type(rest: &str) -> String {
    let mut out = String::new();
    let mut depth = 0i32;
    for tok in rest.split_whitespace() {
        let upper = tok.trim_end_matches(',').to_ascii_uppercase();
        if depth == 0
            && matches!(
                upper.as_str(),
                "PRIMARY" | "NOT" | "NULL" | "UNIQUE" | "CHECK" | "DEFAULT" | "COLLATE" | "REFERENCES" | "GENERATED" | "AS" | "CONSTRAINT" | "AUTOINCREMENT"
            )
        {
            break;
        }
        depth += tok.matches('(').count() as i32;
        depth -= tok.matches(')').count() as i32;
        if !out.is_empty() {
            out.push(' ');
        }
        out.push_str(tok.trim_end_matches(','));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn payload_cap_case(case: u8) {
        use craft_anything_testkit::sqlite::{Val, overflow_row_db};
        use sha2::Digest as _;
        let values = match case {
            1 => vec![Val::Text("x".repeat(8_000_000))],
            2 => vec![Val::Text("x".repeat(8_400_000))],
            3 => vec![Val::Blob(vec![0x5a; 8_400_000])],
            4 => vec![Val::Text("x".repeat(4_300_000)), Val::Blob(vec![0x5a; 4_300_000])],
            5 => vec![Val::Int(42), Val::Blob(vec![0x5a; 8_400_000]), Val::Int(73)],
            6 => vec![Val::Blob(vec![0x5a; 1_000_000])],
            _ => panic!("unknown payload-cap case"),
        };
        let bytes = overflow_row_db(&values);
        let db = SqliteDb::parse(&bytes).expect("fixture parses");
        let page = db.read_rows(2, 0, 1);
        assert_eq!(page.rows.len(), 1);
        let row = &page.rows[0];
        assert_eq!(row.values.len(), values.len(), "d{case}: every column is present");
        for (i, source) in values.iter().enumerate() {
            let value = serde_json::to_value(&row.values[i]).expect("serializes");
            match source {
                Val::Text(_) => assert_eq!(value, serde_json::json!({"text": "x".repeat(MAX_TEXT), "truncated": true}), "d{case}: text prefix"),
                Val::Blob(blob) => {
                    assert_eq!(value["blob_len"], blob.len(), "d{case}: true blob length");
                    if case == 6 {
                        let hash: String = sha2::Sha256::digest(blob).iter().take(8).map(|b| format!("{b:02x}")).collect();
                        assert_eq!(value, serde_json::json!({"blob_len": blob.len(), "sha256_prefix": hash}));
                    } else {
                        assert_eq!(value["truncated"], true, "d{case}: partial blob marked");
                        assert!(value.get("sha256_prefix").is_none_or(serde_json::Value::is_null), "d{case}: no partial hash");
                    }
                }
                Val::Int(n) if i == 0 => assert_eq!(value, *n),
                Val::Int(_) => assert_eq!(value, serde_json::json!({"not_read": true})),
                _ => panic!("unexpected payload-cap fixture value"),
            }
        }
        assert_eq!(page.notes.is_empty(), matches!(case, 1 | 6), "d{case}: cap disclosure");
    }

    #[test]
    fn payload_cap_d1() {
        payload_cap_case(1);
    }
    #[test]
    fn payload_cap_d2() {
        payload_cap_case(2);
    }
    #[test]
    fn payload_cap_d3() {
        payload_cap_case(3);
    }
    #[test]
    fn payload_cap_d4() {
        payload_cap_case(4);
    }
    #[test]
    fn payload_cap_d5() {
        payload_cap_case(5);
    }
    #[test]
    fn payload_cap_d6() {
        payload_cap_case(6);
    }

    #[test]
    fn payload_cap_d7_without_rowid() {
        use craft_anything_testkit::sqlite::{Val, without_rowid_db};
        let bytes = without_rowid_db(
            "CREATE TABLE t(v BLOB, k INT PRIMARY KEY, tail INT) WITHOUT ROWID",
            &[vec![Val::Int(42), Val::Blob(vec![0x5a; 8_400_000]), Val::Int(73)]],
        );
        let page = SqliteDb::parse(&bytes).expect("fixture").read_rows(2, 0, 10);
        assert_eq!(page.rows.len(), 1, "d7: capped index rows must remain present");
        assert_eq!(page.rows[0].rowid, None);
        assert_eq!(
            serde_json::to_value(&page.rows[0].values).unwrap(),
            serde_json::json!([
                {"blob_len": 8_400_000, "truncated": true}, 42, {"not_read": true}
            ])
        );
        assert!(!page.notes.is_empty(), "d7: cap disclosure");
    }

    fn short_record_case(declarations: &str, defaults: Vec<CellValue>, note: bool) {
        use craft_anything_testkit::sqlite::{Val, table_db};
        let mut full = vec![Val::Int(2)];
        full.extend(defaults.iter().map(|v| match v {
            CellValue::Int(n) => Val::Int(*n),
            CellValue::Real(n) => Val::Real(*n),
            CellValue::Text { text, .. } => Val::Text(text.clone()),
            CellValue::Blob { .. } => Val::Blob(vec![0, 255]),
            CellValue::Null => Val::Null,
            _ => panic!("unexpected default fixture value"),
        }));
        let bytes = table_db(&format!("CREATE TABLE t(n INT, {declarations})"), &[(1, vec![Val::Int(1)]), (2, full)]);
        let db = SqliteDb::parse(&bytes).expect("fixture");
        let page = db.read_rows(2, 0, 10);
        let mut expected = vec![CellValue::Int(1)];
        expected.extend(defaults.clone());
        assert_eq!(page.rows[0].values, expected, "old record must include trailing defaults");
        expected[0] = CellValue::Int(2);
        assert_eq!(page.rows[1].values, expected, "full record must stay unchanged");
        assert_eq!(!page.notes.is_empty(), note, "unsupported defaults must be disclosed");
    }

    #[test]
    fn added_columns_c1_integer() {
        short_record_case("x INT DEFAULT 42", vec![CellValue::Int(42)], false);
    }
    #[test]
    fn added_columns_c2_null() {
        short_record_case("x INT", vec![CellValue::Null], false);
    }
    #[test]
    fn added_columns_c3_real_text() {
        short_record_case("x REAL DEFAULT -1.5, y TEXT DEFAULT 'it''s'", vec![CellValue::Real(-1.5), text_value(b"it's")], false);
    }
    #[test]
    fn added_columns_c4_blob() {
        short_record_case("x BLOB DEFAULT X'00ff'", vec![blob_value(&[0, 255], 2)], false);
    }
    #[test]
    fn added_columns_c7_expression() {
        short_record_case("d TEXT DEFAULT (lower('A'))", vec![CellValue::Null], true);
    }
    #[test]
    fn added_columns_c5_rewritten_control() {
        use craft_anything_testkit::sqlite::{Val, table_db};
        let bytes = table_db("CREATE TABLE t(n INT, x INT DEFAULT 42)", &[(1, vec![Val::Int(1), Val::Int(42)])]);
        let page = SqliteDb::parse(&bytes).expect("fixture").read_rows(2, 0, 10);
        assert_eq!(page.rows[0].values, vec![CellValue::Int(1), CellValue::Int(42)]);
        assert!(page.notes.is_empty());
    }

    #[test]
    fn added_columns_literal_forms_and_unknowns() {
        for (declaration, value) in [
            ("x INT DEFAULT +42 NOT NULL", CellValue::Int(42)),
            ("x INT DEFAULT - 42", CellValue::Int(-42)),
            ("x REAL DEFAULT + 1.25e-2", CellValue::Real(0.0125)),
            ("x INT DEFAULT true", CellValue::Int(1)),
            ("x INT DEFAULT FALSE", CellValue::Int(0)),
            ("x DEFAULT null", CellValue::Null),
            ("x TEXT DEFAULT 'a),b''c'", text_value(b"a),b'c")),
            ("x INT CHECK(x <> 'DEFAULT') DEFAULT /* literal */ 7", CellValue::Int(7)),
        ] {
            short_record_case(declaration, vec![value], false);
        }
        for declaration in ["x TEXT DEFAULT CURRENT_TIMESTAMP", "x DEFAULT (42)", "x DEFAULT (lower('A'))", "x DEFAULT X'zz'"] {
            short_record_case(declaration, vec![CellValue::Null], true);
        }
        assert_eq!(blob_value(&[0, 255], 2), CellValue::Blob { len: 2, sha256_prefix: "06eb7d6a69ee19e5".into() });
        assert_eq!(literal_default(&sql_tokens("x''")), Some(blob_value(&[], 0)));
    }

    #[test]
    fn added_columns_preserve_stored_nulls_and_long_records() {
        use craft_anything_testkit::sqlite::{Val, table_db};
        let bytes = table_db("CREATE TABLE t(n INT, x INT DEFAULT 42)", &[(1, vec![Val::Int(1), Val::Null]), (2, vec![Val::Int(2), Val::Int(7), Val::Int(9)])]);
        let page = SqliteDb::parse(&bytes).expect("fixture").read_rows(2, 0, 10);
        assert_eq!(page.rows[0].values, vec![CellValue::Int(1), CellValue::Null]);
        assert_eq!(page.rows[1].values, vec![CellValue::Int(2), CellValue::Int(7), CellValue::Int(9)]);
        assert!(page.notes.is_empty());
    }

    #[test]
    fn added_columns_c6_short_rowid_alias() {
        use craft_anything_testkit::sqlite::{Val, table_db};
        for stored in [vec![Val::Null, Val::Int(10)], vec![]] {
            let bytes = table_db("CREATE TABLE t(id INTEGER PRIMARY KEY, n INT DEFAULT 10, x INT DEFAULT 42)", &[(7, stored)]);
            let page = SqliteDb::parse(&bytes).expect("fixture").read_rows(2, 0, 10);
            assert_eq!(page.rows[0].rowid, Some(7));
            assert_eq!(page.rows[0].values, vec![CellValue::Int(7), CellValue::Int(10), CellValue::Int(42)]);
            assert!(page.notes.is_empty());
        }
    }

    #[test]
    fn version_formatting() {
        assert_eq!(version_string(3_045_001), "3.45.1");
        assert_eq!(version_string(3_008_000), "3.8.0");
    }

    #[test]
    fn varint_round_trip() {
        assert_eq!(varint(&[0x00], 0), Some((0, 1)));
        assert_eq!(varint(&[0x7f], 0), Some((127, 1)));
        assert_eq!(varint(&[0x81, 0x00], 0), Some((128, 2)));
        assert_eq!(varint(&[0xff; 9], 0).map(|(_, n)| n), Some(9));
        assert_eq!(varint(&[0x80], 0), None); // never terminates within range
    }

    #[test]
    fn column_parsing() {
        let cols = parse_create_columns("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT NOT NULL, bio, price REAL DEFAULT 0)");
        assert_eq!(cols.len(), 4);
        assert_eq!(cols[0].name, "id");
        assert_eq!(cols[0].type_name, "INTEGER");
        assert_eq!(cols[1].name, "name");
        assert_eq!(cols[1].type_name, "TEXT");
        assert_eq!(cols[2].name, "bio");
        assert_eq!(cols[2].type_name, "");
        assert_eq!(cols[3].type_name, "REAL");
    }

    #[test]
    fn column_parsing_quoted_and_constraints() {
        let cols = parse_create_columns("CREATE TABLE \"my tbl\" (\"first name\" VARCHAR(50), [odd] NUMERIC, PRIMARY KEY(\"first name\"))");
        assert_eq!(cols.len(), 2);
        assert_eq!(cols[0].name, "first name");
        assert_eq!(cols[0].type_name, "VARCHAR(50)");
        assert_eq!(cols[1].name, "odd");
        assert_eq!(cols[1].type_name, "NUMERIC");
    }

    #[test]
    fn rejects_non_sqlite() {
        assert!(SqliteDb::parse(b"not a database").is_err());
        assert!(SqliteDb::parse(&[]).is_err());
        assert!(!is_sqlite(b"SQLite format 2\0"));
    }

    #[test]
    fn reads_fixture_overview_schema_and_rows() {
        let db = craft_anything_testkit::sqlite::simple_db();
        let parsed = SqliteDb::parse(&db).expect("fixture parses");
        let ov = parsed.overview();
        assert_eq!(ov.header.page_size, 4096);
        assert_eq!(ov.header.text_encoding, "utf-8");
        assert_eq!(ov.header.sqlite_version, "3.45.1");
        assert_eq!(ov.page_count_from_size, 2);
        assert!(!ov.header.wal_mode);
        assert_eq!(ov.schema.len(), 1);
        let items = &ov.schema[0];
        assert_eq!(items.obj_type, "table");
        assert_eq!(items.name, "items");
        assert_eq!(items.rootpage, 2);
        assert_eq!(items.columns.len(), 4);
        assert_eq!(items.columns[0].name, "id");
        assert_eq!(items.columns[3].type_name, "BLOB");

        let count = parsed.count_rows(items.rootpage);
        assert_eq!(count.count, 3);
        assert!(!count.bounded);

        let page = parsed.read_rows(items.rootpage, 0, 10);
        assert_eq!(page.rows.len(), 3);
        assert_eq!(page.rows[0].rowid, Some(1));
        assert_eq!(page.rows[0].values[0], CellValue::Int(1));
        assert_eq!(page.rows[0].values[1], CellValue::Text { text: "alpha".into(), truncated: false });
        assert_eq!(page.rows[0].values[2], CellValue::Real(1.5));
        match &page.rows[0].values[3] {
            CellValue::Blob { len, .. } => assert_eq!(*len, 4),
            other => panic!("expected blob, got {other:?}"),
        }
        assert_eq!(page.rows[1].values[3], CellValue::Null);

        // Paging: offset 1, limit 1 yields the second row only.
        let mid = parsed.read_rows(items.rootpage, 1, 1);
        assert_eq!(mid.rows.len(), 1);
        assert_eq!(mid.rows[0].rowid, Some(2));

        // find_object is case-insensitive.
        assert!(parsed.find_object("ITEMS").is_some());
        assert!(parsed.find_object("nope").is_none());
    }

    #[test]
    fn wal_mode_is_reported() {
        let db = craft_anything_testkit::sqlite::wal_mode_db();
        let parsed = SqliteDb::parse(&db).expect("parses");
        assert!(parsed.header().wal_mode);
        assert!(parsed.overview().integrity_notes.iter().any(|n| n.contains("WAL")));
    }

    fn check_rowid_alias(declaration: &str, column: usize, alias: bool) {
        use craft_anything_testkit::sqlite::{Val, table_db};
        let sql = format!("CREATE TABLE t({declaration})");
        let columns = parse_create_columns(&sql);
        let rows: Vec<_> = [-3, 7]
            .into_iter()
            .map(|rowid| {
                let mut values = vec![Val::Text("x".into()); columns.len()];
                values[column] = Val::Null;
                (rowid, values)
            })
            .collect();
        let bytes = table_db(&sql, &rows);
        let db = SqliteDb::parse(&bytes).expect("fixture parses");
        let page = db.read_rows(2, 0, 10);
        assert_eq!(page.rows.len(), 2);
        for (row, (rowid, _)) in page.rows.iter().zip(&rows) {
            assert_eq!(row.rowid, Some(*rowid));
            let mut expected = vec![CellValue::Text { text: "x".into(), truncated: false }; columns.len()];
            expected[column] = if alias { CellValue::Int(*rowid) } else { CellValue::Null };
            assert_eq!(row.values, expected, "{declaration}, rowid {rowid}");
        }
        // Even an alias must preserve a non-NULL stored value.
        let mut values = vec![Val::Null; columns.len()];
        values[column] = Val::Int(99);
        let bytes = table_db(&sql, &[(7, values)]);
        let db = SqliteDb::parse(&bytes).expect("fixture parses");
        assert_eq!(db.read_rows(2, 0, 1).rows[0].values[column], CellValue::Int(99));
    }

    #[test]
    fn integer_primary_key_aliases_show_the_rowid() {
        // (declaration, column, is an alias): the rule from SQLite's CREATE TABLE docs.
        for (declaration, column, alias) in [
            ("id INTEGER PRIMARY KEY, v TEXT", 0, true),
            ("id integer primary key, v text", 0, true),
            ("id INTEGER, v TEXT, PRIMARY KEY(id)", 0, true),
            ("id INTEGER PRIMARY KEY DESC, v TEXT", 0, false),
            ("id INT PRIMARY KEY, v TEXT", 0, false),
            ("v TEXT, id INTEGER PRIMARY KEY, w TEXT", 1, true),
            ("id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT", 0, true),
            ("a INTEGER, b INTEGER, PRIMARY KEY(a, b)", 0, false),
            ("id INTEGER PRIMARY KEY ASC, v TEXT", 0, true),
            ("id INTEGER NOT NULL PRIMARY KEY, v TEXT", 0, true),
            ("id BIGINT PRIMARY KEY, v TEXT", 0, false),
            ("id INTEGER, v TEXT, CONSTRAINT pk PRIMARY KEY(id DESC)", 0, true),
        ] {
            check_rowid_alias(declaration, column, alias);
        }
    }

    #[test]
    fn a_without_rowid_table_has_no_rowid_alias() {
        // Read through the index b-tree (database_tools `without_rowid_b4_integer_key` covers the rows).
        assert_eq!(rowid_alias_index("CREATE TABLE t(id INTEGER PRIMARY KEY) WITHOUT ROWID"), None);
        assert_eq!(rowid_alias_index("CREATE TABLE t(id INTEGER PRIMARY KEY)"), Some(0));
    }

    #[test]
    fn truncation_never_panics() {
        let db = craft_anything_testkit::sqlite::simple_db();
        for cut in 0..db.len() {
            let slice = &db[..cut];
            if let Ok(parsed) = SqliteDb::parse(slice) {
                let ov = parsed.overview();
                for obj in &ov.schema {
                    let _ = parsed.count_rows(obj.rootpage);
                    let _ = parsed.read_rows(obj.rootpage, 0, 50);
                }
                // Also walk pages that may no longer exist.
                let _ = parsed.count_rows(2);
                let _ = parsed.read_rows(2, 0, 50);
            }
        }
    }

    #[test]
    fn mutation_fuzz_never_panics() {
        let base = craft_anything_testkit::sqlite::simple_db();
        // Deterministic LCG so the test is reproducible.
        let mut state: u64 = 0x1234_5678_9abc_def0;
        let mut next = || {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            state
        };
        for _ in 0..4000 {
            let mut db = base.clone();
            let flips = (next() % 8) as usize + 1;
            for _ in 0..flips {
                let idx = (next() as usize) % db.len();
                db[idx] = (next() & 0xff) as u8;
            }
            if let Ok(parsed) = SqliteDb::parse(&db) {
                let ov = parsed.overview();
                for obj in ov.schema.iter().take(16) {
                    let _ = parsed.count_rows(obj.rootpage);
                    let _ = parsed.read_rows(obj.rootpage, 0, 100);
                }
                let _ = parsed.read_rows(2, 0, 100);
            }
        }
    }

    #[test]
    fn without_rowid_damaged_pages_never_panic() {
        use craft_anything_testkit::sqlite::{Val, without_rowid_db};
        let rows = (0..9).map(|i| vec![Val::Int(i), Val::Text("x".repeat(2000))]).collect::<Vec<_>>();
        let base = without_rowid_db("CREATE TABLE t(k INT PRIMARY KEY, v TEXT) WITHOUT ROWID", &rows);
        for cut in (100..base.len()).step_by(31) {
            let db = SqliteDb::parse(&base[..cut]).unwrap();
            let _ = db.count_rows(2);
            let _ = db.read_rows(2, 1, 20);
        }
        for off in 4096..4120 {
            for value in [0, 2, 10, 255] {
                let mut bytes = base.clone();
                bytes[off] = value;
                let db = SqliteDb::parse(&bytes).unwrap();
                let _ = db.count_rows(2);
                let _ = db.read_rows(2, 0, 20);
            }
        }
    }

    #[test]
    fn decode_serial_types() {
        assert_eq!(decode_serial(0, &[], 0).0, CellValue::Null);
        assert_eq!(decode_serial(8, &[], 0).0, CellValue::Int(0));
        assert_eq!(decode_serial(9, &[], 0).0, CellValue::Int(1));
        assert_eq!(decode_serial(1, &[0xff], 0).0, CellValue::Int(-1));
        assert_eq!(decode_serial(2, &[0x01, 0x00], 0).0, CellValue::Int(256));
        // text: serial 13 -> (13-13)/2 = 0 bytes; serial 19 -> 3 bytes
        assert_eq!(decode_serial(19, b"abc", 0), (CellValue::Text { text: "abc".into(), truncated: false }, 3));
        // blob: serial 18 -> (18-12)/2 = 3 bytes
        match decode_serial(18, b"xyz", 0).0 {
            CellValue::Blob { len, .. } => assert_eq!(len, 3),
            other => panic!("expected blob, got {other:?}"),
        }
    }
}
