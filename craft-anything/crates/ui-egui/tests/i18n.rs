//! Keep locale-changing UI checks in one integration-test executable: i18n is process-wide.

use craft_anything_engine::{Mode, Session, Settings};
use craft_anything_ui_egui::{CraftApp, demo, i18n};
use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;
use std::path::Path;

fn harness(mut settings: Settings, dir: &Path) -> Harness<'static, CraftApp> {
    let dir = dir.to_path_buf();
    // Keep every engine path under the test directory, including after a saved-settings reload.
    settings.engines.store_dir = Some(dir.join("engines"));
    settings.projects_dir = Some(dir.join("projects"));
    Harness::builder().with_size(egui::vec2(1280.0, 1120.0)).with_max_steps(32).build_eframe(move |cc| {
        CraftApp::setup_context(&cc.egui_ctx);
        let engine = demo::engine(Mode::Beginner, true);
        {
            // The home/settings scenario needs no sample target. Isolate the session and set
            // its language BEFORE CraftApp::new (called by demo::app) reads its settings.
            let mut session = engine.session();
            *session = Session::isolated(&dir);
            session.settings = settings;
        }
        let mut app = demo::app(engine);
        // demo::app keeps persistence disabled and uses an isolated, file-only AI key store.
        // Never enable the real settings worker in this test: Settings::save uses the global
        // config path. The roundtrip below uses save_to with an explicit temporary path.
        assert!(!app.persist);
        assert!(app.headless);
        app.state.settings_open = true;
        app
    })
}

#[test]
fn chinese_startup_language_menu_and_saved_selection() {
    let temp = tempfile::tempdir().unwrap();
    for (initial, native, other, other_native, translated_language, translated_open) in [
        ("zh-hans", "简体中文", "zh-hant", "繁體中文", "语言", "已打开 sample.exe"),
        ("zh-hant", "繁體中文", "zh-hans", "简体中文", "語言", "已開啟 sample.exe"),
    ] {
        let dir = temp.path().join(initial);
        let settings = Settings { mode: Mode::Beginner, first_run_done: true, language: initial.into(), ..Default::default() };
        let mut h = harness(settings, &dir);
        h.run_steps(3);

        // Startup must apply the saved locale itself, rather than relying on a manual call to
        // set_language after app construction. Check both lookup and a rendered settings row.
        assert_eq!(i18n::language(), initial);
        h.get_by_label(translated_language);
        assert_eq!(i18n::trf("Opened {name}", &[("name", "sample.exe")]), translated_open);
        assert_eq!(i18n::tr("A deliberately uncatalogued message"), "A deliberately uncatalogued message");
        assert_eq!(i18n::trf("Uncatalogued {name}", &[("name", "sample.exe")]), "Uncatalogued sample.exe");
        assert_eq!(craft_anything_ui_egui::usage::asset_cost_words(0.0031), if initial == "zh-hans" { "低于 $0.01" } else { "低於 $0.01" });
        let kinds = craft_anything_ai::rebuild::KindRegistry::built_in();
        for (suggestion, expected) in [("A website for my bakery", "website"), ("A simple snake game", "game")] {
            let translated = i18n::tr(suggestion);
            assert_ne!(translated, suggestion);
            let (kind, _) = kinds.choose(&translated, &craft_anything_engine::workspace::TargetRef::None, false).unwrap();
            assert_eq!(kind.id(), expected, "{initial}: {translated}");
        }
        let title = h.state().engine.registry().get("native_functions_list").unwrap().title;
        let translated_title = i18n::tr(title);
        assert_ne!(translated_title, title);
        h.state_mut().state.settings_open = false;
        h.state_mut().state.palette.open = true;
        h.state_mut().state.palette.query = translated_title.clone();
        h.run_steps(3);
        h.get_by_label(&translated_title);
        h.state_mut().state.palette.open = false;
        h.state_mut().state.settings_open = true;
        h.run_steps(3);

        // Exercise the real ComboBox and selectable row, including the language-change callback.
        h.get_by_value(native).click();
        h.run();
        h.get_by_label(other_native).scroll_to_me();
        h.run();
        let choice_rect = h.get_by_label(other_native).rect();
        h.get_by_label(other_native).click();
        h.run_steps(3);
        assert_eq!(i18n::language(), other, "language choice at {choice_rect:?}");
        assert_eq!(h.state().settings.language, other);
        let selected = h.state().engine.session().settings.clone();
        assert_eq!(selected.language, other, "the UI must propagate the choice to the engine session");

        // Verify the persisted settings representation and the next startup using only a
        // temporary config.toml. This does not claim to test the UI's debounce worker path.
        let config = dir.join("config.toml");
        selected.save_to(&config).unwrap();
        let loaded = Settings::load_from(&config);
        assert_eq!(loaded.language, other);
        drop(h);
        let mut restored = harness(loaded, &dir);
        restored.run_steps(3);
        assert_eq!(i18n::language(), other);
        restored.get_by_value(other_native);
        restored.get_by_label(if other == "zh-hans" { "语言" } else { "語言" });

        // English remains available from either Chinese catalog and takes effect immediately.
        restored.get_by_value(other_native).click();
        restored.run();
        restored.get_by_label("English").scroll_to_me();
        restored.run();
        restored.get_by_label("English").click();
        restored.run_steps(3);
        assert_eq!(i18n::language(), "en");
        assert_eq!(restored.state().settings.language, "en");
        assert_eq!(restored.state().engine.session().settings.language, "en");
        restored.get_by_label("Language");
        assert!(restored.query_by_label("语言").is_none());
        assert!(restored.query_by_label("語言").is_none());

        restored.get_by_value("English").click();
        restored.run();
        restored.get_by_label("System").scroll_to_me();
        restored.run();
        restored.get_by_label("System").click();
        restored.run_steps(3);
        assert!(restored.state().settings.language.is_empty());
        let expected = sys_locale::get_locales().find_map(|tag| i18n::language_from_tag(&tag)).unwrap_or("en");
        assert_eq!(i18n::language(), expected);
        assert!(restored.state().engine.session().settings.language.is_empty());
    }
    for (code, native, label) in [("fr", "Français", "Langue"), ("ja", "日本語", "言語")] {
        let settings = Settings { mode: Mode::Beginner, first_run_done: true, language: code.into(), ..Default::default() };
        let mut existing = harness(settings, &temp.path().join(code));
        existing.run_steps(3);
        assert_eq!(i18n::language(), code);
        existing.get_by_label(label);
        existing.get_by_value(native);
    }
    i18n::set_language("unsupported-locale");
    assert_eq!(i18n::language(), "en");
    assert_eq!(i18n::tr("Settings"), "Settings");
}
