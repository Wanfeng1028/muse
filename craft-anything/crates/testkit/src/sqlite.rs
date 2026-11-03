//! Hand-built, minimal but valid SQLite 3 database files for tests. No `rusqlite`/C dependency:
//! the bytes are assembled directly so the pure-Rust reader has something real to read.
//!
//! The default fixture has one table `items(id INTEGER, name TEXT, score REAL, blob BLOB)` with
//! three rows across two pages (page 1 = database header + `sqlite_schema` leaf, page 2 = the
//! `items` leaf b-tree).

/// Page size used by the fixtures.
pub const PAGE_SIZE: usize = 4096;
/// The CREATE statement stored in `sqlite_schema` for the `items` table.
pub const ITEMS_SQL: &str = "CREATE TABLE items(id INTEGER, name TEXT, score REAL, data BLOB)";

/// A value to encode into a record.
#[derive(Debug, Clone)]
pub enum Val {
    Null,
    Int(i64),
    Real(f64),
    Text(String),
    Blob(Vec<u8>),
}

fn sqlite_varint(mut v: u64) -> Vec<u8> {
    if v > 0x00ff_ffff_ffff_ffff {
        let mut out = vec![0u8; 9];
        out[8] = v as u8;
        v >>= 8;
        for byte in out[..8].iter_mut().rev() {
            *byte = (v as u8 & 0x7f) | 0x80;
            v >>= 7;
        }
        return out;
    }
    if v == 0 {
        return vec![0];
    }
    let mut groups = Vec::new();
    while v > 0 {
        groups.push((v & 0x7f) as u8);
        v >>= 7;
    }
    groups.reverse();
    let n = groups.len();
    let mut out = Vec::with_capacity(n);
    for (i, g) in groups.iter().enumerate() {
        if i + 1 < n {
            out.push(g | 0x80);
        } else {
            out.push(*g);
        }
    }
    out
}

/// Build a record (payload): serial-type header followed by the value bodies.
pub fn build_record(values: &[Val]) -> Vec<u8> {
    let mut serials: Vec<u64> = Vec::new();
    let mut body: Vec<u8> = Vec::new();
    for v in values {
        match v {
            Val::Null => serials.push(0),
            Val::Int(n) => {
                serials.push(6); // 8-byte big-endian signed integer
                body.extend_from_slice(&n.to_be_bytes());
            }
            Val::Real(f) => {
                serials.push(7);
                body.extend_from_slice(&f.to_be_bytes());
            }
            Val::Text(s) => {
                serials.push(13 + 2 * s.len() as u64);
                body.extend_from_slice(s.as_bytes());
            }
            Val::Blob(b) => {
                serials.push(12 + 2 * b.len() as u64);
                body.extend_from_slice(b);
            }
        }
    }
    // Header = varint(header_length) + serial varints. header_length includes its own varint,
    // which may change its own width; iterate to a fixed point (at most twice in practice).
    let serial_bytes: Vec<u8> = serials.iter().flat_map(|s| sqlite_varint(*s)).collect();
    let mut hdr_len = serial_bytes.len() + 1;
    loop {
        let prefix = sqlite_varint(hdr_len as u64);
        let total = prefix.len() + serial_bytes.len();
        if total == hdr_len {
            let mut out = prefix;
            out.extend_from_slice(&serial_bytes);
            out.extend_from_slice(&body);
            return out;
        }
        hdr_len = total;
    }
}

/// Build a table-leaf b-tree page body (type 0x0d) from (rowid, record) cells, written into a
/// region that begins at `header_off` within a `PAGE_SIZE` page and runs to the page end.
fn write_table_leaf(page: &mut [u8], header_off: usize, cells: &[(i64, Vec<u8>)]) {
    let ncells = cells.len();
    // Place cell content from the end of the page downward.
    let mut content_top = PAGE_SIZE;
    let mut pointers: Vec<u16> = Vec::with_capacity(ncells);
    for (rowid, record) in cells {
        let mut cell = sqlite_varint(record.len() as u64);
        cell.extend_from_slice(&sqlite_varint(*rowid as u64));
        cell.extend_from_slice(record);
        content_top -= cell.len();
        page[content_top..content_top + cell.len()].copy_from_slice(&cell);
        pointers.push(content_top as u16);
    }
    // B-tree header (8 bytes for a leaf).
    page[header_off] = 0x0d; // leaf table b-tree page
    page[header_off + 1] = 0; // first freeblock (none)
    page[header_off + 2] = 0;
    page[header_off + 3..header_off + 5].copy_from_slice(&(ncells as u16).to_be_bytes());
    let cc = if content_top == 65536 { 0u16 } else { content_top as u16 };
    page[header_off + 5..header_off + 7].copy_from_slice(&cc.to_be_bytes());
    page[header_off + 7] = 0; // fragmented free bytes
    // Cell pointer array, right after the header.
    let mut p = header_off + 8;
    for ptr in pointers {
        page[p..p + 2].copy_from_slice(&ptr.to_be_bytes());
        p += 2;
    }
}

