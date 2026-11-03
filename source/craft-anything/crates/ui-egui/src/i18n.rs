//! UI localisation: English strings in code are the lookup keys; a per-language
//! TSV catalog (`key<TAB>translation` per line, `#` comments) maps them to display text at render
//! time. A string with no translation is shown in English. Tool ids, the CLI and MCP never see
//! translated text.
//!
//! Adding a language: put `xx.tsv` in `i18n/` and add one row to [`LANGUAGES`].

use std::collections::HashMap;
use std::sync::{OnceLock, RwLock};

/// One supported UI language.
pub struct LangInfo {
    /// BCP 47 code, lowercase. Also the `settings.language` value.
    pub code: &'static str,
    /// The language's name in itself.
    pub name: &'static str,
    /// Catalog contents (empty for the built-in English).
    pub source: &'static str,
}

pub static LANGUAGES: &[LangInfo] = &[
    LangInfo { code: "en", name: "English", source: "" },
    LangInfo { code: "fr", name: "Français", source: include_str!("fr.tsv") },
    LangInfo { code: "ja", name: "日本語", source: include_str!("ja.tsv") },
    LangInfo { code: "zh-hans", name: "简体中文", source: include_str!("i18n/zh-hans.tsv") },
    LangInfo { code: "zh-hant", name: "繁體中文", source: include_str!("i18n/zh-hant.tsv") },
];

/// Match a locale to a registered UI language. An explicit script wins over the region.
pub fn language_from_tag(tag: &str) -> Option<&'static str> {
    let tag = tag.trim().split(['.', '@']).next().unwrap_or_default().replace('_', "-").to_ascii_lowercase();
    if let Some(lang) = LANGUAGES.iter().find(|l| l.code == tag) {
        return Some(lang.code);
    }
    let mut parts = tag.split('-');
    let primary = parts.next()?;
    match primary {
        "zh" => {
            let parts: Vec<_> = parts.take_while(|p| p.len() != 1).collect();
            if parts.contains(&"hant") {
                Some("zh-hant")
            } else if parts.contains(&"hans") {
                Some("zh-hans")
            } else if parts.iter().any(|p| matches!(*p, "tw" | "hk" | "mo")) {
                Some("zh-hant")
            } else {
                Some("zh-hans")
            }
        }
        _ => LANGUAGES.iter().find(|l| l.code == primary).map(|l| l.code),
    }
}

fn preferred_language(tags: impl IntoIterator<Item = impl AsRef<str>>) -> &'static str {
    tags.into_iter().find_map(|tag| language_from_tag(tag.as_ref())).unwrap_or("en")
}

fn system_language() -> &'static str {
    #[cfg(not(target_arch = "wasm32"))]
    {
        static SYSTEM: OnceLock<&'static str> = OnceLock::new();
        SYSTEM.get_or_init(|| preferred_language(sys_locale::get_locales()))
    }
    #[cfg(target_arch = "wasm32")]
    {
        preferred_language(std::iter::empty::<&str>())
    }
}

fn current() -> &'static RwLock<(String, HashMap<String, String>)> {
    static CUR: OnceLock<RwLock<(String, HashMap<String, String>)>> = OnceLock::new();
    CUR.get_or_init(|| RwLock::new(("en".into(), HashMap::new())))
}

fn parse(source: &str) -> HashMap<String, String> {
    source
        .lines()
        .filter(|l| !l.trim_start().starts_with('#'))
        .filter_map(|l| l.split_once('\t'))
        .filter(|(k, v)| !k.is_empty() && !v.trim().is_empty())
        .map(|(k, v)| (k.replace("\\n", "\n"), v.trim_end().replace("\\n", "\n")))
        .collect()
}

/// Switch language. Empty means the system's preferred language; unsupported codes mean English.
pub fn set_language(code: &str) {
    let code = if code.trim().is_empty() { system_language() } else { language_from_tag(code).unwrap_or("en") };
    let lang = LANGUAGES.iter().find(|l| l.code == code);
    let map = lang.map(|l| parse(l.source)).unwrap_or_default();
    if let Ok(mut g) = current().write() {
        *g = (lang.map(|l| l.code).unwrap_or("en").to_string(), map);
    }
}

pub fn language() -> String {
    current().read().map(|g| g.0.clone()).unwrap_or_else(|_| "en".into())
}

