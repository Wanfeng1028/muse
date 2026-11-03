//! Third-party code fingerprints: licence banners and well-known runtime strings.

use crate::model::Vendor;

/// Parse a licence/preserve banner (`/*! name v1.2.3 | MIT */`, `@license React v18.2.0`).
pub fn banner_vendor(comment: &str, line: u32) -> Option<Vendor> {
    let head: String = comment.chars().take(400).collect();
    let is_banner = head.starts_with("/*!") || head.contains("@license") || head.contains("@preserve") || head.contains("@module");
    if !is_banner {
        return None;
    }
    let words: Vec<&str> =
        head.split(|c: char| c.is_whitespace() || c == '*' || c == '/' || c == '!' || c == '|' || c == ',').filter(|w| !w.is_empty()).collect();
    for (i, w) in words.iter().enumerate() {
        // name@1.2.3
        if let Some((n, v)) = w.rsplit_once('@')
            && !n.is_empty()
            && is_version(v)
        {
            return Some(Vendor { name: clean_name(n), version: Some(v.trim_start_matches('v').to_string()), source: "banner".into(), line });
        }
        if is_version(w) && i > 0 {
            let mut j = i - 1;
            while j > 0 && words.get(j).is_some_and(|p| matches!(*p, "-" | "v" | "version" | "Version" | "@license" | "@preserve")) {
                j -= 1;
            }
            let name = words.get(j).copied().unwrap_or("");
            if !name.is_empty() && !name.starts_with('@') && !matches!(name, "-" | "version" | "Version") {
                return Some(Vendor { name: clean_name(name), version: Some(w.trim_start_matches('v').to_string()), source: "banner".into(), line });
            }
        }
    }
    let after =
        head.split("@license").nth(1).and_then(|r| r.split_whitespace().next()).filter(|n| !n.is_empty() && !n.contains("MIT") && !n.contains("Apache"));
    after.map(|n| Vendor { name: clean_name(n), version: None, source: "banner".into(), line })
}

fn clean_name(n: &str) -> String {
    n.trim_matches(|c: char| !(c.is_alphanumeric() || c == '-' || c == '.' || c == '@' || c == '/' || c == '_')).to_string()
}

fn is_version(w: &str) -> bool {
    let w = w.trim_start_matches('v');
    let mut parts = w.split('.');
    let major = parts.next().unwrap_or("");
    let minor = parts.next().unwrap_or("");
    !major.is_empty() && major.bytes().all(|b| b.is_ascii_digit()) && minor.bytes().next().is_some_and(|b| b.is_ascii_digit())
}

/// Strings that identify widely used libraries even after minification.
const MARKERS: &[(&str, &str)] = &[
    ("react.element", "react"),
    ("react.transitional.element", "react"),
    ("__reactFiber$", "react-dom"),
    ("__reactContainer$", "react-dom"),
    ("__VUE__", "vue"),
    ("__vue_app__", "vue"),
    ("ng-version", "angular"),
    ("__lodash_hash_undefined__", "lodash"),
    ("Moment Timezone", "moment-timezone"),
    ("__core-js_shared__", "core-js"),
    ("Zone.js", "zone.js"),
    ("$$typeof", "react"),
    ("svelte-", "svelte"),
    ("data-emotion", "emotion"),
    ("sc-component-id", "styled-components"),
    ("redux-persist", "redux-persist"),
    ("@@redux/INIT", "redux"),
    ("__NEXT_DATA__", "next.js"),
    ("__NUXT__", "nuxt"),
    ("electron-log", "electron-log"),
    ("electron-updater", "electron-updater"),
    ("Sentry", "sentry"),
    ("posthog", "posthog"),
];

/// Library markers found among a module's string literals.
pub fn marker_vendors(strings: &[String]) -> Vec<Vendor> {
    let mut out: Vec<Vendor> = Vec::new();
    for s in strings {
        for (needle, name) in MARKERS {
            if s.contains(needle) && !out.iter().any(|v| v.name == *name) {
                out.push(Vendor { name: (*name).to_string(), version: None, source: "marker".into(), line: 0 });
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn banners() {
        let v = banner_vendor("/*! jQuery v3.7.1 | (c) OpenJS Foundation */", 1).unwrap();
        assert_eq!((v.name.as_str(), v.version.as_deref()), ("jQuery", Some("3.7.1")));
        let r = banner_vendor("/** @license React v18.2.0\n * react-dom.production.min.js */", 1).unwrap();
        assert_eq!(r.version.as_deref(), Some("18.2.0"));
        let a = banner_vendor("/*! axios@1.6.0 */", 1).unwrap();
        assert_eq!(a.name, "axios");
        assert!(banner_vendor("// just a comment v1.2", 1).is_none());
    }
}
