#[test]
fn test_dark_theme_defines_widget_vars() {
    let css = std::fs::read_to_string(format!("{}/static/style.css", env!("CARGO_MANIFEST_DIR")))
        .unwrap();
    let start = css.find("[data-theme=\"dark\"] {").unwrap();
    let rest = &css[start..];
    let end = rest.find("\n}\n").unwrap();
    let dark_block = &rest[..end];
    assert!(dark_block.contains("--card-bg: rgba(33,29,23,0.92)"));
    assert!(dark_block.contains("--border-color: rgba(237,230,214,0.14)"));
    assert!(dark_block.contains("--text-color: #ede6d6"));
    assert!(css.contains(".widget") && css.contains("var(--card-bg, rgba(255, 255, 255, 0.92))"));
}
