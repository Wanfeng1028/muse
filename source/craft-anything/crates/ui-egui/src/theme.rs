//! Design system: two themes (Studio dark, Studio Light), colour tokens, radii and type.
//!
//! A calm desktop look: neutral graphite (or near-white) surfaces, a slightly darker sidebar,
//! soft rounded cards and controls, sentence-case DM Sans throughout, and ink-filled main buttons.
//! Indigo is the app colour for highlights, progress, links and selection.
//! Widgets read [`Tokens::get`] instead of hard-coding colours, so a theme switch applies everywhere.
//! Confidence has its own fixed palette so "how sure are we" reads the same in both themes.

use craft_anything_engine::evidence::Confidence;
use egui::{Color32, CornerRadius, FontData, FontDefinitions, FontFamily, FontId, Stroke, TextStyle, Visuals};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum ThemeKind {
    #[default]
    Studio,
    StudioLight,
}

impl ThemeKind {
    pub const ALL: [ThemeKind; 2] = [ThemeKind::Studio, ThemeKind::StudioLight];

    pub fn label(self) -> &'static str {
        match self {
            ThemeKind::Studio => "Studio (dark)",
            ThemeKind::StudioLight => "Studio Light",
        }
    }

    /// The value stored in `settings.theme`.
    pub fn id(self) -> &'static str {
        match self {
            ThemeKind::Studio => "studio",
            ThemeKind::StudioLight => "studio-light",
        }
    }

    pub fn from_id(s: &str) -> ThemeKind {
        match s.trim().to_ascii_lowercase().replace(['_', ' '], "-").as_str() {
            "studio-light" | "light" => ThemeKind::StudioLight,
            _ => ThemeKind::Studio,
        }
    }
}

/// Colour and shape tokens.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Tokens {
    pub kind: ThemeKind,
    /// Title bar, rails, panels.
    pub chrome: Color32,
    /// The main reading surface behind cards.
    pub canvas: Color32,
    pub card: Color32,
    pub card_border: Color32,
    /// A card a step above `card` (hovered cards, chips).
    pub raised: Color32,
    pub field: Color32,
    pub field_border: Color32,
    pub hover: Color32,
    pub pressed: Color32,
    pub text: Color32,
    pub text_dim: Color32,
    pub text_faint: Color32,
    pub icon: Color32,
    pub accent: Color32,
    pub accent_hover: Color32,
    /// Indigo that reads as text on the theme's surfaces.
    pub accent_ink: Color32,
    /// Indigo wash for soft highlights.
    pub accent_soft: Color32,
    /// Text drawn on an `accent` fill.
    pub on_accent: Color32,
    pub separator: Color32,
    pub shadow: Color32,
    pub danger: Color32,
    pub warning: Color32,
    pub success: Color32,
    pub code_bg: Color32,
    pub radius_sm: f32,
    pub radius: f32,
    pub radius_lg: f32,
}

/// The app colour: getartcraft.com's deep accent (#1659c4). White on it passes WCAG AA; on its
/// bright accent (#2d81ff, used for hover) it doesn't.
pub const BRAND: Color32 = Color32::from_rgb(0x16, 0x59, 0xc4);

pub const SEEN_IT: Color32 = Color32::from_rgb(0x3f, 0xb2, 0x7f);
pub const WORKED_OUT: Color32 = Color32::from_rgb(0x5b, 0x8d, 0xef);
pub const BEST_GUESS: Color32 = Color32::from_rgb(0xe0, 0xa2, 0x3a);
pub const UNKNOWN: Color32 = Color32::from_rgb(0x8a, 0x8a, 0x93);

/// The colour for a confidence level (`None` = unknown).
pub fn confidence_color(c: Option<Confidence>) -> Color32 {
    match c {
        Some(Confidence::Observed) => SEEN_IT,
        Some(Confidence::Derived) => WORKED_OUT,
        Some(Confidence::Inferred) => BEST_GUESS,
        None => UNKNOWN,
    }
}

pub fn confidence_label(c: Option<Confidence>) -> &'static str {
    c.map(Confidence::plain_label).unwrap_or("Unknown")
}

