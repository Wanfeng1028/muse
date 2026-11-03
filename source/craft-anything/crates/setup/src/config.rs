//! Reading and editing one client's config text, per format. Pure text in, text out.

use crate::clients::{Client, Format, SERVER_NAME};
use crate::yaml;
use craft_anything_formats::jsonc;
use serde_json::Value;

/// Parse the whole config to JSON-like data. An empty file is `{}` unless the client forbids it.
pub fn parse(client: &Client, text: &str) -> Result<Value, String> {
    if text.trim().is_empty() && client.empty_is_invalid {
        return Err("the file is empty, and this app requires valid JSON".into());
    }
    match client.format {
        Format::Jsonc => jsonc::parse(text, false).map(|d| d.to_value()),
        Format::StrictJson => {
            if text.trim().is_empty() {
                return Ok(Value::Object(Default::default()));
            }
            jsonc::parse(text, true).map(|d| d.to_value())
        }
        Format::Toml => {
            let t: toml::Table = toml::from_str(text).map_err(|e| e.to_string())?;
            serde_json::to_value(t).map_err(|e| e.to_string())
        }
        Format::Yaml => yaml::parse(text),
        Format::Manual => Err("this app's config is not edited automatically".into()),
    }
}

/// Our entry, if present.
pub fn read_entry(client: &Client, text: &str) -> Result<Option<Value>, String> {
    let v = parse(client, text)?;
    let mut cur = &v;
    for k in client.entry_path() {
        match cur.get(k) {
            Some(n) => cur = n,
            None => return Ok(None),
        }
    }
    Ok(Some(cur.clone()))
}

/// True when the client lists our server as disabled (Grok Build's `disabled_mcp_servers`).
pub fn is_disabled(client: &Client, text: &str) -> bool {
    if client.id != "grok_build" {
        return false;
    }
    parse(client, text).ok().and_then(|v| v.get("disabled_mcp_servers").and_then(|d| d.as_array()).map(|a| a.iter().any(|x| x == SERVER_NAME))).unwrap_or(false)
}

/// Text with our entry set to `entry`.
pub fn set_entry(client: &Client, text: &str, entry: &Value) -> Result<String, String> {
    match client.format {
        Format::Jsonc | Format::StrictJson => {
            parse(client, text)?;
            let doc = jsonc::parse(text, client.format == Format::StrictJson)?;
            doc.set(&client.entry_path(), entry)
        }
        Format::Toml => toml_set(client, text, entry),
        Format::Yaml => {
            let table = client.table.first().copied().unwrap_or("mcp_servers");
            yaml::set(text, table, SERVER_NAME, entry)
        }
        Format::Manual => Err("this app's config is not edited automatically".into()),
    }
}

/// Text with our entry removed, or `None` when it wasn't there.
pub fn remove_entry(client: &Client, text: &str) -> Result<Option<String>, String> {
    match client.format {
        Format::Jsonc | Format::StrictJson => {
            let doc = jsonc::parse(text, client.format == Format::StrictJson)?;
            Ok(doc.remove(&client.entry_path()))
        }
        Format::Toml => {
            let mut doc: toml_edit::DocumentMut = text.parse().map_err(|e: toml_edit::TomlError| e.to_string())?;
            let table = client.table.first().copied().unwrap_or("mcp_servers");
            let removed = doc.get_mut(table).and_then(|t| t.as_table_like_mut()).and_then(|t| t.remove(SERVER_NAME)).is_some();
            Ok(removed.then(|| doc.to_string()))
        }
        Format::Yaml => {
            let table = client.table.first().copied().unwrap_or("mcp_servers");
            yaml::parse(text)?;
            Ok(yaml::remove(text, table, SERVER_NAME))
        }
        Format::Manual => Ok(None),
    }
}

fn json_to_toml(v: &Value) -> Option<toml_edit::Value> {
    Some(match v {
        Value::String(s) => s.as_str().into(),
        Value::Bool(b) => (*b).into(),
        Value::Number(n) => match n.as_i64() {
            Some(i) => i.into(),
            None => n.as_f64()?.into(),
        },
        Value::Array(items) => {
            let mut a = toml_edit::Array::new();
            for it in items {
                a.push(json_to_toml(it)?);
            }
            toml_edit::Value::Array(a)
        }
        Value::Object(m) => {
            let mut t = toml_edit::InlineTable::new();
            for (k, v) in m {
                t.insert(k, json_to_toml(v)?);
            }
            toml_edit::Value::InlineTable(t)
        }
        Value::Null => return None,
    })
}

