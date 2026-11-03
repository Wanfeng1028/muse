//! A params form generated from a tool's JSON schema (schemars output). Values are edited as text
//! and converted by the schema's types when the tool runs.

use crate::i18n::tr;
use crate::theme::{self, Tokens};
use crate::widgets;
use egui::{RichText, Ui};
use serde_json::{Map, Value};
use std::collections::BTreeMap;

/// One field of the form.
#[derive(Debug, Clone, PartialEq)]
pub struct Field {
    pub name: String,
    pub kind: FieldKind,
    pub required: bool,
    pub description: String,
    pub choices: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FieldKind {
    Text,
    Integer,
    Number,
    Bool,
    /// Arrays and objects, edited as JSON.
    Json,
}

fn resolve<'a>(schema: &'a Value, v: &'a Value) -> &'a Value {
    // Follow a local `$ref` ("#/$defs/Name" or "#/definitions/Name") one level.
    if let Some(r) = v.get("$ref").and_then(Value::as_str) {
        let name = r.rsplit('/').next().unwrap_or_default();
        for defs in ["$defs", "definitions"] {
            if let Some(d) = schema.get(defs).and_then(|d| d.get(name)) {
                return d;
            }
        }
    }
    v
}

fn kind_of(schema: &Value, v: &Value) -> (FieldKind, Vec<String>) {
    let v = resolve(schema, v);
    if let Some(e) = v.get("enum").and_then(Value::as_array) {
        return (FieldKind::Text, e.iter().filter_map(|x| x.as_str().map(String::from)).collect());
    }
    if let Some(any) = v.get("anyOf").or_else(|| v.get("oneOf")).and_then(Value::as_array) {
        // Option<T> is `anyOf: [T, null]`; use the first non-null branch.
        if let Some(first) = any.iter().find(|b| b.get("type").and_then(Value::as_str) != Some("null")) {
            return kind_of(schema, first);
        }
    }
    let ty = match v.get("type") {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Array(a)) => a.iter().filter_map(Value::as_str).find(|s| *s != "null").unwrap_or("string").to_string(),
        _ => "string".into(),
    };
    let kind = match ty.as_str() {
        "integer" => FieldKind::Integer,
        "number" => FieldKind::Number,
        "boolean" => FieldKind::Bool,
        "array" | "object" => FieldKind::Json,
        _ => FieldKind::Text,
    };
    (kind, Vec::new())
}

/// The fields a schema describes, required first.
pub fn fields(schema: &Value) -> Vec<Field> {
    let required: Vec<&str> = schema.get("required").and_then(Value::as_array).map(|a| a.iter().filter_map(Value::as_str).collect()).unwrap_or_default();
    let mut out: Vec<Field> = schema
        .get("properties")
        .and_then(Value::as_object)
        .map(|props| {
            props
                .iter()
                .map(|(name, v)| {
                    let (kind, choices) = kind_of(schema, v);
                    Field {
                        name: name.clone(),
                        kind,
                        required: required.contains(&name.as_str()),
                        description: v.get("description").and_then(Value::as_str).unwrap_or_default().to_string(),
                        choices,
                    }
                })
                .collect()
        })
        .unwrap_or_default();
    out.sort_by_key(|f| !f.required);
    out
}

/// Convert the form's text into params. Errors name the field in plain words.
pub fn build(fields: &[Field], values: &BTreeMap<String, String>) -> Result<Value, String> {
    let mut m = Map::new();
    for f in fields {
        let raw = values.get(&f.name).map(|s| s.trim()).unwrap_or_default();
        if raw.is_empty() {
            if f.required && f.kind != FieldKind::Bool {
                return Err(format!("{} {}", f.name, tr("is required")));
            }
            continue;
        }
        let v = match f.kind {
            FieldKind::Text => Value::String(raw.to_string()),
            FieldKind::Bool => Value::Bool(raw == "true"),
            FieldKind::Integer => {
                let n = if let Some(h) = raw.strip_prefix("0x").or_else(|| raw.strip_prefix("0X")) {
                    i64::from_str_radix(h, 16).ok()
                } else {
                    raw.parse::<i64>().ok()
                };
                Value::from(n.ok_or_else(|| format!("{} {}", f.name, tr("must be a whole number")))?)
            }
            FieldKind::Number => Value::from(raw.parse::<f64>().map_err(|_| format!("{} {}", f.name, tr("must be a number")))?),
            FieldKind::Json => serde_json::from_str(raw).map_err(|e| format!("{}: {e}", f.name))?,
        };
        m.insert(f.name.clone(), v);
    }
    Ok(Value::Object(m))
}

