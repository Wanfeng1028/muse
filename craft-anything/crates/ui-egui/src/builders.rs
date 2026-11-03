//! Who builds: the AIs that can build, the one that builds by default, the choice on Make
//! ("Built by"), and the dialog when nothing can build yet. One rule decides "can it build?"
//! ([`craft_anything_ai::default_builder`]), so the Make screen's warning and Start agree.

use crate::i18n::{tr, trf};
use crate::state::Modal;
use crate::theme::{self, Tokens};
use crate::{CraftApp, icons, widgets};
use craft_anything_ai::{BackendConfig, BackendKind};
use egui::{RichText, Ui, Vec2};

/// One AI that could build.
#[derive(Debug, Clone, PartialEq)]
pub struct Choice {
    pub name: String,
    /// What it is, in a few words ("Agent app", "Anthropic (Claude API) · claude-…").
    pub detail: String,
    /// Found on this computer and not set up yet: it's set up when a build starts with it.
    pub found: bool,
}

fn detail(b: &BackendConfig) -> String {
    match b.kind {
        BackendKind::AgentCli => tr("Coding agent app"),
        k if b.model.is_empty() => tr(k.title()),
        k => format!("{} · {}", tr(k.title()), b.model),
    }
}

impl CraftApp {
    /// Agent apps found on this computer that aren't set up yet (they need no key).
    fn found_agents(&self) -> impl Iterator<Item = &BackendConfig> {
        self.detected
            .iter()
            .flatten()
            .filter(|d| d.suggestion.kind == BackendKind::AgentCli && !d.needs_key)
            .map(|d| &d.suggestion)
            .filter(|s| !self.backends.iter().any(|b| b.name == s.name))
    }

    /// Every AI that can build: the ones set up and on, then agent apps found here.
    pub fn builder_choices(&self) -> Vec<Choice> {
        let set_up = self.backends.iter().filter(|b| b.enabled).map(|b| Choice { name: b.name.clone(), detail: detail(b), found: false });
        let found = self.found_agents().map(|b| Choice { name: b.name.clone(), detail: detail(b), found: true });
        set_up.chain(found).collect()
    }

    /// What builds when the person doesn't choose: the default from Settings → AI, else an agent
    /// app found on this computer.
    pub fn default_builder(&self) -> Option<String> {
        craft_anything_ai::default_builder(&self.backends, self.builder.as_deref()).or_else(|| self.found_agents().next()).map(|b| b.name.clone())
    }

    /// Something can build.
    pub fn can_build(&self) -> bool {
        self.default_builder().is_some()
    }

    /// The AI to build with: `wanted` while it can build, else the default. An agent app that was
    /// only found is set up now (it needs no key, and the person pressed Start).
    pub fn builder_backend(&mut self, wanted: Option<&str>) -> Option<String> {
        let choices = self.builder_choices();
        let name = wanted.filter(|w| choices.iter().any(|c| c.name == *w)).map(str::to_string).or_else(|| self.default_builder())?;
        let Some(found) = self.found_agents().find(|b| b.name == name).cloned() else { return Some(name) };
        match self.hub.add_backend(found.clone(), None) {
            Ok(()) => {
                self.backends.push(found);
                Some(name)
            }
            Err(e) => {
                self.toast(e.message, true);
                None
            }
        }
    }

    /// Turn an AI on or off in Settings → AI (it keeps its key).
    pub fn set_backend_enabled(&mut self, name: &str, on: bool) {
        let (hub, name) = (self.hub.clone(), name.to_string());
        self.jobs.spawn(if on { tr("Turn on an AI") } else { tr("Turn off an AI") }, false, move |_| {
            hub.set_enabled(&name, on).map_err(|e| e.message)?;
            Ok(crate::backends(&hub))
        });
    }

