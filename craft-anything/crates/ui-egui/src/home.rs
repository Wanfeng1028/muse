//! Simple-mode Home: "What do you want to make?" and your projects, with one quiet link to look
//! inside something instead. Plus the friendly modals.

use crate::i18n::tr;
use crate::state::{Modal, Screen};
use crate::theme::{self, Tokens};
use crate::{CraftApp, Pick, Route, icons, widgets};
use craft_anything_engine::Consent;
use egui::{Margin, RichText, Ui, Vec2};
use serde_json::json;

/// Tools that open a website, best first.
pub const WEBSITE_TOOLS: &[&str] = &["web_site_open"];
/// Tools that list connected phones, best first.
pub const PHONE_TOOLS: &[&str] = &["adb_devices_find"];

pub static TUTORIALS: &[(&str, &str, &str, &[&str])] = &[
    (
        "calculator",
        "How does the % key work?",
        "Open a calculator app and find the code behind one button.",
        &[
            "Drop a calculator app (or any small program) on the window.",
            "Ask: \"How does the % key work?\"",
            "Open \"Show me the proof\" to see the exact code we found, and how sure we are.",
        ],
    ),
    (
        "network",
        "What does it send over the internet?",
        "See which servers an app talks to, and what it says.",
        &[
            "Open the app you're curious about.",
            "Ask: \"What does it send over the internet?\"",
            "We list the web addresses and messages we can see inside it. Watching it live needs your OK first.",
        ],
    ),
    (
        "safe",
        "Is this file safe to open?",
        "A first look at a file you're unsure about, without running it.",
        &[
            "Drop the file on the window. We only read it; nothing runs.",
            "Ask: \"Is it safe to run?\"",
            "Each answer says how sure we are: Seen it, Worked it out or Best guess.",
        ],
    ),
];

pub fn show(app: &mut CraftApp, ui: &mut Ui) {
    egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
        let full_w = ui.available_width();
        let w = full_w.min(1000.0) - 48.0;
        let pad = ((full_w - w) / 2.0).max(24.0);
        // Tight enough that Start is in view at 900 px with every choice showing (tested).
        ui.add_space(24.0);
        ui.horizontal(|ui| {
            ui.add_space(pad);
            ui.vertical(|ui| {
                ui.set_width(w);
                crate::make::hero(app, ui, w);
                ui.add_space(36.0);
            });
        });
    });
}