/// Draw the form.
pub fn show(ui: &mut Ui, fields: &[Field], values: &mut BTreeMap<String, String>) {
    let t = Tokens::get(ui.ctx());
    if fields.is_empty() {
        ui.label(RichText::new(tr("This tool takes no settings.")).color(t.text_dim));
        return;
    }
    egui::Grid::new("schema-form").num_columns(2).spacing([12.0, 8.0]).show(ui, |ui| {
        for f in fields {
            ui.vertical(|ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new(&f.name).font(theme::mono(12.5)));
                    if f.required {
                        ui.label(RichText::new("*").color(t.accent));
                    }
                });
            });
            let v = values.entry(f.name.clone()).or_default();
            ui.vertical(|ui| {
                match f.kind {
                    FieldKind::Bool => {
                        let mut b = v == "true";
                        if widgets::toggle(ui, &mut b, "").changed() {
                            *v = b.to_string();
                        }
                    }
                    _ if !f.choices.is_empty() => {
                        egui::ComboBox::from_id_salt(("choice", &f.name))
                            .icon(widgets::combo_icon)
                            .selected_text(if v.is_empty() { "—".to_string() } else { v.clone() })
                            .show_ui(ui, |ui| {
                                if !f.required {
                                    ui.selectable_value(v, String::new(), "—");
                                }
                                for c in &f.choices {
                                    ui.selectable_value(v, c.clone(), c);
                                }
                            });
                    }
                    FieldKind::Json => {
                        ui.add(
                            egui::TextEdit::multiline(v)
                                .font(theme::mono(12.0))
                                .desired_rows(2)
                                .desired_width(320.0)
                                .hint_text("JSON")
                                .frame(widgets::text_field_frame_compact(&Tokens::get(ui.ctx()))),
                        );
                    }
                    _ => {
                        let hint = match f.kind {
                            FieldKind::Integer => "0x… or number",
                            FieldKind::Number => "number",
                            _ => "",
                        };
                        ui.add(
                            egui::TextEdit::singleline(v)
                                .desired_width(320.0)
                                .hint_text(tr(hint))
                                .frame(widgets::text_field_frame_compact(&Tokens::get(ui.ctx()))),
                        );
                    }
                }
                if !f.description.is_empty() {
                    ui.add(egui::Label::new(RichText::new(&f.description).color(t.text_faint).size(theme::CAPTION)).wrap());
                }
            });
            ui.end_row();
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn schema() -> Value {
        json!({
            "type": "object",
            "required": ["path"],
            "properties": {
                "limit": {"type": ["integer", "null"], "description": "How many"},
                "path": {"type": "string"},
                "verbose": {"type": "boolean"},
                "mode": {"$ref": "#/$defs/Mode"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "addr": {"anyOf": [{"type": "integer"}, {"type": "null"}]}
            },
            "$defs": {"Mode": {"type": "string", "enum": ["fast", "deep"]}}
        })
    }

    #[test]
    fn fields_and_values_follow_the_schema() {
        let f = fields(&schema());
        assert_eq!(f[0].name, "path");
        assert!(f[0].required);
        let by = |n: &str| f.iter().find(|x| x.name == n).unwrap().clone();
        assert_eq!(by("limit").kind, FieldKind::Integer);
        assert_eq!(by("addr").kind, FieldKind::Integer);
        assert_eq!(by("mode").choices, vec!["fast", "deep"]);
        assert_eq!(by("tags").kind, FieldKind::Json);
        let mut v = BTreeMap::new();
        assert!(build(&f, &v).is_err(), "path is required");
        v.insert("path".into(), "/tmp/a".into());
        v.insert("limit".into(), "0x10".into());
        v.insert("verbose".into(), "true".into());
        v.insert("tags".into(), "[\"a\"]".into());
        let p = build(&f, &v).unwrap();
        assert_eq!(p, json!({"path": "/tmp/a", "limit": 16, "verbose": true, "tags": ["a"]}));
        v.insert("limit".into(), "lots".into());
        assert!(build(&f, &v).is_err());
        assert!(fields(&json!(null)).is_empty());
    }
}
