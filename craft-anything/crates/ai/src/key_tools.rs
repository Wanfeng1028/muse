//! Asset providers' keys (fal.ai today) for generated game assets as tools, so they can be set up
//! without the app. Each provider has its own key, in the system keychain (or the private key
//! file); a key is never returned, and the journal redacts `api_key` like every secret-named field.

use crate::AiHub;
use craft_anything_engine::EngineRef;
use craft_anything_engine::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::assets::{AssetProvider, AssetProviders, fal};
use craft_anything_evidence::{ErrorCode, ToolError};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::sync::Arc;

pub fn specs() -> Vec<ToolSpec> {
    let spec = |id, title, summary, beginner, effects, input_schema, run| ToolSpec {
        id,
        title,
        summary,
        beginner,
        toolset: Toolset::Setup,
        effects,
        requires: Requires::Nothing,
        input_schema,
        run,
    };
    vec![
        spec(
            "assets_key_status",
            "Is an asset key set up?",
            "Whether each asset provider (fal.ai today) has a key for generated pictures and 3D models, stored or in its environment variable. `stored` answers for `provider` (default fal). Keys themselves are never shown.",
            "Shows whether generated art is set up.",
            Effects::READ_ONLY,
            schema_of::<ProviderParams>,
            assets_key_status,
        ),
        spec(
            "assets_key_set",
            "Save an asset key",
            "Store an asset provider's key (`provider`, default fal) for generated pictures and 3D models in the system keychain (or the private key file). It's never shown again or written to logs.",
            "Saves your key for generated art.",
            Effects::WRITES_FILESYSTEM,
            schema_of::<SetParams>,
            assets_key_set,
        ),
        spec(
            "assets_key_remove",
            "Remove an asset key",
            "Remove an asset provider's stored key (`provider`, default fal).",
            "Removes your key for generated art.",
            Effects::WRITES_FILESYSTEM,
            schema_of::<ProviderParams>,
            assets_key_remove,
        ),
    ]
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ProviderParams {
    /// The asset provider's id (default `fal`).
    #[serde(default)]
    pub provider: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SetParams {
    /// The provider's key.
    pub api_key: String,
    /// The asset provider's id (default `fal`).
    #[serde(default)]
    pub provider: Option<String>,
}

/// The session's asset providers (a fork's or a test's, else the built-in ones).
fn providers(ctx: &Ctx<'_>) -> AssetProviders {
    ctx.session.ext.get::<AssetProviders>().map(|p| p.as_ref().clone()).unwrap_or_default()
}

/// The provider named (default fal), refused when there's no such provider.
fn provider(ctx: &Ctx<'_>, id: Option<&str>) -> Result<Arc<dyn AssetProvider>, ToolError> {
    let all = providers(ctx);
    let id = id.map(str::trim).filter(|s| !s.is_empty()).unwrap_or(fal::ID);
    all.get(id).ok_or_else(|| {
        ToolError::invalid(format!("There's no asset provider called {id:?}.")).with_remediation(format!("Use one of: {}.", all.ids().join(", ")))
    })
}

fn hub(ctx: &Ctx<'_>) -> Result<AiHub, ToolError> {
    let engine = ctx
        .session
        .ext
        .get::<EngineRef>()
        .and_then(|r| r.0.upgrade())
        .ok_or_else(|| ToolError::new(ErrorCode::FeatureMissing, "Keys aren't available in this engine."))?;
    Ok(AiHub::new(engine))
}

fn assets_key_status(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ProviderParams = parse_params(params)?;
    let asked = provider(ctx, p.provider.as_deref())?;
    let (hub, all) = (hub(ctx)?, providers(ctx));
    let each: Vec<Value> = all
        .ids()
        .into_iter()
        .filter_map(|id| all.get(id))
        .map(|p| json!({"provider": p.id(), "name": p.name(), "stored": hub.has_asset_key(&all, p.id())}))
        .collect();
    Ok(ToolOutput::Value(json!({"provider": asked.id(), "stored": hub.has_asset_key(&all, asked.id()), "providers": each})))
}

fn assets_key_set(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SetParams = parse_params(params)?;
    let to = provider(ctx, p.provider.as_deref())?;
    let key = p.api_key.trim();
    if key.is_empty() || key.len() > 512 || key.chars().any(char::is_whitespace) {
        return Err(ToolError::invalid(format!("That doesn't look like a {} key.", to.name())).with_remediation("Copy the key from the provider's dashboard."));
    }
    let stored_in = hub(ctx)?.set_asset_key(to.id(), key)?;
    Ok(ToolOutput::Value(json!({"provider": to.id(), "stored": true, "stored_in": stored_in})))
}

fn assets_key_remove(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ProviderParams = parse_params(params)?;
    let from = provider(ctx, p.provider.as_deref())?;
    hub(ctx)?.remove_asset_key(from.id())?;
    Ok(ToolOutput::Value(json!({"provider": from.id(), "stored": false})))
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_engine::{CallOptions, Caller, Engine};

    // Nothing here stores or reads a real key (tests never touch the machine's keychain).
    #[test]
    fn a_key_that_doesnt_look_like_one_is_refused_before_anything_is_stored() {
        let e = Engine::shared(craft_anything_engine::testing::session(), specs());
        for bad in ["", "has a space", &"x".repeat(600)] {
            let err = e.call("assets_key_set", json!({"api_key": bad}), CallOptions::new(Caller::Cli)).unwrap_err();
            assert_eq!(err.code, ErrorCode::BadInput, "{bad:?}");
        }
        assert!(craft_anything_engine::journal::bounded(&json!({"api_key": "fal-secret"})).to_string().contains("(redacted)"));
        // A provider that doesn't exist is refused before the keychain is touched.
        let set = json!({"api_key": "k-1", "provider": "nope"});
        let other = json!({"provider": "nope"});
        for (id, params) in [("assets_key_set", &set), ("assets_key_status", &other), ("assets_key_remove", &other)] {
            let err = e.call(id, params.clone(), CallOptions::new(Caller::Cli)).unwrap_err();
            assert!(err.message.contains("no asset provider called \"nope\"") && err.remediation.unwrap_or_default().contains("fal"), "{id}");
        }
    }
}
