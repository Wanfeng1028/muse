//! .NET (ECMA-335) assemblies: a built-in reader for the PE/CLI header, metadata streams and all
//! 45 tables, signature blobs, method bodies and CIL. Pure and bounded; never panics on input.
//!
//! - [`open`] parses an assembly;
//! - [`inventory`], [`members`] and [`native_boundaries`] project it for tools.

pub mod cil;
pub mod csharp;
pub mod meta;
pub mod model;
pub mod pe;
pub mod sig;

pub use model::{
    Assembly, BodyInfo, Classification, CodeRef, FieldInfo, Inventory, MemberOptions, Members, MethodInfo, NativeBoundaries, PInvoke, Param, TypeInfo,
    inventory, members, native_boundaries, open,
};

#[cfg(test)]
mod tests;