    /// Ask an AI which models it can use, for Settings → AI's model picker.
    pub fn pick_model(&mut self, name: &str) {
        let (hub, name) = (self.hub.clone(), name.to_string());
        self.model_picker = Some((name.clone(), None));
        self.jobs.spawn(tr("List an AI's models"), false, move |_| {
            let result = hub.model_choices(&name);
            Ok(crate::Done::ModelChoices { name, result })
        });
    }

    /// Use `model` for an AI from now on.
    pub fn set_model(&mut self, name: &str, model: &str) {
        self.model_picker = None;
        let (hub, name, model) = (self.hub.clone(), name.to_string(), model.to_string());
        self.jobs.spawn(tr("Change an AI's model"), false, move |_| {
            hub.set_model(&name, &model).map_err(|e| e.message)?;
            Ok(crate::backends(&hub))
        });
    }

    /// How hard a Claude AI thinks from now on.
    pub fn set_effort(&mut self, name: &str, effort: craft_anything_ai::Effort) {
        let (hub, name) = (self.hub.clone(), name.to_string());
        self.jobs.spawn(tr("Change how hard an AI thinks"), false, move |_| {
            hub.set_effort(&name, Some(effort)).map_err(|e| e.message)?;
            Ok(crate::backends(&hub))
        });
    }

    /// Connect the server in Settings → AI's address form. Its key goes to the keychain; the form
    /// keeps what was typed until it's added, so a mistake can be fixed.
    pub fn add_server(&mut self) {
        let hub = self.hub.clone();
        let f = &self.server_form;
        let (name, address, model, key) = (f.name.trim().to_string(), f.address.clone(), f.model.trim().to_string(), Some(f.key.clone()));
        self.jobs.spawn(trf("Connect {name}", &[("name", &name)]), true, move |_| {
            let result = hub.add_server(&name, &address, Some(model.as_str()).filter(|m| !m.is_empty()), key).map(|_| ());
            Ok(crate::Done::BackendAdded { name, result })
        });
    }

    /// Run an agent app from this program (`None`: find it by its usual name again).
    pub fn set_agent_program(&mut self, name: &str, program: Option<String>) {
        let (hub, name) = (self.hub.clone(), name.to_string());
        self.jobs.spawn(tr("Set an AI's program"), false, move |_| {
            hub.set_command(&name, program.as_deref()).map_err(|e| e.message)?;
            Ok(crate::backends(&hub))
        });
    }

    /// Remove an AI and its stored key.
    pub fn remove_backend(&mut self, name: &str) {
        let (hub, name) = (self.hub.clone(), name.to_string());
        self.jobs.spawn(tr("Remove an AI"), false, move |_| {
            hub.remove_backend(&name).map_err(|e| e.message)?;
            Ok(crate::backends(&hub))
        });
    }

    /// Nothing can build: say how to set something up (`start`: Start was pressed on Make, and
    /// picking an AI here starts the project).
    pub fn need_builder(&mut self, start: bool) {
        self.detect_backends();
        self.state.modal = Some(Modal::NeedBuilder { start });
    }
}

/// "Built by" on Make: the AI that builds this project. Automatic follows Settings → AI; picking
/// one is remembered by the project (its later changes are built by it too). With nothing that
/// can build, a warning and the way to set one up instead.
pub fn built_by(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let Some(default) = app.default_builder() else {
        icons::show(ui, "triangle-alert", 16.0, t.warning);
        ui.label(RichText::new(tr("Building needs a coding agent such as Claude Code, or an AI with an API key.")).size(theme::BODY).color(t.text_dim));
        if widgets::link(ui, "Set one up").clicked() {
            app.need_builder(false);
        }
        return;
    };
    let choices = app.builder_choices();
    // A choice that was removed or turned off meanwhile goes back to automatic.
    if app.state.make.ai.as_ref().is_some_and(|a| !choices.iter().any(|c| &c.name == a)) {
        app.state.make.ai = None;
    }
    let automatic = trf("Automatic ({name})", &[("name", &default)]);
    let shown = app.state.make.ai.clone().unwrap_or_else(|| automatic.clone());
    ui.label(RichText::new(tr("Built by")).size(theme::BODY).color(t.text_dim));
    let mut pick = None;
    let r = egui::ComboBox::from_id_salt("built-by").icon(widgets::combo_icon).selected_text(shown).width(220.0).show_ui(ui, |ui| {
        if ui.selectable_label(app.state.make.ai.is_none(), automatic).on_hover_text(tr("Whatever Settings → AI builds with.")).clicked() {
            pick = Some(None);
        }
        for c in &choices {
            let note = if c.found { format!("{} · {}", c.detail, tr("found on this computer; set up when you start")) } else { c.detail.clone() };
            if ui.selectable_label(app.state.make.ai.as_ref() == Some(&c.name), &c.name).on_hover_text(note).clicked() {
                pick = Some(Some(c.name.clone()));
            }
        }
    });
    widgets::named(r.response, "Built by");
    if let Some(p) = pick {
        app.state.make.ai = p;
    }
}

