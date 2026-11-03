//! Windows only: mark `craft-anything-cli.exe` DPI-aware (an application manifest), so window
//! pictures (`native_window_capture`) and screen coordinates are in real pixels at any display
//! scaling. On every other target this does nothing. A missing resource compiler is a warning,
//! unless `CRAFT_ANYTHING_REQUIRE_WINRES=1` (the release workflow) makes it an error.

const MANIFEST: &str = r#"<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
    </windowsSettings>
  </application>
</assembly>"#;

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-env-changed=CRAFT_ANYTHING_REQUIRE_WINRES");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("windows") {
        return;
    }
    let mut res = winresource::WindowsResource::new();
    res.set_manifest(MANIFEST).set("OriginalFilename", "craft-anything-cli.exe").set("InternalName", "craft-anything-cli");
    if let Err(e) = res.compile() {
        if std::env::var_os("CRAFT_ANYTHING_REQUIRE_WINRES").is_some() {
            println!("cargo::error=embedding Windows resources failed: {e}");
            return;
        }
        println!("cargo:warning=craft-anything-cli.exe built without its DPI-aware manifest: {e}");
    }
}
