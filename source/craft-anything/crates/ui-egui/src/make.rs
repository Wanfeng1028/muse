//! Simple mode's front door, for people new to computers: two numbered questions in plain words
//! ("What do you want to recreate?", "Say what you want"), big targets and one big Start button. Below it,
//! the projects made so far.

use crate::i18n::tr;
use crate::state::MakeDraft;
use crate::theme::{self, Tokens};
use crate::{CraftApp, Pick, icons, widgets};
use craft_anything_engine::workspace::{Status, TargetRef};
use egui::{Margin, RichText, Sense, Ui, Vec2};

const SUGGESTIONS_WEB: &[&str] = &["Recreate this website", "Recreate it with darker colours"];
const SUGGESTIONS_APP: &[&str] = &["Make my own version of this app", "Recreate just its main feature"];
const SUGGESTIONS_GAME: &[&str] = &["Make a game that plays like this", "Make a simpler version of this game"];
const SUGGESTIONS_NONE: &[&str] = &["A website for my bakery", "A simple snake game"];

/// The first http(s) address in some text.
pub fn find_url(text: &str) -> Option<String> {
    text.split_whitespace()
        .map(|w| w.trim_matches(|c: char| matches!(c, '"' | '\'' | '(' | ')' | '<' | '>' | ',' | '.' | ';')))
        .find(|w| w.starts_with("http://") || w.starts_with("https://"))
        .map(str::to_string)
}

/// Why a typed web address can't be used, or `None` when it's fine (or empty).
pub fn url_problem(typed: &str) -> Option<&'static str> {
    let t = typed.trim();
    if t.is_empty() {
        return None;
    }
    let url = normalize_url(t);
    let host = url.split("://").nth(1).unwrap_or_default().split(['/', '?', '#']).next().unwrap_or_default();
    let host = host.rsplit('@').next().unwrap_or_default().split(':').next().unwrap_or_default();
    let ok = (url.starts_with("http://") || url.starts_with("https://"))
        && !t.chars().any(char::is_whitespace)
        && (host == "localhost" || (host.contains('.') && !host.starts_with('.') && !host.ends_with('.')));
    (!ok).then_some("Enter a full web address, like example.com or https://example.com/page.")
}

/// "example.com" → "https://example.com"; anything with a scheme is kept.
pub fn normalize_url(s: &str) -> String {
    let t = s.trim();
    if t.is_empty() || t.contains("://") { t.to_string() } else { format!("https://{t}") }
}

/// The target the draft will use: the picked one, the typed address, or an address in the request.
pub fn resolve_target(d: &MakeDraft) -> TargetRef {
    if d.target != TargetRef::None {
        return d.target.clone();
    }
    if !d.url.trim().is_empty() {
        return TargetRef::parse(&normalize_url(&d.url));
    }
    find_url(&d.request).map(|url| TargetRef::Website { url }).unwrap_or(TargetRef::None)
}

/// A game is being copied or made, so it's built with a game engine ("Build with").
pub fn is_game(kinds: &craft_anything_ai::rebuild::KindRegistry, d: &MakeDraft) -> bool {
    use craft_anything_ai::rebuild::GameKind;
    d.found.is_some()
        || (d.game && matches!(d.target, TargetRef::Local { .. }))
        || kinds.choose(&d.request, &resolve_target(d), false).is_some_and(|(k, _)| k.id() == GameKind::ID)
}