impl Tokens {
    pub fn for_kind(kind: ThemeKind) -> Self {
        match kind {
            // getartcraft.com's dark: warm near-black (#121316), its #101014 for the sidebar, cards
            // and controls its warm ink (#f2f1ee) laid over the background at 4-15%.
            ThemeKind::Studio => Tokens {
                kind,
                chrome: Color32::from_rgb(0x10, 0x10, 0x14),
                canvas: Color32::from_rgb(0x12, 0x13, 0x16),
                card: Color32::from_rgb(0x1b, 0x1c, 0x1f),
                card_border: Color32::from_rgb(0x34, 0x34, 0x36),
                raised: Color32::from_rgb(0x22, 0x23, 0x25),
                field: Color32::from_rgb(0x1b, 0x1c, 0x1f),
                field_border: Color32::from_rgb(0x6c, 0x6c, 0x6c),
                hover: Color32::from_rgb(0x22, 0x23, 0x25),
                pressed: Color32::from_rgb(0x2d, 0x2e, 0x30),
                text: Color32::from_rgb(0xf2, 0xf1, 0xee),
                text_dim: Color32::from_rgb(0xb3, 0xb3, 0xb2),
                text_faint: Color32::from_rgb(0x8d, 0x8d, 0x8d),
                icon: Color32::from_rgb(0xa8, 0xa8, 0xa6),
                accent: BRAND,
                accent_hover: Color32::from_rgb(0x2d, 0x81, 0xff),
                accent_ink: Color32::from_rgb(0x74, 0xaa, 0xff),
                accent_soft: Color32::from_rgba_unmultiplied(0x2d, 0x81, 0xff, 44),
                on_accent: Color32::WHITE,
                separator: Color32::from_rgb(0x24, 0x25, 0x27),
                shadow: Color32::from_black_alpha(120),
                danger: Color32::from_rgb(0xff, 0x62, 0x59),
                warning: BEST_GUESS,
                success: Color32::from_rgb(0x5b, 0xbf, 0x8f),
                code_bg: Color32::from_rgb(0x06, 0x06, 0x07),
                radius_sm: 6.0,
                radius: 8.0,
                radius_lg: 12.0,
            },
            // getartcraft.com's light: warm paper (#f2f1ee), its sunken #e9e8e4 for the sidebar,
            // raised #faf9f7 for cards, ink #101014.
            ThemeKind::StudioLight => Tokens {
                kind,
                chrome: Color32::from_rgb(0xe9, 0xe8, 0xe4),
                canvas: Color32::from_rgb(0xf2, 0xf1, 0xee),
                card: Color32::from_rgb(0xfa, 0xf9, 0xf7),
                card_border: Color32::from_rgb(0xce, 0xcd, 0xcb),
                raised: Color32::from_rgb(0xe9, 0xe8, 0xe4),
                field: Color32::from_rgb(0xfa, 0xf9, 0xf7),
                field_border: Color32::from_rgb(0x86, 0x85, 0x85),
                hover: Color32::from_rgb(0xe4, 0xe4, 0xe1),
                pressed: Color32::from_rgb(0xdb, 0xda, 0xd8),
                text: Color32::from_rgb(0x10, 0x10, 0x14),
                text_dim: Color32::from_rgb(0x3d, 0x3d, 0x40),
                text_faint: Color32::from_rgb(0x5d, 0x5c, 0x5e),
                icon: Color32::from_rgb(0x4f, 0x4f, 0x52),
                accent: BRAND,
                accent_hover: Color32::from_rgb(0x2d, 0x81, 0xff),
                accent_ink: BRAND,
                accent_soft: Color32::from_rgba_unmultiplied(0x2d, 0x81, 0xff, 28),
                on_accent: Color32::WHITE,
                separator: Color32::from_rgb(0xdb, 0xda, 0xd8),
                shadow: Color32::from_black_alpha(20),
                danger: Color32::from_rgb(0xb3, 0x26, 0x1e),
                warning: Color32::from_rgb(0x9a, 0x67, 0x00),
                success: Color32::from_rgb(0x12, 0x75, 0x36),
                code_bg: Color32::from_rgb(0xe9, 0xe8, 0xe4),
                radius_sm: 6.0,
                radius: 8.0,
                radius_lg: 12.0,
            },
        }
    }

