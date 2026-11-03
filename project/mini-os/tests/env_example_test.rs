use std::fs;

#[test]
fn test_env_example_covers_new_vars() {
    let content = fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/.env.example"))
        .expect("failed to read .env.example");
    assert!(content.contains("MINIOS_DATA_DIR="));
    assert!(content.contains("MINIOS_SESSION_SLIDING=true"));
    assert!(content.contains("MINIOS_SHARE_RPS=5"));
    assert!(content.contains("MINIOS_SHARE_BURST=30"));
    assert!(content.contains("MINIOS_SHARE_RATE_LIMIT_ENABLED=true"));
    assert!(content.contains("MINIOS_TERM_OUTPUT_LIMIT=1048576"));
    assert!(!content.contains("MINIOS_SHARE_READ_RPM"));
    assert!(!content.contains("MINIOS_SHARE_READ_BURST"));
}
