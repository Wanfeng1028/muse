use super::*;
use craft_anything_testkit::managed as fx;

#[test]
fn managed_architecture_follows_the_cli_flags() {
    let mut pe = pe::parse_pe(&fx::managed_assembly(1)).unwrap();
    for (flags, want) in [
        (pe::COMIMAGE_FLAGS_ILONLY, "anycpu"),
        (pe::COMIMAGE_FLAGS_ILONLY | pe::COMIMAGE_FLAGS_32BITREQUIRED, "x86"),
        (pe::COMIMAGE_FLAGS_ILONLY | pe::COMIMAGE_FLAGS_32BITREQUIRED | pe::COMIMAGE_FLAGS_32BITPREFERRED, "anycpu-prefer-32"),
        // Mixed-mode (native code inside) is pinned to the PE machine.
        (0, "x86"),
    ] {
        pe.cli.flags = flags;
        assert_eq!(pe.dotnet_arch(), want, "flags {flags:#x}");
    }
    pe.machine = 0x8664;
    pe.cli.flags = pe::COMIMAGE_FLAGS_ILONLY;
    assert_eq!(pe.dotnet_arch(), "x64");
}

#[test]
fn inventory_of_the_sample() {
    let bytes = fx::managed_assembly(1);
    let a = open(&bytes).unwrap();
    let inv = inventory(&a);
    assert_eq!(inv.pe_kind, "PE32");
    assert!(inv.is_dll);
    assert_eq!(inv.metadata_version, "v4.0.30319");
    assert_eq!(inv.runtime_version, "2.5");
    assert_eq!(inv.cli_flags, vec!["il-only"]);
    let asm = inv.assembly.as_ref().unwrap();
    assert_eq!((asm.name.as_str(), asm.version.as_str()), ("Sample", "1.2.3.4"));
    assert_eq!(inv.assembly_refs.len(), 2);
    assert_eq!(inv.assembly_refs[0].name, "System.Runtime");
    assert_eq!(inv.assembly_refs[0].public_key_or_token, "b03f5f7f11d50a3a");
    assert_eq!(inv.module_refs, vec!["craft"]);
    assert_eq!(inv.manifest_resources[0].name, "Sample.Strings.resources");
    assert_eq!(inv.manifest_resources[0].size, Some(5));
    assert_eq!(inv.target_frameworks, vec![fx::TFM]);
    assert_eq!(inv.assembly_attributes[0].named_args["FrameworkDisplayName"], ".NET 8.0");
    assert_eq!(inv.classification.dotnet_family, "dotnet-core");
    assert_eq!(inv.classification.implementation, "il-only");
    assert_eq!(inv.classification.dotnet_arch, "anycpu");
    assert_eq!(inv.row_counts["MethodDef"], 7);
    assert!(inv.module.as_ref().unwrap()["mvid"].as_str().unwrap().starts_with("11111111-1111"));
    assert!(inv.warnings.is_empty(), "{:?}", inv.warnings);
}

#[test]
fn members_signatures_bodies_and_calls() {
    let bytes = fx::managed_assembly(1);
    let a = open(&bytes).unwrap();
    let m = members(&a, &MemberOptions { include_il: true, max_instructions: 10_000, ..Default::default() });
    assert_eq!(m.total_types, 4);
    let calc = m.types.iter().find(|t| t.full_name == "Sample.Calculator").unwrap();
    assert_eq!(calc.kind, "class");
    assert_eq!(calc.extends.as_deref(), Some("object"));
    assert_eq!(calc.fields[0].name, "_total");
    assert_eq!(calc.fields[0].ty, "int");
    let add = calc.methods.iter().find(|x| x.name == "Add").unwrap();
    assert_eq!(add.signature, "public int Add(int a, int b)");
    assert_eq!(add.key, "Sample.Calculator::Add(int, int):int");
    let body = add.body.as_ref().unwrap();
    assert_eq!((body.header, body.code_size, body.instruction_count), ("tiny", 4, 4));
    assert_eq!(body.il.as_ref().unwrap()[2], "IL_0002: add");
    let acc = calc.methods.iter().find(|x| x.name == "Accumulate").unwrap();
    let b = acc.body.as_ref().unwrap();
    assert_eq!(b.header, "fat");
    assert!(b.init_locals);
    assert_eq!(b.locals, vec!["int"]);
    assert_eq!(b.exception_clauses.len(), 1);
    assert_eq!(b.exception_clauses[0].kind, "finally");
    assert_eq!(b.strings, vec!["hi"]);
    let targets: Vec<&str> = b.calls.iter().map(|c| c.target.as_str()).collect();
    assert_eq!(targets, vec!["System.Console::WriteLine(string)", "Sample.Calculator::Add(int, int)"]);
    assert_eq!(b.field_accesses.len(), 2);
    assert_eq!(b.field_accesses[0].target, "Sample.Calculator::_total");
    assert!(b.decode_issue.is_none());
    let id = calc.methods.iter().find(|x| x.name == "Identity").unwrap();
    assert_eq!(id.signature, "public static T Identity<T>(T value)");
    let ctor = calc.methods.iter().find(|x| x.name == ".ctor").unwrap();
    assert_eq!(ctor.signature, "public Calculator()");
    assert_eq!(ctor.body.as_ref().unwrap().calls[0].target, "object::.ctor()");
    let opts = m.types.iter().find(|t| t.name == "Options").unwrap();
    assert_eq!(opts.full_name, "Sample.Calculator/Options");
    assert_eq!(opts.enclosing_type.as_deref(), Some("Sample.Calculator"));
    let nm = m.types.iter().find(|t| t.name == "NativeMethods").unwrap();
    assert_eq!(nm.modifiers, vec!["static"]);
    // Filter.
    let f = members(&a, &MemberOptions { type_filter: Some(vec!["NativeMethods".into()]), ..Default::default() });
    assert_eq!(f.types.len(), 1);
}

