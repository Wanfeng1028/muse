//! The page: a welcome screen, drag and drop (and an Open button), then the answer.

use crate::triage::{Look, MAX_BYTES, look};
use craft_anything_evidence::Confidence;
use egui::{Color32, RichText};
#[allow(clippy::disallowed_types)] // The browser has one thread: nothing can wait here.
use std::sync::{Arc, Mutex, PoisonError};

// A few tokens copied from the desktop app's Studio theme (crates/ui-egui/src/theme.rs).
const CANVAS: Color32 = Color32::from_rgb(0x0e, 0x0e, 0x0f);
const CARD: Color32 = Color32::from_rgb(0x1a, 0x1a, 0x1c);
const CARD_BORDER: Color32 = Color32::from_rgb(0x2a, 0x2a, 0x2e);
const TEXT: Color32 = Color32::from_rgb(0xec, 0xec, 0xf0);
const TEXT_DIM: Color32 = Color32::from_rgb(0xa9, 0xa9, 0xb2);
/// The app colour (getartcraft.com's deep accent), as in the desktop app.
const BRAND: Color32 = Color32::from_rgb(0x16, 0x59, 0xc4);
/// The app colour as text on the dark background (getartcraft.com's light accent).
const BRAND_INK: Color32 = Color32::from_rgb(0x74, 0xaa, 0xff);
const SEEN_IT: Color32 = Color32::from_rgb(0x3f, 0xb2, 0x7f);
const WORKED_OUT: Color32 = Color32::from_rgb(0x5b, 0x8d, 0xef);
const BEST_GUESS: Color32 = Color32::from_rgb(0xe0, 0xa2, 0x3a);

/// A file handed over from outside a frame (the browser's file picker).
/// A file (name and contents), or a plain message saying why it couldn't be read.
#[allow(clippy::disallowed_types)]
pub type Inbox = Arc<Mutex<Option<Result<(String, Vec<u8>), String>>>>;

pub struct Viewer {
    look: Option<Look>,
    error: Option<String>,
    inbox: Inbox,
    /// Opens the browser's file picker; its result arrives in `inbox`.
    open: Box<dyn Fn()>,
    /// Reads a dropped file (asynchronously in the browser); its contents arrive in `inbox`.
    read_drop: Box<dyn Fn(egui::DroppedFileHandle)>,
}

impl Viewer {
    pub fn new(inbox: Inbox, open: Box<dyn Fn()>, read_drop: Box<dyn Fn(egui::DroppedFileHandle)>) -> Self {
        Viewer { look: None, error: None, inbox, open, read_drop }
    }

    pub fn setup(ctx: &egui::Context) {
        let mut visuals = egui::Visuals::dark();
        visuals.panel_fill = CANVAS;
        visuals.window_fill = CARD;
        visuals.override_text_color = Some(TEXT);
        visuals.selection.bg_fill = BRAND;
        visuals.hyperlink_color = BRAND_INK;
        // The desktop app's Studio theme is dark; don't follow the system's light preference.
        ctx.set_theme(egui::ThemePreference::Dark);
        ctx.set_visuals_of(egui::Theme::Dark, visuals);
    }

    fn take(&mut self, name: String, bytes: &[u8]) {
        if bytes.len() > MAX_BYTES {
            self.error = Some(format!("{name} is larger than {} MB, which is more than the web viewer reads.", MAX_BYTES / (1024 * 1024)));
            return;
        }
        self.error = None;
        self.look = Some(look(&name, bytes));
    }

    pub fn ui(&mut self, ui: &mut egui::Ui) {
        let ctx = ui.ctx().clone();
        let dropped = ctx.input_mut(|i| std::mem::take(&mut i.raw.dropped_files));
        if let Some(f) = dropped.into_iter().next() {
            (self.read_drop)(f);
        }
        let picked = self.inbox.lock().unwrap_or_else(PoisonError::into_inner).take();
        match picked {
            Some(Ok((name, bytes))) => self.take(name, &bytes),
            Some(Err(e)) => self.error = Some(e),
            None => {}
        }
        let hovering = ctx.input(|i| !i.raw.hovered_files.is_empty());

        egui::CentralPanel::default().show(ui, |ui| {
            egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
                ui.set_max_width(ui.available_width().min(860.0));
                ui.add_space(24.0);
                ui.horizontal(|ui| {
                    ui.label(RichText::new("Craft Anything").size(26.0).strong());
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button(RichText::new("Open a file…").size(15.0)).clicked() {
                            (self.open)();
                        }
                    });
                });
                ui.label(RichText::new("Drop a file to see what it is.").size(17.0).color(TEXT_DIM));
                ui.add_space(16.0);
                if hovering {
                    card(ui, |ui| {
                        ui.label(RichText::new("Let go to look at it").size(18.0).color(BRAND_INK));
                    });
                } else if let Some(e) = &self.error {
                    card(ui, |ui| {
                        ui.label(RichText::new(e).color(BEST_GUESS));
                    });
                } else if let Some(l) = &self.look {
                    show_look(ui, l);
                } else {
                    card(ui, |ui| {
                        ui.label(
                            "Drop a program, app, library or any file here. Craft Anything tells you what it is, what it runs on and what it was made with.",
                        );
                        ui.add_space(6.0);
                        ui.label(RichText::new("Everything happens in this page: your file is never uploaded.").color(TEXT_DIM));
                    });
                }
                ui.add_space(16.0);
                ui.label(
                    RichText::new(
                        "This is the small web version. The desktop app does much more: disassembly, functions and call graphs, \
                         JavaScript and Electron apps, Android, websites, devices, and an AI that explains what it finds.",
                    )
                    .color(TEXT_DIM),
                );
                ui.hyperlink_to("Get the desktop app", "https://github.com/storytold/craft-anything/releases/latest");
            });
        });
    }
}

fn card(ui: &mut egui::Ui, add: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::new().fill(CARD).stroke(egui::Stroke::new(1.0, CARD_BORDER)).corner_radius(12.0).inner_margin(18.0).show(ui, |ui| {
        ui.set_width(ui.available_width());
        add(ui);
    });
}

fn show_look(ui: &mut egui::Ui, l: &Look) {
    card(ui, |ui| {
        ui.label(RichText::new(&l.file_name).size(18.0).strong());
        let (color, label) = match l.confidence {
            Confidence::Observed => (SEEN_IT, "Seen it"),
            Confidence::Derived => (WORKED_OUT, "Worked it out"),
            Confidence::Inferred => (BEST_GUESS, "Best guess"),
        };
        ui.label(RichText::new(label).color(color).small());
        ui.add_space(6.0);
        ui.label(RichText::new(&l.summary).size(15.0));
        ui.add_space(10.0);
        egui::Grid::new("facts").num_columns(2).spacing([16.0, 6.0]).striped(true).show(ui, |ui| {
            for (k, v) in &l.facts {
                ui.label(RichText::new(k).color(TEXT_DIM));
                ui.add(egui::Label::new(RichText::new(v).monospace()).wrap());
                ui.end_row();
            }
        });
        if !l.limitations.is_empty() {
            ui.add_space(10.0);
            ui.label(RichText::new("What this can't tell you").color(TEXT_DIM));
            for m in &l.limitations {
                ui.label(format!("• {m}"));
            }
        }
        if !l.details.is_empty() {
            ui.add_space(10.0);
            egui::CollapsingHeader::new("All details (JSON)").show(ui, |ui| {
                ui.add(egui::Label::new(RichText::new(&l.details).monospace().size(12.0)).wrap());
            });
        }
    });
}