/// The front door: make your own version of something, or just look inside it.
pub fn hero(app: &mut CraftApp, ui: &mut Ui, w: f32) {
    let t = Tokens::get(ui.ctx());
    if let Some(i) = widgets::segmented_sized(ui, &["Make my own version", "Just look inside"], usize::from(app.state.make.look), 38.0, 12.5) {
        app.state.make.look = i == 1;
    }
    ui.add_space(18.0);
    if app.state.make.look {
        look(app, ui, w);
        return;
    }
    ui.label(theme::heading(tr("What do you want to make?"), theme::TITLE));
    ui.add_space(6.0);
    ui.label(RichText::new(tr("Choose what to recreate, say what you want, then press Start.")).size(theme::LEAD).color(t.text_dim));
    ui.add_space(16.0);
    widgets::card(&t).inner_margin(Margin::same(20)).show(ui, |ui| {
        ui.set_width(w - 50.0);
        step_title(ui, 1, "What do you want to recreate?");
        ui.add_space(12.0);
        choose_target(app, ui);
        // How closely the original may be looked at, once there is one.
        let d = &app.state.make;
        if matches!(d.target, TargetRef::Local { .. }) || d.editing_url || !d.url.is_empty() {
            ui.add_space(14.0);
            look_inside(app, ui);
        }
        ui.add_space(20.0);
        step_title(ui, 2, "Say what you want");
        ui.add_space(12.0);
        // The example matches the tile picked above (a "recreate this website" hint under
        // "Nothing — start fresh" contradicts the choice).
        let d = &app.state.make;
        let hint = match &d.target {
            TargetRef::Local { .. } if d.game => "For example: the same game, with a high-score table",
            TargetRef::Local { .. } => "For example: the same app, but simpler",
            TargetRef::Website { .. } => "For example: recreate this website",
            TargetRef::None if d.editing_url || !d.url.is_empty() => "For example: recreate this website",
            TargetRef::None => "For example: a website for my bakery",
        };
        // Websites are photographed for the builder; anything else looks right from pictures.
        let website = matches!(resolve_target(d), TargetRef::Website { .. }) || d.editing_url;
        let out = crate::prompt_box::show(
            ui,
            &mut app.state.make.request,
            &app.state.make.pictures,
            crate::prompt_box::PromptBox {
                name: "Say what you want",
                hint: tr(hint),
                rows: (3, 10),
                attach: (!website).then_some("Add pictures of the original (optional: screenshots help it look right)"),
                stop_button: None,
                send: false,
                recall: false,
                history: None,
                font_size: theme::LEAD,
            },
        );
        if let Some(i) = out.remove {
            app.state.make.pictures.remove(i);
        }
        if out.attach {
            app.pick(Pick::Pictures);
        }
        let submit = out.send;
        if app.state.make.request.trim().is_empty() {
            ui.add_space(10.0);
            suggestions(app, ui);
        }
        if is_game(&app.kinds, &app.state.make) {
            ui.add_space(22.0);
            crate::engine_ui::build_with(app, ui);
            ui.add_space(14.0);
            let on = app.state.make.generate_assets;
            crate::engine_ui::assets_toggle(app, ui, on);
        }
        ui.add_space(16.0);
        ui.horizontal(|ui| {
            crate::builders::built_by(app, ui);
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                let ready = !app.state.make.request.trim().is_empty() && url_problem(&app.state.make.url).is_none() && app.creating.is_none();
                let start = widgets::primary_sized(ui, Some("sparkles"), "Start", ready, 50.0, 14.0);
                let start = if ready { start } else { start.on_disabled_hover_text(tr("Say what you want first.")) };
                if (start.clicked() || submit) && ready {
                    app.start_make();
                }
            });
        });
        // Where it's saved: secondary to Start, so under it.
        ui.add_space(10.0);
        crate::folders::make_line(app, ui);
    });
}