#[test]
fn normalized_hash_tracks_code_not_layout() {
    let a1 = fx::managed_assembly(1);
    let a2 = fx::managed_assembly(2);
    let m1 = members(&open(&a1).unwrap(), &MemberOptions::default());
    let m2 = members(&open(&a2).unwrap(), &MemberOptions::default());
    let find = |m: &Members, n: &str| m.types.iter().flat_map(|t| t.methods.iter()).find(|x| x.name == n).cloned().unwrap();
    let h = |m: &MethodInfo| m.body.as_ref().unwrap().il_shape_hash.clone();
    assert_ne!(h(&find(&m1, "Add")), h(&find(&m2, "Add")));
    assert_eq!(h(&find(&m1, "Identity")), h(&find(&m2, "Identity")));
}

#[test]
fn native_boundaries_of_the_sample() {
    let bytes = fx::managed_assembly(1);
    let nb = native_boundaries(&open(&bytes).unwrap());
    assert_eq!(nb.pinvokes.len(), 2);
    let h = &nb.pinvokes[0];
    assert_eq!((h.module.as_str(), h.entry_point.as_str(), h.method.as_str()), ("craft", "helper", "helper"));
    assert!(h.set_last_error && h.preserve_sig);
    assert_eq!(h.calling_convention, "winapi");
    let m = &nb.pinvokes[1];
    assert_eq!((m.entry_point.as_str(), m.charset), ("missing_fn", "ansi"));
    assert!(m.explicit_entry_point);
    assert_eq!(nb.internal_calls.len(), 1);
    assert_eq!(nb.internal_calls[0].method, "GetTicks");
    assert!(nb.il_only);
}

#[test]
fn hostile_inputs_never_panic() {
    let sample = fx::managed_assembly(1);
    let mut inputs = craft_anything_testkit::mutations(&sample);
    for len in 0..sample.len().min(4096) {
        inputs.push(sample[..len].to_vec());
    }
    for seed in 0..64 {
        let mut n = craft_anything_testkit::noise(seed, 2048);
        n[0] = b'M';
        n[1] = b'Z';
        inputs.push(n);
    }
    // Corrupt every byte of the metadata and bodies region one at a time.
    for i in (0x200..sample.len()).step_by(3) {
        let mut m = sample.clone();
        m[i] ^= 0xa5;
        inputs.push(m);
    }
    for input in &inputs {
        if let Ok(a) = open(input) {
            let _ = inventory(&a);
            let _ = members(&a, &MemberOptions { include_il: true, max_instructions: 1000, ..Default::default() });
            let _ = native_boundaries(&a);
        }
    }
    assert!(open(b"not a pe").is_err());
}

#[test]
fn reconstruction_reconciles_against_metadata() {
    let bytes = fx::managed_assembly(1);
    let m = members(&open(&bytes).unwrap(), &MemberOptions { skip_bodies: true, ..Default::default() });
    let scan = csharp::scan(fx::RECONSTRUCTION_CS);
    let r = csharp::reconcile(&m, &scan);
    let names = |v: &[csharp::MemberMatch]| v.iter().map(|x| x.name.clone()).collect::<Vec<_>>();
    assert_eq!(names(&r.signature_mismatch), vec!["Add"], "{r:#?}");
    assert_eq!(names(&r.extra), vec!["Reset"]);
    assert!(r.missing.is_empty(), "{:?}", r.missing);
    for n in ["Accumulate", "Identity", ".ctor", "_total", "Verbose", "helper", "MissingFn", "GetTicks"] {
        assert!(names(&r.matched).contains(&n.to_string()), "{n} not matched: {r:#?}");
    }
    assert_eq!(r.matched_types, 3);
    assert!(r.missing_types.is_empty() && r.extra_types.is_empty(), "{r:#?}");
}

#[test]
fn wide_heaps_and_extra_data_read_the_same() {
    let narrow = fx::managed_assembly(1);
    let wide = fx::managed_assembly_wide_heaps(1);
    let (a, b) = (open(&narrow).unwrap(), open(&wide).unwrap());
    assert_eq!(b.md.heap_sizes, 0x47);
    let (ma, mb) = (members(&a, &MemberOptions::default()), members(&b, &MemberOptions::default()));
    assert_eq!(serde_json::to_value(&ma.types).unwrap(), serde_json::to_value(&mb.types).unwrap());
    assert_eq!(inventory(&b).target_frameworks, vec![fx::TFM]);
    for m in craft_anything_testkit::mutations(&wide) {
        if let Ok(x) = open(&m) {
            let _ = members(&x, &MemberOptions::default());
            let _ = inventory(&x);
        }
    }
}

#[test]
fn uncompressed_stream_with_pointer_tables() {
    let a = fx::managed_assembly(1);
    let b = fx::managed_assembly_with_ptr_tables(1);
    let (x, y) = (open(&a).unwrap(), open(&b).unwrap());
    assert_eq!(y.md.tables_stream, "#-");
    assert_eq!(y.md.rows(meta::t::METHOD_PTR), 7);
    let (mx, my) = (members(&x, &MemberOptions::default()), members(&y, &MemberOptions::default()));
    assert_eq!(serde_json::to_value(&mx.types).unwrap(), serde_json::to_value(&my.types).unwrap());
}
