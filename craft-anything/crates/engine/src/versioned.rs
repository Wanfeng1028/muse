//! Versioned files: the one way a saved file is brought up to the current version.
//!
//! Each persisted file keeps a version number and an ordered list of steps. Step `i` rewrites a
//! document from version `first + i` to `first + i + 1`, working on the raw document (a JSON value
//! or a TOML table) before it is turned into Rust types. To change a file's format: bump its
//! version constant and append one step. See `docs/file-formats.md`.

/// One migration step: rewrites a raw document from version n to n + 1. An `Err` is a plain-English
/// reason the document can't be brought forward.
pub type Step<D> = fn(&mut D) -> Result<(), String>;

/// Run the steps that take a document from version `from` to the latest, in order, and return the
/// version reached (`first + steps.len()`). `first` is the oldest version `steps` starts from.
/// A version older than `first` or newer than the latest is refused; callers decide what newer means.
pub fn upgrade<D>(doc: &mut D, from: u32, first: u32, steps: &[Step<D>]) -> Result<u32, String> {
    let latest = u32::try_from(steps.len()).ok().and_then(|n| first.checked_add(n)).ok_or("too many migration steps")?;
    if from < first {
        return Err(format!("version {from} is older than any this build can read (oldest: {first})"));
    }
    if from > latest {
        return Err(format!("version {from} is newer than this build knows (latest: {latest})"));
    }
    let skip = usize::try_from(from - first).map_err(|_| "version out of range")?;
    for step in steps.iter().skip(skip) {
        step(doc)?;
    }
    Ok(latest)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn add_a(d: &mut Vec<&'static str>) -> Result<(), String> {
        d.push("a");
        Ok(())
    }
    fn add_b(d: &mut Vec<&'static str>) -> Result<(), String> {
        d.push("b");
        Ok(())
    }
    fn refuse(_: &mut Vec<&'static str>) -> Result<(), String> {
        Err("no".into())
    }

    #[test]
    fn steps_run_in_order_from_the_document_version() {
        let steps: &[Step<Vec<&str>>] = &[add_a, add_b];
        let mut d = Vec::new();
        assert_eq!(upgrade(&mut d, 0, 0, steps), Ok(2));
        assert_eq!(d, ["a", "b"]);
        let mut d = Vec::new();
        assert_eq!(upgrade(&mut d, 1, 0, steps), Ok(2), "a version-1 document only needs the second step");
        assert_eq!(d, ["b"]);
        let mut d = Vec::new();
        assert_eq!(upgrade(&mut d, 2, 0, steps), Ok(2));
        assert!(d.is_empty(), "already current: nothing runs");
    }

    #[test]
    fn out_of_range_versions_and_failing_steps_are_errors() {
        let steps: &[Step<Vec<&str>>] = &[add_a, refuse];
        assert!(upgrade(&mut Vec::new(), 3, 0, steps).unwrap_err().contains("newer"));
        assert!(upgrade(&mut Vec::new(), 0, 1, steps).unwrap_err().contains("older"));
        assert_eq!(upgrade(&mut Vec::new(), 0, 0, steps), Err("no".into()));
        // No steps: only the first version is readable.
        assert_eq!(upgrade(&mut Vec::<&str>::new(), 1, 1, &[]), Ok(1));
    }
}