/// Write the 100-byte database header into the start of page 1.
fn write_db_header(page: &mut [u8], page_count: u32) {
    page[..16].copy_from_slice(b"SQLite format 3\0");
    // page size (16, u16 be): 4096 fits directly.
    page[16..18].copy_from_slice(&(PAGE_SIZE as u16).to_be_bytes());
    page[18] = 1; // write version: legacy (rollback journal)
    page[19] = 1; // read version: legacy
    page[20] = 0; // reserved bytes per page
    page[21] = 64; // max embedded payload fraction
    page[22] = 32; // min embedded payload fraction
    page[23] = 32; // leaf payload fraction
    page[24..28].copy_from_slice(&1u32.to_be_bytes()); // file change counter
    page[28..32].copy_from_slice(&page_count.to_be_bytes()); // db size in pages
    page[32..36].copy_from_slice(&0u32.to_be_bytes()); // first freelist trunk page
    page[36..40].copy_from_slice(&0u32.to_be_bytes()); // freelist pages
    page[40..44].copy_from_slice(&1u32.to_be_bytes()); // schema cookie
    page[44..48].copy_from_slice(&4u32.to_be_bytes()); // schema format number
    page[48..52].copy_from_slice(&0u32.to_be_bytes()); // default page cache size
    page[52..56].copy_from_slice(&0u32.to_be_bytes()); // largest root b-tree page
    page[56..60].copy_from_slice(&1u32.to_be_bytes()); // text encoding: UTF-8
    page[60..64].copy_from_slice(&0u32.to_be_bytes()); // user version
    page[64..68].copy_from_slice(&0u32.to_be_bytes()); // incremental vacuum
    page[68..72].copy_from_slice(&0u32.to_be_bytes()); // application id
    // bytes 72..92 reserved, left zero.
    page[92..96].copy_from_slice(&1u32.to_be_bytes()); // version valid for
    page[96..100].copy_from_slice(&3_045_001u32.to_be_bytes()); // SQLITE_VERSION_NUMBER (3.45.1)
}

/// A minimal valid database: `items` with three rows. Page 1 holds the schema, page 2 the table.
pub fn simple_db() -> Vec<u8> {
    let page_count = 2u32;
    let mut file = vec![0u8; PAGE_SIZE * page_count as usize];

    // Page 2: the items table leaf.
    let rows: Vec<(i64, Vec<u8>)> = vec![
        (1, build_record(&[Val::Int(1), Val::Text("alpha".into()), Val::Real(1.5), Val::Blob(vec![0xde, 0xad, 0xbe, 0xef])])),
        (2, build_record(&[Val::Int(2), Val::Text("beta".into()), Val::Real(-2.0), Val::Null])),
        (3, build_record(&[Val::Int(3), Val::Text("gamma".into()), Val::Null, Val::Blob(vec![0x01; 10])])),
    ];
    {
        let page2 = &mut file[PAGE_SIZE..PAGE_SIZE * 2];
        write_table_leaf(page2, 0, &rows);
    }

    // Page 1: database header + sqlite_schema leaf (b-tree header at offset 100).
    let schema_record = build_record(&[
        Val::Text("table".into()),
        Val::Text("items".into()),
        Val::Text("items".into()),
        Val::Int(2), // rootpage
        Val::Text(ITEMS_SQL.into()),
    ]);
    {
        let page1 = &mut file[..PAGE_SIZE];
        write_db_header(page1, page_count);
        write_table_leaf(page1, 100, &[(1, schema_record)]);
    }
    file
}