/// "Just look inside": what to look at, each opening straight away. Nothing is built or run.
fn look(app: &mut CraftApp, ui: &mut Ui, w: f32) {
    let t = Tokens::get(ui.ctx());
    ui.label(theme::heading(tr("What do you want to look inside?"), theme::TITLE));
    ui.add_space(6.0);
    ui.label(RichText::new(tr("We only read it; nothing runs. Every answer shows how sure we are.")).size(theme::LEAD).color(t.text_dim));
    ui.add_space(22.0);
    widgets::card(&t).inner_margin(Margin::same(24)).show(ui, |ui| {
        ui.set_width(w - 50.0);
        // Each of these reads the original, which Clean room never does.
        if !app.settings.deep_mode {
            crate::engine_ui::deep_needed(app, ui);
            return;
        }
        let size = Vec2::new(ui.available_width(), 72.0);
        ui.spacing_mut().item_spacing.y = 10.0;
        if widgets::choice_tile(ui, size, "app-window", "An app or a file", "See how a program works: what it does, what it talks to, what's inside.", false)
            .clicked()
        {
            app.pick(Pick::OpenFile);
        }
        if widgets::choice_tile(ui, size, "globe", "A website", "See how a page is built: its layout, styles, scripts and the requests it makes.", false)
            .clicked()
        {
            app.state.modal = Some(crate::state::Modal::Website);
        }
        if widgets::choice_tile(ui, size, "package", "A game's files", "See what a game packs, and save its pictures as PNG files.", false).clicked() {
            app.state.screen = crate::state::Screen::GameFiles;
        }
    });
}

/// "1  What do you want to recreate?" — a numbered circle and a plain question.
fn step_title(ui: &mut Ui, n: u32, text: &str) {
    let t = Tokens::get(ui.ctx());
    ui.horizontal(|ui| {
        let (r, _) = ui.allocate_exact_size(Vec2::splat(28.0), Sense::hover());
        ui.painter().rect(r, r.width() / 2.0, t.raised, egui::Stroke::new(1.0, t.card_border), egui::StrokeKind::Inside);
        let g = widgets::label_galley(ui, &n.to_string(), 13.0, t.text);
        ui.painter().galley_with_override_text_color(r.center() - g.size() / 2.0, g, t.text);
        ui.add_space(4.0);
        ui.label(theme::heading(tr(text), theme::SECTION));
    });
}

fn choose_target(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let d = &app.state.make;
    let local = matches!(d.target, TargetRef::Local { .. }).then_some(d.game);
    let website = local.is_none() && (d.editing_url || !d.url.is_empty());
    let scratch = local.is_none() && !website;
    let gap = 10.0;
    let cols = if ui.available_width() > 760.0 { 4 } else { 2 };
    let tile_w = ((ui.available_width() - gap * (cols as f32 - 1.0)) / cols as f32).floor();
    let size = Vec2::new(tile_w, 60.0);
    let mut pick = None;
    ui.horizontal_wrapped(|ui| {
        ui.spacing_mut().item_spacing = Vec2::splat(gap);
        for (i, (icon, label, on)) in [
            ("globe", "A website", website),
            ("app-window", "An app", local == Some(false)),
            ("puzzle", "A game", local == Some(true)),
            ("sparkles", "Nothing — start fresh", scratch),
        ]
        .into_iter()
        .enumerate()
        {
            if widgets::choice_tile(ui, size, icon, label, "", on).clicked() {
                pick = Some(i);
            }
        }
    });
    let m = &mut app.state.make;
    if matches!(pick, Some(0) | Some(3)) {
        // A different kind of start: forget the last game's engine and the engine picked for it.
        m.found = None;
        m.builder = None;
    }
    match pick {
        Some(0) => {
            m.target = TargetRef::None;
            m.editing_url = true;
        }
        Some(1) => app.pick(Pick::TargetFile),
        Some(2) => app.pick(Pick::TargetFolder),
        Some(_) => {
            m.target = TargetRef::None;
            m.url.clear();
            m.editing_url = false;
        }
        None => {}
    }
    let m = &mut app.state.make;
    // Recomputed so the address field shows on the very frame "A website" is clicked.
    let website = !matches!(m.target, TargetRef::Local { .. }) && (m.editing_url || !m.url.is_empty());
    if let TargetRef::Local { path } = m.target.clone() {
        ui.add_space(14.0);
        ui.horizontal(|ui| {
            ui.label(RichText::new(tr("You chose:")).size(theme::BODY).color(t.text_dim));
            ui.label(RichText::new(m.target.label()).font(theme::semibold(theme::BODY)));
            ui.label(RichText::new(crate::short_path(&path)).color(t.text_faint).size(theme::SMALL));
        });
    } else if website {
        ui.add_space(16.0);
        ui.label(RichText::new(tr("Type the website's address:")).size(theme::BODY).color(t.text_dim));
        ui.add_space(6.0);
        let r = ui.add(
            egui::TextEdit::singleline(&mut m.url)
                .hint_text("example.com")
                .desired_width(520.0)
                .font(egui::FontId::proportional(theme::LEAD))
                .frame(widgets::text_field_frame(&t).inner_margin(Margin::symmetric(14, 12))),
        );
        if pick == Some(0) {
            r.request_focus();
        }
        // Say what's wrong right under the field, once something has been typed.
        if let Some(problem) = url_problem(&m.url) {
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                icons::show(ui, "triangle-alert", 16.0, t.danger);
                ui.label(RichText::new(tr(problem)).color(t.danger).size(theme::BODY));
            });
        }
    }
}

