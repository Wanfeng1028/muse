//! Icons. Lucide SVGs are embedded (`icon_data.rs`), recoloured to white, rasterised by the
//! egui_extras SVG loader at the exact on-screen pixel size, and tinted per use.

use std::collections::HashMap;
use std::sync::{Arc, OnceLock};

use egui::{Color32, Rect, Response, Sense, Vec2};

use crate::icon_data::ICONS;
use crate::theme::Tokens;

fn white_icons() -> &'static HashMap<&'static str, Arc<[u8]>> {
    static MAP: OnceLock<HashMap<&'static str, Arc<[u8]>>> = OnceLock::new();
    MAP.get_or_init(|| {
        ICONS
            .iter()
            .map(|(name, bytes)| {
                let svg = String::from_utf8_lossy(bytes).replace("currentColor", "#ffffff").replace("stroke-width=\"2\"", "stroke-width=\"1.75\"");
                (*name, Arc::from(svg.into_bytes().into_boxed_slice()))
            })
            .collect()
    })
}

pub fn exists(name: &str) -> bool {
    white_icons().contains_key(name)
}

/// An egui image for an icon, tinted. Unknown names fall back to a square.
pub fn image(name: &str, size: f32, tint: Color32) -> egui::Image<'static> {
    let (name, bytes) = match white_icons().get(name) {
        Some(b) => (name, b.clone()),
        None => ("square", white_icons().get("square").cloned().unwrap_or_else(|| Arc::from(Vec::new().into_boxed_slice()))),
    };
    egui::Image::from_bytes(format!("bytes://icons/{name}.svg"), egui::load::Bytes::Shared(bytes)).fit_to_exact_size(Vec2::splat(size)).tint(tint)
}

/// Paint an icon centred in `rect`.
pub fn paint(ui: &egui::Ui, rect: Rect, name: &str, size: f32, tint: Color32) {
    let r = Rect::from_center_size(rect.center(), Vec2::splat(size));
    // Left is right turned around: one icon fewer to carry.
    if name == "chevron-left" {
        image("chevron-right", size, tint).rotate(std::f32::consts::PI, Vec2::splat(0.5)).paint_at(ui, r);
        return;
    }
    image(name, size, tint).paint_at(ui, r);
}

/// An inline icon that takes layout space.
pub fn show(ui: &mut egui::Ui, name: &str, size: f32, tint: Color32) -> Response {
    let (rect, resp) = ui.allocate_exact_size(Vec2::splat(size), Sense::hover());
    paint(ui, rect, name, size, tint);
    resp
}

/// Square icon button: transparent until hovered; `selected` gets the accent treatment.
pub fn button(ui: &mut egui::Ui, name: &str, box_size: f32, selected: bool, tooltip: &str) -> Response {
    let t = Tokens::get(ui.ctx());
    let (rect, resp) = ui.allocate_exact_size(Vec2::splat(box_size), Sense::click());
    if selected {
        ui.painter().rect_filled(rect, t.radius_sm, t.accent_soft);
    } else {
        let h = crate::widgets::hover_t(ui, &resp);
        ui.painter().rect_filled(rect, t.radius_sm, crate::theme::mix(Color32::TRANSPARENT, t.hover, h));
    }
    let tint = if selected {
        t.accent_ink
    } else if resp.hovered() {
        t.text
    } else {
        t.icon
    };
    paint(ui, rect, name, (box_size * 0.55).round(), tint);
    crate::widgets::focus_ring(ui, &resp, rect);
    let resp = resp.on_hover_cursor(egui::CursorIcon::PointingHand);
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Button, true, crate::i18n::tr(if tooltip.is_empty() { name } else { tooltip })));
    if tooltip.is_empty() { resp } else { resp.on_hover_text(crate::i18n::tr(tooltip)) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn icons_are_recoloured_and_present() {
        let m = white_icons();
        assert!(m.len() >= 80);
        for (name, b) in m.iter() {
            let s = std::str::from_utf8(b).unwrap();
            assert!(!s.contains("currentColor"), "{name}");
        }
        for name in crate::USED_ICONS {
            assert!(exists(name), "{name} is used but not embedded");
        }
    }

    #[test]
    fn every_target_kind_has_an_embedded_icon() {
        use craft_anything_engine::TargetKind as K;
        for k in [
            K::Elf,
            K::Pe,
            K::MachO,
            K::MachOFat,
            K::Managed,
            K::Wasm,
            K::Apk,
            K::Dex,
            K::Jar,
            K::JavaClass,
            K::Zip,
            K::Asar,
            K::Directory,
            K::Script,
            K::NetworkCapture,
            K::Plist,
            K::Evm,
            K::Sqlite,
            K::DosCom,
            K::RawBinary,
            K::Unknown,
        ] {
            let name = crate::kind_icon(k);
            assert!(exists(name) && crate::USED_ICONS.contains(&name), "{k:?} uses icon {name}, which is not embedded and listed");
        }
    }
}