    /// The tokens of the active theme.
    pub fn get(ctx: &egui::Context) -> Tokens {
        ctx.data(|d| d.get_temp::<Tokens>(tokens_id())).unwrap_or_else(|| Tokens::for_kind(ThemeKind::Studio))
    }

    pub fn dark(&self) -> bool {
        self.kind == ThemeKind::Studio
    }

    pub fn r_sm(&self) -> CornerRadius {
        CornerRadius::same(self.radius_sm as u8)
    }
    pub fn r(&self) -> CornerRadius {
        CornerRadius::same(self.radius as u8)
    }
    pub fn r_lg(&self) -> CornerRadius {
        CornerRadius::same(self.radius_lg as u8)
    }
}

fn tokens_id() -> egui::Id {
    egui::Id::new("craft-anything-theme")
}

// ---- fonts -------------------------------------------------------------------------------------

pub static DM_SANS_REGULAR: &[u8] = include_bytes!("../../../assets/fonts/DMSans-Regular.ttf");
pub static DM_SANS_MEDIUM: &[u8] = include_bytes!("../../../assets/fonts/DMSans-Medium.ttf");
pub static DM_SANS_BOLD: &[u8] = include_bytes!("../../../assets/fonts/DMSans-Bold.ttf");
pub static JETBRAINS_MONO: &[u8] = include_bytes!("../../../assets/fonts/JetBrainsMono-Regular.ttf");

/// A font from the optional craft-fonts build input (empty unless built with `CRAFT_FONTS_DIR`).
pub struct CraftFont {
    pub family: &'static str,
    pub style: &'static str,
    /// ISO 15924 scripts the font is for, e.g. `"Jpan"`.
    pub scripts: &'static [&'static str],
    pub bytes: &'static [u8],
}

include!(concat!(env!("OUT_DIR"), "/craft_fonts.rs"));

/// Install DM Sans (three weights: body, labels and bold for headings; it has no static
/// SemiBold), JetBrains Mono (code), plus any craft-fonts as fallbacks.
pub fn install_fonts(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();
    let mut add = |name: &str, bytes: &'static [u8]| {
        fonts.font_data.insert(name.to_owned(), Arc::new(FontData::from_static(bytes)));
    };
    add("DMSans", DM_SANS_REGULAR);
    add("DMSans-Medium", DM_SANS_MEDIUM);
    add("DMSans-Bold", DM_SANS_BOLD);
    add("JetBrainsMono", JETBRAINS_MONO);
    let mut fallbacks = Vec::new();
    for f in CRAFT_FONTS {
        let name = format!("craft:{}:{}", f.family, f.style);
        fonts.font_data.insert(name.clone(), Arc::new(FontData::from_static(f.bytes)));
        if f.style.eq_ignore_ascii_case("regular") {
            fallbacks.push(name);
        }
    }
    // Sans first: a mincho/serif fallback makes Japanese and Chinese UI text look like prose.
    let fallbacks = sans_first(fallbacks);
    fonts.families.entry(FontFamily::Proportional).or_default().insert(0, "DMSans".to_owned());
    fonts.families.entry(FontFamily::Monospace).or_default().insert(0, "JetBrainsMono".to_owned());
    for fam in [FontFamily::Proportional, FontFamily::Monospace] {
        fonts.families.entry(fam).or_default().extend(fallbacks.iter().cloned());
    }
    let base: Vec<String> = fonts.families.get(&FontFamily::Proportional).cloned().unwrap_or_default();
    for (fam, primary) in [("medium", "DMSans-Medium"), ("semibold", "DMSans-Bold")] {
        let mut stack = vec![primary.to_owned()];
        stack.extend(base.iter().cloned());
        fonts.families.insert(FontFamily::Name(fam.into()), stack);
    }
    ctx.set_fonts(fonts);
}

