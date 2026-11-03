//! Starting a project from a request: the target, the folder, the stack the person asked for, the
//! asset budget from settings and whether assets may be generated. Shared by the CLI's `rebuild` and the `rebuild_start` tool.

use super::*;
use craft_anything_engine::Settings;
use craft_anything_engine::workspace::{ExistingFiles, suggest_name};

/// Where a new project goes.
#[derive(Debug, Clone, Copy, Default)]
pub enum Place<'a> {
    /// A new folder in the projects folder from settings.
    #[default]
    Projects,
    /// A new folder inside this one.
    In(&'a Path),
    /// This folder itself ([`Workspace::create_at`]), with what its files are if it has any.
    At(&'a Path, Option<ExistingFiles>),
}

/// A stack picked by name for `--build-with` / `build_with` (an engine id or a stack's full name).
pub fn build_with(name: &str) -> Result<&'static stacks::Stack, ToolError> {
    stacks::resolve(name).ok_or_else(|| {
        let known = stacks::catalogue().iter().map(|s| s.engine.clone().unwrap_or_else(|| s.name.clone())).collect::<Vec<_>>().join(", ");
        ToolError::invalid(format!("Unknown build-with {name:?}.")).with_remediation(format!("Use one of: {known}."))
    })
}

/// A new project for `request` about `target` (a web address, an absolute path, or `-` for none),
/// at `place`, with the stack the person
/// picked (`build_with`), the asset budget from settings, and `generate_assets`: the person lets the
/// builder generate pictures and 3D models.
pub fn new_project(
    settings: &Settings,
    target: &str,
    request: &str,
    place: Place,
    build_with: Option<&str>,
    generate_assets: bool,
    builder: Option<&str>,
) -> Result<Workspace, ToolError> {
    let stack = build_with.map(self::build_with).transpose()?;
    let target_ref = if target.trim() == "-" { TargetRef::None } else { TargetRef::parse(target) };
    if target_ref == TargetRef::None && target.trim() != "-" {
        return Err(ToolError::invalid(format!("{target:?} is neither a web address nor an existing absolute path"))
            .with_remediation("Pass https://… for a website, a full path for a program, or - for none."));
    }
    let name = suggest_name(request, &target_ref);
    let mut ws = match place {
        Place::Projects => Workspace::create(&settings.projects_dir(), &name, request, target_ref)?,
        Place::In(dir) => Workspace::create(dir, &name, request, target_ref)?,
        Place::At(folder, existing) => Workspace::create_at(folder, &name, request, target_ref, existing)?,
    };
    if let Some(s) = stack {
        ws.manifest.stack = s.name.clone();
    }
    let budget = settings.assets.budget();
    ws.set_person(|m| {
        m.asset_budget_usd = budget;
        m.generate_assets = generate_assets;
        m.builder = builder.map(str::to_string);
    })?;
    Ok(ws)
}
