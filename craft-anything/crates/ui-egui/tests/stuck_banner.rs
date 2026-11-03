//! The stuck-lock banner. In a test program of its own: what it shows is the whole process's, and
//! a banner appearing moves everything under it, which makes clicks in tests running beside it miss.

use craft_anything_engine::Mode;
use craft_anything_platform::sync;
use craft_anything_ui_egui::demo;
use egui_kittest::Harness;
use egui_kittest::kittest::Queryable;

#[test]
fn a_stuck_lock_is_shown_with_a_way_out() {
    let mut h = Harness::builder().with_size(egui::vec2(1280.0, 820.0)).with_max_steps(32).build_eframe(move |cc| {
        craft_anything_ui_egui::CraftApp::setup_context(&cc.egui_ctx);
        demo::app(demo::engine(Mode::Beginner, true))
    });
    let summary = "a lock taken at x.rs:1 is stuck";
    h.run_steps(2);
    assert!(h.query_by_label("Restart").is_none(), "nothing wrong, nothing shown");
    sync::report(sync::ProblemKind::SlowJob, "a long job is still running");
    h.run_steps(2);
    assert!(h.query_by_label("Restart").is_none(), "a long job is no alarm");
    sync::report(sync::ProblemKind::Stuck, summary);
    h.run_steps(4);
    h.get_by_label("Restart");
    h.get_by_label("Dismiss").click();
    h.run_steps(4);
    assert!(!sync::problems().iter().any(|p| p.summary == summary));
    assert!(h.query_by_label("Restart").is_none());
}
