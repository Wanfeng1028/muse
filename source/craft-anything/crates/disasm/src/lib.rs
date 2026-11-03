//! Craft Anything's own native engine: decoding, functions, control flow, references, pseudo-C.
//!
//! [`Image`] wraps a parsed container and its bytes; [`Program::analyze`] discovers functions
//! (entry, symbols, exports, container function lists, call targets, code pointers, prologue
//! scan), splits them into basic blocks with jump-table recovery, and records cross-references,
//! string references and the call graph. [`pseudo`] lifts one function to structured pseudo-C
//! and [`dataflow`] builds a register def-use graph. Everything is bounded and cancellable, and
//! never panics on hostile input.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod arity;
pub mod dataflow;
pub mod decode;
pub mod image;
pub mod program;
pub mod pseudo;
/// eBPF / Solana sBPF decoding and static analysis (clean room, self-contained).
pub mod sbpf;

pub use decode::{ArmConsts, Cond, Flow, Insn, Kind, MemOp, Mode, Op, canonical_reg, decode};
pub use image::Image;
pub use program::{Block, CallSite, Callee, Function, JumpTable, Limits, ProgString, Program, SlotInfo, Stats, Term, Xref, XrefKind, slot_label};

/// Why the native engine stopped.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum DisasmError {
    #[error("{0}")]
    Format(craft_anything_formats::FormatError),
    #[error("not supported: {0}")]
    Unsupported(String),
    #[error("cancelled")]
    Cancelled,
}

/// Cancellation and progress for long analyses (the engine passes its cancel token through).
pub trait Control {
    fn cancelled(&self) -> bool {
        false
    }
    fn progress(&self, _fraction: f32, _message: &str) {}
}

/// A [`Control`] that never cancels and ignores progress.
#[derive(Debug, Clone, Copy, Default)]
pub struct NoControl;

impl Control for NoControl {}