/// Clean room or Deep for what is recreated: the title bar's switch, as a plain choice.
fn look_inside(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    // The app's one setting (the title bar's switch), not this project's: said where it's chosen.
    ui.horizontal_wrapped(|ui| {
        ui.label(RichText::new(tr("How closely may Craft Anything look at it?")).size(theme::BODY).color(t.text_dim));
        ui.label(RichText::new(tr("For everything you make, like the switch in the title bar.")).size(theme::SMALL).color(t.text_faint));
    });
    ui.add_space(6.0);
    let deep = app.settings.deep_mode;
    let gap = 10.0;
    let size = Vec2::new(((ui.available_width() - gap) / 2.0).floor(), 72.0);
    let mut pick = None;
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = gap;
        for (on, icon, label, blurb) in [
            (false, "shield-check", "Clean room", "Nothing inside it is read; Craft Anything works from what you can see. Your version gets its own art."),
            (true, "microscope", "Deep", "Craft Anything reads its code and files with every tool it has. For your private use."),
        ] {
            if widgets::choice_tile(ui, size, icon, label, blurb, deep == on).clicked() {
                pick = Some(on);
            }
        }
    });
    if let Some(on) = pick {
        app.set_deep(on);
    }
    // Ghidra reads programs, not websites.
    if !matches!(app.state.make.target, TargetRef::Local { .. }) {
        return;
    }
    if app.settings.deep_mode && !app.ghidra_missing() {
        ui.add_space(8.0);
        ui.horizontal_wrapped(|ui| {
            icons::show(ui, "cpu", 16.0, t.icon);
            let line = format!("{} {}", crate::engine_ui::ghidra_memory_words(app), tr("More makes a big program's first look faster."));
            ui.label(RichText::new(line).size(theme::SMALL).color(t.text_dim)).on_hover_text(crate::engine_ui::ghidra_memory_guide());
            if widgets::link(ui, "Change").clicked() {
                app.state.settings_open = true;
                app.state.settings_tab = crate::state::SettingsTab::Engines;
            }
        });
    }
    if app.settings.deep_mode && app.ghidra_missing() {
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            icons::show(ui, "triangle-alert", 16.0, t.warning);
            ui.label(RichText::new(tr("Ghidra isn't on this computer yet, so the built-in decompiler stands in.")).size(theme::SMALL).color(t.text_dim));
            if app.ghidra.job.is_none() && widgets::secondary(ui, Some("download"), "Get Ghidra").clicked() {
                app.state.modal = Some(crate::state::Modal::Ghidra);
            }
        });
    }
}

