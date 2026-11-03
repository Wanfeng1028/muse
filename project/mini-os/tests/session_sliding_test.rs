//! session_sliding_test.rs — verify_session_sliding 函数级语义测试
use mini_os::auth::{create_session, hash_token, now_epoch_secs, verify_session_sliding};
use mini_os::config::parse_session_sliding_raw;
use mini_os::{init_state, AppState};
use rusqlite::params;
use std::sync::Arc;

fn setup() -> (Arc<AppState>, i64) {
    let state = init_state(":memory:", "static");
    let conn = state.db.lock().unwrap();
    conn.execute(
        "INSERT INTO users (username, password_hash, is_admin, role) VALUES (?1, ?2, ?3, ?4)",
        params!["slider1", "x", 0, "editor"],
    )
    .unwrap();
    let user_id = conn.last_insert_rowid();
    drop(conn);
    (state, user_id)
}

fn make_token(state: &Arc<AppState>, user_id: i64, expires_at: i64) -> String {
    let conn = state.db.lock().unwrap();
    let token = create_session(&conn, user_id, 3600).unwrap();
    let token_hash = hash_token(&token);
    conn.execute(
        "UPDATE sessions SET expires_at = ?1 WHERE token_hash = ?2",
        params![expires_at, token_hash],
    )
    .unwrap();
    drop(conn);
    token
}

fn read_expires(state: &Arc<AppState>, token: &str) -> Option<i64> {
    let conn = state.db.lock().unwrap();
    let token_hash = hash_token(token);
    conn.query_row(
        "SELECT expires_at FROM sessions WHERE token_hash = ?1",
        params![token_hash],
        |row| row.get(0),
    )
    .ok()
}

#[test]
fn renews_when_remaining_less_than_half() {
    let (state, user_id) = setup();
    let now = now_epoch_secs();
    let token = make_token(&state, user_id, now + 400);
    let res = {
        let conn = state.db.lock().unwrap();
        verify_session_sliding(&conn, &token, 1000, true)
    };
    let sess = res.unwrap().unwrap();
    assert!(sess.renewed);
    assert_eq!(sess.user.id, user_id);
    let exp = read_expires(&state, &token).unwrap();
    assert!((now + 999..=now + 1001).contains(&exp));
}

#[test]
fn no_renew_when_fresh() {
    let (state, user_id) = setup();
    let now = now_epoch_secs();
    let token = make_token(&state, user_id, now + 1000);
    let res = {
        let conn = state.db.lock().unwrap();
        verify_session_sliding(&conn, &token, 1000, true)
    };
    let sess = res.unwrap().unwrap();
    assert!(!sess.renewed);
    assert_eq!(read_expires(&state, &token).unwrap(), now + 1000);
}

#[test]
fn boundary_half_not_renewed() {
    let (state, user_id) = setup();
    let now = now_epoch_secs();
    let token = make_token(&state, user_id, now + 5005);
    let res = {
        let conn = state.db.lock().unwrap();
        verify_session_sliding(&conn, &token, 10000, true)
    };
    let sess = res.unwrap().unwrap();
    assert!(!sess.renewed);
}

#[test]
fn just_below_half_renews() {
    let (state, user_id) = setup();
    let now = now_epoch_secs();
    let token = make_token(&state, user_id, now + 4995);
    let res = {
        let conn = state.db.lock().unwrap();
        verify_session_sliding(&conn, &token, 10000, true)
    };
    let sess = res.unwrap().unwrap();
    assert!(sess.renewed);
}

#[test]
fn disabled_no_renew() {
    let (state, user_id) = setup();
    let now = now_epoch_secs();
    let token = make_token(&state, user_id, now + 100);
    let res = {
        let conn = state.db.lock().unwrap();
        verify_session_sliding(&conn, &token, 1000, false)
    };
    let sess = res.unwrap().unwrap();
    assert!(!sess.renewed);
    assert_eq!(read_expires(&state, &token).unwrap(), now + 100);
}

#[test]
fn expired_returns_none_and_cleans() {
    let (state, user_id) = setup();
    let now = now_epoch_secs();
    let token = make_token(&state, user_id, now - 10);
    let res = {
        let conn = state.db.lock().unwrap();
        verify_session_sliding(&conn, &token, 1000, true)
    };
    assert!(matches!(res, Ok(None)));
    assert!(read_expires(&state, &token).is_none());
}

#[test]
fn unknown_and_empty_token() {
    let (state, _) = setup();
    let conn = state.db.lock().unwrap();
    let res1 = verify_session_sliding(&conn, "no-such-token", 1000, true);
    assert!(matches!(res1, Ok(None)));
    let res2 = verify_session_sliding(&conn, "", 1000, true);
    assert!(matches!(res2, Ok(None)));
}

#[test]
fn parse_session_sliding_truth_table() {
    assert_eq!(parse_session_sliding_raw(None), Ok(true));
    assert_eq!(parse_session_sliding_raw(Some("1")), Ok(true));
    assert_eq!(parse_session_sliding_raw(Some("TRUE")), Ok(true));
    assert_eq!(parse_session_sliding_raw(Some(" yes ")), Ok(true));
    assert_eq!(parse_session_sliding_raw(Some("on")), Ok(true));
    assert_eq!(parse_session_sliding_raw(Some("0")), Ok(false));
    assert_eq!(parse_session_sliding_raw(Some("false")), Ok(false));
    assert_eq!(parse_session_sliding_raw(Some("No")), Ok(false));
    assert_eq!(parse_session_sliding_raw(Some("off")), Ok(false));
    assert!(parse_session_sliding_raw(Some("maybe")).is_err());
    assert!(parse_session_sliding_raw(Some("")).is_err());
}
