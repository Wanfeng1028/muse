//! Database-file tools with a built-in parser: read-only SQLite inspection (schema, tables,
//! indexes, views, triggers, row counts and paged rows). Takes an absolute path or the active
//! target. Nothing is executed and nothing is written.

use super::native_common::spec;
use super::static_input::{self, builder, format_err};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, CoverageStatus, Limitation, Location, ToolError};
use craft_anything_formats::sqlite::{self, SqliteDb};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "db_sqlite_show",
        "SQLite database contents",
        "Read a SQLite 3 database file without running any SQL: the header (page size, page count, text encoding, SQLite version that wrote it, WAL mode, freelist), the schema from sqlite_schema (tables, indexes, views and triggers with their CREATE statements and, for tables, parsed column names and types), per-table row counts (counted by walking the b-tree, bounded), and a page of rows from a named table (offset/limit; values as JSON; BLOBs shown as length plus a SHA-256 prefix, never dumped). Everything is bounded and read-only. Built-in parser (no SQLite library).",
        "Look inside an app's SQLite database: its tables, columns and some rows.",
        Toolset::Database,
        Effects::EVIDENCE | Effects::CARRIES_TARGET_CONTENT,
        Requires::Nothing,
        schema_of::<SqliteParams>,
        db_sqlite_show,
    )]
}

