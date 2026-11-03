//! Swift symbol manglings, classified without a full demangler: the module and type path are
//! read from the length-prefixed identifiers, the kind from the operator that follows.

use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SwiftSymbol {
    pub mangled: String,
    /// classes, structs, enums, protocols, extensions, other
    pub category: &'static str,
    pub module: Option<String>,
    /// Dotted type path, e.g. `MyApp.Settings.Panel`.
    pub path: String,
    /// What the symbol is about the type: metadata accessor, type descriptor, method…
    pub role: &'static str,
}

/// True for Swift manglings (`$s…`, `_$s…`, `$S…`, `_T0…`).
pub fn is_swift_mangled(name: &str) -> bool {
    let n = name.strip_prefix('_').unwrap_or(name);
    n.starts_with("$s") || n.starts_with("$S") || n.starts_with("$e") || n.starts_with("T0")
}

/// Read `<len><ident>` pairs; returns the identifiers and the rest of the string.
fn idents(mut s: &str) -> (Vec<String>, &str) {
    let mut out = Vec::new();
    while out.len() < 16 {
        let digits: String = s.chars().take_while(|c| c.is_ascii_digit()).collect();
        if digits.is_empty() || digits.len() > 4 {
            break;
        }
        let Ok(n) = digits.parse::<usize>() else { break };
        let rest = s.get(digits.len()..).unwrap_or("");
        let Some(id) = rest.get(..n) else { break };
        if n == 0 {
            break;
        }
        out.push(id.to_string());
        s = rest.get(n..).unwrap_or("");
        // Word substitutions (`0`), generics and other operators end the simple path.
    }
    (out, s)
}

/// Classify one mangled Swift symbol (best effort, never panics).
pub fn classify(name: &str) -> Option<SwiftSymbol> {
    if !is_swift_mangled(name) {
        return None;
    }
    let n = name.strip_prefix('_').unwrap_or(name);
    let body = n.get(2..)?;
    let (ids, rest) = idents(body);
    let module = ids.first().cloned();
    let path = ids.join(".");
    let mut chars = rest.chars();
    let op = chars.next();
    let suffix: String = chars.collect();
    let category = match op {
        Some('C') => "classes",
        Some('V') => "structs",
        Some('O') => "enums",
        Some('P') => "protocols",
        Some('E') => "extensions",
        _ => {
            if rest.starts_with("Mp") {
                "protocols"
            } else {
                "other"
            }
        }
    };
    let tail = if category == "other" { rest } else { suffix.as_str() };
    let role = if tail.starts_with("Ma") {
        "metadata accessor"
    } else if tail.starts_with("Mn") {
        "type descriptor"
    } else if tail.starts_with("MN") || tail.starts_with('N') {
        "type metadata"
    } else if tail.starts_with("Mp") {
        "protocol descriptor"
    } else if tail.starts_with("Mf") || tail.starts_with("Mm") {
        "metaclass or full metadata"
    } else if tail.starts_with("fc") || tail.starts_with("fC") || tail.contains("fc") {
        "constructor"
    } else if tail.contains("To") {
        "Objective-C thunk"
    } else if tail.contains("vg") || tail.contains("vs") || tail.contains("vM") {
        "property accessor"
    } else if tail.contains('F') || tail.ends_with('F') || tail.contains("yy") {
        "function or method"
    } else if tail.starts_with("WP") || tail.starts_with("Wp") {
        "protocol witness table"
    } else {
        "other"
    };
    Some(SwiftSymbol { mangled: name.to_string(), category, module, path, role })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classifies_common_manglings() {
        let c = classify("_$s4main8CAWidgetCMa").unwrap();
        assert_eq!(c.category, "classes");
        assert_eq!(c.module.as_deref(), Some("main"));
        assert_eq!(c.path, "main.CAWidget");
        assert_eq!(c.role, "metadata accessor");
        assert_eq!(classify("$s5MyApp8SettingsVMn").unwrap().category, "structs");
        assert_eq!(classify("$s5MyApp4ModeOMn").unwrap().category, "enums");
        assert_eq!(classify("$s5MyApp8DelegateMp").unwrap().category, "protocols");
        assert!(classify("main").is_none());
        for junk in ["$s", "$s999999", "$s3ab", "_$s0", "$s4\u{e9}\u{e9}\u{e9}C"] {
            let _ = classify(junk);
        }
    }
}
