//! Projections of a parsed assembly: the inventory (identity, references, resources,
//! classification), members (types, fields, methods with decoded bodies and call edges) and the
//! native boundary (P/Invoke and friends).

use super::cil::{self, Instr, Operand, OperandKind};
use super::meta::{Metadata, t};
use super::pe::{self, PeImage};
use super::sig::{Cur, GenCtx, Names};
use crate::FormatError;
use crate::bytes::Reader;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

/// Largest input accepted.
pub const MAX_INPUT: usize = 128 << 20;
const MAX_LIST: usize = 1 << 20;

/// A parsed .NET assembly.
#[derive(Debug, Clone)]
pub struct Assembly<'a> {
    pub data: &'a [u8],
    pub pe: PeImage,
    pub md: Metadata<'a>,
}

/// Parse the PE, CLI header and metadata.
pub fn open(data: &[u8]) -> Result<Assembly<'_>, FormatError> {
    if data.len() > MAX_INPUT {
        return Err(FormatError::TooLarge(format!("{} bytes; the limit is {MAX_INPUT}", data.len())));
    }
    let pe = pe::parse_pe(data)?;
    let md_bytes = pe.dir_bytes(data, pe.cli.metadata).ok_or_else(|| FormatError::Malformed("the metadata directory lies outside the file".into()))?;
    let md = Metadata::parse(md_bytes)?;
    Ok(Assembly { data, pe, md })
}

pub fn token(table: u8, row: u32) -> String {
    format!("0x{:08x}", (u32::from(table) << 24) | (row & 0x00ff_ffff))
}

fn hex_bytes(b: &[u8], max: usize) -> String {
    b.iter().take(max).map(|x| format!("{x:02x}")).collect()
}

// ---------------------------------------------------------------------------------------------
// Inventory