fn toml_set(client: &Client, text: &str, entry: &Value) -> Result<String, String> {
    let mut doc: toml_edit::DocumentMut = text.parse().map_err(|e: toml_edit::TomlError| e.to_string())?;
    let table_name = client.table.first().copied().unwrap_or("mcp_servers");
    let Value::Object(fields) = entry else { return Err("entry must be a table".into()) };
    let mut ours = toml_edit::Table::new();
    for (k, v) in fields {
        let tv = json_to_toml(v).ok_or_else(|| format!("cannot write {k} as TOML"))?;
        ours.insert(k, toml_edit::Item::Value(tv));
    }
    if doc.get(table_name).is_none() {
        let mut t = toml_edit::Table::new();
        t.set_implicit(true);
        doc.insert(table_name, toml_edit::Item::Table(t));
    }
    let servers = doc.get_mut(table_name).and_then(|t| t.as_table_mut()).ok_or_else(|| format!("`{table_name}` exists but is not a table"))?;
    match servers.get_mut(SERVER_NAME).and_then(|i| i.as_table_mut()) {
        Some(existing) => {
            // Keep the existing table's position and decor; replace its keys.
            existing.clear();
            for (k, v) in ours.iter() {
                existing.insert(k, v.clone());
            }
        }
        None => {
            servers.insert(SERVER_NAME, toml_edit::Item::Table(ours));
        }
    }
    if client.id == "grok_build"
        && let Some(arr) = doc.get_mut("disabled_mcp_servers").and_then(|d| d.as_array_mut())
    {
        arr.retain(|v| v.as_str() != Some(SERVER_NAME));
    }
    Ok(doc.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clients::{Host, clients};
    use serde_json::json;

    fn client(id: &str) -> Client {
        clients(&Host::with_home("/h")).into_iter().find(|c| c.id == id).unwrap()
    }

    #[test]
    fn toml_merge_preserves_comments() {
        let c = client("codex");
        let text = "# Codex settings\nmodel = \"x\" # pick one\n\n[mcp_servers.other]\ncommand = \"o\" # theirs\n";
        let e = c.desired_entry(&["/b/craft-anything-cli".into(), "mcp".into()]);
        let new = set_entry(&c, text, &e).unwrap();
        assert!(new.contains("# Codex settings") && new.contains("# pick one") && new.contains("# theirs"));
        assert_eq!(read_entry(&c, &new).unwrap(), Some(e.clone()));
        assert_eq!(parse(&c, &new).unwrap()["mcp_servers"]["other"]["command"], "o");
        let again = set_entry(&c, &new, &e).unwrap();
        assert_eq!(again, new);
        let removed = remove_entry(&c, &new).unwrap().unwrap();
        assert_eq!(read_entry(&c, &removed).unwrap(), None);
        assert!(removed.contains("# theirs"));
        assert!(parse(&c, "a = [").is_err());
    }

    #[test]
    fn grok_enables_disabled_server() {
        let c = client("grok_build");
        let text = "disabled_mcp_servers = [\"craft-anything\", \"x\"]\n";
        assert!(is_disabled(&c, text));
        let new = set_entry(&c, text, &json!({"command": "c", "args": ["mcp"]})).unwrap();
        assert!(!is_disabled(&c, &new));
        assert!(new.contains("\"x\""));
    }

    #[test]
    fn strict_and_empty_rules() {
        let pi = client("pi");
        assert!(parse(&pi, "").is_err());
        assert!(parse(&pi, "{} // c").is_err());
        let z = client("zcode");
        let new = set_entry(&z, "", &json!({"command": "c"})).unwrap();
        assert_eq!(read_entry(&z, &new).unwrap(), Some(json!({"command": "c"})));
        assert_eq!(parse(&z, &new).unwrap()["mcp"]["servers"]["craft-anything"]["command"], "c");
    }
}
