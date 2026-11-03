//! The app build scripts must fail the build (Cargo's `cargo::error` instruction) when Windows
//! resources are required. The single-colon `cargo:error=` form is ignored by Cargo as metadata.

use std::path::Path;

fn read(rel: &str) -> String {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(rel);
    std::fs::read_to_string(&path).unwrap_or_default()
}

#[test]
fn required_windows_resource_failure_uses_cargo_error_directive() {
    for rel in ["build.rs", "../craft-anything/build.rs"] {
        let src = read(rel);
        assert!(!src.is_empty(), "{rel} should be readable");
        assert!(!src.contains("cargo:error="), "{rel} emits the ignored single-colon error directive");
        assert!(src.contains("cargo::error="), "{rel} must emit cargo::error= when resources are required");
    }
}