/// Fallback faces, most wanted first. A stable sort keeps the manifest's order inside a rank.
fn sans_first(fallbacks: Vec<String>) -> Vec<String> {
    let mut ranked: Vec<(FallbackRank, String)> = fallbacks.into_iter().map(|n| (fallback_rank(&n), n)).collect();
    ranked.sort_by_key(|(rank, _)| *rank);
    ranked.into_iter().map(|(_, name)| name).collect()
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum FallbackRank {
    /// A face made for the interface's language (BIZ UDPGothic for Japanese).
    Local,
    /// One pan-CJK sans.
    Cjk,
    /// Any other sans or gothic.
    Sans,
    /// Nothing known about it.
    Other,
    /// A book face: last, because interface text set in one reads like prose.
    Serif,
}

/// Which face a craft-fonts name looks like, from the family name: a face made for the interface's
/// language first, a book face last.
fn fallback_rank(name: &str) -> FallbackRank {
    let n = name.to_ascii_lowercase();
    if n.contains("udpgothic") {
        FallbackRank::Local
    } else if n.contains("sans cjk") {
        FallbackRank::Cjk
    } else if n.contains("gothic") || n.contains("sans") {
        FallbackRank::Sans
    } else if n.contains("mincho") || n.contains("serif") {
        FallbackRank::Serif
    } else {
        FallbackRank::Other
    }
}

pub fn medium(size: f32) -> FontId {
    FontId::new(size, FontFamily::Name("medium".into()))
}
pub fn semibold(size: f32) -> FontId {
    FontId::new(size, FontFamily::Name("semibold".into()))
}
/// The type scale: every text size in the interface is one of these.
/// Headings (`heading`, DM Sans bold), largest first: a screen's title, a step or a dialog's
/// title, a card's or a list item's title.
pub const TITLE: f32 = 26.0;
pub const SECTION: f32 = 18.0;
pub const CARD: f32 = 16.0;
/// Text: the line under a title (and Simple mode's main field), reading text, secondary text
/// and list rows, fine print (paths, counts, notes), and tags painted in tight spots.
pub const LEAD: f32 = 17.0;
pub const BODY: f32 = 15.0;
pub const SMALL: f32 = 14.0;
pub const CAPTION: f32 = 12.0;
pub const TINY: f32 = 11.0;

/// A heading: DM Sans bold, at one of the heading sizes above.
pub fn heading(text: impl Into<String>, size: f32) -> egui::RichText {
    egui::RichText::new(text).font(semibold(size))
}

/// `heading` laid out for painting, wrapped at `wrap`.
pub fn heading_galley(painter: &egui::Painter, text: impl Into<String>, size: f32, color: Color32, wrap: f32) -> Arc<egui::Galley> {
    painter.layout(text.into(), semibold(size), color, wrap)
}
pub fn mono(size: f32) -> FontId {
    FontId::monospace(size)
}

/// `a` blended toward `b` by `t` (0..=1), channel by channel (alpha included).
pub fn mix(a: Color32, b: Color32, t: f32) -> Color32 {
    let t = t.clamp(0.0, 1.0);
    let m = |x: u8, y: u8| (x as f32 + (y as f32 - x as f32) * t).round() as u8;
    Color32::from_rgba_premultiplied(m(a.r(), b.r()), m(a.g(), b.g()), m(a.b(), b.b()), m(a.a(), b.a()))
}

/// A short label (captions, buttons, the title bar) in sentence case. `size` is the old
/// uppercase-mono size; mixed-case DM Sans needs a point and a half more to read the same.
pub fn label_text(text: &str, size: f32) -> egui::RichText {
    egui::RichText::new(text).font(medium(size + 1.5))
}

/// Scroll bars that can always be seen and grabbed. egui's thin preset paints the thumb in the
/// button fill and its track in the field colour, which here are the same, and narrows it to 2 px
/// at rest, so it showed only on hover. The thumb is the text colour, see-through enough to stay
/// quiet but 3:1 against the surfaces it sits on (WCAG 1.4.11), 6 px at rest and 10 px on hover.
pub fn scroll_style() -> egui::style::ScrollStyle {
    egui::style::ScrollStyle {
        floating: true,
        bar_width: 10.0,
        floating_width: 6.0,
        floating_allocated_width: 8.0,
        foreground_color: true,
        dormant_background_opacity: 0.0,
        active_background_opacity: 0.5,
        interact_background_opacity: 0.8,
        dormant_handle_opacity: SCROLL_THUMB_AT_REST,
        active_handle_opacity: 0.65,
        interact_handle_opacity: 0.85,
        ..egui::style::ScrollStyle::solid()
    }
}

/// How opaque a scroll bar's thumb is at rest (over the text colour).
const SCROLL_THUMB_AT_REST: f32 = 0.5;

/// Apply a theme. `roomy` = Beginner mode (bigger type, more air).
pub fn apply(ctx: &egui::Context, kind: ThemeKind, roomy: bool) {
    let t = Tokens::for_kind(kind);
    ctx.data_mut(|d| d.insert_temp(tokens_id(), t));
    ctx.set_theme(if t.dark() { egui::Theme::Dark } else { egui::Theme::Light });
    let mut v = if t.dark() { Visuals::dark() } else { Visuals::light() };
    v.panel_fill = t.chrome;
    v.window_fill = t.card;
    v.window_stroke = Stroke::new(1.0, t.card_border);
    v.extreme_bg_color = t.field;
    v.faint_bg_color = t.raised;
    v.code_bg_color = t.code_bg;
    v.override_text_color = Some(t.text);
    v.hyperlink_color = t.accent_ink;
    v.warn_fg_color = t.warning;
    v.error_fg_color = t.danger;
    v.window_corner_radius = t.r_lg();
    v.menu_corner_radius = t.r();
    v.window_shadow = egui::Shadow { offset: [0, 10], blur: 28, spread: 0, color: t.shadow };
    v.popup_shadow = egui::Shadow { offset: [0, 4], blur: 14, spread: 0, color: t.shadow };
    v.text_edit_bg_color = Some(t.field);
    v.selection.bg_fill = t.accent_soft;
    v.selection.stroke = Stroke::new(1.0, t.accent);
    v.handle_shape = egui::style::HandleShape::Circle;
    v.striped = false;
    v.indent_has_left_vline = false;
    let r = t.r_sm();
    let w = &mut v.widgets;
    w.noninteractive.bg_fill = t.card;
    w.noninteractive.weak_bg_fill = t.card;
    w.noninteractive.bg_stroke = Stroke::new(1.0, t.separator);
    w.noninteractive.fg_stroke = Stroke::new(1.0, t.text_dim);
    w.noninteractive.corner_radius = r;
    // Buttons and combo boxes are hairline boxes on the surface (weak fill transparent at rest).
    for (wv, bg, weak, stroke) in [
        (&mut w.inactive, t.field, Color32::TRANSPARENT, t.field_border),
        (&mut w.hovered, t.hover, t.hover, t.text_faint),
        (&mut w.active, t.pressed, t.pressed, t.accent),
        (&mut w.open, t.hover, t.hover, t.field_border),
    ] {
        wv.bg_fill = bg;
        wv.weak_bg_fill = weak;
        wv.bg_stroke = Stroke::new(1.0, stroke);
        wv.fg_stroke = Stroke::new(1.0, t.text);
        wv.corner_radius = r;
        wv.expansion = 0.0;
    }
    ctx.set_visuals(v);
    // Simple mode is for anyone, including people who find small text hard to read.
    let body = if roomy { 16.0 } else { 13.0 };
    ctx.global_style_mut(|s| {
        s.text_styles = [
            (TextStyle::Small, FontId::proportional(if roomy { 13.5 } else { 11.0 })),
            (TextStyle::Body, FontId::proportional(body)),
            (TextStyle::Button, FontId::proportional(body)),
            (TextStyle::Heading, semibold(if roomy { SECTION } else { CARD })),
            (TextStyle::Monospace, FontId::monospace(if roomy { 13.5 } else { 12.5 })),
        ]
        .into();
        s.spacing.item_spacing = if roomy { egui::vec2(10.0, 8.0) } else { egui::vec2(8.0, 5.0) };
        s.spacing.button_padding = if roomy { egui::vec2(12.0, 6.0) } else { egui::vec2(9.0, 4.0) };
        s.spacing.interact_size = egui::vec2(24.0, if roomy { 28.0 } else { 24.0 });
        s.spacing.menu_margin = egui::Margin::same(6);
        s.spacing.window_margin = egui::Margin::same(18);
        s.spacing.icon_width = 14.0;
        s.spacing.scroll = scroll_style();
        s.spacing.tooltip_width = 320.0;
        s.interaction.tooltip_delay = 0.3;
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The type scale is the only place a size is written down. Screens outside the workbench
    /// use its names (`CAPTION`, `BODY`, …) or a literal of 12 pt or more; the workbench's dense
    /// lists may use `TINY`. This walks the source so a new screen can't quietly go smaller.
    #[test]
    fn no_literal_text_size_under_12_outside_the_workbench() {
        fn rust_files(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
            for entry in std::fs::read_dir(dir).unwrap().flatten() {
                let path = entry.path();
                if path.is_dir() {
                    rust_files(&path, out);
                } else if path.extension().is_some_and(|x| x == "rs") {
                    out.push(path);
                }
            }
        }

        // Markers whose next argument is a text size. `.size` on a `RichText` counts; the
        // `.size` of a spinner or a galley does not.
        let texts = ["label_text(", "heading(", "medium(", "semibold(", "mono(", "FontId::proportional(", "FontId::monospace("];

        let mut files = Vec::new();
        rust_files(&std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("src"), &mut files);
        assert!(files.len() > 10, "the source scan found only {} files", files.len());

        let mut checked = 0;
        for path in files {
            let name = path.file_name().and_then(|n| n.to_str()).unwrap_or_default();
            // `theme.rs` is the scale itself, and `workbench.rs` is the dense workbench.
            if name == "theme.rs" || name == "workbench.rs" {
                continue;
            }
            let text = std::fs::read_to_string(&path).unwrap();
            for (n, line) in text.lines().enumerate() {
                let code = line.trim_start();
                if code.starts_with("//") {
                    continue;
                }
                let mut markers: Vec<&str> = texts.iter().copied().filter(|m| code.contains(m)).collect();
                if code.contains("RichText") && code.contains(".size(") && !code.contains("Spinner") {
                    markers.push(".size(");
                }
                for marker in markers {
                    let mut from = 0;
                    while let Some(rel) = code[from..].find(marker) {
                        let at = from + rel;
                        let open = at + marker.len() - 1;
                        if let Some(call) = call_text(code, open) {
                            let arg = if marker == "label_text(" || marker == "heading(" { top_level_parts(call).last().copied().unwrap_or("") } else { call };
                            for size in size_literals(arg) {
                                assert!(
                                    size >= 12.0,
                                    "{}:{}: a literal text size of {size} pt is below 12; use the theme scale: {}",
                                    path.display(),
                                    n + 1,
                                    code
                                );
                            }
                            checked += 1;
                        }
                        from = at + marker.len();
                    }
                }
            }
        }
        assert!(checked > 40, "the source scan checked only {checked} text sizes");
    }

    /// The text between `open`'s parenthesis and its match, or `None` when it isn't closed on
    /// this line.
    fn call_text(line: &str, open: usize) -> Option<&str> {
        let mut depth = 0i32;
        let mut in_string = false;
        let mut escaped = false;
        for (i, c) in line.get(open..)?.char_indices() {
            if in_string {
                if escaped {
                    escaped = false;
                } else if c == '\\' {
                    escaped = true;
                } else if c == '"' {
                    in_string = false;
                }
                continue;
            }
            match c {
                '"' => in_string = true,
                '(' => depth += 1,
                ')' => {
                    depth -= 1;
                    if depth == 0 {
                        return line.get(open + 1..open + i);
                    }
                }
                _ => {}
            }
        }
        None
    }

    /// Split at commas that aren't inside brackets, braces or a string.
    fn top_level_parts(s: &str) -> Vec<&str> {
        let mut out = Vec::new();
        let mut start = 0;
        let mut depth = 0i32;
        let mut in_string = false;
        let mut escaped = false;
        for (i, c) in s.char_indices() {
            if in_string {
                if escaped {
                    escaped = false;
                } else if c == '\\' {
                    escaped = true;
                } else if c == '"' {
                    in_string = false;
                }
                continue;
            }
            match c {
                '"' => in_string = true,
                '(' | '[' | '{' => depth += 1,
                ')' | ']' | '}' => depth -= 1,
                ',' if depth == 0 => {
                    out.push(&s[start..i]);
                    start = i + 1;
                }
                _ => {}
            }
        }
        out.push(&s[start..]);
        out
    }

    /// The literals a size argument is written as: one bare number, or every number in an
    /// `if`/`else`. An expression such as `body.size + 2.0` isn't a size of its own and is left
    /// to the reviewer.
    fn size_literals(arg: &str) -> Vec<f64> {
        let arg = arg.trim();
        if arg.starts_with("if ") {
            return floats_outside_strings(arg);
        }
        let bare = arg.strip_suffix("f32").unwrap_or(arg).trim();
        bare.parse::<f64>().ok().into_iter().collect()
    }

    /// Float literals on a line, ignoring digits inside string literals (a version or a count).
    fn floats_outside_strings(line: &str) -> Vec<f64> {
        let mut out = Vec::new();
        let mut in_string = false;
        let mut escaped = false;
        let mut chars = line.chars().peekable();
        while let Some(c) = chars.next() {
            if in_string {
                if escaped {
                    escaped = false;
                } else if c == '\\' {
                    escaped = true;
                } else if c == '"' {
                    in_string = false;
                }
                continue;
            }
            if c == '"' {
                in_string = true;
                continue;
            }
            if c.is_ascii_digit() {
                let mut number = String::from(c);
                while chars.peek().is_some_and(|c| c.is_ascii_digit()) {
                    if let Some(d) = chars.next() {
                        number.push(d);
                    }
                }
                if chars.peek() == Some(&'.') {
                    number.push('.');
                    chars.next();
                    while chars.peek().is_some_and(|c| c.is_ascii_digit()) {
                        if let Some(d) = chars.next() {
                            number.push(d);
                        }
                    }
                    if let Ok(v) = number.parse::<f64>() {
                        out.push(v);
                    }
                }
            }
        }
        out
    }

    /// WCAG relative luminance of an opaque colour.
    fn luminance(c: Color32) -> f64 {
        let ch = |v: u8| {
            let s = f64::from(v) / 255.0;
            if s <= 0.03928 { s / 12.92 } else { ((s + 0.055) / 1.055).powf(2.4) }
        };
        0.2126 * ch(c.r()) + 0.7152 * ch(c.g()) + 0.0722 * ch(c.b())
    }

    /// A Japanese sans comes before a serif, so interface text is not set like a book page.
    #[test]
    fn fallback_fonts_are_sans_first() {
        let names = |list: &[&str]| list.iter().map(|f| format!("craft:{f}:Regular")).collect::<Vec<_>>();
        let ordered = sans_first(names(&["Shippori Mincho", "Noto Sans CJK SC", "BIZ UDPGothic", "NanumGothic", "Unknown Face"]));
        assert_eq!(ordered[0], "craft:BIZ UDPGothic:Regular");
        assert_eq!(ordered[1], "craft:Noto Sans CJK SC:Regular");
        assert_eq!(ordered[2], "craft:NanumGothic:Regular");
        assert_eq!(ordered[3], "craft:Unknown Face:Regular");
        assert_eq!(ordered[4], "craft:Shippori Mincho:Regular");
        assert_eq!(fallback_rank("craft:Unknown Face:Regular"), FallbackRank::Other);
        assert_eq!(fallback_rank("craft:BIZ UDMincho:Regular"), FallbackRank::Serif);
        assert_eq!(fallback_rank("craft:BIZ UDPGothic:Regular"), FallbackRank::Local);
    }

    /// Releases are built with craft-fonts (#19), and so is CI; a build without them has only
    /// DM Sans, and shows other scripts as boxes.
    #[test]
    fn with_craft_fonts_every_script_people_type_shows() {
        if CRAFT_FONTS.is_empty() {
            return;
        }
        let ctx = egui::Context::default();
        install_fonts(&ctx);
        ctx.run_ui(egui::RawInput::default(), |_| {}).textures_delta.clear();
        let texts = [
            ("Korean", "한국어 사용자"),
            ("Chinese", "你好，世界"),
            ("Japanese", "こんにちは、カタカナ"),
            ("Thai", "ภาษาไทย"),
            ("Arabic", "مرحبا بالعالم"),
            ("Hebrew", "שלום עולם"),
            ("Hindi", "नमस्ते दुनिया"),
            ("Vietnamese", "Tiếng Việt"),
            ("Russian", "Привет"),
            ("Greek", "Γειά σου"),
            ("arrows", "Settings → AI ← ↑ ↓"),
        ];
        for (script, text) in texts {
            for font in [FontId::proportional(14.0), FontId::monospace(14.0), medium(14.0), semibold(14.0)] {
                assert!(ctx.fonts_mut(|f| f.has_glyphs(&font, text)), "{script} ({text}) shows as boxes in {font:?}");
            }
        }
    }

    #[test]
    fn a_scroll_thumb_at_rest_stands_out_from_every_surface_in_every_theme() {
        let style = scroll_style();
        assert!(style.floating_width >= 6.0 && style.foreground_color, "visible and wide enough to grab at rest");
        for k in ThemeKind::ALL {
            let t = Tokens::for_kind(k);
            for (name, surface) in [("chrome", t.chrome), ("canvas", t.canvas), ("card", t.card)] {
                // The thumb is the text colour at that opacity, over the surface.
                let a = f64::from(style.dormant_handle_opacity);
                let mix = |f: u8, b: u8| (a * f64::from(f) + (1.0 - a) * f64::from(b)).round() as u8;
                let thumb = Color32::from_rgb(mix(t.text.r(), surface.r()), mix(t.text.g(), surface.g()), mix(t.text.b(), surface.b()));
                let (l1, l2) = (luminance(thumb), luminance(surface));
                let ratio = (l1.max(l2) + 0.05) / (l1.min(l2) + 0.05);
                assert!(ratio >= 3.0, "{k:?} {name}: the thumb at rest is only {ratio:.2}:1");
            }
        }
    }

    #[test]
    fn theme_ids_round_trip() {
        for k in ThemeKind::ALL {
            assert_eq!(ThemeKind::from_id(k.id()), k);
        }
        assert_eq!(ThemeKind::from_id("nonsense"), ThemeKind::Studio);
    }

    /// WCAG 2.x contrast ratio between two opaque colours.
    fn contrast(a: Color32, b: Color32) -> f32 {
        let lum = |c: Color32| {
            let ch = |v: u8| {
                let s = v as f32 / 255.0;
                if s <= 0.04045 { s / 12.92 } else { ((s + 0.055) / 1.055).powf(2.4) }
            };
            0.2126 * ch(c.r()) + 0.7152 * ch(c.g()) + 0.0722 * ch(c.b())
        };
        let (x, y) = (lum(a), lum(b));
        (x.max(y) + 0.05) / (x.min(y) + 0.05)
    }

    #[test]
    fn contrast_meets_wcag_aa_in_both_themes() {
        for k in ThemeKind::ALL {
            let t = Tokens::for_kind(k);
            // `success` is text too: the Clean room and Ready pills.
            for (name, fg) in [("text", t.text), ("text_dim", t.text_dim), ("text_faint", t.text_faint), ("accent_ink", t.accent_ink), ("success", t.success)] {
                for bg in [t.canvas, t.card, t.chrome, t.raised] {
                    assert!(contrast(fg, bg) >= 4.5, "{k:?} {name} on {bg:?}: {:.2}", contrast(fg, bg));
                }
            }
            assert!(contrast(t.on_accent, t.accent) >= 4.5, "{k:?} text on the app colour: {:.2}", contrast(t.on_accent, t.accent));
            assert!(contrast(t.field_border, t.canvas) >= 3.0, "{k:?} control borders: {:.2}", contrast(t.field_border, t.canvas));
            // Main buttons are ink-filled with the canvas colour as their label.
            assert!(contrast(t.canvas, t.text) >= 4.5, "{k:?} main buttons");
            assert_eq!(t.accent, BRAND);
        }
    }

    #[test]
    fn confidence_has_four_distinct_colours() {
        let cs = [
            confidence_color(Some(Confidence::Observed)),
            confidence_color(Some(Confidence::Derived)),
            confidence_color(Some(Confidence::Inferred)),
            confidence_color(None),
        ];
        for (i, a) in cs.iter().enumerate() {
            for b in cs.iter().skip(i + 1) {
                assert_ne!(a, b);
            }
        }
        assert_eq!(confidence_label(None), "Unknown");
    }
}
