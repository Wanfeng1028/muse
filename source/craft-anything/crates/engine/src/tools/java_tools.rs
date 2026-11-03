//! Java programs with built-in parsers: a JAR/WAR overview (manifest, package tree, main class,
//! dependencies, class-file versions), class/method search, one class's fields and methods, a
//! method's JVM bytecode disassembly with resolved constant-pool references plus a best-effort
//! pseudo-Java decompilation, and cross-archive reference tracing. All clean-room and pure Rust;
//! no JDK or external decompiler is used.

use super::native_common::page;
use super::static_input::{self, Input, builder};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_analysis::java_decompile;
use craft_anything_evidence::{Authority, Confidence, Coverage, CoverageStatus, ErrorCode, EvidenceBuilder, Limitation, Location, ToolError};
use craft_anything_formats::java_class::{self, ClassFile};
use craft_anything_formats::{java_ops, zip};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::Java;
    let e = Effects::EVIDENCE;
    vec![
        ToolSpec {
            id: "java_archive_show",
            title: "Java archive overview",
            summary: "Read a JAR or WAR with the built-in parser: the MANIFEST.MF attributes (main class, class-path, versions), the classes it defines grouped into a package tree, bundled dependencies (nested jars and native libraries), resources, and the class-file (Java) version(s) seen.",
            beginner: "See what's inside a Java program (.jar/.war): its name, its main entry point, its packages and what it bundles.",
            toolset: Java,
            effects: e,
            requires: Requires::Nothing,
            input_schema: schema_of::<ArchiveParams>,
            run: java_archive_show,
        },
        ToolSpec {
            id: "java_classes_find",
            title: "Find Java classes",
            summary: "Search the classes (and optionally methods) defined in a JAR/WAR or a single .class by name; an empty query lists every class. Paged (offset/limit).",
            beginner: "Find the pieces of code inside a Java program by name.",
            toolset: Java,
            effects: e,
            requires: Requires::Nothing,
            input_schema: schema_of::<SearchParams>,
            run: java_classes_find,
        },
        ToolSpec {
            id: "java_class_show",
            title: "Java class",
            summary: "One class from a JAR/WAR or a bare .class: its Java version, access flags, superclass, interfaces, source file, annotations, inner classes, and its fields and methods with Java-style signatures. With decompile=true, also a pseudo-Java skeleton of the class.",
            beginner: "Look inside one piece of a Java program's code.",
            toolset: Java,
            effects: e,
            requires: Requires::Nothing,
            input_schema: schema_of::<ClassParams>,
            run: java_class_show,
        },
        ToolSpec {
            id: "java_method_show",
            title: "Java method bytecode and pseudo-Java",
            summary: "A method's JVM bytecode as a disassembly listing with resolved constant-pool references (fields, methods, classes, string/number constants), branch targets, switch tables and the exception table, plus a best-effort structured pseudo-Java reconstruction (confidence Inferred). Paged over instructions.",
            beginner: "Read the instructions of one function in a Java program, and a best-guess of its original Java source.",
            toolset: Java,
            effects: e | Effects::CARRIES_TARGET_CONTENT,
            requires: Requires::Nothing,
            input_schema: schema_of::<MethodParams>,
            run: java_method_show,
        },
        ToolSpec {
            id: "java_class_users_find",
            title: "Who uses this Java class?",
            summary: "Every instruction in every class of a JAR/WAR (or a single .class) that calls, reads, writes, creates or casts to a class (or only calls one of its methods when method_name is given), with the calling method and bytecode offset. Paged.",
            beginner: "Find every place in a Java program that uses a piece of code.",
            toolset: Java,
            effects: e,
            requires: Requires::Nothing,
            input_schema: schema_of::<ReferencesParams>,
            run: java_class_users_find,
        },
    ]
}

// ---------------------------------------------------------------------------------------------
// Params

