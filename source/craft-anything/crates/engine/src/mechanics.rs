//! `app/mechanics.json`: the numbers and rules that shape how a rebuild plays, in a form checks
//! can read. The builder keeps it next to `app/MECHANICS.md` (the same values, written for
//! people); the mechanics check reads it after each build. Its schema is published in
//! `docs/schemas/mechanics.schema.json` (`cargo xtask schemas`).

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::path::Path;

/// The sheet's current version. A sheet without one is read as this version: builders may leave
/// it out.
pub const MECHANICS_VERSION: u32 = 1;
/// Its file name inside `app/`.
pub const MECHANICS: &str = "mechanics.json";
/// A bigger sheet isn't read.
pub const MAX_BYTES: u64 = 1024 * 1024;
/// At most this many values are read; the rest are ignored.
pub const MAX_VALUES: usize = 2000;

/// Every value that shapes how the rebuild plays.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Mechanics {
    #[serde(default = "current_version")]
    pub version: u32,
    pub values: Vec<Mechanic>,
}

fn current_version() -> u32 {
    MECHANICS_VERSION
}

/// One value: "walk speed" is 4.5 m/s, from a function in the original.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Mechanic {
    /// What it is, as `MECHANICS.md` names it ("walk speed", "rifle damage").
    pub name: String,
    /// What it belongs to ("movement", "rifle"), or empty.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub group: String,
    pub value: MechanicValue,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub unit: String,
    /// Where it came from: a file in the original's folder, a function address or an evidence
    /// id. Empty for an estimate.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub source: String,
    /// Guessed rather than found (from pictures, play or documentation).
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub estimated: bool,
}

impl Mechanic {
    /// Neither a source nor marked as an estimate.
    pub fn unsourced(&self) -> bool {
        self.source.trim().is_empty() && !self.estimated
    }
}

/// A number, a piece of text ("hold to crouch") or a switch.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(untagged)]
pub enum MechanicValue {
    Flag(bool),
    Number(f64),
    Text(String),
}

/// Why a sheet can't be used.
#[derive(Debug, Clone, PartialEq)]
pub enum SheetProblem {
    Missing,
    TooLarge,
    /// Not JSON, or not this shape: the parser's reason.
    Unreadable(String),
    /// Written for a newer Craft Anything.
    Newer(u32),
    /// No values.
    Empty,
}

/// Read a sheet from `path`. Values past [`MAX_VALUES`] are dropped.
pub fn read(path: &Path) -> Result<Mechanics, SheetProblem> {
    let Ok(meta) = std::fs::metadata(path) else { return Err(SheetProblem::Missing) };
    if meta.len() > MAX_BYTES {
        return Err(SheetProblem::TooLarge);
    }
    let bytes = std::fs::read(path).map_err(|_| SheetProblem::Missing)?;
    parse(&bytes)
}

/// Parse a sheet's bytes.
pub fn parse(bytes: &[u8]) -> Result<Mechanics, SheetProblem> {
    let mut sheet: Mechanics = serde_json::from_slice(bytes).map_err(|e| SheetProblem::Unreadable(e.to_string()))?;
    if sheet.version > MECHANICS_VERSION {
        return Err(SheetProblem::Newer(sheet.version));
    }
    sheet.values.truncate(MAX_VALUES);
    if sheet.values.is_empty() {
        return Err(SheetProblem::Empty);
    }
    Ok(sheet)
}

/// The JSON Schema of `mechanics.json` as published in `docs/schemas/mechanics.schema.json`.
pub fn mechanics_schema() -> String {
    let schema = schemars::generate::SchemaSettings::draft2020_12().into_generator().into_root_schema_for::<Mechanics>();
    serde_json::to_string_pretty(&schema).map(|s| s + "\n").unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_sheet_reads_numbers_text_and_switches() {
        let s = parse(
            br#"{"values": [
                {"name": "walk speed", "group": "movement", "value": 4.5, "unit": "m/s", "source": "function 0x140012a0"},
                {"name": "crouch", "value": "hold", "estimated": true},
                {"name": "friendly fire", "value": false}
            ]}"#,
        )
        .unwrap();
        assert_eq!(s.version, MECHANICS_VERSION, "a missing version is the current one");
        assert_eq!(s.values[0].value, MechanicValue::Number(4.5));
        assert_eq!(s.values[1].value, MechanicValue::Text("hold".into()));
        assert_eq!(s.values[2].value, MechanicValue::Flag(false));
        assert!(!s.values[0].unsourced() && !s.values[1].unsourced() && s.values[2].unsourced());
    }

    #[test]
    fn bad_sheets_say_why() {
        assert!(matches!(parse(b"{"), Err(SheetProblem::Unreadable(_))));
        assert!(matches!(parse(br#"{"values": [{"name": "x"}]}"#), Err(SheetProblem::Unreadable(_))), "a value is required");
        assert_eq!(parse(br#"{"values": []}"#), Err(SheetProblem::Empty));
        assert_eq!(parse(br#"{"version": 9, "values": []}"#), Err(SheetProblem::Newer(9)));
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(read(&dir.path().join(MECHANICS)), Err(SheetProblem::Missing));
        let big = dir.path().join("big.json");
        std::fs::write(&big, vec![b' '; (MAX_BYTES + 1) as usize]).unwrap();
        assert_eq!(read(&big), Err(SheetProblem::TooLarge));
    }

    #[test]
    fn the_published_schema_is_current() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../docs/schemas/mechanics.schema.json");
        let published = std::fs::read_to_string(path).unwrap_or_default().replace("\r\n", "\n");
        assert!(published == mechanics_schema(), "docs/schemas/mechanics.schema.json is stale: run `cargo xtask schemas`");
    }
}