fn d_limit() -> usize {
    100
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SqliteParams {
    /// Absolute path of a .sqlite/.db file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Read a page of rows from this table (by name, case-insensitive). Omit to list the schema only.
    #[serde(default)]
    pub table: Option<String>,
    /// First row of the page (0-based).
    #[serde(default)]
    pub offset: usize,
    /// Rows per page (1–100000, default 100).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

fn db_sqlite_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SqliteParams = parse_params(params)?;
    let input = static_input::load(ctx, p.path.as_deref(), sqlite::MAX_INPUT as u64)?;
    ctx.report(None, format!("Reading SQLite database {}", input.name));
    let db = SqliteDb::parse(&input.bytes).map_err(|e| {
        format_err(e, "a SQLite database")
            .with_remediation("Check the file is a SQLite 3 database. An encrypted database (for example SQLCipher) has no readable header and cannot be read.")
    })?;
    ctx.cancel.check()?;
    let overview = db.overview();

    // A -wal sidecar next to the file means the newest committed data may not be in this file.
    let wal_sibling = {
        let mut sib = input.path.clone().into_os_string();
        sib.push("-wal");
        std::path::PathBuf::from(sib).is_file()
    };

    // Per-table row counts and column info.
    let mut tables = Vec::new();
    let mut other_objects = Vec::new();
    let mut any_bounded = false;
    for obj in &overview.schema {
        ctx.cancel.check()?;
        if obj.obj_type == "table" && obj.rootpage != 0 {
            let rc = db.count_rows(obj.rootpage);
            any_bounded |= rc.bounded;
            tables.push(json!({
                "name": obj.name,
                "rootpage": obj.rootpage,
                "columns": obj.columns,
                "row_count": rc.count,
                "row_count_bounded": rc.bounded,
                "sql": obj.sql,
            }));
        } else {
            other_objects.push(json!({
                "type": obj.obj_type,
                "name": obj.name,
                "tbl_name": obj.tbl_name,
                "rootpage": obj.rootpage,
                "sql": obj.sql,
            }));
        }
    }

    // Optional: read a page of rows from the named table.
    let limit = p.limit.clamp(1, sqlite::MAX_ROWS);
    let mut rows_block = Value::Null;
    let mut row_coverage: Option<Coverage> = None;
    let mut row_notes: Vec<String> = Vec::new();
    if let Some(name) = p.table.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
        match db.find_object(name) {
            Some(obj) if obj.obj_type == "table" && obj.rootpage != 0 => {
                ctx.report(None, format!("Reading rows from {}", obj.name));
                let page = db.read_rows(obj.rootpage, p.offset, limit);
                row_notes = page.notes.clone();
                let rc = db.count_rows(obj.rootpage);
                let total = rc.count;
                let shown = page.rows.len() as u64;
                let next = p.offset as u64 + shown;
                let cov = if page.truncated || rc.bounded || next < total || !page.notes.is_empty() {
                    Coverage { status: CoverageStatus::Partial, examined: Some(shown), total: Some(total), next_offset: (next < total).then_some(next) }
                } else {
                    Coverage { status: CoverageStatus::Complete, examined: Some(shown), total: Some(total), next_offset: None }
                };
                row_coverage = Some(cov);
                rows_block = json!({
                    "table": obj.name,
                    "column_names": obj.columns.iter().map(|c| c.name.clone()).collect::<Vec<_>>(),
                    "offset": page.offset,
                    "limit": limit,
                    "returned": shown,
                    "total_rows": total,
                    "truncated": page.truncated,
                    "rows": page.rows,
                    "notes": page.notes,
                });
            }
            Some(obj) => {
                return Err(ToolError::invalid(format!("\"{}\" is a {}, not a table; rows can only be read from tables", obj.name, obj.obj_type)));
            }
            None => {
                return Err(ToolError::invalid(format!("no table named {name:?} in this database"))
                    .with_remediation("Call the tool without `table` to list the schema, then pass an exact name."));
            }
        }
    }

    let h = &overview.header;
    let summary = format!(
        "SQLite {} database: page size {}, {} pages, {} encoding, {} table(s), {} other object(s){}.",
        h.sqlite_version,
        h.page_size,
        overview.page_count_from_size,
        h.text_encoding,
        tables.len(),
        other_objects.len(),
        if h.wal_mode || wal_sibling { ", WAL mode" } else { "" },
    );

    // Honest limitations.
    let mut lims = vec![Limitation::new(
        "row_counts_derived",
        "Row counts are computed by walking each table's b-tree, not read from a stored value; they count only rows present in this file.",
    )];
    if h.wal_mode || wal_sibling {
        lims.push(Limitation::new(
            "wal_not_read",
            if wal_sibling {
                "A write-ahead log (-wal) sits next to this file. The newest committed rows may live there and are NOT merged in; only the main database file was read."
            } else {
                "The header declares WAL mode. If a -wal sidecar exists elsewhere, its newest committed rows are not included here."
            },
        ));
    }
    if h.text_encoding == "utf-16le" || h.text_encoding == "utf-16be" {
        lims.push(Limitation::new(
            "utf16_text",
            "This database stores text as UTF-16; text values are decoded as if UTF-8 and may be garbled. Structure and non-text values are unaffected.",
        ));
    }
    if h.text_encoding == "unknown" {
        lims.push(Limitation::new("unknown_encoding", "The text-encoding field is not a known value; text may be decoded incorrectly."));
    }
    if any_bounded {
        lims.push(Limitation::new("count_bounded", "A page-walk budget was hit while counting at least one table; those counts are lower bounds."));
    }
    lims.push(Limitation::new(
        "no_decryption",
        "Encrypted databases (for example SQLCipher) have no readable header and cannot be opened; only unencrypted SQLite files are supported.",
    ));
    lims.push(Limitation::new(
        "freelist_not_read",
        "Deleted rows may linger on freelist or unused pages; those pages are not read, so deleted content is not recovered.",
    ));
    lims.push(Limitation::new(
        "blobs_not_dumped",
        "BLOB values are reported as a byte length and a SHA-256 prefix, never dumped; overflow payloads are bounded.",
    ));
    if !row_notes.is_empty() {
        lims.push(Limitation::new("read_notes", "Some rows or values were skipped or truncated while reading; see rows.notes."));
    }

    let coverage = row_coverage.unwrap_or_else(|| Coverage::complete(tables.len() as u64));

    let ev = builder(ctx, "db_sqlite_show", input.subject.clone(), json!({"path": input.path, "table": p.table, "offset": p.offset, "limit": limit}))
        .result(json!({
            "header": overview.header,
            "file_size": overview.file_size,
            "page_count": overview.page_count_from_size,
            "wal_sidecar_present": wal_sibling,
            "integrity_notes": overview.integrity_notes,
            "tables": tables,
            "other_objects": other_objects,
            "schema_truncated": overview.schema_truncated,
            "rows": rows_block,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(coverage)
        .location(Location::new("path", input.path.display().to_string()));
    Ok(ToolOutput::evidence(ev.build()?))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use crate::Engine;
    use craft_anything_testkit::sqlite as fx;
    use craft_anything_testkit::temp_file;
    use serde_json::{Value, json};

    fn check_without_rowid(sql: &str, stored: Vec<Vec<fx::Val>>, expected: Value) {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("rows.db", &fx::without_rowid_db(sql, &stored));
        let count = expected.as_array().unwrap().len();
        let v = call(&e, "db_sqlite_show", json!({"path": p, "table": "t", "limit": count + 1}));
        assert_eq!(v["result"]["tables"][0]["row_count"], count, "WITHOUT ROWID row_count");
        let rows = v["result"]["rows"]["rows"].as_array().unwrap();
        assert_eq!(rows.len(), count);
        for (row, values) in rows.iter().zip(expected.as_array().unwrap()) {
            assert_eq!(row["rowid"], Value::Null);
            assert_eq!(&row["values"], values);
        }
        assert_eq!(v["coverage"]["status"], "complete");
        assert_eq!(v["coverage"]["total"], count);
        assert_eq!(v["coverage"]["next_offset"], Value::Null);
        assert!(v["result"]["rows"]["notes"].as_array().unwrap().is_empty());
        let first = call(&e, "db_sqlite_show", json!({"path": p, "table": "t", "limit": 1}));
        assert_eq!(first["result"]["rows"]["rows"][0]["values"], expected[0]);
        assert_eq!(first["coverage"]["total"], count);
        assert_eq!(first["coverage"]["next_offset"], 1);
        let last = call(&e, "db_sqlite_show", json!({"path": p, "table": "t", "offset": count - 1, "limit": 2}));
        assert_eq!(last["result"]["rows"]["rows"][0]["values"], expected[count - 1]);
        assert_eq!(last["coverage"]["next_offset"], Value::Null);
        assert_eq!(last["coverage"]["status"], "complete");
    }

    #[test]
    fn without_rowid_b1_composite_key() {
        use fx::Val::{Int, Text};
        check_without_rowid(
            "CREATE TABLE t(a TEXT, b INT, PRIMARY KEY(a,b)) WITHOUT ROWID",
            vec![vec![Text("j".into()), Int(2)], vec![Text("k".into()), Int(1)], vec![Text("m".into()), Int(3)]],
            json!([["j", 2], ["k", 1], ["m", 3]]),
        );
    }

    #[test]
    fn without_rowid_b2_interior_rows() {
        use fx::Val::Text;
        let pad = "p".repeat(200);
        let rows = (0..3000).map(|i| vec![Text(format!("k{i:04}")), Text(pad.clone())]).collect();
        let expected = (0..3000).map(|i| json!([format!("k{i:04}"), pad])).collect::<Vec<_>>();
        check_without_rowid("CREATE TABLE t(a TEXT PRIMARY KEY, pad TEXT) WITHOUT ROWID", rows, json!(expected));
    }

    #[test]
    fn without_rowid_b4_integer_key() {
        use fx::Val::{Int, Text};
        check_without_rowid(
            "CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT) WITHOUT ROWID",
            vec![vec![Int(5), Text("a".into())], vec![Int(9), Text("b".into())]],
            json!([[5, "a"], [9, "b"]]),
        );
    }

    #[test]
    fn without_rowid_b5_declaration_order() {
        use fx::Val::{Int, Text};
        check_without_rowid(
            "CREATE TABLE t(v TEXT, k INT PRIMARY KEY) without\n rowid ;",
            vec![vec![Int(5), Text("a".into())], vec![Int(9), Text("b".into())]],
            json!([["a", 5], ["b", 9]]),
        );
    }

    #[test]
    fn without_rowid_b3_rowid_control() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("rows.db", &fx::indexed_rowid_db());
        let v = call(&e, "db_sqlite_show", json!({"path": p, "table": "t"}));
        assert_eq!(v["result"]["tables"][0]["row_count"], 2);
        assert_eq!(v["result"]["rows"]["rows"], json!([{"rowid": 1, "values": ["z", 1]}, {"rowid": 2, "values": ["a", 2]}]));
    }

    #[test]
    fn without_rowid_overflow_and_composite_storage_order() {
        use fx::Val::{Int, Text};
        let pad = "x".repeat(2000);
        let rows = (0..5).rev().map(|i| vec![Int(i), Text(format!("k{i}")), Text(pad.clone())]).collect();
        let expected = (0..5).rev().map(|i| json!([pad, format!("k{i}"), i])).collect::<Vec<_>>();
        check_without_rowid(
            "CREATE TABLE t(pad TEXT, \"a key\" TEXT, b INT, CONSTRAINT pk PRIMARY KEY(b DESC, \"a key\" COLLATE BINARY)) WITHOUT ROWID",
            rows,
            json!(expected),
        );
    }

    #[test]
    fn inspects_schema_and_rows() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("app.db", &fx::simple_db());
        let v = call(&e, "db_sqlite_show", json!({"path": p}));
        let r = &v["result"];
        assert_eq!(r["header"]["page_size"], 4096);
        assert_eq!(r["header"]["sqlite_version"], "3.45.1");
        assert_eq!(r["header"]["text_encoding"], "utf-8");
        assert_eq!(r["tables"].as_array().unwrap().len(), 1);
        assert_eq!(r["tables"][0]["name"], "items");
        assert_eq!(r["tables"][0]["row_count"], 3);
        assert_eq!(r["tables"][0]["columns"].as_array().unwrap().len(), 4);
        assert!(v["summary"].as_str().unwrap().contains("SQLite 3.45.1"));

        // Paged rows for a named table.
        let rows = call(&e, "db_sqlite_show", json!({"path": p, "table": "items", "offset": 1, "limit": 1}));
        let rb = &rows["result"]["rows"];
        assert_eq!(rb["table"], "items");
        assert_eq!(rb["total_rows"], 3);
        assert_eq!(rb["rows"].as_array().unwrap().len(), 1);
        assert_eq!(rb["rows"][0]["rowid"], 2);
        assert_eq!(rb["rows"][0]["values"][1], "beta");
        assert_eq!(rows["coverage"]["next_offset"], 2);
        assert_eq!(rows["coverage"]["total"], 3);
    }

    #[test]
    fn payload_cap_is_disclosed_in_coverage() {
        let e = Engine::new(crate::testing::session());
        for size in [1_000_000, 8_400_000] {
            let bytes = fx::overflow_row_db(&[fx::Val::Int(42), fx::Val::Blob(vec![0x5a; size]), fx::Val::Int(73)]);
            let p = temp_file("overflow.db", &bytes);
            let v = call(&e, "db_sqlite_show", json!({"path": p, "table": "items"}));
            let partial = size == 8_400_000;
            assert_eq!(v["coverage"]["status"], if partial { "partial" } else { "complete" });
            assert_eq!(v["result"]["rows"]["notes"].as_array().unwrap().is_empty(), !partial);
            assert_eq!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "read_notes"), partial);
        }
    }

    #[test]
    fn blob_is_summarised_not_dumped() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("app.db", &fx::simple_db());
        let rows = call(&e, "db_sqlite_show", json!({"path": p, "table": "items"}));
        let first = &rows["result"]["rows"]["rows"][0]["values"][3];
        assert_eq!(first["blob_len"], 4);
        assert!(first["sha256_prefix"].as_str().unwrap().len() >= 8);
    }

    #[test]
    fn active_target_and_errors() {
        let e = Engine::new(crate::testing::session());
        // Active target path.
        let p = temp_file("app.db", &fx::simple_db());
        let _ = e.call("core_target_open", json!({"path": p.to_string_lossy()}), crate::CallOptions::new(crate::Caller::Cli));
        let v = call(&e, "db_sqlite_show", json!({}));
        assert_eq!(v["result"]["tables"][0]["name"], "items");

        // Unknown table.
        call_err(&e, "db_sqlite_show", json!({"path": p, "table": "nope"}));

        // A non-SQLite file errors cleanly.
        let bad = temp_file("notdb.bin", b"this is not a database at all");
        let err = call_err(&e, "db_sqlite_show", json!({"path": bad}));
        assert!(err.message.to_lowercase().contains("sqlite"));
    }

    #[test]
    fn wal_header_is_flagged() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("wal.db", &fx::wal_mode_db());
        let v = call(&e, "db_sqlite_show", json!({"path": p}));
        assert!(v["summary"].as_str().unwrap().contains("WAL"));
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "wal_not_read"));
    }

    #[test]
    fn short_records_include_defaults_and_disclose_expressions() {
        let e = Engine::new(crate::testing::session());
        let bytes = fx::table_db("CREATE TABLE t(n INT, x INT DEFAULT 42, d TEXT DEFAULT (lower('A')))", &[(1, vec![fx::Val::Int(1)])]);
        let p = temp_file("defaults.db", &bytes);
        let v = call(&e, "db_sqlite_show", json!({"path": p, "table": "t"}));
        assert_eq!(v["result"]["rows"]["rows"][0]["values"], json!([1, 42, null]));
        assert!(v["result"]["rows"]["notes"].as_array().unwrap().iter().any(|n| n.as_str().unwrap().contains("unsupported DEFAULT")));
    }

    #[test]
    fn payload_cap_without_rowid_is_disclosed_in_coverage() {
        let e = Engine::new(crate::testing::session());
        let bytes = fx::without_rowid_db(
            "CREATE TABLE t(v BLOB, k INT PRIMARY KEY, tail INT) WITHOUT ROWID",
            &[vec![fx::Val::Int(42), fx::Val::Blob(vec![0x5a; 8_400_000]), fx::Val::Int(73)]],
        );
        let p = temp_file("overflow-index.db", &bytes);
        let v = call(&e, "db_sqlite_show", json!({"path": p, "table": "t"}));
        assert_eq!(v["coverage"]["status"], "partial");
        assert_eq!(
            v["result"]["rows"]["rows"][0]["values"],
            json!([
                {"blob_len": 8_400_000, "truncated": true}, 42, {"not_read": true}
            ])
        );
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "read_notes"));
    }
}
