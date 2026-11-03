use mini_os::terminal::{TermError, TerminalManager};

fn make_manager(tag: &str) -> TerminalManager {
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join(format!("tmp-term-{}-{}", tag, std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    TerminalManager::new(dir.to_string_lossy().into_owned(), 8, 60)
}

#[test]
fn open_invalid_zero_cols() {
    let mgr = make_manager("zero-cols");
    let res = mgr.open(1, 0, 24);
    assert_eq!(res, Err(TermError::InvalidSize));
}

#[test]
fn open_invalid_one_row() {
    let mgr = make_manager("one-row");
    let res = mgr.open(1, 80, 1);
    assert_eq!(res, Err(TermError::InvalidSize));
}

#[test]
fn open_invalid_over_500() {
    let mgr = make_manager("over-500");
    assert_eq!(mgr.open(1, 501, 24), Err(TermError::InvalidSize));
    assert_eq!(mgr.open(1, 80, 501), Err(TermError::InvalidSize));
}

#[test]
fn resize_invalid_beats_not_found() {
    let mgr = make_manager("invalid-beats-notfound");
    let res = mgr.resize(1, "no-such", 1, 24);
    assert_eq!(res, Err(TermError::InvalidSize));
}

#[test]
fn resize_invalid_cols_over() {
    let mgr = make_manager("resize-cols-over");
    let sid = mgr.open(1, 80, 24).unwrap();
    let res = mgr.resize(1, &sid, 600, 24);
    assert_eq!(res, Err(TermError::InvalidSize));
}

#[test]
fn open_boundary_ok() {
    let mgr = make_manager("open-boundary");
    let sid = mgr.open(1, 2, 2).unwrap();
    let res = mgr.resize(1, &sid, 500, 500);
    assert_eq!(res, Ok(()));
}

#[test]
fn resize_boundary_low_ok() {
    let mgr = make_manager("resize-boundary-low");
    let sid = mgr.open(1, 80, 24).unwrap();
    let res = mgr.resize(1, &sid, 2, 2);
    assert_eq!(res, Ok(()));
}

#[test]
fn open_valid_then_resize_invalid_keeps_session() {
    let mgr = make_manager("keeps-session");
    let sid = mgr.open(1, 80, 24).unwrap();
    let bad = mgr.resize(1, &sid, 0, 24);
    assert_eq!(bad, Err(TermError::InvalidSize));
    let ok = mgr.resize(1, &sid, 80, 24);
    assert_eq!(ok, Ok(()));
}
