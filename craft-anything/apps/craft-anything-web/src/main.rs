//! Craft Anything in the browser: a small viewer that tells you what a file is.
//!
//! It runs only the wasm-safe crates (formats, analysis, evidence), entirely in the page: the file
//! never leaves the browser. Native programs (ELF, PE, Mach-O, DOS) get the same plain-English
//! triage as the desktop app's `triage_binary`; other files are identified by their signature. The
//! desktop app does everything else (disassembly, JavaScript apps, Android, devices, AI).
//!
//! Build with `trunk build --release` from this directory; the site lands in `dist/web`.
//! URL query flag: `?webgl` forces the WebGL2 backend instead of WebGPU.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]
// The viewer and triage only run in the browser; natively they're compiled (and tested) but unused.
#![cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]

mod triage;
mod viewer;
#[cfg(target_arch = "wasm32")]
mod web;

#[cfg(target_arch = "wasm32")]
fn main() {
    web::start();
}

#[cfg(not(target_arch = "wasm32"))]
fn main() {
    eprintln!("craft-anything-web only runs in the browser: build it with `trunk build --release` in apps/craft-anything-web");
}
