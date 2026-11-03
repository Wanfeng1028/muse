//! Audit literal UI lookup keys and engine tool titles against both Chinese catalogs.

use std::collections::BTreeSet;
use std::path::Path;
use syn::visit::{self, Visit};

#[derive(Default)]
struct Strings(BTreeSet<String>);

impl<'ast> Visit<'ast> for Strings {
    fn visit_expr_call(&mut self, _: &'ast syn::ExprCall) {}

    fn visit_expr_if(&mut self, expr: &'ast syn::ExprIf) {
        self.visit_block(&expr.then_branch);
        if let Some((_, otherwise)) = &expr.else_branch {
            self.visit_expr(otherwise);
        }
    }

    fn visit_lit_str(&mut self, s: &'ast syn::LitStr) {
        let value = s.value();
        if value.chars().any(|c| c.is_ascii_alphabetic()) {
            self.0.insert(value);
        }
    }
}

#[derive(Default)]
struct Lookups(Strings);

impl<'ast> Visit<'ast> for Lookups {
    fn visit_item_mod(&mut self, module: &'ast syn::ItemMod) {
        if module.ident != "tests" {
            visit::visit_item_mod(self, module);
        }
    }

    fn visit_expr_call(&mut self, call: &'ast syn::ExprCall) {
        if let syn::Expr::Path(path) = &*call.func {
            let name = path.path.segments.last().map(|s| s.ident.to_string()).unwrap_or_default();
            let owner = path.path.segments.iter().rev().nth(1).map(|s| s.ident.to_string()).unwrap_or_default();
            let positions: &[usize] = match (owner.as_str(), name.as_str()) {
                (_, "tr" | "trf") => &[0],
                ("widgets", "primary" | "link" | "suggestion" | "caption" | "pill" | "working" | "working_since" | "segmented" | "segmented_sized") => &[1],
                ("widgets", "named") => &[1],
                ("widgets", "primary_icon" | "primary_sized" | "secondary") => &[2],
                ("widgets", "toggle") => &[2],
                ("widgets", "choice_tile" | "big_card") => &[3, 4],
                ("widgets", "empty_state") => &[2, 3],
                ("icons", "button") => &[4],
                _ => &[],
            };
            for &i in positions {
                if let Some(syn::Expr::Lit(syn::ExprLit { lit: syn::Lit::Str(s), .. })) = call.args.iter().nth(i) {
                    self.0.visit_lit_str(s);
                }
                // Conditional literals in tr(if ...), and string arrays in segmented(...).
                if let Some(expr @ (syn::Expr::If(_) | syn::Expr::Array(_) | syn::Expr::Reference(_))) = call.args.iter().nth(i) {
                    self.0.visit_expr(expr);
                }
            }
        }
        visit::visit_expr_call(self, call);
    }
}

pub fn check(root: &Path) -> bool {
    let mut lookups = Lookups::default();
    let source = root.join("crates/ui-egui/src");
    let Ok(paths) = std::fs::read_dir(&source) else {
        eprintln!("i18n: can't read {}", source.display());
        return false;
    };
    for path in paths {
        let Ok(path) = path.map(|p| p.path()) else { return false };
        if path.extension().is_none_or(|e| e != "rs") || path.file_stem().is_some_and(|n| n == "demo" || n == "i18n" || n == "icon_data") {
            continue;
        }
        let Ok(text) = std::fs::read_to_string(&path) else { return false };
        let Ok(file) = syn::parse_file(&text) else {
            eprintln!("i18n: can't parse {}", path.display());
            return false;
        };
        lookups.visit_file(&file);
    }
    for spec in craft_anything_engine::Registry::with_all_tools().all() {
        lookups.0.0.insert(spec.title.to_string());
        lookups.0.0.insert(spec.toolset.title().to_string());
    }
    let mut ok = true;
    for code in ["zh-hans", "zh-hant"] {
        let path = source.join("i18n").join(format!("{code}.tsv"));
        let Ok(text) = std::fs::read_to_string(&path) else {
            eprintln!("i18n: can't read {}", path.display());
            return false;
        };
        let keys: BTreeSet<_> = text.lines().filter(|l| !l.starts_with('#')).filter_map(|l| l.split_once('\t')).map(|(k, _)| k.replace("\\n", "\n")).collect();
        let missing: Vec<_> = lookups.0.0.difference(&keys).collect();
        for key in &missing {
            eprintln!("i18n: {code}: missing {key:?}");
        }
        println!("{code}: {} lookup keys checked, {} missing ({} catalog entries)", lookups.0.0.len(), missing.len(), keys.len());
        ok &= missing.is_empty();
    }
    ok
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collects_rendered_literals_without_machine_ids_or_arguments() {
        let file = syn::parse_file(
            r#"
            fn screen() {
                tr(if mode == "internal" { "Simple" } else { "Advanced" });
                widgets::primary_icon(ui, Some("play"), "Start", true);
                icons::button(ui, "x", 20.0, false, "Close");
                widgets::segmented(ui, &["One", "Two"], 0, 30.0);
                widgets::named(resp, &trf("Open {name}", &[("name", "sample.exe")]));
            }
            #[cfg(test)] mod tests { fn other() { tr("Test only"); } }
            "#,
        )
        .unwrap();
        let mut lookups = Lookups::default();
        lookups.visit_file(&file);
        assert_eq!(lookups.0.0, ["Advanced", "Close", "One", "Open {name}", "Simple", "Start", "Two"].into_iter().map(str::to_string).collect());
    }
}