fn suggestions(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let list = match resolve_target(&app.state.make) {
        TargetRef::Website { .. } => SUGGESTIONS_WEB,
        TargetRef::Local { .. } if app.state.make.game => SUGGESTIONS_GAME,
        TargetRef::Local { .. } => SUGGESTIONS_APP,
        TargetRef::None => SUGGESTIONS_NONE,
    };
    ui.horizontal_wrapped(|ui| {
        ui.spacing_mut().item_spacing = Vec2::new(8.0, 8.0);
        ui.label(RichText::new(tr("Ideas:")).size(theme::BODY).color(t.text_dim));
        for s in list.iter().take(2) {
            if widgets::suggestion(ui, s).clicked() {
                app.state.make.request = tr(s);
            }
        }
    });
}

/// Time since `ms` in plain words.
pub fn ago(ms: u64) -> String {
    let now = craft_anything_engine::inbox::now_ms();
    let s = now.saturating_sub(ms) / 1000;
    match s {
        0..=59 => tr("just now"),
        60..=3599 => crate::i18n::trf("{n} min ago", &[("n", &(s / 60).to_string())]),
        3600..=86_399 => crate::i18n::trf("{n} h ago", &[("n", &(s / 3600).to_string())]),
        86_400..=172_799 => tr("yesterday"),
        _ => crate::i18n::trf("{n} days ago", &[("n", &(s / 86_400).to_string())]),
    }
}

/// A project's status as the app shows it: waiting its turn, interrupted (its run stopped
/// part-way: the app or the computer closed), or the one it saved. (label, text, fill).
pub fn status_shown(app: &CraftApp, ws: &craft_anything_engine::workspace::Workspace, t: &Tokens) -> (&'static str, egui::Color32, egui::Color32) {
    let s = ws.manifest.status;
    let (label, look) = if app.asking.contains(&ws.root) {
        ("Needs you", Status::NeedsYou)
    } else if app.runs.position(&ws.root).is_some() {
        ("Waiting", s)
    } else if crate::project::interrupted(app, ws) {
        ("Interrupted", Status::NeedsYou)
    } else {
        (s.label(), s)
    };
    let (fg, bg) = status_colors(t, look);
    (label, fg, bg)
}

pub fn status_colors(t: &Tokens, s: Status) -> (egui::Color32, egui::Color32) {
    match s {
        Status::Ready => (t.success, t.raised),
        Status::NeedsYou => (t.warning, t.raised),
        Status::Stopped | Status::New => (t.text_dim, t.raised),
        _ => (t.accent_ink, t.accent_soft),
    }
}

/// A project's icon: a game (built with a game engine), a website, an app, or something new.
pub fn project_icon(m: &craft_anything_engine::workspace::Manifest) -> &'static str {
    if craft_anything_engines::game::Builder::from_stack(&m.stack).is_some() {
        return "puzzle";
    }
    match m.target {
        TargetRef::Website { .. } => "globe",
        TargetRef::Local { .. } => "app-window",
        TargetRef::None => "sparkles",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn web_addresses_are_checked_inline() {
        for ok in ["", "example.com", "https://a.b/c?d", "http://localhost:5173", "sub.example.co.uk/page"] {
            assert!(url_problem(ok).is_none(), "{ok}");
        }
        for bad in ["example", "https://", "two words.com", "ftp://x.y", "https://.com", "x."] {
            assert!(url_problem(bad).is_some(), "{bad}");
        }
    }

    #[test]
    fn targets_from_the_draft() {
        let mut d = MakeDraft { request: "Please recreate https://example.com/pricing.".into(), ..Default::default() };
        assert_eq!(resolve_target(&d), TargetRef::Website { url: "https://example.com/pricing".into() });
        d.url = "acme.io".into();
        assert_eq!(resolve_target(&d), TargetRef::Website { url: "https://acme.io".into() }, "the typed address wins");
        d.url.clear();
        d.request = "a snake game".into();
        assert_eq!(resolve_target(&d), TargetRef::None);
        assert_eq!(normalize_url("http://x.y"), "http://x.y");
    }
}