/// Friendly modals (coming soon, website, tutorials).
pub fn modals(app: &mut CraftApp, ctx: &egui::Context) {
    let Some(modal) = app.state.modal.clone() else {
        // Closed, however it was: the website field is focused again when it next opens.
        ctx.data_mut(|d| d.remove::<bool>(egui::Id::new("website-dialog-focused")));
        return;
    };
    let t = Tokens::get(ctx);
    let mut close = false;
    let resp = egui::Modal::new(egui::Id::new("craft-modal"))
        .frame(egui::Frame::new().fill(t.card).corner_radius(t.r_lg()).inner_margin(Margin::same(24)).stroke(egui::Stroke::new(1.0, t.card_border)))
        .show(ctx, |ui| {
            ui.set_width(440.0);
            match &modal {
                Modal::ComingSoon { title, body, icon } => {
                    let (rect, _) = ui.allocate_exact_size(Vec2::splat(52.0), egui::Sense::hover());
                    ui.painter().rect_filled(rect, t.radius, t.accent_soft);
                    icons::paint(ui, rect, icon, 26.0, t.accent_ink);
                    ui.add_space(10.0);
                    ui.label(theme::heading(tr(title), theme::SECTION));
                    ui.add_space(4.0);
                    ui.label(RichText::new(tr(body)).color(t.text_dim));
                    ui.add_space(16.0);
                    if widgets::primary(ui, "Got it").clicked() {
                        close = true;
                    }
                }
                Modal::Website => {
                    ui.label(theme::heading(tr("Look at a website"), theme::SECTION));
                    ui.add_space(8.0);
                    let r = ui.add(
                        egui::TextEdit::singleline(&mut app.state.url_input)
                            .hint_text("https://example.com")
                            .desired_width(f32::INFINITY)
                            .frame(widgets::text_field_frame(&t)),
                    );
                    widgets::named(r.clone(), "Website address");
                    // Ready to type into as the dialog opens.
                    let opened = egui::Id::new("website-dialog-focused");
                    if !ui.data(|d| d.get_temp::<bool>(opened).unwrap_or(false)) {
                        r.request_focus();
                        ui.data_mut(|d| d.insert_temp(opened, true));
                    }
                    let enter = r.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
                    ui.add_space(12.0);
                    ui.horizontal(|ui| {
                        let ok = !app.state.url_input.trim().is_empty();
                        if (widgets::primary_icon(ui, Some("globe"), "Open it", ok).clicked() || enter)
                            && ok
                            && let Some(tool) = app.first_tool(WEBSITE_TOOLS)
                        {
                            let url = app.state.url_input.trim().to_string();
                            let params = app.params_for(tool, &[("url", json!(url))]);
                            app.state.screen = Screen::Ask;
                            app.run_tool(
                                tool,
                                params,
                                Route::Chat { intro: tr("Here's what I found on that page:"), cta: app.state.backend.is_none() },
                                Consent::NotAsked,
                            );
                            close = true;
                        }
                        if widgets::secondary(ui, None, "Cancel").clicked() {
                            close = true;
                        }
                    });
                }
                Modal::Tutorial(i) => {
                    if let Some((_, title, blurb, steps)) = TUTORIALS.get(*i) {
                        ui.label(theme::heading(tr(title), theme::SECTION));
                        ui.label(RichText::new(tr(blurb)).color(t.text_dim));
                        ui.add_space(12.0);
                        for (n, s) in steps.iter().enumerate() {
                            ui.horizontal(|ui| {
                                let (rect, _) = ui.allocate_exact_size(Vec2::splat(24.0), egui::Sense::hover());
                                ui.painter().circle_filled(rect.center(), 12.0, t.accent_soft);
                                ui.painter().text(
                                    rect.center(),
                                    egui::Align2::CENTER_CENTER,
                                    (n + 1).to_string(),
                                    theme::semibold(theme::CAPTION),
                                    t.accent_ink,
                                );
                                ui.add(egui::Label::new(tr(s)).wrap());
                            });
                            ui.add_space(4.0);
                        }
                        ui.add_space(12.0);
                        ui.horizontal(|ui| {
                            if widgets::primary_icon(ui, Some("folder-open"), "Open something", true).clicked() {
                                app.pick(Pick::OpenFile);
                                close = true;
                            }
                            if widgets::secondary(ui, None, "Close").clicked() {
                                close = true;
                            }
                        });
                    }
                }
                Modal::Engine(b) => crate::engine_ui::modal(app, ui, *b, &mut close),
                Modal::Assets => crate::engine_ui::assets_modal(app, ui, &mut close),
                Modal::Ghidra => crate::engine_ui::ghidra_modal(app, ui, &mut close),
                Modal::GamePermission => crate::game_files::permission_modal(app, ui, &mut close),
                Modal::DeepMode => crate::engine_ui::deep_modal(app, ui, &mut close),
                Modal::ExistingFiles => crate::folders::existing_modal(app, ui, &mut close),
                Modal::NeedBuilder { start } => crate::builders::need_builder_modal(app, ui, *start, &mut close),
                Modal::Rename(root) => crate::manage::rename_modal(app, ui, root, &mut close),
                Modal::Delete(root) => crate::manage::delete_modal(app, ui, root, &mut close),
                Modal::Pin => crate::pins::pin_modal(app, ui, &mut close),
                Modal::PinRename(root, id) => crate::pins::rename_modal(app, ui, root, *id, &mut close),
                Modal::PinDelete(root, id) => crate::pins::delete_modal(app, ui, root, *id, &mut close),
                Modal::About => {
                    ui.label(theme::heading("Craft Anything", theme::SECTION));
                    ui.label(RichText::new(format!("{} {}", tr("Version"), env!("CARGO_PKG_VERSION"))).color(t.text_dim));
                    ui.add_space(12.0);
                    if widgets::primary(ui, "Close").clicked() {
                        close = true;
                    }
                }
            }
        });
    if resp.should_close() {
        dismiss(app);
    } else if close {
        app.state.modal = None;
    }
}

/// Close the dialog without choosing (Esc, a click outside). With nothing downloading, the
/// project waiting on it doesn't start later by itself.
pub fn dismiss(app: &mut CraftApp) {
    if app.ghidra.job.is_none() {
        app.ghidra.start_after = None;
    }
    if app.engine_flow.job.is_none() {
        app.engine_flow.start_after = false;
    }
    app.state.modal = None;
}