/// Translate a UI string.
pub fn tr(s: &str) -> String {
    match current().read() {
        Ok(g) => g.1.get(s).cloned().unwrap_or_else(|| s.to_string()),
        Err(_) => s.to_string(),
    }
}

/// Translate, then fill `{name}` placeholders.
pub fn trf(s: &str, args: &[(&str, &str)]) -> String {
    let mut out = tr(s);
    for (k, v) in args {
        out = out.replace(&format!("{{{k}}}"), v);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_parse_and_fallback() {
        let m = parse("# comment\nHello\tHola\nEmpty\t \nbad line\n");
        assert_eq!(m.get("Hello").map(String::as_str), Some("Hola"));
        assert!(!m.contains_key("Empty"));
        assert_eq!(trf("Open {name}", &[("name", "a.exe")]), "Open a.exe");
        assert_eq!(tr("Untranslated"), "Untranslated");
    }

    #[test]
    fn chinese_scripts_regions_and_fallback() {
        for tag in ["zh", "zh-CN", "zh_SG.UTF-8", "ZH-Hans", "zh-Hans-TW"] {
            assert_eq!(language_from_tag(tag), Some("zh-hans"), "{tag}");
        }
        for tag in ["zh-TW", "zh-HK", "zh-MO", "zh-Hant", "zh-Hant-CN"] {
            assert_eq!(language_from_tag(tag), Some("zh-hant"), "{tag}");
        }
        assert_eq!(language_from_tag("en-US"), Some("en"));
        assert_eq!(language_from_tag("ja-JP"), Some("ja"));
        assert_eq!(language_from_tag("fr-CA"), Some("fr"));
        assert_eq!(language_from_tag("de-DE"), None);
        assert_eq!(preferred_language(["de-DE", "zh-HK", "en-US"]), "zh-hant");
        assert_eq!(preferred_language(["en-US", "zh-CN"]), "en");
        assert_eq!(preferred_language(["de-DE"]), "en");
        assert_eq!(preferred_language(std::iter::empty::<&str>()), "en");
    }

    #[test]
    fn chinese_catalogs_are_valid_and_have_matching_keys() {
        fn placeholders(s: &str) -> Vec<&str> {
            let mut out: Vec<_> = s.split('{').skip(1).filter_map(|s| s.split_once('}').map(|(p, _)| p)).collect();
            out.sort_unstable();
            out
        }
        let mut catalogs = Vec::new();
        for lang in LANGUAGES.iter().filter(|l| matches!(l.code, "zh-hans" | "zh-hant")) {
            let mut keys = std::collections::BTreeSet::new();
            for (i, line) in lang.source.lines().enumerate() {
                if line.trim().is_empty() || line.starts_with('#') {
                    continue;
                }
                let (key, value) = line.split_once('\t').unwrap_or_else(|| panic!("{}:{}: missing tab", lang.code, i + 1));
                assert!(!key.is_empty() && !value.trim().is_empty(), "{}:{}: empty column", lang.code, i + 1);
                assert!(!value.contains('\t'), "{}:{}: extra column", lang.code, i + 1);
                assert!(keys.insert(key.to_string()), "{}:{}: duplicate {key}", lang.code, i + 1);
                assert_eq!(placeholders(key), placeholders(value), "{}: {key}", lang.code);
                assert_eq!(key.ends_with('…'), value.ends_with('…'), "{}: {key}", lang.code);
            }
            let parsed = parse(lang.source);
            assert_eq!(parsed.len(), keys.len());
            assert!(keys.len() > 500, "{}: incomplete catalog", lang.code);
            catalogs.push(keys);
        }
        assert_eq!(catalogs.len(), 2);
        assert_eq!(catalogs.first(), catalogs.last());
    }

    /// Every translation keeps its key's `{placeholders}`, or `trf` would leave them unfilled.
    #[test]
    fn catalogs_keep_placeholders() {
        let holes = |s: &str| {
            let mut v: Vec<String> = s.split('{').skip(1).filter_map(|p| p.split_once('}')).map(|(h, _)| h.to_string()).collect();
            v.sort();
            v
        };
        for l in LANGUAGES {
            let m = parse(l.source);
            assert!(l.source.is_empty() || m.len() > 100, "{} catalog barely parsed", l.code);
            for (k, v) in &m {
                assert_eq!(holes(k), holes(v), "{}: {k:?}", l.code);
            }
        }
    }
}
