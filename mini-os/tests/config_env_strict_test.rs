use mini_os::config::{
    parse_port_raw, parse_session_ttl_secs_raw, parse_shutdown_timeout_secs_raw,
    parse_upload_max_bytes_raw,
};

#[test]
fn port_parser() {
    assert_eq!(parse_port_raw(None).unwrap(), 8090);
    assert_eq!(parse_port_raw(Some("9100")).unwrap(), 9100);
    assert_eq!(parse_port_raw(Some(" 9100 ")).unwrap(), 9100);
    assert_eq!(parse_port_raw(Some("0")).unwrap(), 0);
    assert_eq!(parse_port_raw(Some("65535")).unwrap(), 65535);
    for bad in ["", "abc", "70000", "-1", "1.5", "9100x"] {
        let err = parse_port_raw(Some(bad)).unwrap_err();
        assert!(err.contains("PORT"), "PORT err={} bad={}", err, bad);
    }
}

#[test]
fn upload_max_bytes_parser() {
    assert_eq!(parse_upload_max_bytes_raw(None).unwrap(), 50 * 1024 * 1024);
    assert_eq!(
        parse_upload_max_bytes_raw(Some("1048576")).unwrap(),
        1048576
    );
    assert_eq!(parse_upload_max_bytes_raw(Some(" 2048 ")).unwrap(), 2048);
    assert_eq!(parse_upload_max_bytes_raw(Some("0")).unwrap(), 0);
    for bad in ["", "abc", "-1", "1.5", "10x"] {
        let err = parse_upload_max_bytes_raw(Some(bad)).unwrap_err();
        assert!(
            err.contains("UPLOAD_MAX_BYTES"),
            "UPLOAD_MAX_BYTES err={} bad={}",
            err,
            bad
        );
    }
}

#[test]
fn shutdown_timeout_secs_parser() {
    assert_eq!(parse_shutdown_timeout_secs_raw(None).unwrap(), 30);
    assert_eq!(parse_shutdown_timeout_secs_raw(Some("7")).unwrap(), 7);
    assert_eq!(parse_shutdown_timeout_secs_raw(Some("0")).unwrap(), 0);
    for bad in ["", "abc", "-1", "1.5", "7x"] {
        let err = parse_shutdown_timeout_secs_raw(Some(bad)).unwrap_err();
        assert!(
            err.contains("SHUTDOWN_TIMEOUT_SECS"),
            "SHUTDOWN_TIMEOUT_SECS err={} bad={}",
            err,
            bad
        );
    }
}

#[test]
fn session_ttl_secs_parser() {
    assert_eq!(parse_session_ttl_secs_raw(None).unwrap(), 604800);
    assert_eq!(parse_session_ttl_secs_raw(Some("120")).unwrap(), 120);
    assert_eq!(parse_session_ttl_secs_raw(Some("1")).unwrap(), 1);
    for bad in ["", "abc", "-1", "0", "1.5", "120x"] {
        let err = parse_session_ttl_secs_raw(Some(bad)).unwrap_err();
        assert!(
            err.contains("SESSION_TTL_SECS"),
            "SESSION_TTL_SECS err={} bad={}",
            err,
            bad
        );
    }
}
