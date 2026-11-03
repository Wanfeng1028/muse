//! Evidence: proof cards ("Show me the proof"), a pretty JSON viewer and compact ledger rows.

use crate::i18n::tr;
use crate::theme::{self, Tokens, confidence_color};
use crate::{icons, widgets};
use craft_anything_engine::evidence::{CoverageStatus, Evidence};
use egui::{Margin, RichText, Ui};
use serde_json::Value;

/// A proof card: summary + confidence up top, the details behind an expander.
pub fn proof_card(ui: &mut Ui, e: &Evidence, dense: bool, open: bool) {
    let t = Tokens::get(ui.ctx());
    let col = confidence_color(Some(e.confidence));
    let frame = egui::Frame::new().fill(t.card).stroke(egui::Stroke::new(1.0, t.card_border)).corner_radius(t.r_lg()).inner_margin(Margin::same(if dense {
        10
    } else {
        14
    }));
    frame.show(ui, |ui| {
        ui.set_width(ui.available_width());
        // A thin confidence stripe on the left edge.
        let r = ui.max_rect();
        ui.painter().rect_filled(egui::Rect::from_min_max(egui::pos2(r.left() - 8.0, r.top() + 2.0), egui::pos2(r.left() - 5.0, r.bottom() - 2.0)), 2.0, col);
        ui.horizontal(|ui| {
            widgets::confidence_badge(ui, Some(e.confidence));
            ui.label(RichText::new(nice_operation(&e.operation)).font(theme::medium(theme::CAPTION)).color(t.text_dim));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if e.environment.clean_room {
                    widgets::pill(ui, "Clean room", t.success, t.raised).on_hover_text(tr("Made without looking inside the original."));
                } else {
                    widgets::pill(ui, &e.environment.engine, t.accent_ink, t.accent_soft);
                }
            });
        });
        ui.add_space(4.0);
        if !e.summary.is_empty() {
            ui.label(RichText::new(&e.summary).size(if dense { 13.0 } else { 15.0 }));
        }
        let id = ui.id().with(("proof", &e.id));
        egui::CollapsingHeader::new(RichText::new(tr("Show me the proof")).color(t.accent_ink).font(theme::medium(theme::SMALL)))
            .id_salt(id)
            .default_open(open)
            .icon(widgets::disclosure_icon)
            .show(ui, |ui| {
                details(ui, e, &t);
            });
    });
}

fn details(ui: &mut Ui, e: &Evidence, t: &Tokens) {
    if !e.locations.is_empty() {
        widgets::caption(ui, "Where we found it");
        ui.horizontal_wrapped(|ui| {
            for l in e.locations.iter().take(40) {
                let text = match &l.label {
                    Some(lbl) => format!("{lbl}  {}", l.value),
                    None => l.value.clone(),
                };
                egui::Frame::new().fill(t.raised).corner_radius(t.r_sm()).inner_margin(Margin::symmetric(8, 3)).show(ui, |ui| {
                    ui.label(RichText::new(text).font(theme::mono(theme::CAPTION)).color(t.text)).on_hover_text(&l.kind);
                });
            }
            if e.locations.len() > 40 {
                ui.label(RichText::new(format!("+{}", e.locations.len() - 40)).color(t.text_faint));
            }
        });
        ui.add_space(6.0);
    }
    if !e.limitations.is_empty() {
        widgets::caption(ui, "What we couldn't check");
        for l in &e.limitations {
            ui.horizontal(|ui| {
                icons::show(ui, "info", 13.0, t.warning);
                ui.add(egui::Label::new(RichText::new(&l.message).color(t.text_dim)).wrap());
            });
        }
        ui.add_space(6.0);
    }
    ui.horizontal_wrapped(|ui| {
        let cov = match e.coverage.status {
            CoverageStatus::Complete => tr("Looked at everything"),
            CoverageStatus::Partial => match (e.coverage.examined, e.coverage.total) {
                (Some(a), Some(b)) => crate::i18n::trf("Looked at {a} of {b}", &[("a", &a.to_string()), ("b", &b.to_string())]),
                _ => tr("Looked at part of it"),
            },
            CoverageStatus::Unknown => tr("Coverage unknown"),
        };
        widgets::pill(ui, &cov, t.text_dim, t.raised);
        widgets::pill(ui, &format!("{} · {}", e.environment.engine, e.environment.host), t.text_faint, t.raised);
        let short = e.id.get(..18).unwrap_or(&e.id).to_string();
        if ui
            .add(egui::Button::new(RichText::new(format!("{short}…")).font(theme::mono(theme::CAPTION)).color(t.text_faint)).frame(false))
            .on_hover_text(tr("Copy the evidence id"))
            .clicked()
        {
            ui.ctx().copy_text(e.id.clone());
        }
    });
    ui.add_space(6.0);
    if let Some(code) = crate::workbench::code_text(&e.result) {
        widgets::caption(ui, "The code");
        egui::Frame::new().fill(t.code_bg).corner_radius(t.r()).inner_margin(Margin::same(10)).show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.label(RichText::new(truncate(code, 4000)).font(theme::mono(12.5)).color(t.text));
        });
        ui.add_space(6.0);
    }
    egui::CollapsingHeader::new(RichText::new(tr("The raw result")).color(t.text_dim).size(theme::CAPTION))
        .id_salt(("raw", &e.id))
        .default_open(false)
        .icon(widgets::disclosure_icon)
        .show(ui, |ui| {
            egui::Frame::new().fill(t.code_bg).corner_radius(t.r()).inner_margin(Margin::same(8)).show(ui, |ui| {
                ui.set_width(ui.available_width());
                json_tree(ui, "result", &e.result, 0);
            });
        });
}

