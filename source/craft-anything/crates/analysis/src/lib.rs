//! Analyzers that turn parsed targets into evidence for Craft Anything.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod function_match;
pub mod java_decompile;
pub mod js_app;
pub mod js_compare;
pub mod js_inventory;
pub mod js_ledger;
pub mod js_projection;
pub mod js_source;
pub mod js_trace;
pub mod native;
pub mod standin;
pub mod web_har;
pub mod web_scripts;