/// A two-page database with one table named `t` and explicitly stored rowids and values.
pub fn table_db(sql: &str, rows: &[(i64, Vec<Val>)]) -> Vec<u8> {
    let mut file = vec![0u8; PAGE_SIZE * 2];
    let cells: Vec<_> = rows.iter().map(|(rowid, values)| (*rowid, build_record(values))).collect();
    write_table_leaf(&mut file[PAGE_SIZE..], 0, &cells);
    let schema = build_record(&[Val::Text("table".into()), Val::Text("t".into()), Val::Text("t".into()), Val::Int(2), Val::Text(sql.into())]);
    write_db_header(&mut file[..PAGE_SIZE], 2);
    write_table_leaf(&mut file[..PAGE_SIZE], 100, &[(1, schema)]);
    file
}

/// Build one table row, spilling its record over a chain of overflow pages.
pub fn overflow_row_db(values: &[Val]) -> Vec<u8> {
    let record = build_record(values);
    let max_local = PAGE_SIZE - 35;
    let min_local = (PAGE_SIZE - 12) * 32 / 255 - 23;
    let candidate = min_local + (record.len().saturating_sub(min_local) % (PAGE_SIZE - 4));
    let local = if record.len() <= max_local {
        record.len()
    } else if candidate <= max_local {
        candidate
    } else {
        min_local
    };
    let overflow = &record[local..];
    let pages = 2 + overflow.len().div_ceil(PAGE_SIZE - 4);
    let mut file = vec![0; pages * PAGE_SIZE];
    write_db_header(&mut file[..PAGE_SIZE], pages as u32);
    let sql = format!("CREATE TABLE items({})", (0..values.len()).map(|i| format!("c{i}")).collect::<Vec<_>>().join(", "));
    let schema = build_record(&[Val::Text("table".into()), Val::Text("items".into()), Val::Text("items".into()), Val::Int(2), Val::Text(sql)]);
    write_table_leaf(&mut file[..PAGE_SIZE], 100, &[(1, schema)]);
    let mut cell = sqlite_varint(record.len() as u64);
    cell.extend(sqlite_varint(1));
    cell.extend_from_slice(&record[..local]);
    if !overflow.is_empty() {
        cell.extend_from_slice(&3u32.to_be_bytes());
    }
    let top = PAGE_SIZE - cell.len();
    let leaf = &mut file[PAGE_SIZE..2 * PAGE_SIZE];
    leaf[0] = 0x0d;
    leaf[3..5].copy_from_slice(&1u16.to_be_bytes());
    leaf[5..7].copy_from_slice(&(top as u16).to_be_bytes());
    leaf[8..10].copy_from_slice(&(top as u16).to_be_bytes());
    leaf[top..].copy_from_slice(&cell);
    for (i, chunk) in overflow.chunks(PAGE_SIZE - 4).enumerate() {
        let base = (i + 2) * PAGE_SIZE;
        let next = if i + 3 < pages { (i + 4) as u32 } else { 0 };
        file[base..base + 4].copy_from_slice(&next.to_be_bytes());
        file[base + 4..base + 4 + chunk.len()].copy_from_slice(chunk);
    }
    file
}

/// A database whose header declares WAL mode (write/read version 2) but no sidecar is present.
pub fn wal_mode_db() -> Vec<u8> {
    let mut db = simple_db();
    db[18] = 2; // write version: WAL
    db[19] = 2; // read version: WAL
    db
}