/// `native_strings_browse` → "Native strings browse".
pub fn nice_operation(op: &str) -> String {
    let s = op.replace(['_', '.'], " ");
    let mut c = s.chars();
    match c.next() {
        Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        None => String::new(),
    }
}

const MAX_CHILDREN: usize = 200;
const MAX_DEPTH: usize = 24;

/// A collapsible, capped JSON tree in monospace.
pub fn json_tree(ui: &mut Ui, key: &str, v: &Value, depth: usize) {
    let t = Tokens::get(ui.ctx());
    let key_text = RichText::new(key).font(theme::mono(12.0)).color(t.accent_ink);
    if depth > MAX_DEPTH {
        ui.label(RichText::new("…").color(t.text_faint));
        return;
    }
    match v {
        Value::Object(m) => {
            egui::CollapsingHeader::new(key_text.clone().append_text(format!("  {{{}}}", m.len()), &t))
                .id_salt(ui.id().with((key, depth)))
                .default_open(depth < 2)
                .icon(widgets::disclosure_icon)
                .show(ui, |ui| {
                    for (k, v) in m.iter().take(MAX_CHILDREN) {
                        json_tree(ui, k, v, depth + 1);
                    }
                    if m.len() > MAX_CHILDREN {
                        ui.label(RichText::new(crate::i18n::trf("… {n} more", &[("n", &(m.len() - MAX_CHILDREN).to_string())])).color(t.text_faint));
                    }
                });
        }
        Value::Array(a) => {
            egui::CollapsingHeader::new(key_text.append_text(format!("  [{}]", a.len()), &t))
                .id_salt(ui.id().with((key, depth)))
                .default_open(depth < 1 && a.len() <= 20)
                .icon(widgets::disclosure_icon)
                .show(ui, |ui| {
                    for (i, v) in a.iter().take(MAX_CHILDREN).enumerate() {
                        json_tree(ui, &i.to_string(), v, depth + 1);
                    }
                    if a.len() > MAX_CHILDREN {
                        ui.label(RichText::new(crate::i18n::trf("… {n} more", &[("n", &(a.len() - MAX_CHILDREN).to_string())])).color(t.text_faint));
                    }
                });
        }
        leaf => {
            ui.horizontal(|ui| {
                ui.spacing_mut().item_spacing.x = 6.0;
                ui.label(RichText::new(format!("{key}:")).font(theme::mono(12.0)).color(t.accent_ink));
                let (text, col) = match leaf {
                    Value::String(s) => (format!("\"{}\"", truncate(s, 400)), t.text),
                    Value::Null => ("null".into(), t.text_faint),
                    Value::Bool(b) => (b.to_string(), theme::WORKED_OUT),
                    other => (other.to_string(), theme::SEEN_IT),
                };
                ui.add(egui::Label::new(RichText::new(text).font(theme::mono(12.0)).color(col)).wrap());
            });
        }
    }
}

trait AppendText {
    fn append_text(self, s: String, t: &Tokens) -> egui::WidgetText;
}

impl AppendText for RichText {
    fn append_text(self, s: String, t: &Tokens) -> egui::WidgetText {
        let mut job = egui::text::LayoutJob::default();
        job.append(self.text(), 0.0, egui::TextFormat { font_id: theme::mono(12.0), color: t.accent_ink, ..Default::default() });
        job.append(&s, 0.0, egui::TextFormat { font_id: theme::mono(12.0), color: t.text_faint, ..Default::default() });
        job.into()
    }
}

pub fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max { s.to_string() } else { s.chars().take(max).collect::<String>() + "…" }
}

/// A compact ledger row; returns true when clicked.
pub fn ledger_row(ui: &mut Ui, e: &Evidence, selected: bool) -> bool {
    let t = Tokens::get(ui.ctx());
    let col = confidence_color(Some(e.confidence));
    let resp = egui::Frame::new()
        .fill(if selected { t.accent_soft } else { t.card })
        .corner_radius(t.r_sm())
        .inner_margin(Margin::symmetric(8, 6))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.horizontal(|ui| {
                let (r, _) = ui.allocate_exact_size(egui::vec2(8.0, 8.0), egui::Sense::hover());
                ui.painter().circle_filled(r.center(), 3.5, col);
                ui.label(RichText::new(nice_operation(&e.operation)).font(theme::medium(theme::CAPTION)));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(RichText::new(tr(crate::theme::confidence_label(Some(e.confidence)))).size(theme::TINY).color(col));
                });
            });
            ui.add(egui::Label::new(RichText::new(truncate(&e.summary, 160)).size(theme::CAPTION).color(t.text_dim)).wrap());
        })
        .response;
    let resp = resp.interact(egui::Sense::click());
    if resp.hovered() && !selected {
        ui.painter().rect_stroke(resp.rect, t.radius_sm, egui::Stroke::new(1.0, t.field_border), egui::StrokeKind::Inside);
    }
    resp.clicked()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn operation_names_read_nicely() {
        assert_eq!(nice_operation("native_strings_browse"), "Native strings browse");
        assert_eq!(nice_operation(""), "");
        assert_eq!(truncate("héllo", 2), "hé…");
    }
}
