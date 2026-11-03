use mini_os::config::{parse_database_path_raw, parse_static_dir_raw};

#[test]
fn database_path_parser_defaults_and_valid() {
    assert_eq!(parse_database_path_raw(None).unwrap(), "data/mini-os.db");
    assert_eq!(
        parse_database_path_raw(Some("data/x.db")).unwrap(),
        "data/x.db"
    );
    assert_eq!(
        parse_database_path_raw(Some("  data/x.db  ")).unwrap(),
        "data/x.db"
    );
    assert_eq!(
        parse_database_path_raw(Some("/srv/mini-os/prod.db")).unwrap(),
        "/srv/mini-os/prod.db"
    );
}

#[test]
fn database_path_parser_rejects_empty() {
    for bad in ["", "   ", "\t"] {
        let err = parse_database_path_raw(Some(bad)).unwrap_err();
        assert!(
            err.contains("DATABASE_PATH"),
            "error message missing DATABASE_PATH: {:?}",
            err
        );
        assert!(
            err.contains("不能为空"),
            "error message missing 不能为空: {:?}",
            err
        );
    }
}

#[test]
fn static_dir_parser_defaults_and_valid() {
    assert_eq!(parse_static_dir_raw(None).unwrap(), "static");
    assert_eq!(parse_static_dir_raw(Some("www")).unwrap(), "www");
    assert_eq!(parse_static_dir_raw(Some("  www  ")).unwrap(), "www");
    assert_eq!(
        parse_static_dir_raw(Some("/srv/mini-os/www")).unwrap(),
        "/srv/mini-os/www"
    );
}

#[test]
fn static_dir_parser_rejects_empty() {
    for bad in ["", "   ", "\t"] {
        let err = parse_static_dir_raw(Some(bad)).unwrap_err();
        assert!(
            err.contains("STATIC_DIR"),
            "error message missing STATIC_DIR: {:?}",
            err
        );
        assert!(
            err.contains("不能为空"),
            "error message missing 不能为空: {:?}",
            err
        );
    }
}