/// Build a WITHOUT ROWID table from records already sorted and arranged in storage order.
pub fn without_rowid_db(sql: &str, rows: &[Vec<Val>]) -> Vec<u8> {
    fn cell(file: &mut Vec<u8>, record: &[u8]) -> Vec<u8> {
        let max = (PAGE_SIZE - 12) * 64 / 255 - 23;
        let min = (PAGE_SIZE - 12) * 32 / 255 - 23;
        let local = if record.len() <= max {
            record.len()
        } else {
            let candidate = min + (record.len() - min) % (PAGE_SIZE - 4);
            if candidate <= max { candidate } else { min }
        };
        let mut out = sqlite_varint(record.len() as u64);
        out.extend_from_slice(&record[..local]);
        if local < record.len() {
            out.extend_from_slice(&((file.len() / PAGE_SIZE + 1) as u32).to_be_bytes());
            for (i, chunk) in record[local..].chunks(PAGE_SIZE - 4).enumerate() {
                let base = file.len();
                file.resize(base + PAGE_SIZE, 0);
                if local + (i + 1) * (PAGE_SIZE - 4) < record.len() {
                    file[base..base + 4].copy_from_slice(&((base / PAGE_SIZE + 2) as u32).to_be_bytes());
                }
                file[base + 4..base + 4 + chunk.len()].copy_from_slice(chunk);
            }
        }
        out
    }
    fn tree(file: &mut Vec<u8>, rows: &[Vec<Val>], height: u32) -> u32 {
        let base = file.len();
        let page = (base / PAGE_SIZE + 1) as u32;
        file.resize(base + PAGE_SIZE, 0);
        let interior = height > 0;
        let mut cells = Vec::new();
        let mut right = 0;
        if interior {
            // Up to four children; every leaf is at the same depth.
            let children = (rows.len() + 1).div_ceil(4usize.pow(height)).max(2);
            let mut start = 0;
            for i in 0..children {
                let remaining_children = children - i;
                let len = (rows.len() - start - (remaining_children - 1)) / remaining_children;
                let child = tree(file, &rows[start..start + len], height - 1);
                start += len;
                if i + 1 == children {
                    right = child;
                } else {
                    let mut entry = child.to_be_bytes().to_vec();
                    entry.extend_from_slice(&cell(file, &build_record(&rows[start])));
                    cells.push(entry);
                    start += 1;
                }
            }
        } else {
            for row in rows {
                cells.push(cell(file, &build_record(row)));
            }
        }
        let page_bytes = &mut file[base..base + PAGE_SIZE];
        page_bytes[0] = if interior { 2 } else { 10 };
        page_bytes[3..5].copy_from_slice(&(cells.len() as u16).to_be_bytes());
        let header = if interior { 12 } else { 8 };
        if interior {
            page_bytes[8..12].copy_from_slice(&right.to_be_bytes());
        }
        let mut top = PAGE_SIZE;
        for (i, entry) in cells.iter().enumerate() {
            top -= entry.len();
            page_bytes[top..top + entry.len()].copy_from_slice(entry);
            page_bytes[header + 2 * i..header + 2 * i + 2].copy_from_slice(&(top as u16).to_be_bytes());
        }
        page_bytes[5..7].copy_from_slice(&(top as u16).to_be_bytes());
        page
    }
    let mut file = vec![0; PAGE_SIZE];
    let mut height = 0;
    let mut capacity = 3;
    while rows.len() > capacity {
        height += 1;
        capacity = capacity * 4 + 3;
    }
    let root = tree(&mut file, rows, height);
    let schema = build_record(&[Val::Text("table".into()), Val::Text("t".into()), Val::Text("t".into()), Val::Int(root.into()), Val::Text(sql.into())]);
    let pages = (file.len() / PAGE_SIZE) as u32;
    write_db_header(&mut file[..PAGE_SIZE], pages);
    write_table_leaf(&mut file[..PAGE_SIZE], 100, &[(1, schema)]);
    file
}

/// A rowid table with a separate secondary index (the index must not contribute rows).
pub fn indexed_rowid_db() -> Vec<u8> {
    let mut file = vec![0; PAGE_SIZE * 3];
    write_db_header(&mut file[..PAGE_SIZE], 3);
    let schema: Vec<_> = [("table", "t", 2, "CREATE TABLE t(a TEXT, b INT)"), ("index", "ti", 3, "CREATE INDEX ti ON t(a)")]
        .into_iter()
        .enumerate()
        .map(|(i, (kind, name, root, sql))| {
            (i as i64 + 1, build_record(&[Val::Text(kind.into()), Val::Text(name.into()), Val::Text("t".into()), Val::Int(root), Val::Text(sql.into())]))
        })
        .collect();
    write_table_leaf(&mut file[..PAGE_SIZE], 100, &schema);
    let rows = [(1, build_record(&[Val::Text("z".into()), Val::Int(1)])), (2, build_record(&[Val::Text("a".into()), Val::Int(2)]))];
    write_table_leaf(&mut file[PAGE_SIZE..PAGE_SIZE * 2], 0, &rows);
    let index = without_rowid_db(
        "CREATE TABLE t(a TEXT PRIMARY KEY) WITHOUT ROWID",
        &[vec![Val::Text("a".into()), Val::Int(2)], vec![Val::Text("z".into()), Val::Int(1)]],
    );
    file[PAGE_SIZE * 2..].copy_from_slice(&index[PAGE_SIZE..PAGE_SIZE * 2]);
    file
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixture_has_header_and_pages() {
        let db = simple_db();
        assert_eq!(db.len(), PAGE_SIZE * 2);
        assert_eq!(&db[..16], b"SQLite format 3\0");
        // page 2 is a leaf table page
        assert_eq!(db[PAGE_SIZE], 0x0d);
    }
}