/// Nothing can build yet: what was found on this computer (one click to use it), a way to look
/// again, and Settings for API keys. Never a dead end.
pub fn need_builder_modal(app: &mut CraftApp, ui: &mut Ui, start: bool, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    ui.set_width(520.0);
    ui.horizontal(|ui| {
        let (rect, _) = ui.allocate_exact_size(Vec2::splat(48.0), egui::Sense::hover());
        ui.painter().rect_filled(rect, t.radius, t.accent_soft);
        icons::paint(ui, rect, "bot", 24.0, t.accent_ink);
        ui.vertical(|ui| {
            ui.label(theme::heading(tr("Set up a builder"), theme::CARD));
            ui.add(
                egui::Label::new(
                    RichText::new(tr(
                        "Building needs a coding agent on this computer (Claude Code, Codex or Gemini CLI: install one and sign in to it once in its own window), or an AI with an API key. Craft Anything never sees your account.",
                    ))
                    .color(t.text_dim),
                )
                .wrap(),
            );
        });
    });
    ui.add_space(14.0);
    let found: Vec<BackendConfig> = app.found_agents().cloned().collect();
    if app.detecting {
        ui.horizontal(|ui| {
            ui.add(egui::Spinner::new().color(t.accent));
            ui.label(RichText::new(tr("Looking on this computer…")).color(t.text_dim));
        });
    } else if found.is_empty() {
        ui.label(RichText::new(tr("No coding agent was found on this computer yet.")).color(t.text_dim));
    }
    for b in found {
        widgets::panel(&t).show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.horizontal(|ui| {
                icons::show(ui, "bot", 18.0, t.accent);
                ui.vertical(|ui| {
                    ui.label(RichText::new(&b.name).font(theme::semibold(theme::SMALL)));
                    ui.label(RichText::new(tr("Found on this computer")).color(t.text_faint).size(theme::CAPTION));
                });
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let label = if start { trf("Build with {name}", &[("name", &b.name)]) } else { trf("Use {name}", &[("name", &b.name)]) };
                    if widgets::primary(ui, &label).clicked() {
                        *close = true;
                        if start {
                            app.state.make.ai = Some(b.name.clone());
                            app.start_make();
                        } else {
                            app.builder_backend(Some(&b.name));
                        }
                    }
                });
            });
        });
        ui.add_space(6.0);
    }
    ui.add_space(10.0);
    ui.horizontal(|ui| {
        if !app.detecting && widgets::secondary(ui, Some("radar"), "Look again").on_hover_text(tr("After installing one, look for it again.")).clicked() {
            app.detect_backends();
        }
        if widgets::secondary(ui, Some("key-round"), "Use an API key…").clicked() {
            *close = true;
            app.state.settings_open = true;
            app.state.settings_tab = crate::state::SettingsTab::Ai;
        }
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if widgets::secondary(ui, None, "Cancel").clicked() {
                *close = true;
            }
        });
    });
}
