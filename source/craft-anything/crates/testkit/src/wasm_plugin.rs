//! WASM component plugins written out in WAT (no guest toolchain needed).

/// A plugin exporting `craft-anything:plugin/tools@0.1.0` with one tool, `echo`, whose `call`
/// answers `{"ok": <input>}`. With `spin`, `call` loops forever instead (to test the work limit).
pub fn echo_plugin_wat(spin: bool) -> String {
    let describe = r#"[{"name":"echo","title":"Echo","description":"Returns its input","input_schema":{"type":"object"}}]"#;
    component_wat("tools", "call", "input", describe, r#"{"ok":"#, spin)
}

/// A plugin exporting `craft-anything:plugin/checks@0.1.0` with one check, `looks_fine`, for
/// games, that asks for `.md` files and answers
/// `{"passed": <passed>, "similarity": 70, "summary": "…", "seen": <the build it was given>}`.
pub fn check_plugin_wat(passed: bool) -> String {
    let describe = r#"[{"name":"looks_fine","title":"Looks fine","description":"A stand-in check","kinds":["game"],"extensions":["md"]}]"#;
    let prefix = format!(r#"{{"passed":{passed},"similarity":70,"summary":"The stand-in check looked.","seen":"#);
    component_wat("checks", "run", "build", describe, &prefix, false)
}

/// A component exporting `craft-anything:plugin/<interface>@0.1.0` with `describe` (returns
/// `describe`) and `<func>(name, <param>)`, which answers `prefix + <param> + "}"` (or loops).
pub fn component_wat(interface: &str, func: &str, param: &str, describe: &str, prefix: &str, spin: bool) -> String {
    let body = if spin {
        "(loop $l (br $l)) (i32.const 0)".to_string()
    } else {
        format!(
            r#"
        ;; out = prefix + the second string + }}
        (local $out i32) (local $n i32)
        (local.set $n (i32.add (local.get 3) (i32.const {extra})))
        (local.set $out (call $alloc (local.get $n)))
        (memory.copy (local.get $out) (i32.const 1536) (i32.const {plen}))
        (memory.copy (i32.add (local.get $out) (i32.const {plen})) (local.get 2) (local.get 3))
        (i32.store8 (i32.add (local.get $out) (i32.add (local.get 3) (i32.const {plen}))) (i32.const 125))
        (i32.store (i32.const 1024) (local.get $out))
        (i32.store (i32.const 1028) (local.get $n))
        (i32.const 1024)"#,
            extra = prefix.len() + 1,
            plen = prefix.len(),
        )
    };
    let wat_str = |s: &str| s.replace('\\', "\\\\").replace('"', "\\\"");
    format!(
        r#"(component
  (core module $m
    (memory (export "memory") 1)
    (global $next (mut i32) (i32.const 4096))
    (data (i32.const 0) "{describe}")
    (data (i32.const 1536) "{prefix}")
    (func $alloc (param $n i32) (result i32) (local $p i32)
      (local.set $p (global.get $next))
      (global.set $next (i32.add (global.get $next) (local.get $n)))
      (if (i32.gt_u (global.get $next) (i32.mul (memory.size) (i32.const 65536)))
        (then (drop (memory.grow (i32.add (i32.const 16) (i32.shr_u (local.get $n) (i32.const 16)))))))
      (local.get $p))
    (func (export "cabi_realloc") (param i32 i32 i32 i32) (result i32) (call $alloc (local.get 3)))
    (func (export "describe") (result i32)
      (i32.store (i32.const 1024) (i32.const 0))
      (i32.store (i32.const 1028) (i32.const {describe_len}))
      (i32.const 1024))
    (func (export "{func}") (param i32 i32 i32 i32) (result i32) {body}))
  (core instance $i (instantiate $m))
  (func $describe (result string) (canon lift (core func $i "describe") (memory (core memory $i "memory"))))
  (func $f (param "name" string) (param "{param}" string) (result string)
    (canon lift (core func $i "{func}") (memory (core memory $i "memory")) (realloc (core func $i "cabi_realloc"))))
  (instance $x (export "describe" (func $describe)) (export "{func}" (func $f)))
  (export "craft-anything:plugin/{interface}@0.1.0" (instance $x)))"#,
        describe = wat_str(describe),
        prefix = wat_str(prefix),
        describe_len = describe.len(),
    )
}