fn d_limit() -> usize {
    200
}
fn d_insn_limit() -> usize {
    2000
}
fn d_true() -> bool {
    true
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ArchiveParams {
    /// Absolute path of the JAR/WAR; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SearchParams {
    #[serde(default)]
    pub path: Option<String>,
    /// Case-insensitive part of a class (or method) name. Empty lists every class.
    #[serde(default)]
    pub query: String,
    /// Also match (and show) method names.
    #[serde(default)]
    pub include_methods: bool,
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ClassParams {
    #[serde(default)]
    pub path: Option<String>,
    /// `com.example.Main`, `com/example/Main` or `Lcom/example/Main;`. Optional for a bare .class.
    #[serde(default)]
    pub class_name: Option<String>,
    /// Also include a pseudo-Java skeleton of the class (confidence Inferred).
    #[serde(default)]
    pub decompile: bool,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct MethodParams {
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub class_name: Option<String>,
    pub method_name: String,
    /// The method descriptor (`(I)I`) to pick a specific overload; the first match otherwise.
    #[serde(default)]
    pub descriptor: Option<String>,
    /// Include the pseudo-Java reconstruction (default true).
    #[serde(default = "d_true")]
    pub decompile: bool,
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "d_insn_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReferencesParams {
    #[serde(default)]
    pub path: Option<String>,
    pub class_name: String,
    /// Only calls to methods with this name.
    #[serde(default)]
    pub method_name: Option<String>,
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "d_limit")]
    pub limit: usize,
}

// ---------------------------------------------------------------------------------------------
// Loading

/// Biggest archive read.
const MAX_JAR: u64 = 1 << 30;
/// Biggest single member decompressed.
const MAX_MEMBER: u64 = 256 << 20;
/// Most classes parsed for a whole-archive operation.
const MAX_CLASSES: usize = 100_000;
/// Total class bytes parsed for a whole-archive operation.
const MAX_CLASS_TOTAL: u64 = 768 << 20;

/// Parsed classes keyed by entry (or file) name, plus any parse warnings.
type ParsedClasses = (Vec<(String, ClassFile)>, Vec<String>);

struct Source {
    input: Input,
    zip: Option<zip::ZipArchive>,
    /// (name, bytes) for a single bare `.class`.
    single: Option<(String, Vec<u8>)>,
}

fn load(ctx: &Ctx<'_>, path: Option<&str>) -> Result<Source, ToolError> {
    let input = static_input::load(ctx, path, MAX_JAR)?;
    if java_class::is_class(&input.bytes) {
        let name = input.name.clone();
        let bytes = input.bytes.to_vec();
        return Ok(Source { input, zip: None, single: Some((name, bytes)) });
    }
    if zip::looks_like_zip(&input.bytes) {
        let z = zip::parse(&input.bytes, 500_000)
            .map_err(|e| ToolError::new(ErrorCode::NotSupported, format!("Couldn't read the archive's ZIP directory: {e}")))?;
        return Ok(Source { input, zip: Some(z), single: None });
    }
    Err(ToolError::unsupported(format!("{} is not a Java .class or a JAR/WAR archive", input.name))
        .with_remediation("Pass a .class, .jar or .war file; run triage to see what this file is."))
}

fn is_class_entry(name: &str) -> bool {
    name.ends_with(".class") && !name.ends_with("package-info.class")
}

impl Source {
    fn bytes(&self) -> &[u8] {
        &self.input.bytes
    }

    fn read_entry(&self, e: &zip::ZipEntry) -> Result<Vec<u8>, String> {
        zip::read_entry(self.bytes(), e, MAX_MEMBER).map_err(|e| e.to_string())
    }

    fn member(&self, name: &str) -> Option<Vec<u8>> {
        let z = self.zip.as_ref()?;
        let e = z.entries.iter().find(|e| e.name == name)?;
        self.read_entry(e).ok()
    }

    /// Parse every class (bounded), returning (entry-or-class name, parsed) and warnings.
    fn parse_all(&self, ctx: &Ctx<'_>) -> Result<ParsedClasses, ToolError> {
        let mut out = Vec::new();
        let mut warnings = Vec::new();
        if let Some((name, bytes)) = &self.single {
            match java_class::parse(bytes) {
                Ok(cf) => {
                    warnings.extend(cf.warnings.iter().map(|w| format!("{name}: {w}")));
                    out.push((name.clone(), cf));
                }
                Err(e) => return Err(ToolError::new(ErrorCode::NotSupported, format!("Couldn't read {name} as a Java class: {e}"))),
            }
            return Ok((out, warnings));
        }
        let Some(z) = self.zip.as_ref() else { return Ok((out, warnings)) };
        let mut total = 0u64;
        for e in z.entries.iter().filter(|e| !e.is_dir && is_class_entry(&e.name)) {
            if out.len() >= MAX_CLASSES {
                warnings.push(format!("stopped after {MAX_CLASSES} classes"));
                break;
            }
            if total.saturating_add(e.uncompressed_size) > MAX_CLASS_TOTAL {
                warnings.push(format!("{} skipped: class-byte budget used up", e.name));
                continue;
            }
            if out.len() % 256 == 0 {
                ctx.cancel.check()?;
            }
            match self.read_entry(e) {
                Ok(b) => {
                    total += b.len() as u64;
                    match java_class::parse(&b) {
                        Ok(cf) => {
                            warnings.extend(cf.warnings.iter().map(|w| format!("{}: {w}", e.name)));
                            out.push((e.name.clone(), cf));
                        }
                        Err(err) => warnings.push(format!("{}: {err}", e.name)),
                    }
                }
                Err(err) => warnings.push(format!("{}: {err}", e.name)),
            }
        }
        Ok((out, warnings))
    }

    /// Find and parse one class by name (dotted, internal or descriptor form).
    fn resolve_class(&self, query: Option<&str>) -> Result<(String, ClassFile), ToolError> {
        if let Some((name, bytes)) = &self.single {
            let cf = java_class::parse(bytes).map_err(|e| ToolError::new(ErrorCode::NotSupported, format!("Couldn't read {name} as a Java class: {e}")))?;
            return Ok((name.clone(), cf));
        }
        let q = query.ok_or_else(|| {
            ToolError::invalid("class_name is required for an archive").with_remediation("Pass class_name; list classes with java_classes_find.")
        })?;
        let want = normalize_internal(q);
        let path = format!("{want}.class");
        let simple = want.rsplit('/').next().unwrap_or(&want).to_string();
        let Some(z) = self.zip.as_ref() else { return Err(ToolError::internal("no archive")) };
        let entry = z
            .entries
            .iter()
            .find(|e| e.name == path)
            .or_else(|| z.entries.iter().find(|e| is_class_entry(&e.name) && e.name.trim_end_matches(".class").rsplit('/').next() == Some(simple.as_str())))
            .ok_or_else(|| class_not_found(self, q))?;
        let bytes = self.read_entry(&entry.clone()).map_err(|e| ToolError::new(ErrorCode::NotSupported, format!("{}: {e}", entry.name)))?;
        let cf =
            java_class::parse(&bytes).map_err(|e| ToolError::new(ErrorCode::NotSupported, format!("Couldn't read {} as a Java class: {e}", entry.name)))?;
        Ok((entry.name.clone(), cf))
    }
}

/// `com.example.Foo`, `Lcom/example/Foo;` or `com/example/Foo` → `com/example/Foo`.
fn normalize_internal(name: &str) -> String {
    let n = name.trim();
    let n = n.strip_prefix('L').map(|s| s.strip_suffix(';').unwrap_or(s)).unwrap_or(n);
    n.replace('.', "/")
}

fn class_not_found(src: &Source, name: &str) -> ToolError {
    let simple = name.rsplit(['.', '/']).next().unwrap_or(name).trim_end_matches(';').to_ascii_lowercase();
    let mut similar = Vec::new();
    if let Some(z) = src.zip.as_ref() {
        for e in z.entries.iter().filter(|e| is_class_entry(&e.name)) {
            let dotted = e.name.trim_end_matches(".class").replace('/', ".");
            if !simple.is_empty() && dotted.to_ascii_lowercase().contains(&simple) && similar.len() < 10 {
                similar.push(dotted);
            }
        }
    }
    ToolError::invalid(format!("No class {name} is defined in this archive"))
        .with_remediation("Find the exact name with java_classes_find (classes from the JRE are not inside the archive).")
        .with_details(json!({"reason": "class_not_found", "similar": similar}))
}

fn warn_lims(warnings: &[String]) -> Vec<Limitation> {
    warnings.iter().take(50).map(|w| Limitation::new("parse_warning", w.clone())).collect()
}

fn ev(ctx: &Ctx<'_>, op: &str, src: &Source, params: Value) -> EvidenceBuilder {
    builder(ctx, op, src.input.subject.clone(), params)
        .authority(Authority::OriginalFiles)
        .location(Location::new("path", src.input.path.display().to_string()))
}

// ---------------------------------------------------------------------------------------------
// java_archive_show

fn parse_manifest(bytes: &[u8]) -> BTreeMap<String, String> {
    let text = String::from_utf8_lossy(bytes);
    let mut map: BTreeMap<String, String> = BTreeMap::new();
    let mut last_key: Option<String> = None;
    for line in text.lines() {
        if line.is_empty() {
            break; // only the main section
        }
        if let Some(rest) = line.strip_prefix(' ') {
            // continuation of the previous value
            if let Some(k) = &last_key
                && let Some(v) = map.get_mut(k)
            {
                v.push_str(rest);
            }
        } else if let Some((k, v)) = line.split_once(": ") {
            map.insert(k.trim().to_string(), v.trim().to_string());
            last_key = Some(k.trim().to_string());
        }
    }
    map
}

fn java_archive_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ArchiveParams = parse_params(params)?;
    let src = load(ctx, p.path.as_deref())?;
    let Some(z) = src.zip.as_ref() else {
        return Err(ToolError::unsupported(format!("{} is a single .class, not a JAR/WAR", src.input.name))
            .with_remediation("Use java_class_show or java_method_show for a bare .class."));
    };
    let manifest = src.member("META-INF/MANIFEST.MF").map(|b| parse_manifest(&b)).unwrap_or_default();
    // Classify entries.
    let mut packages: BTreeMap<String, usize> = BTreeMap::new();
    let mut class_count = 0usize;
    let mut versions: BTreeMap<String, usize> = BTreeMap::new();
    let mut nested_jars = Vec::new();
    let mut native_libs = Vec::new();
    let mut resources = 0usize;
    // Sample class-file versions from up to a few hundred classes (cheap: read the 8-byte header).
    let mut sampled = 0usize;
    for e in z.entries.iter().filter(|e| !e.is_dir) {
        if is_class_entry(&e.name) {
            class_count += 1;
            let pkg = e.name.trim_end_matches(".class").rsplit_once('/').map(|(p, _)| p.replace('/', ".")).unwrap_or_default();
            *packages.entry(if pkg.is_empty() { "(default)".into() } else { pkg }).or_default() += 1;
            if sampled < 512
                && let Ok(b) = self_header(&src, e)
                && let Some(major) = craft_anything_formats::bytes::Reader::new(&b).u16_be(6)
            {
                *versions.entry(java_class::Version { major, minor: 0 }.java_label()).or_default() += 1;
                sampled += 1;
            }
        } else if e.name.ends_with(".jar") {
            nested_jars.push(json!({"name": e.name, "bytes": e.uncompressed_size}));
        } else if e.name.ends_with(".so") || e.name.ends_with(".dll") || e.name.ends_with(".dylib") || e.name.ends_with(".jnilib") {
            native_libs.push(json!({"name": e.name, "bytes": e.uncompressed_size}));
        } else {
            resources += 1;
        }
    }
    let main_class = manifest.get("Main-Class").cloned();
    let class_path: Vec<String> = manifest.get("Class-Path").map(|c| c.split_whitespace().map(str::to_string).collect()).unwrap_or_default();
    let kind = if src.input.name.to_ascii_lowercase().ends_with(".war") { "WAR" } else { "JAR" };
    let summary = format!(
        "{} ({kind}): {} classes in {} package(s), main class {}, {} nested jar(s), {} native lib(s), {} resource(s).",
        src.input.name,
        class_count,
        packages.len(),
        main_class.as_deref().unwrap_or("(none declared)"),
        nested_jars.len(),
        native_libs.len(),
        resources,
    );
    let pkg_rows: Vec<Value> = packages.iter().map(|(k, v)| json!({"package": k, "classes": v})).collect();
    let b = ev(ctx, "java_archive_show", &src, json!({"path": p.path}))
        .result(json!({
            "kind": kind,
            "manifest": manifest,
            "main_class": main_class,
            "class_path": class_path,
            "classes_total": class_count,
            "packages": pkg_rows,
            "class_file_versions": versions,
            "nested_jars": nested_jars,
            "native_libraries": native_libs,
            "resources": resources,
            "entries": z.entries.len(),
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .coverage(Coverage::complete(z.entries.len() as u64))
        .limitation(Limitation::new(
            "dependencies_from_manifest",
            "Dependencies are taken from the manifest Class-Path and bundled jars/native libraries; dependencies resolved at run time (module path, classloaders, reflection) are not listed.",
        ));
    Ok(ToolOutput::evidence(b.build()?))
}

/// Read just the first 8 bytes of a class entry (magic + version) without decompressing it all.
fn self_header(src: &Source, e: &zip::ZipEntry) -> Result<Vec<u8>, String> {
    // Stored entries can be read cheaply; deflated ones need decompression, so cap the read.
    src.read_entry(e).map(|mut b| {
        b.truncate(8);
        b
    })
}

// ---------------------------------------------------------------------------------------------
// java_classes_find

fn inspect_access(flags: u16) -> Vec<&'static str> {
    java_class::access_flags(flags, java_class::AccessKind::Class)
}

fn java_classes_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SearchParams = parse_params(params)?;
    let src = load(ctx, p.path.as_deref())?;
    let (classes, warnings) = src.parse_all(ctx)?;
    let q = p.query.trim().to_ascii_lowercase();
    let mut rows = Vec::new();
    for (entry, cf) in &classes {
        let dotted = cf.name_dotted();
        let methods: Vec<Value> = if p.include_methods {
            cf.methods
                .iter()
                .filter(|m| q.is_empty() || m.name.to_ascii_lowercase().contains(&q))
                .take(5000)
                .map(|m| json!({"name": m.name, "signature": cf.method_signature(m)}))
                .collect()
        } else {
            Vec::new()
        };
        let class_hit = q.is_empty() || dotted.to_ascii_lowercase().contains(&q);
        if !class_hit && methods.is_empty() {
            continue;
        }
        rows.push(json!({
            "name": dotted,
            "internal": cf.this_class,
            "entry": entry,
            "access": inspect_access(cf.access),
            "superclass": cf.super_class.as_ref().map(|s| java_class::internal_to_dotted(s)),
            "interfaces": cf.interfaces.iter().map(|i| java_class::internal_to_dotted(i)).collect::<Vec<_>>(),
            "fields": cf.fields.len(),
            "methods": cf.methods.len(),
            "matched_methods": methods,
        }));
    }
    rows.sort_by(|a, b| a["name"].as_str().unwrap_or("").cmp(b["name"].as_str().unwrap_or("")));
    let (slice, cov) = page(&rows, p.offset, p.limit);
    let summary = format!(
        "{} of {} classes{} ; showing {}.",
        rows.len(),
        classes.len(),
        if q.is_empty() { String::new() } else { format!(" match \"{}\"", p.query.trim()) },
        slice.len()
    );
    let b = ev(
        ctx,
        "java_classes_find",
        &src,
        json!({"path": p.path, "query": p.query, "include_methods": p.include_methods, "offset": p.offset, "limit": p.limit}),
    )
    .result(json!({"query": p.query, "matches": rows.len(), "classes_total": classes.len(), "classes": slice}))
    .summary(summary)
    .confidence(Confidence::Observed)
    .limitations(warn_lims(&warnings))
    .coverage(cov);
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// java_class_show

fn field_json(f: &java_class::Member) -> Value {
    json!({
        "name": f.name,
        "type": java_class::field_type(&f.descriptor),
        "descriptor": f.descriptor,
        "access": java_class::access_flags(f.access, java_class::AccessKind::Field),
        "constant_value": f.constant_value,
        "signature": f.signature,
        "deprecated": f.deprecated,
    })
}

fn method_json(cf: &ClassFile, m: &java_class::Member) -> Value {
    let code = m.code.as_ref();
    json!({
        "name": m.name,
        "descriptor": m.descriptor,
        "signature": cf.method_signature(m),
        "access": java_class::access_flags(m.access, java_class::AccessKind::Method),
        "throws": m.exceptions,
        "signature_attr": m.signature,
        "deprecated": m.deprecated,
        "code_bytes": code.map(|c| c.bytecode.len()),
        "max_stack": code.map(|c| c.max_stack),
        "max_locals": code.map(|c| c.max_locals),
        "try_blocks": code.map(|c| c.exceptions.len()),
    })
}

fn java_class_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ClassParams = parse_params(params)?;
    let src = load(ctx, p.path.as_deref())?;
    let (entry, cf) = src.resolve_class(p.class_name.as_deref())?;
    let fields: Vec<Value> = cf.fields.iter().map(field_json).collect();
    let methods: Vec<Value> = cf.methods.iter().map(|m| method_json(&cf, m)).collect();
    let mut lims = warn_lims(&cf.warnings);
    let decompiled = if p.decompile {
        let d = java_decompile::decompile_class(&cf);
        lims.extend(d.limitations);
        Some(d.source)
    } else {
        None
    };
    let summary = format!(
        "{} ({}) {}: {} fields, {} methods{}.",
        cf.name_dotted(),
        cf.version.java_label(),
        match &cf.super_class {
            Some(s) if s != "java/lang/Object" => format!("extends {}", java_class::internal_to_dotted(s)),
            _ => "extends Object".to_string(),
        },
        fields.len(),
        methods.len(),
        cf.source_file.as_deref().map(|s| format!(", from {s}")).unwrap_or_default()
    );
    let b = ev(ctx, "java_class_show", &src, json!({"path": p.path, "class_name": p.class_name, "decompile": p.decompile}))
        .result(json!({
            "name": cf.name_dotted(),
            "internal": cf.this_class,
            "entry": entry,
            "version": cf.version,
            "java_version": cf.version.java_label(),
            "access": inspect_access(cf.access),
            "superclass": cf.super_class.as_ref().map(|s| java_class::internal_to_dotted(s)),
            "interfaces": cf.interfaces.iter().map(|i| java_class::internal_to_dotted(i)).collect::<Vec<_>>(),
            "source_file": cf.source_file,
            "signature": cf.signature,
            "annotations": cf.annotations,
            "inner_classes": cf.inner_classes,
            "fields": fields,
            "methods": methods,
            "pseudo_java": decompiled,
        }))
        .summary(summary)
        .confidence(if p.decompile { Confidence::Inferred } else { Confidence::Observed })
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .location(Location::new("class", cf.this_class.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// java_method_show

#[derive(Serialize)]
struct InsnRow {
    offset: String,
    text: String,
    opcode: String,
    len: u32,
}

fn java_method_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: MethodParams = parse_params(params)?;
    let src = load(ctx, p.path.as_deref())?;
    let (entry, cf) = src.resolve_class(p.class_name.as_deref())?;
    let overloads: Vec<&java_class::Member> = cf.methods.iter().filter(|m| m.name == p.method_name).collect();
    if overloads.is_empty() {
        let names: Vec<String> = cf.methods.iter().take(400).map(|m| m.name.clone()).collect();
        return Err(ToolError::invalid(format!("{} has no method named {}", cf.name_dotted(), p.method_name))
            .with_remediation("List the class's methods with java_class_show.")
            .with_details(json!({"reason": "method_not_found", "methods": names})));
    }
    let m = match &p.descriptor {
        Some(d) => *overloads.iter().find(|m| &m.descriptor == d).ok_or_else(|| {
            ToolError::invalid(format!("{} has no overload with descriptor {d}", p.method_name))
                .with_details(json!({"overloads": overloads.iter().map(|m| m.descriptor.clone()).collect::<Vec<_>>()}))
        })?,
        None => overloads[0],
    };
    let mut lims = warn_lims(&cf.warnings);
    if overloads.len() > 1 && p.descriptor.is_none() {
        lims.push(Limitation::new(
            "overload_chosen",
            format!("{} has {} overloads; showing the first. Pass descriptor to pick another.", p.method_name, overloads.len()),
        ));
    }
    let code = m.code.as_ref();
    let (rows, complete) = match code {
        Some(c) => {
            let (insns, complete) = java_ops::decode(&c.bytecode, 200_000);
            let rows: Vec<InsnRow> = insns
                .iter()
                .map(|i| InsnRow { offset: format!("{:04x}", i.pc), text: cf.format_insn(i), opcode: format!("{:#04x}", i.opcode), len: i.len })
                .collect();
            if !complete {
                lims.push(Limitation::new("listing_incomplete", "Decoding stopped at an instruction that runs past the end of the code."));
            }
            (rows, complete)
        }
        None => {
            lims.push(Limitation::new(
                "no_code",
                if m.access & 0x0100 != 0 {
                    "This method is native: its code is not in the class file."
                } else if m.access & 0x0400 != 0 {
                    "This method is abstract: it has no body."
                } else {
                    "This method has no Code attribute."
                },
            ));
            (Vec::new(), true)
        }
    };
    let (slice, cov) = page(&rows, p.offset, p.limit);
    let listing: String =
        slice.iter().filter_map(|r| Some(format!("{}: {}", r.get("offset")?.as_str()?, r.get("text")?.as_str()?))).collect::<Vec<_>>().join("\n");
    let exceptions: Vec<Value> = code
        .map(|c| {
            c.exceptions
                .iter()
                .map(|x| json!({"start_pc": x.start_pc, "end_pc": x.end_pc, "handler_pc": x.handler_pc, "catch_type": x.catch_type.as_ref().map(|t| java_class::internal_to_dotted(t))}))
                .collect()
        })
        .unwrap_or_default();
    let pseudo = if p.decompile {
        let d = java_decompile::decompile_method(&cf, m);
        lims.extend(d.limitations);
        json!({"signature": d.signature, "code": format!("{} {}", d.signature, d.body), "confidence": "inferred", "fully_structured": d.fully_structured})
    } else {
        Value::Null
    };
    let summary = format!(
        "{}.{}{} ({}): {} instructions{}{}.",
        cf.name_dotted(),
        m.name,
        m.descriptor,
        entry,
        rows.len(),
        if exceptions.is_empty() { String::new() } else { format!(", {} try block(s)", exceptions.len()) },
        if complete { "" } else { " (incomplete)" }
    );
    let reference = format!("{}.{}{}", cf.name_dotted(), m.name, m.descriptor);
    let b = ev(ctx, "java_method_show", &src, json!({"path": p.path, "class_name": p.class_name, "method_name": p.method_name, "descriptor": p.descriptor, "decompile": p.decompile, "offset": p.offset, "limit": p.limit}))
        .result(json!({
            "class": cf.name_dotted(),
            "entry": entry,
            "method": reference,
            "signature": cf.method_signature(m),
            "descriptor": m.descriptor,
            "access": java_class::access_flags(m.access, java_class::AccessKind::Method),
            "throws": m.exceptions,
            "overloads": overloads.iter().map(|m| m.descriptor.clone()).collect::<Vec<_>>(),
            "max_stack": code.map(|c| c.max_stack),
            "max_locals": code.map(|c| c.max_locals),
            "exception_table": exceptions,
            "instructions_total": rows.len(),
            "instructions": slice,
            "listing": listing,
            "pseudo_java": pseudo,
        }))
        .summary(summary)
        .confidence(if p.decompile { Confidence::Inferred } else { Confidence::Observed })
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("method", reference.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// java_class_users_find

fn java_class_users_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ReferencesParams = parse_params(params)?;
    let src = load(ctx, p.path.as_deref())?;
    let (classes, warnings) = src.parse_all(ctx)?;
    let owner = normalize_internal(&p.class_name);
    const MAX_REFS: usize = 100_000;
    let mut rows = Vec::new();
    let mut truncated = false;
    let mut callers: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    let mut defined_in = None;
    for (entry, cf) in &classes {
        ctx.cancel.check()?;
        if cf.this_class == owner {
            defined_in = Some(entry.clone());
        }
        let (refs, more) = java_class::references(cf, &owner, p.method_name.as_deref(), MAX_REFS.saturating_sub(rows.len()));
        truncated |= more;
        for r in refs {
            callers.insert(r.caller.clone());
            rows.push(json!({"entry": entry, "caller": r.caller, "offset": format!("{:04x}", r.pc), "instruction": r.instruction, "kind": r.kind, "target": r.target}));
        }
    }
    let (slice, mut cov) = page(&rows, p.offset, p.limit);
    let what = match &p.method_name {
        Some(m) => format!("{}.{m}", java_class::internal_to_dotted(&owner)),
        None => java_class::internal_to_dotted(&owner),
    };
    let summary = format!(
        "{} reference(s) to {what} from {} method(s) across {} class(es){}.",
        rows.len(),
        callers.len(),
        classes.len(),
        match &defined_in {
            Some(d) => format!("; defined in {d}"),
            None => "; not defined in this archive (JRE or external library class)".into(),
        }
    );
    let mut lims = warn_lims(&warnings);
    lims.push(Limitation::new(
        "static_references_only",
        "Only direct bytecode references are found; reflection, invokedynamic bootstrap targets, service loaders and names built at run time are not.",
    ));
    if truncated {
        lims.push(Limitation::new("truncated", format!("stopped after {MAX_REFS} references")));
        cov.status = CoverageStatus::Partial;
    }
    let b = ev(ctx, "java_class_users_find", &src, json!({"path": p.path, "class_name": p.class_name, "method_name": p.method_name, "offset": p.offset, "limit": p.limit}))
        .result(json!({"class": owner, "method_name": p.method_name, "defined_in": defined_in, "references_total": rows.len(), "callers": callers.len(), "references": slice}))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("class", owner.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use crate::Engine;
    use craft_anything_testkit::java as fx;
    use serde_json::json;

    fn jar() -> String {
        craft_anything_testkit::temp_file("notes.jar", &fx::notes_jar()).to_string_lossy().into_owned()
    }
    fn class_file() -> String {
        craft_anything_testkit::temp_file("Hello.class", &fx::hello_class()).to_string_lossy().into_owned()
    }

    #[test]
    fn archive_overview() {
        let e = Engine::new(crate::testing::session());
        let v = call(&e, "java_archive_show", json!({"path": jar()}));
        let r = &v["result"];
        assert_eq!(r["main_class"], "com.example.Hello");
        assert_eq!(r["classes_total"], 2);
        assert!(r["packages"].as_array().unwrap().iter().any(|p| p["package"] == "com.example"));
        assert!(v["summary"].as_str().unwrap().contains("main class com.example.Hello"), "{}", v["summary"]);
    }

    #[test]
    fn search_and_class_and_method() {
        let e = Engine::new(crate::testing::session());
        let path = jar();
        let s = call(&e, "java_classes_find", json!({"path": path, "query": "hello"}));
        assert_eq!(s["result"]["matches"], 1);
        let c = call(&e, "java_class_show", json!({"path": path, "class_name": "com.example.Hello"}));
        assert_eq!(c["result"]["interfaces"][0], "java.lang.Runnable");
        assert_eq!(c["result"]["java_version"], "Java 8");
        assert!(c["result"]["methods"].as_array().unwrap().iter().any(|m| m["name"] == "run"));
        assert!(c["result"]["fields"].as_array().unwrap().iter().any(|f| f["name"] == "BIG" && f["constant_value"].is_string()));

        let m = call(&e, "java_method_show", json!({"path": path, "class_name": "com.example.Hello", "method_name": "run"}));
        assert!(m["result"]["listing"].as_str().unwrap().contains("invokevirtual java.io.PrintStream.println"), "{}", m["result"]["listing"]);
        assert!(m["result"]["pseudo_java"]["code"].as_str().unwrap().contains("System.out.println(\"Hello, Craft!\");"), "{}", m["result"]["pseudo_java"]);
        assert_eq!(v_conf(&m), "inferred");

        // overload selection by descriptor + a method with a switch
        let pick = call(&e, "java_method_show", json!({"path": path, "class_name": "com.example.Hello", "method_name": "pick"}));
        assert!(pick["result"]["pseudo_java"]["code"].as_str().unwrap().contains("switch"), "{}", pick["result"]["pseudo_java"]);
    }

    fn v_conf(v: &serde_json::Value) -> String {
        v["confidence"].as_str().unwrap_or_default().to_string()
    }

    #[test]
    fn references_cross_class() {
        let e = Engine::new(crate::testing::session());
        let path = jar();
        let r = call(&e, "java_class_users_find", json!({"path": path, "class_name": "com.example.Hello", "method_name": "run"}));
        assert_eq!(r["result"]["references_total"], 1, "{}", r["result"]);
        assert_eq!(r["result"]["references"][0]["caller"], "com.example.Helper.go:()V");
        assert_eq!(r["result"]["defined_in"], "com/example/Hello.class");
    }

    #[test]
    fn bare_class_file_works() {
        let e = Engine::new(crate::testing::session());
        let path = class_file();
        let c = call(&e, "java_class_show", json!({"path": path, "decompile": true}));
        assert_eq!(c["result"]["name"], "com.example.Hello");
        assert!(c["result"]["pseudo_java"].as_str().unwrap().contains("class com.example.Hello"), "{}", c["result"]["pseudo_java"]);
        // archive tool rejects a bare class
        let err = call_err(&e, "java_archive_show", json!({"path": path}));
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::NotSupported);
    }

    #[test]
    fn hostile_inputs_do_not_panic() {
        let e = Engine::new(crate::testing::session());
        let jar_bytes = fx::notes_jar();
        for (i, m) in craft_anything_testkit::mutations(&jar_bytes).into_iter().enumerate().step_by(3) {
            let p = craft_anything_testkit::temp_file(&format!("m{i}.jar"), &m);
            for (tool, params) in [
                ("java_archive_show", json!({"path": p})),
                ("java_classes_find", json!({"path": p, "include_methods": true})),
                ("java_class_show", json!({"path": p, "class_name": "com.example.Hello"})),
                ("java_method_show", json!({"path": p, "class_name": "com.example.Hello", "method_name": "run"})),
                ("java_class_users_find", json!({"path": p, "class_name": "com.example.Hello"})),
            ] {
                let _ = e.call(tool, params, crate::CallOptions::new(crate::Caller::Mcp));
            }
        }
        // hostile bare class files
        let cls = fx::hello_class();
        for m in craft_anything_testkit::mutations(&cls).into_iter().step_by(2) {
            let p = craft_anything_testkit::temp_file("m.class", &m);
            let _ = e.call("java_class_show", json!({"path": p, "decompile": true}), crate::CallOptions::new(crate::Caller::Mcp));
        }
    }
}