#[derive(Debug, Clone, Serialize)]
pub struct AssemblyIdentity {
    pub name: String,
    pub version: String,
    pub culture: String,
    pub flags: u32,
    pub hash_algorithm: u32,
    pub public_key_bytes: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct AssemblyRefInfo {
    pub token: String,
    pub name: String,
    pub version: String,
    pub culture: String,
    /// Public key or token, hex.
    pub public_key_or_token: String,
    pub flags: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct ResourceInfo {
    pub name: String,
    pub offset: u32,
    pub visibility: &'static str,
    /// embedded, file:<name>, assembly:<name>
    pub implementation: String,
    /// Size of an embedded resource, when readable.
    pub size: Option<u32>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExportedTypeInfo {
    pub name: String,
    pub implementation: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct AttributeInfo {
    pub owner: String,
    pub attribute_type: String,
    pub fixed_args: Vec<serde_json::Value>,
    pub named_args: BTreeMap<String, serde_json::Value>,
    /// False when some arguments could not be decoded.
    pub complete: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Classification {
    /// dotnet-framework, dotnet-core, dotnet-standard, clr-and-native, unknown
    pub dotnet_family: String,
    /// il-only, mixed-mode, ready-to-run, native-code-present
    pub implementation: String,
    /// anycpu, anycpu-prefer-32, x86, x64, arm64, arm…
    pub dotnet_arch: String,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Inventory {
    pub pe_kind: &'static str,
    pub machine: String,
    pub is_dll: bool,
    pub subsystem: u16,
    pub sections: Vec<pe::PeSection>,
    pub runtime_version: String,
    pub metadata_version: String,
    pub cli_flags: Vec<&'static str>,
    pub entry_point: Option<serde_json::Value>,
    pub strong_name_signature_bytes: u32,
    pub resources_bytes: u32,
    pub has_vtable_fixups: bool,
    pub ready_to_run: bool,
    pub ready_to_run_version: Option<String>,
    pub streams: Vec<super::meta::StreamInfo>,
    pub tables_stream: String,
    pub table_schema_version: String,
    pub row_counts: BTreeMap<&'static str, u32>,
    pub module: Option<serde_json::Value>,
    pub assembly: Option<AssemblyIdentity>,
    pub assembly_refs: Vec<AssemblyRefInfo>,
    pub module_refs: Vec<String>,
    pub manifest_resources: Vec<ResourceInfo>,
    pub exported_types: Vec<ExportedTypeInfo>,
    pub assembly_attributes: Vec<AttributeInfo>,
    pub target_frameworks: Vec<String>,
    pub classification: Classification,
    pub warnings: Vec<String>,
}

fn version4(md: &Metadata<'_>, table: u8, row: u32, first: usize) -> String {
    format!("{}.{}.{}.{}", md.cell(table, row, first), md.cell(table, row, first + 1), md.cell(table, row, first + 2), md.cell(table, row, first + 3))
}

fn implementation(md: &Metadata<'_>, names: &Names<'_, '_>, table: u8, row: u32, col: usize) -> String {
    match md.coded(table, row, col) {
        None => "embedded".into(),
        Some((t::FILE, r)) => format!("file:{}", md.str_cell(t::FILE, r, 1)),
        Some((t::ASSEMBLY_REF, r)) => format!("assembly:{}", md.str_cell(t::ASSEMBLY_REF, r, 6)),
        Some((t::EXPORTED_TYPE, r)) => format!("exported-type:{}", exported_name(md, r, names)),
        Some(_) => "unknown".into(),
    }
}

fn exported_name(md: &Metadata<'_>, row: u32, _names: &Names<'_, '_>) -> String {
    let ns = md.str_cell(t::EXPORTED_TYPE, row, 3);
    let n = md.str_cell(t::EXPORTED_TYPE, row, 2);
    if ns.is_empty() { n } else { format!("{ns}.{n}") }
}

/// Owner description for a HasCustomAttribute target.
fn owner_name(a: &Assembly<'_>, names: &Names<'_, '_>, owners: &Owners, table: u8, row: u32) -> String {
    let md = &a.md;
    match table {
        t::ASSEMBLY => "assembly".into(),
        t::MODULE => "module".into(),
        t::TYPE_DEF => names.typedef_name(row),
        t::METHOD_DEF => method_display(a, names, owners, row),
        t::FIELD => format!("{}::{}", owners.field_owner.get(&row).map(|&o| names.typedef_name(o)).unwrap_or_default(), md.str_cell(t::FIELD, row, 1)),
        t::PROPERTY => md.str_cell(t::PROPERTY, row, 1),
        t::EVENT => md.str_cell(t::EVENT, row, 1),
        t::PARAM => format!("param {}", md.str_cell(t::PARAM, row, 2)),
        _ => format!("{}[{row}]", super::meta::TABLE_NAMES.get(usize::from(table)).unwrap_or(&"?")),
    }
}

/// The attribute type and constructor signature of a CustomAttribute row.
fn attribute_ctor(a: &Assembly<'_>, names: &Names<'_, '_>, owners: &Owners, row: u32) -> Option<(String, Vec<u8>)> {
    let md = &a.md;
    let g = GenCtx::default();
    match md.coded(t::CUSTOM_ATTRIBUTE, row, 1)? {
        (t::MEMBER_REF, r) => {
            let ty = match md.coded(t::MEMBER_REF, r, 0)? {
                (tb @ (t::TYPE_REF | t::TYPE_DEF | t::TYPE_SPEC), tr) => names.type_name(tb, tr, &g, 0),
                _ => return None,
            };
            Some((ty, md.blob_cell(t::MEMBER_REF, r, 2).to_vec()))
        }
        (t::METHOD_DEF, r) => {
            let owner = owners.method_owner.get(&r).map(|&o| names.typedef_name(o))?;
            Some((owner, md.blob_cell(t::METHOD_DEF, r, 4).to_vec()))
        }
        _ => None,
    }
}

fn ser_string(c: &mut Cur<'_>) -> Option<Option<String>> {
    if c.peek() == Some(0xff) {
        c.u8()?;
        return Some(None);
    }
    let n = c.cu32()? as usize;
    let b = c.slice(n)?;
    Some(Some(String::from_utf8_lossy(b).into_owned()))
}

/// Read one attribute value of element type `et`.
fn ca_value(c: &mut Cur<'_>, et: u8, depth: u32) -> Option<serde_json::Value> {
    use serde_json::Value as V;
    if depth > 4 {
        return None;
    }
    Some(match et {
        0x02 => V::Bool(c.u8()? != 0),
        0x03 => V::String(char::from_u32(u32::from(c.u16()?)).map(String::from).unwrap_or_default()),
        0x04 => V::from(c.u8()? as i8),
        0x05 => V::from(c.u8()?),
        0x06 => V::from(c.u16()? as i16),
        0x07 => V::from(c.u16()?),
        0x08 => V::from(c.u32()? as i32),
        0x09 => V::from(c.u32()?),
        0x0a => V::from(c.u64()? as i64),
        0x0b => V::from(c.u64()?),
        0x0c => serde_json::Number::from_f64(f64::from(f32::from_bits(c.u32()?))).map(V::Number).unwrap_or(V::Null),
        0x0d => serde_json::Number::from_f64(f64::from_bits(c.u64()?)).map(V::Number).unwrap_or(V::Null),
        0x0e | 0x50 => ser_string(c)?.map(V::String).unwrap_or(V::Null),
        0x51 => {
            let inner = c.u8()?;
            if inner == 0x55 {
                ser_string(c)?;
                V::from(c.u32()? as i32)
            } else {
                ca_value(c, inner, depth + 1)?
            }
        }
        _ => return None,
    })
}

/// Decode a custom attribute blob against its constructor signature (primitive, string, Type and
/// int32-backed enum arguments; anything else stops decoding and marks it incomplete).
fn decode_attribute(names: &Names<'_, '_>, ctor_sig: &[u8], blob: &[u8]) -> (Vec<serde_json::Value>, BTreeMap<String, serde_json::Value>, bool) {
    let mut fixed = Vec::new();
    let mut named = BTreeMap::new();
    let mut c = Cur::new(blob);
    if c.u16() != Some(1) {
        return (fixed, named, blob.is_empty());
    }
    // Parameter element types from the ctor signature.
    let mut s = Cur::new(ctor_sig);
    let ok = (|| {
        let flags = s.u8()?;
        if flags & 0x10 != 0 {
            s.cu32()?;
        }
        let n = s.cu32()?;
        if n > 64 {
            return None;
        }
        s.u8()?; // void return
        for _ in 0..n {
            let et = s.u8()?;
            let et = match et {
                0x11 | 0x12 => {
                    // A class or enum: System.Type is serialised as a string; enums assumed int32.
                    let v = s.cu32()?;
                    let tb = match v & 3 {
                        0 => t::TYPE_DEF,
                        1 => t::TYPE_REF,
                        _ => return None,
                    };
                    let name = names.type_name(tb, v >> 2, &GenCtx::default(), 0);
                    if name == "System.Type" {
                        0x50
                    } else if et == 0x11 {
                        0x08
                    } else {
                        return None;
                    }
                }
                0x1c => 0x51,
                x => x,
            };
            fixed.push(ca_value(&mut c, et, 0)?);
        }
        let nnamed = c.u16()?;
        for _ in 0..nnamed.min(64) {
            let _kind = c.u8()?;
            let mut et = c.u8()?;
            if et == 0x55 {
                ser_string(&mut c)?;
                et = 0x08;
            }
            if et == 0x1d {
                return None;
            }
            let name = ser_string(&mut c)?.unwrap_or_default();
            let v = ca_value(&mut c, et, 0)?;
            named.insert(name, v);
        }
        Some(())
    })()
    .is_some();
    (fixed, named, ok)
}

/// Every custom attribute whose owner is `(table, row)` (or all when `owner` is None), capped.
fn attributes(a: &Assembly<'_>, names: &Names<'_, '_>, owners: &Owners, owner: Option<(u8, u32)>, cap: usize) -> Vec<AttributeInfo> {
    let md = &a.md;
    let mut out = Vec::new();
    for r in 1..=md.rows(t::CUSTOM_ATTRIBUTE) {
        if out.len() >= cap {
            break;
        }
        let Some(parent) = md.coded(t::CUSTOM_ATTRIBUTE, r, 0) else { continue };
        if owner.is_some_and(|o| o != parent) {
            continue;
        }
        let Some((ty, sig)) = attribute_ctor(a, names, owners, r) else { continue };
        let (fixed_args, named_args, complete) = decode_attribute(names, &sig, md.blob_cell(t::CUSTOM_ATTRIBUTE, r, 2));
        out.push(AttributeInfo { owner: owner_name(a, names, owners, parent.0, parent.1), attribute_type: ty, fixed_args, named_args, complete });
    }
    out
}

/// Which TypeDef owns each method and field.
#[derive(Debug, Default)]
pub struct Owners {
    pub method_owner: BTreeMap<u32, u32>,
    pub field_owner: BTreeMap<u32, u32>,
}

impl Owners {
    pub fn build(md: &Metadata<'_>) -> Owners {
        let mut o = Owners::default();
        for ty in 1..=md.rows(t::TYPE_DEF) {
            for m in md.list(t::TYPE_DEF, ty, 5, t::METHOD_DEF, MAX_LIST) {
                o.method_owner.entry(m).or_insert(ty);
            }
            for f in md.list(t::TYPE_DEF, ty, 4, t::FIELD, MAX_LIST) {
                o.field_owner.entry(f).or_insert(ty);
            }
        }
        o
    }
}

fn method_display(a: &Assembly<'_>, names: &Names<'_, '_>, owners: &Owners, row: u32) -> String {
    let md = &a.md;
    let owner = owners.method_owner.get(&row).copied().unwrap_or(0);
    let g = GenCtx { type_params: names.type_generics(owner), method_params: names.method_generics(row) };
    let params = names.method_sig(md.blob_cell(t::METHOD_DEF, row, 4), &g).map(|s| s.param_list()).unwrap_or_else(|| "(?)".into());
    format!("{}::{}{params}", if owner == 0 { "<global>".to_string() } else { names.typedef_name(owner) }, md.str_cell(t::METHOD_DEF, row, 3))
}

/// Inventory an assembly.
pub fn inventory(a: &Assembly<'_>) -> Inventory {
    let md = &a.md;
    let names = Names::new(md);
    let owners = Owners::build(md);
    let mut warnings = md.warnings.clone();
    let cli = &a.pe.cli;
    let entry_point = if cli.entry_point_token == 0 {
        None
    } else if cli.flags & pe::COMIMAGE_FLAGS_NATIVE_ENTRYPOINT != 0 {
        Some(serde_json::json!({"native_rva": format!("{:#x}", cli.entry_point_token)}))
    } else {
        let tb = (cli.entry_point_token >> 24) as u8;
        let row = cli.entry_point_token & 0x00ff_ffff;
        let name = if tb == t::METHOD_DEF { Some(method_display(a, &names, &owners, row)) } else { None };
        Some(serde_json::json!({"token": format!("0x{:08x}", cli.entry_point_token), "method": name}))
    };
    let assembly = (md.rows(t::ASSEMBLY) > 0).then(|| AssemblyIdentity {
        name: md.str_cell(t::ASSEMBLY, 1, 7),
        version: version4(md, t::ASSEMBLY, 1, 1),
        culture: md.str_cell(t::ASSEMBLY, 1, 8),
        flags: md.cell(t::ASSEMBLY, 1, 5),
        hash_algorithm: md.cell(t::ASSEMBLY, 1, 0),
        public_key_bytes: md.blob_cell(t::ASSEMBLY, 1, 6).len(),
    });
    let module = (md.rows(t::MODULE) > 0).then(|| serde_json::json!({"name": md.str_cell(t::MODULE, 1, 1), "mvid": md.guid(md.cell(t::MODULE, 1, 2))}));
    let assembly_refs = (1..=md.rows(t::ASSEMBLY_REF).min(65_536))
        .map(|r| AssemblyRefInfo {
            token: token(t::ASSEMBLY_REF, r),
            name: md.str_cell(t::ASSEMBLY_REF, r, 6),
            version: version4(md, t::ASSEMBLY_REF, r, 0),
            culture: md.str_cell(t::ASSEMBLY_REF, r, 7),
            public_key_or_token: hex_bytes(md.blob_cell(t::ASSEMBLY_REF, r, 5), 512),
            flags: md.cell(t::ASSEMBLY_REF, r, 4),
        })
        .collect::<Vec<_>>();
    let module_refs = (1..=md.rows(t::MODULE_REF).min(65_536)).map(|r| md.str_cell(t::MODULE_REF, r, 0)).collect();
    let res_base = a.pe.rva_to_offset(cli.resources.rva).filter(|_| !cli.resources.is_empty());
    let manifest_resources = (1..=md.rows(t::MANIFEST_RESOURCE).min(65_536))
        .map(|r| {
            let offset = md.cell(t::MANIFEST_RESOURCE, r, 0);
            let implementation = implementation(md, &names, t::MANIFEST_RESOURCE, r, 3);
            let size = if implementation == "embedded" {
                res_base.and_then(|b| b.checked_add(offset as usize)).and_then(|o| Reader::new(a.data).u32_le(o))
            } else {
                None
            };
            ResourceInfo {
                name: md.str_cell(t::MANIFEST_RESOURCE, r, 2),
                offset,
                visibility: if md.cell(t::MANIFEST_RESOURCE, r, 1) & 7 == 2 { "private" } else { "public" },
                implementation,
                size,
            }
        })
        .collect();
    let exported_types = (1..=md.rows(t::EXPORTED_TYPE).min(65_536))
        .map(|r| ExportedTypeInfo { name: exported_name(md, r, &names), implementation: implementation(md, &names, t::EXPORTED_TYPE, r, 4) })
        .collect();
    let assembly_attributes = if md.rows(t::ASSEMBLY) > 0 { attributes(a, &names, &owners, Some((t::ASSEMBLY, 1)), 512) } else { Vec::new() };
    let target_frameworks: Vec<String> = assembly_attributes
        .iter()
        .filter(|at| at.attribute_type.ends_with("TargetFrameworkAttribute"))
        .filter_map(|at| at.fixed_args.first().and_then(|v| v.as_str()).map(String::from))
        .collect();
    let classification = classify(a, &target_frameworks, &assembly_refs);
    if cli.flags & pe::COMIMAGE_FLAGS_ILONLY == 0 {
        warnings.push("the image is not IL-only: native code may run that metadata does not describe".into());
    }
    Inventory {
        pe_kind: if a.pe.optional_magic == 0x20b { "PE32+" } else { "PE32" },
        machine: a.pe.machine_name(),
        is_dll: a.pe.characteristics & 0x2000 != 0,
        subsystem: a.pe.subsystem,
        sections: a.pe.sections.clone(),
        runtime_version: format!("{}.{}", cli.major_runtime_version, cli.minor_runtime_version),
        metadata_version: md.version.clone(),
        cli_flags: cli.flag_names(),
        entry_point,
        strong_name_signature_bytes: cli.strong_name_signature.size,
        resources_bytes: cli.resources.size,
        has_vtable_fixups: !cli.vtable_fixups.is_empty(),
        ready_to_run: a.pe.ready_to_run,
        ready_to_run_version: a.pe.ready_to_run_version.map(|(x, y)| format!("{x}.{y}")),
        streams: md.streams.clone(),
        tables_stream: md.tables_stream.clone(),
        table_schema_version: format!("{}.{}", md.table_schema_version.0, md.table_schema_version.1),
        row_counts: md.row_counts().into_iter().collect(),
        module,
        assembly,
        assembly_refs,
        module_refs,
        manifest_resources,
        exported_types,
        assembly_attributes,
        target_frameworks,
        classification,
        warnings,
    }
}

fn classify(a: &Assembly<'_>, tfms: &[String], refs: &[AssemblyRefInfo]) -> Classification {
    let cli = &a.pe.cli;
    let il_only = cli.flags & pe::COMIMAGE_FLAGS_ILONLY != 0;
    let mut reasons = Vec::new();
    let tfm = tfms.first().map(String::as_str).unwrap_or("");
    let has_ref = |n: &str| refs.iter().any(|r| r.name.eq_ignore_ascii_case(n));
    let mut dotnet_family = if tfm.starts_with(".NETCoreApp") {
        reasons.push(format!("TargetFramework {tfm}"));
        "dotnet-core"
    } else if tfm.starts_with(".NETFramework") {
        reasons.push(format!("TargetFramework {tfm}"));
        "dotnet-framework"
    } else if tfm.starts_with(".NETStandard") {
        reasons.push(format!("TargetFramework {tfm}"));
        "dotnet-standard"
    } else if has_ref("System.Runtime") || has_ref("System.Private.CoreLib") || has_ref("netstandard") {
        reasons.push("references System.Runtime/System.Private.CoreLib/netstandard".into());
        if has_ref("netstandard") { "dotnet-standard" } else { "dotnet-core" }
    } else if has_ref("mscorlib") {
        reasons.push("references mscorlib".into());
        "dotnet-framework"
    } else if a.md.str_cell(t::ASSEMBLY, 1, 7) == "mscorlib" || a.md.str_cell(t::ASSEMBLY, 1, 7) == "System.Private.CoreLib" {
        "core-library"
    } else {
        "unknown"
    }
    .to_string();
    if !il_only {
        reasons.push("ILONLY flag clear".into());
        dotnet_family = format!("clr-and-native ({dotnet_family})");
    }
    let implementation = if a.pe.ready_to_run {
        reasons.push("ReadyToRun header present".into());
        "ready-to-run"
    } else if !il_only && (!cli.vtable_fixups.is_empty() || cli.flags & pe::COMIMAGE_FLAGS_NATIVE_ENTRYPOINT != 0) {
        reasons.push("vtable fixups or a native entry point".into());
        "mixed-mode"
    } else if !il_only {
        "native-code-present"
    } else {
        "il-only"
    }
    .to_string();
    Classification { dotnet_family, implementation, dotnet_arch: a.pe.dotnet_arch(), reasons }
}

// ---------------------------------------------------------------------------------------------
// Members

#[derive(Debug, Clone, Default)]
pub struct MemberOptions {
    /// Only types whose full name (or simple name) is listed.
    pub type_filter: Option<Vec<String>>,
    /// Include each method's instruction listing.
    pub include_il: bool,
    /// Most instructions decoded per method (0 means 100 000).
    pub max_instructions: usize,
    /// Most types returned.
    pub max_types: usize,
    /// Don't decode method bodies.
    pub skip_bodies: bool,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Param {
    pub name: String,
    #[serde(rename = "type")]
    pub ty: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct CodeRef {
    pub offset: u32,
    pub opcode: &'static str,
    pub token: String,
    pub target: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct BodyInfo {
    pub header: &'static str,
    pub max_stack: u16,
    pub code_size: u32,
    pub init_locals: bool,
    pub locals: Vec<String>,
    pub exception_clauses: Vec<cil::EhClause>,
    pub il_hash: String,
    pub il_shape_hash: String,
    pub instruction_count: usize,
    pub calls: Vec<CodeRef>,
    pub field_accesses: Vec<CodeRef>,
    pub strings: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub decode_issue: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub il: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct MethodInfo {
    pub token: String,
    pub name: String,
    /// `Type::Name(params):return`, stable across builds when nothing changed.
    pub key: String,
    /// C#-like declaration.
    pub signature: String,
    pub return_type: String,
    pub params: Vec<Param>,
    pub generic_params: Vec<String>,
    pub visibility: &'static str,
    pub modifiers: Vec<&'static str>,
    /// il, native, optil, runtime
    pub code_type: &'static str,
    pub internal_call: bool,
    pub pinvoke: bool,
    pub rva: u32,
    pub body: Option<BodyInfo>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct FieldInfo {
    pub token: String,
    pub name: String,
    #[serde(rename = "type")]
    pub ty: String,
    pub visibility: &'static str,
    pub modifiers: Vec<&'static str>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PropertyInfo {
    pub name: String,
    #[serde(rename = "type")]
    pub ty: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TypeInfo {
    pub token: String,
    pub full_name: String,
    pub namespace: String,
    pub name: String,
    /// class, interface, struct, enum, delegate, module
    pub kind: &'static str,
    pub visibility: &'static str,
    pub modifiers: Vec<&'static str>,
    pub extends: Option<String>,
    pub enclosing_type: Option<String>,
    pub generic_params: Vec<String>,
    pub interfaces: Vec<String>,
    pub fields: Vec<FieldInfo>,
    pub methods: Vec<MethodInfo>,
    pub properties: Vec<PropertyInfo>,
    pub events: Vec<PropertyInfo>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Members {
    pub types: Vec<TypeInfo>,
    pub total_types: u32,
    pub total_methods: usize,
    pub total_fields: usize,
    pub truncated: bool,
    pub warnings: Vec<String>,
}

fn member_visibility(flags: u32) -> &'static str {
    match flags & 7 {
        1 => "private",
        2 => "private protected",
        3 => "internal",
        4 => "protected",
        5 => "protected internal",
        6 => "public",
        _ => "privatescope",
    }
}

fn type_visibility(flags: u32) -> &'static str {
    match flags & 7 {
        0 => "internal",
        1 | 2 => "public",
        3 => "private",
        4 => "protected",
        5 => "internal",
        6 => "private protected",
        _ => "protected internal",
    }
}

/// Resolves IL tokens to readable names.
pub struct Resolver<'m, 'a> {
    pub a: &'m Assembly<'a>,
    pub names: Names<'m, 'a>,
    pub owners: Owners,
}

impl<'m, 'a> Resolver<'m, 'a> {
    pub fn new(a: &'m Assembly<'a>) -> Self {
        Resolver { names: Names::new(&a.md), owners: Owners::build(&a.md), a }
    }

    fn md(&self) -> &Metadata<'a> {
        &self.a.md
    }

    pub fn type_token(&self, tok: u32) -> String {
        let tb = (tok >> 24) as u8;
        self.names.type_name(tb, tok & 0x00ff_ffff, &GenCtx::default(), 0)
    }

    pub fn method_token(&self, tok: u32, depth: u32) -> String {
        let md = self.md();
        let tb = (tok >> 24) as u8;
        let row = tok & 0x00ff_ffff;
        match tb {
            t::METHOD_DEF => method_display(self.a, &self.names, &self.owners, row),
            t::MEMBER_REF => {
                let g = GenCtx::default();
                let parent = match md.coded(t::MEMBER_REF, row, 0) {
                    Some((tb @ (t::TYPE_REF | t::TYPE_DEF | t::TYPE_SPEC), r)) => self.names.type_name(tb, r, &g, 0),
                    Some((t::MODULE_REF, r)) => format!("[{}]", md.str_cell(t::MODULE_REF, r, 0)),
                    Some((t::METHOD_DEF, r)) => return method_display(self.a, &self.names, &self.owners, r),
                    _ => "?".into(),
                };
                let blob = md.blob_cell(t::MEMBER_REF, row, 2);
                let name = md.str_cell(t::MEMBER_REF, row, 1);
                if blob.first() == Some(&0x06) {
                    return format!("{parent}::{name}");
                }
                let params = self.names.method_sig(blob, &g).map(|s| s.param_list()).unwrap_or_else(|| "(?)".into());
                format!("{parent}::{name}{params}")
            }
            t::METHOD_SPEC if depth < 2 => {
                let base = match md.coded(t::METHOD_SPEC, row, 0) {
                    Some((tb, r)) => self.method_token((u32::from(tb) << 24) | r, depth + 1),
                    None => "?".into(),
                };
                let args = self.names.method_spec_args(md.blob_cell(t::METHOD_SPEC, row, 1), &GenCtx::default()).unwrap_or_default();
                format!("{base}<{}>", args.join(", "))
            }
            t::FIELD => {
                let owner = self.owners.field_owner.get(&row).map(|&o| self.names.typedef_name(o)).unwrap_or_default();
                format!("{owner}::{}", md.str_cell(t::FIELD, row, 1))
            }
            _ => format!("token 0x{tok:08x}"),
        }
    }

    pub fn any_token(&self, tok: u32) -> String {
        match (tok >> 24) as u8 {
            t::TYPE_DEF | t::TYPE_REF | t::TYPE_SPEC => self.type_token(tok),
            t::METHOD_DEF | t::MEMBER_REF | t::METHOD_SPEC | t::FIELD => self.method_token(tok, 0),
            t::STAND_ALONE_SIG => format!("signature 0x{tok:08x}"),
            0x70 => self.md().user_string(tok & 0x00ff_ffff, 256).map(|s| format!("{s:?}")).unwrap_or_else(|| "?".into()),
            _ => format!("token 0x{tok:08x}"),
        }
    }

    fn instr_text(&self, i: &Instr) -> String {
        let op = match &i.operand {
            Operand::None => String::new(),
            Operand::Int(v) => format!(" {v}"),
            Operand::Float(f) => format!(" {f}"),
            Operand::Targets(ts) => format!(" {}", ts.iter().map(|x| format!("IL_{x:04x}")).collect::<Vec<_>>().join(", ")),
            Operand::Token(tok) => format!(" {}", self.any_token(*tok)),
        };
        format!("IL_{:04x}: {}{op}", i.offset, i.opcode)
    }

    fn body(&self, method: u32, rva: u32, opts: &MemberOptions, g: &GenCtx<'_>) -> Option<BodyInfo> {
        let md = self.md();
        let off = self.a.pe.rva_to_offset(rva)?;
        let Some(b) = cil::parse_body(self.a.data, off) else {
            return Some(BodyInfo {
                header: "unreadable",
                max_stack: 0,
                code_size: 0,
                init_locals: false,
                locals: Vec::new(),
                exception_clauses: Vec::new(),
                il_hash: String::new(),
                il_shape_hash: String::new(),
                instruction_count: 0,
                calls: Vec::new(),
                field_accesses: Vec::new(),
                strings: Vec::new(),
                decode_issue: Some(format!("method {} has an unreadable body header at RVA {rva:#x}", token(t::METHOD_DEF, method))),
                il: None,
                warnings: Vec::new(),
            });
        };
        let code = Reader::new(self.a.data).slice(b.code_offset, b.code_size as usize).unwrap_or(&[]);
        let max = if opts.max_instructions == 0 { 100_000 } else { opts.max_instructions };
        let (instrs, issue) = cil::decode(code, max);
        let locals = if b.local_var_sig_token >> 24 == u32::from(t::STAND_ALONE_SIG) {
            self.names.locals_sig(md.blob_cell(t::STAND_ALONE_SIG, b.local_var_sig_token & 0x00ff_ffff, 0), g).unwrap_or_else(|| vec!["?".into()])
        } else {
            Vec::new()
        };
        let mut calls = Vec::new();
        let mut field_accesses = Vec::new();
        let mut strings = Vec::new();
        for i in &instrs {
            if let Operand::Token(tok) = i.operand {
                match i.kind {
                    OperandKind::Method if calls.len() < 4096 => {
                        calls.push(CodeRef { offset: i.offset, opcode: i.opcode, token: format!("0x{tok:08x}"), target: self.method_token(tok, 0) })
                    }
                    OperandKind::Field if field_accesses.len() < 4096 => {
                        field_accesses.push(CodeRef { offset: i.offset, opcode: i.opcode, token: format!("0x{tok:08x}"), target: self.method_token(tok, 0) })
                    }
                    OperandKind::String if strings.len() < 256 => {
                        if let Some(s) = md.user_string(tok & 0x00ff_ffff, 512) {
                            strings.push(s);
                        }
                    }
                    _ => {}
                }
            }
        }
        let il = opts.include_il.then(|| instrs.iter().map(|i| self.instr_text(i)).collect());
        Some(BodyInfo {
            header: b.header,
            max_stack: b.max_stack,
            code_size: b.code_size,
            init_locals: b.init_locals,
            locals,
            exception_clauses: b.exception_clauses,
            il_hash: cil::sha256(code),
            il_shape_hash: cil::normalized_hash(&instrs),
            instruction_count: instrs.len(),
            calls,
            field_accesses,
            strings,
            decode_issue: issue.map(|i| format!("IL_{:04x}: {}", i.offset, i.reason)),
            il,
            warnings: b.warnings,
        })
    }

    /// One method.
    pub fn method(&self, owner: u32, row: u32, opts: &MemberOptions) -> MethodInfo {
        let md = self.md();
        let type_name = if owner == 0 { "<global>".to_string() } else { self.names.typedef_name(owner) };
        let simple_type = md.str_cell(t::TYPE_DEF, owner, 1);
        let g = GenCtx { type_params: self.names.type_generics(owner), method_params: self.names.method_generics(row) };
        let rva = md.cell(t::METHOD_DEF, row, 0);
        let impl_flags = md.cell(t::METHOD_DEF, row, 1);
        let flags = md.cell(t::METHOD_DEF, row, 2);
        let name = md.str_cell(t::METHOD_DEF, row, 3);
        let sig = self.names.method_sig(md.blob_cell(t::METHOD_DEF, row, 4), &g);
        let mut pnames: BTreeMap<u32, String> = BTreeMap::new();
        for p in md.list(t::METHOD_DEF, row, 5, t::PARAM, 4096) {
            pnames.insert(md.cell(t::PARAM, p, 1), md.str_cell(t::PARAM, p, 2));
        }
        let (return_type, params) = match &sig {
            Some(s) => (
                s.return_type.clone(),
                s.params
                    .iter()
                    .enumerate()
                    .map(|(i, ty)| Param { name: pnames.get(&(i as u32 + 1)).cloned().unwrap_or_else(|| format!("arg{i}")), ty: ty.clone() })
                    .collect(),
            ),
            None => ("?".into(), Vec::new()),
        };
        let mut modifiers = Vec::new();
        for (bit, m) in [(0x10, "static"), (0x400, "abstract"), (0x40, "virtual"), (0x20, "sealed"), (0x100, "newslot"), (0x2000, "extern")] {
            if flags & bit != 0 {
                modifiers.push(m);
            }
        }
        let visibility = member_visibility(flags);
        let code_type = match impl_flags & 3 {
            0 => "il",
            1 => "native",
            2 => "optil",
            _ => "runtime",
        };
        let generic_params = g.method_params.to_vec();
        let param_types: Vec<&str> = params.iter().map(|p: &Param| p.ty.as_str()).collect();
        let arity = if generic_params.is_empty() { String::new() } else { format!("<{}>", generic_params.join(", ")) };
        let key = format!("{type_name}::{name}{arity}({}):{return_type}", param_types.join(", "));
        let display_name = match name.as_str() {
            ".ctor" | ".cctor" => simple_type.split('`').next().unwrap_or("").to_string(),
            _ => name.clone(),
        };
        let ret = if name == ".ctor" || name == ".cctor" { String::new() } else { format!("{return_type} ") };
        let signature = format!(
            "{visibility} {}{ret}{display_name}{arity}({})",
            modifiers.iter().filter(|m| **m != "newslot").map(|m| format!("{m} ")).collect::<String>(),
            params.iter().map(|p| format!("{} {}", p.ty, p.name)).collect::<Vec<_>>().join(", ")
        );
        let body = if rva != 0 && code_type == "il" && !opts.skip_bodies { self.body(row, rva, opts, &g) } else { None };
        MethodInfo {
            token: token(t::METHOD_DEF, row),
            name,
            key,
            signature,
            return_type,
            params,
            generic_params,
            visibility,
            modifiers,
            code_type,
            internal_call: impl_flags & 0x1000 != 0,
            pinvoke: flags & 0x2000 != 0,
            rva,
            body,
        }
    }
}

fn type_kind(names: &Names<'_, '_>, md: &Metadata<'_>, row: u32, extends: Option<&str>) -> &'static str {
    let flags = md.cell(t::TYPE_DEF, row, 0);
    if names.typedef_name(row) == "<Module>" {
        "module"
    } else if flags & 0x20 != 0 {
        "interface"
    } else {
        match extends {
            Some("System.Enum") => "enum",
            Some("System.ValueType") if names.typedef_name(row) != "System.Enum" => "struct",
            Some("System.MulticastDelegate") => "delegate",
            _ => "class",
        }
    }
}

/// Types, fields, methods (with bodies), properties and events.
pub fn members(a: &Assembly<'_>, opts: &MemberOptions) -> Members {
    let md = &a.md;
    let res = Resolver::new(a);
    let names = &res.names;
    let mut types = Vec::new();
    let mut truncated = false;
    let mut total_methods = 0usize;
    let mut total_fields = 0usize;
    let max_types = if opts.max_types == 0 { usize::MAX } else { opts.max_types };
    // Interfaces, properties and events by owner.
    let mut ifaces: BTreeMap<u32, Vec<String>> = BTreeMap::new();
    for r in 1..=md.rows(t::INTERFACE_IMPL).min(1_000_000) {
        let owner = md.cell(t::INTERFACE_IMPL, r, 0);
        if let Some((tb, row)) = md.coded(t::INTERFACE_IMPL, r, 1) {
            let g = GenCtx { type_params: names.type_generics(owner), method_params: &[] };
            ifaces.entry(owner).or_default().push(names.type_name(tb, row, &g, 0));
        }
    }
    let mut props: BTreeMap<u32, Vec<PropertyInfo>> = BTreeMap::new();
    for r in 1..=md.rows(t::PROPERTY_MAP).min(1_000_000) {
        let owner = md.cell(t::PROPERTY_MAP, r, 0);
        let g = GenCtx { type_params: names.type_generics(owner), method_params: &[] };
        for p in md.list(t::PROPERTY_MAP, r, 1, t::PROPERTY, 65_536) {
            let ty = names.method_sig(md.blob_cell(t::PROPERTY, p, 2), &g).map(|s| s.return_type).unwrap_or_else(|| "?".into());
            props.entry(owner).or_default().push(PropertyInfo { name: md.str_cell(t::PROPERTY, p, 1), ty });
        }
    }
    let mut events: BTreeMap<u32, Vec<PropertyInfo>> = BTreeMap::new();
    for r in 1..=md.rows(t::EVENT_MAP).min(1_000_000) {
        let owner = md.cell(t::EVENT_MAP, r, 0);
        for e in md.list(t::EVENT_MAP, r, 1, t::EVENT, 65_536) {
            let ty = md.coded(t::EVENT, e, 2).map(|(tb, row)| names.type_name(tb, row, &GenCtx::default(), 0)).unwrap_or_default();
            events.entry(owner).or_default().push(PropertyInfo { name: md.str_cell(t::EVENT, e, 1), ty });
        }
    }
    let filter: Option<BTreeSet<String>> = opts.type_filter.as_ref().map(|v| v.iter().cloned().collect());
    for row in 1..=md.rows(t::TYPE_DEF) {
        let full_name = names.typedef_name(row);
        if let Some(f) = &filter {
            let simple = md.str_cell(t::TYPE_DEF, row, 1);
            if !f.contains(&full_name) && !f.contains(&simple) && !f.contains(&full_name.replace('/', ".")) {
                continue;
            }
        }
        if types.len() >= max_types {
            truncated = true;
            break;
        }
        let flags = md.cell(t::TYPE_DEF, row, 0);
        let g = GenCtx { type_params: names.type_generics(row), method_params: &[] };
        let extends = md.coded(t::TYPE_DEF, row, 3).map(|(tb, r)| {
            // Base type names keep their full form for kind detection.
            match tb {
                t::TYPE_REF => names.typeref_name(r),
                t::TYPE_DEF => names.typedef_name(r),
                _ => names.type_name(tb, r, &g, 0),
            }
        });
        let kind = type_kind(names, md, row, extends.as_deref());
        let mut modifiers = Vec::new();
        if flags & 0x80 != 0 && flags & 0x100 != 0 && kind == "class" {
            modifiers.push("static");
        } else {
            if flags & 0x80 != 0 && kind == "class" {
                modifiers.push("abstract");
            }
            if flags & 0x100 != 0 && kind == "class" {
                modifiers.push("sealed");
            }
        }
        let fields: Vec<FieldInfo> = md
            .list(t::TYPE_DEF, row, 4, t::FIELD, MAX_LIST)
            .into_iter()
            .map(|f| {
                let ff = md.cell(t::FIELD, f, 0);
                let mut mods = Vec::new();
                for (bit, m) in [(0x10, "static"), (0x20, "readonly"), (0x40, "const"), (0x100, "has-rva")] {
                    if ff & bit != 0 {
                        mods.push(m);
                    }
                }
                FieldInfo {
                    token: token(t::FIELD, f),
                    name: md.str_cell(t::FIELD, f, 1),
                    ty: names.field_sig(md.blob_cell(t::FIELD, f, 2), &g).unwrap_or_else(|| "?".into()),
                    visibility: member_visibility(ff),
                    modifiers: mods,
                }
            })
            .collect();
        let methods: Vec<MethodInfo> = md.list(t::TYPE_DEF, row, 5, t::METHOD_DEF, MAX_LIST).into_iter().map(|m| res.method(row, m, opts)).collect();
        total_methods += methods.len();
        total_fields += fields.len();
        types.push(TypeInfo {
            token: token(t::TYPE_DEF, row),
            namespace: md.str_cell(t::TYPE_DEF, row, 2),
            name: md.str_cell(t::TYPE_DEF, row, 1),
            full_name,
            kind,
            visibility: type_visibility(flags),
            modifiers,
            extends: extends.map(|e| super::sig::alias(&e).map(String::from).unwrap_or(e)),
            enclosing_type: names.enclosing(row).map(|o| names.typedef_name(o)),
            generic_params: g.type_params.to_vec(),
            interfaces: ifaces.remove(&row).unwrap_or_default(),
            fields,
            methods,
            properties: props.remove(&row).unwrap_or_default(),
            events: events.remove(&row).unwrap_or_default(),
        });
    }
    Members { types, total_types: md.rows(t::TYPE_DEF), total_methods, total_fields, truncated, warnings: md.warnings.clone() }
}

// ---------------------------------------------------------------------------------------------
// Native boundaries

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PInvoke {
    pub token: String,
    pub declaring_type: String,
    pub method: String,
    pub signature: String,
    pub module: String,
    pub entry_point: String,
    /// True when the import name was given explicitly (it differs from the method name).
    pub explicit_entry_point: bool,
    pub exact_spelling: bool,
    pub charset: &'static str,
    pub calling_convention: &'static str,
    pub set_last_error: bool,
    pub best_fit_mapping: &'static str,
    pub throw_on_unmappable_char: &'static str,
    pub preserve_sig: bool,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct BoundaryMethod {
    pub token: String,
    pub declaring_type: String,
    pub method: String,
    pub signature: String,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct NativeBoundaries {
    pub pinvokes: Vec<PInvoke>,
    pub internal_calls: Vec<BoundaryMethod>,
    pub native_code_methods: Vec<BoundaryMethod>,
    pub runtime_methods: Vec<BoundaryMethod>,
    pub unmanaged_callers_only: Vec<BoundaryMethod>,
    pub library_imports: Vec<BoundaryMethod>,
    pub module_refs: Vec<String>,
    pub has_vtable_fixups: bool,
    pub has_export_address_table_jumps: bool,
    pub il_only: bool,
    pub warnings: Vec<String>,
}

/// P/Invoke rows, internal calls, native-code methods and attribute-declared boundaries.
pub fn native_boundaries(a: &Assembly<'_>) -> NativeBoundaries {
    let md = &a.md;
    let res = Resolver::new(a);
    let opts = MemberOptions { max_instructions: 1, ..MemberOptions::default() };
    let bm = |row: u32, detail: String| -> BoundaryMethod {
        let owner = res.owners.method_owner.get(&row).copied().unwrap_or(0);
        let m = res.method_info_light(owner, row, &opts);
        BoundaryMethod { token: m.token, declaring_type: res.owner_name(owner), method: m.name, signature: m.signature, detail }
    };
    let mut pinvokes = Vec::new();
    let mut warnings = md.warnings.clone();
    for r in 1..=md.rows(t::IMPL_MAP).min(1_000_000) {
        let flags = md.cell(t::IMPL_MAP, r, 0);
        let Some((tb, row)) = md.coded(t::IMPL_MAP, r, 1) else {
            warnings.push(format!("ImplMap row {r} has no member"));
            continue;
        };
        if tb != t::METHOD_DEF {
            warnings.push(format!("ImplMap row {r} forwards a field; skipped"));
            continue;
        }
        let owner = res.owners.method_owner.get(&row).copied().unwrap_or(0);
        let m = res.method_info_light(owner, row, &opts);
        let import = md.str_cell(t::IMPL_MAP, r, 2);
        let module = md.str_cell(t::MODULE_REF, md.cell(t::IMPL_MAP, r, 3), 0);
        let impl_flags = md.cell(t::METHOD_DEF, row, 1);
        pinvokes.push(PInvoke {
            token: m.token,
            declaring_type: res.owner_name(owner),
            explicit_entry_point: !import.is_empty() && import != m.name,
            entry_point: if import.is_empty() { m.name.clone() } else { import },
            method: m.name,
            signature: m.signature,
            module,
            exact_spelling: flags & 0x1 != 0,
            charset: match flags & 0x6 {
                2 => "ansi",
                4 => "unicode",
                6 => "auto",
                _ => "not-specified",
            },
            calling_convention: match flags & 0x700 {
                0x100 => "winapi",
                0x200 => "cdecl",
                0x300 => "stdcall",
                0x400 => "thiscall",
                0x500 => "fastcall",
                _ => "not-specified",
            },
            set_last_error: flags & 0x40 != 0,
            best_fit_mapping: match flags & 0x30 {
                0x10 => "enabled",
                0x20 => "disabled",
                _ => "assembly-default",
            },
            throw_on_unmappable_char: match flags & 0x3000 {
                0x1000 => "enabled",
                0x2000 => "disabled",
                _ => "assembly-default",
            },
            preserve_sig: impl_flags & 0x80 != 0,
        });
    }
    let mut internal_calls = Vec::new();
    let mut native_code_methods = Vec::new();
    let mut runtime_methods = Vec::new();
    for row in 1..=md.rows(t::METHOD_DEF).min(4_000_000) {
        let impl_flags = md.cell(t::METHOD_DEF, row, 1);
        if impl_flags & 0x1000 != 0 && internal_calls.len() < 65_536 {
            internal_calls.push(bm(row, "implemented inside the runtime (internal call)".into()));
        }
        match impl_flags & 3 {
            1 if native_code_methods.len() < 65_536 => native_code_methods.push(bm(row, format!("native code at RVA {:#x}", md.cell(t::METHOD_DEF, row, 0)))),
            3 if runtime_methods.len() < 65_536 => runtime_methods.push(bm(row, "body supplied by the runtime".into())),
            _ => {}
        }
    }
    let mut unmanaged_callers_only = Vec::new();
    let mut library_imports = Vec::new();
    for r in 1..=md.rows(t::CUSTOM_ATTRIBUTE).min(4_000_000) {
        let Some((t::METHOD_DEF, row)) = md.coded(t::CUSTOM_ATTRIBUTE, r, 0) else { continue };
        let Some((ty, sig)) = attribute_ctor(a, &res.names, &res.owners, r) else { continue };
        if ty.ends_with("UnmanagedCallersOnlyAttribute") && unmanaged_callers_only.len() < 65_536 {
            let (_, named, _) = decode_attribute(&res.names, &sig, md.blob_cell(t::CUSTOM_ATTRIBUTE, r, 2));
            let entry =
                named.get("EntryPoint").and_then(|v| v.as_str()).map(|e| format!("exported as {e}")).unwrap_or_else(|| "callable from native code".into());
            unmanaged_callers_only.push(bm(row, entry));
        } else if ty.ends_with("LibraryImportAttribute") && library_imports.len() < 65_536 {
            let (fixed, named, _) = decode_attribute(&res.names, &sig, md.blob_cell(t::CUSTOM_ATTRIBUTE, r, 2));
            let lib = fixed.first().and_then(|v| v.as_str()).unwrap_or("?").to_string();
            let entry = named.get("EntryPoint").and_then(|v| v.as_str()).map(|e| format!(" entry {e}")).unwrap_or_default();
            library_imports.push(bm(row, format!("source-generated import from {lib}{entry}")));
        }
    }
    let cli = &a.pe.cli;
    NativeBoundaries {
        pinvokes,
        internal_calls,
        native_code_methods,
        runtime_methods,
        unmanaged_callers_only,
        library_imports,
        module_refs: (1..=md.rows(t::MODULE_REF).min(65_536)).map(|r| md.str_cell(t::MODULE_REF, r, 0)).collect(),
        has_vtable_fixups: !cli.vtable_fixups.is_empty(),
        has_export_address_table_jumps: !cli.export_address_table_jumps.is_empty(),
        il_only: cli.flags & pe::COMIMAGE_FLAGS_ILONLY != 0,
        warnings,
    }
}

impl Resolver<'_, '_> {
    fn owner_name(&self, owner: u32) -> String {
        if owner == 0 { "<global>".into() } else { self.names.typedef_name(owner) }
    }

    /// A method without decoding its body.
    fn method_info_light(&self, owner: u32, row: u32, opts: &MemberOptions) -> MethodInfo {
        self.method(owner, row, &MemberOptions { include_il: false, skip_bodies: true, ..opts.clone() })
    }
}
