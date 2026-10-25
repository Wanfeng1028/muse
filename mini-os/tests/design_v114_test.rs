// v1.14.0 design layer: static assertions, no service needed.
fn design_css() -> String {
    std::fs::read_to_string("static/design-v114.css").expect("design-v114.css must exist")
}

fn index_html() -> String {
    std::fs::read_to_string("static/index.html").expect("index.html must exist")
}

#[test]
fn design_layer_covers_real_selectors() {
    let css = design_css();
    assert!(
        css.contains("#icon-grid"),
        "must style #icon-grid, the real desktop container"
    );
    assert!(css.contains("display: grid"), "#icon-grid must be a grid");
    assert!(
        css.contains("#start-menu.hidden"),
        "must hide #start-menu via .hidden"
    );
    assert!(css.contains("#start-btn"), "must style the real #start-btn");
    assert!(
        css.contains("#taskbar-apps"),
        "must style the real #taskbar-apps"
    );
    assert!(
        css.contains("#logout-btn"),
        "must style the real #logout-btn"
    );
    assert!(css.contains("#clock"), "must style #clock");
    assert!(
        css.contains("tabular-nums"),
        "clock must use tabular numbers"
    );
}

#[test]
fn index_links_design_layer_after_base_style() {
    let html = index_html();
    let base = html.find("/style.css").expect("base style link must exist");
    let layer = html
        .find("/design-v114.css")
        .expect("design layer link must exist");
    assert!(
        layer > base,
        "design layer must load after style.css so it overrides"
    );
}

#[test]
fn design_layer_has_no_ai_slop_markers() {
    let css = design_css();
    assert!(!css.contains("#7c3aed"), "no purple accent");
    assert!(!css.contains("#8b5cf6"), "no purple accent");
    assert!(!css.contains("Inter"), "Inter must not be the UI font");
    assert!(
        !css.contains("linear-gradient"),
        "design layer must not add gradients"
    );
    let opens = css.matches('{').count();
    let closes = css.matches('}').count();
    assert_eq!(opens, closes, "braces must balance");
}
