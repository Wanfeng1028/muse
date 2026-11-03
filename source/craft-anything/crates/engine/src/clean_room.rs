//! Clean room: what runs without looking inside the original.
//!
//! In Clean room (Deep mode off) nothing reads a target's code, files or page source. Only the
//! tools in [`TOOLS`] run. They touch no target at all (the session, evidence and open questions,
//! projects, settings, engines, the builder's own project, generated assets), or they watch from
//! outside, as a visitor or a user would: a website's screenshots and visible layout, a picture of
//! a window, the controls on its screen, a recorded run, a phone's screen. Every other tool, a
//! plugin's included, needs Deep mode, so a new tool is Deep-only until it's added here.

use crate::Availability;
use craft_anything_evidence::{ErrorCode, ToolError};

/// The tools that run in Clean room, by id. Tools of the AI and setup layers are listed here too.
pub const TOOLS: &[&str] = &[
    // The session, its evidence and open questions, and the investigation memory.
    "core_session_show",
    "core_targets_list",
    "core_target_select",
    "core_target_close",
    "core_evidence_show",
    "core_evidence_browse",
    "core_evidence_export",
    "core_evidence_import",
    "core_unknowns_show",
    "core_unknown_add",
    "core_unknown_edit",
    "core_unknown_verify",
    "core_person_ask",
    "core_action_approve",
    "core_investigation_show",
    "core_brief_write",
    "core_plan_update",
    "core_hypothesis_record",
    "core_hypothesis_update",
    "core_finding_record",
    "core_handoff_write",
    "core_journal_read",
    "core_report_save",
    "core_report_write",
    // Generated pictures and models, and the keys that pay for them.
    "assets_image_generate",
    "assets_model_generate",
    "assets_key_set",
    "assets_key_remove",
    "assets_key_status",
    // Projects and the rebuild run.
    "project_list",
    "project_show",
    "project_inbox_answer",
    "project_play",
    "project_preview",
    "project_open_folder",
    "project_assets_budget",
    "project_assets_allow",
    "project_rename",
    "project_duplicate",
    "project_delete",
    "project_questions_set",
    "project_build_finish",
    "project_pin_create",
    "project_pins_list",
    "project_pin_open",
    "project_pin_stop",
    "project_pin_rename",
    "project_pin_delete",
    "rebuild_start",
    "rebuild_status",
    "rebuild_activity_show",
    "rebuild_check",
    "rebuild_note",
    "rebuild_note_withdraw",
    "rebuild_question_ask",
    "rebuild_questions_list",
    "rebuild_stop",
    // The builder's own project.
    "build_files_list",
    "build_file_read",
    "build_file_write",
    "build_file_edit",
    "build_checklist",
    "build_command_run",
    // Settings, engines, plugins and this computer's setup.
    "settings_show",
    "settings_set",
    "engines_list",
    "engines_install",
    "engines_app_open",
    "engines_adb_check",
    "engines_apktool_check",
    "engines_jeb_check",
    "engines_tshark_check",
    "plugins_list",
    "plugins_refresh",
    "plugins_add",
    "plugins_remove",
    "setup_plan",
    "setup_apply",
    "setup_doctor",
    "setup_uninstall",
    // A website as a visitor sees it (in Clean room web_site_capture keeps only that).
    "web_site_open",
    "web_site_capture",
    "web_page_states_capture",
    "web_page_screenshot_take",
    "web_pixels_compare",
    "web_site_close",
    // Checks a script's form; it touches no target and starts no browser.
    "web_walkthrough_check",
    // A program watched from outside: its window, the controls on its screen, a recorded run.
    "native_window_capture",
    "runtime_ui_read",
    "runtime_ui_walkthrough_record",
    "runtime_walkthrough_record",
    "runtime_captures_compare",
    // A phone, its screen and its list of apps, without reading inside them.
    "adb_devices_find",
    "adb_device_show",
    "adb_display_show",
    "adb_screenshot_take",
    "adb_apps_list",
    "adb_apps_find",
    "adb_app_install",
    "adb_app_remove",
    "adb_app_launch",
    "adb_app_force_stop",
];

/// Whether `id` runs in Clean room.
pub fn allows(id: &str) -> bool {
    TOOLS.contains(&id)
}

const REASON: &str = "This looks inside the original (its code, files or page source), which Clean room never does.";
const REMEDIATION: &str = "Turn on Deep mode: the switch in the title bar or Settings, `settings_set deep_mode true`, or `--deep` on the CLI.";

/// Why `id` can't run in this mode, if it can't.
pub(crate) fn availability(id: &str, clean_room: bool) -> Option<Availability> {
    (clean_room && !allows(id)).then(|| Availability::no(REASON, REMEDIATION))
}

/// The error for a tool Clean room doesn't run; `details.reason` is `clean_room`.
pub(crate) fn refusal(id: &str) -> ToolError {
    ToolError::new(ErrorCode::FeatureMissing, REASON).with_remediation(REMEDIATION).with_details(serde_json::json!({"reason": "clean_room", "tool": id}))
}

/// How a report names the mode its findings were made in.
pub fn mode_words(clean_room: bool) -> &'static str {
    if clean_room { "Clean room (nothing inside the original was read)" } else { "Deep (the original's code and files could be read)" }
}

/// Whether an error is Clean room refusing a tool (so a client can offer Deep mode).
pub fn is_refusal(e: &ToolError) -> bool {
    e.details.as_ref().and_then(|d| d.get("reason")).and_then(serde_json::Value::as_str) == Some("clean_room")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_engine_tool_in_the_table_exists_and_none_is_listed_twice() {
        let r = crate::Registry::with_all_tools();
        let higher_layers = ["rebuild_", "assets_key_", "setup_"];
        for id in TOOLS {
            assert!(r.get(id).is_some() || higher_layers.iter().any(|p| id.starts_with(p)), "{id} isn't a tool");
            assert_eq!(TOOLS.iter().filter(|t| *t == id).count(), 1, "{id} is listed twice");
        }
    }

    #[test]
    fn looking_inside_needs_deep_mode() {
        for id in [
            "core_target_open",
            "core_target_triage",
            "native_function_pseudocode",
            "native_strings_browse",
            "js_app_map",
            "web_page_show",
            "game_archives_list",
        ] {
            assert!(!allows(id), "{id} reads the original");
            assert!(availability(id, true).is_some_and(|a| !a.available));
            assert!(availability(id, false).is_none(), "Deep mode runs {id}");
        }
        assert!(availability("web_site_capture", true).is_none());
        assert!(is_refusal(&refusal("native_functions_list")));
    }

    #[test]
    fn a_run_picks_its_mode_without_changing_the_settings() {
        let mut s = crate::testing::session();
        s.settings.deep_mode = false;
        assert!(s.clean_room());
        s.deep_for_run = Some(true);
        assert!(!s.clean_room() && !s.settings.deep_mode, "what's saved stays as it was");
        s.settings.deep_mode = true;
        s.deep_for_run = Some(false);
        assert!(s.clean_room());
    }
}
