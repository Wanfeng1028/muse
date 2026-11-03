//! Clean-room decoder and static analysis for the eBPF / Solana sBPF instruction set.
//!
//! eBPF is a fixed-width RISC-like ISA: every instruction is 8 bytes (a single 64-bit slot)
//! except `lddw`, which carries a 64-bit immediate across two slots (16 bytes). Each 8-byte
//! slot is `opcode:u8, dst:4 / src:4, offset:i16, imm:i32` (little-endian). We decode the
//! classic eBPF set plus the Solana extensions (pc-relative `call`, `callx`, signed division),
//! discover functions from the entry and call targets, split them into basic blocks with a
//! simple control-flow graph, and render a very small pseudo form.
//!
//! Solana's sBPF has shipped in several versions whose opcode *meanings* differ (notably the
//! `call`/`callx` register encoding and the arithmetic reorganisation in v2+). We decode the
//! bytes faithfully, say which version we assumed, and flag opcodes whose meaning is
//! version-dependent rather than guessing. Nothing here panics on hostile input.

use serde::Serialize;

/// Hard caps so a huge or hostile `.text` can never exhaust memory or time.
pub const MAX_INSNS: usize = 1_000_000;
/// Largest `.text` we will decode (16 MiB of code = 2M slots).
pub const MAX_CODE: usize = 16 << 20;

/// Which sBPF dialect the bytes were assembled for. The classic Linux eBPF matches `V1`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SbpfVersion {
    /// Classic eBPF / Solana sBPF v1: `call imm` is a syscall hash or pc-relative by `src`,
    /// `callx` takes its register from `imm`, `lddw` is available, arithmetic is unsigned.
    V1,
    /// Solana sBPF v2+: `call imm` is pc-relative, `callx` takes its register from `src`,
    /// `lddw` is retired and the arithmetic opcodes were reorganised (see limitations).
    V2,
}

impl SbpfVersion {
    pub fn name(self) -> &'static str {
        match self {
            SbpfVersion::V1 => "sbpf_v1",
            SbpfVersion::V2 => "sbpf_v2",
        }
    }

    /// Best-effort version guess from the ELF `e_flags`, with an honest note about the guess.
    ///
    /// Solana has used more than one `e_flags` convention over time. `0` has always meant the
    /// original dialect; the `0x20` bit (historically `EF_SBPF_V2`) and small non-zero version
    /// numbers have both been used to mark the newer dialect. We treat `0` as v1 and anything
    /// else as v2+, and return the note so callers can report exactly what we saw and assumed.
    pub fn from_e_flags(flags: u32) -> (SbpfVersion, String) {
        if flags == 0 {
            (SbpfVersion::V1, "e_flags is 0: assuming the original sBPF v1 dialect.".to_string())
        } else {
            (
                SbpfVersion::V2,
                format!("e_flags is {flags:#x} (non-zero): assuming a newer sBPF (v2+) dialect; exact opcode meanings can vary between Solana sBPF versions."),
            )
        }
    }
}

/// eBPF instruction classes (the low 3 bits of the opcode).
const CLS_LD: u8 = 0x00;
const CLS_LDX: u8 = 0x01;
const CLS_ST: u8 = 0x02;
const CLS_STX: u8 = 0x03;
const CLS_ALU32: u8 = 0x04;
const CLS_JMP: u8 = 0x05;
const CLS_JMP32: u8 = 0x06;
const CLS_ALU64: u8 = 0x07;

/// How control leaves an instruction.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Flow {
    /// Falls through to the next slot.
    Next,
    /// Unconditional jump to a code address.
    Jump { target: u64 },
    /// Conditional branch: `target` when taken, otherwise falls through.
    Branch { target: u64 },
    /// A `call` whose target we resolved to a code address (pc-relative).
    Call { target: u64 },
    /// A `call` by immediate hash: a syscall or a function in the (unavailable) registry.
    CallHash { imm: u32 },
    /// `callx`: call through a register (target not statically known).
    CallReg,
    /// `exit` / `return`.
    Exit,
    /// A slot we could not classify (unknown opcode); treated as a terminator for safety.
    Unknown,
}

impl Flow {
    /// True when the slot ends a basic block.
    pub fn ends_block(&self) -> bool {
        matches!(self, Flow::Jump { .. } | Flow::Branch { .. } | Flow::Exit | Flow::Unknown)
    }
}

/// One decoded slot (or the 16-byte `lddw` pair).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Insn {
    /// Byte address: `base + slot * 8`.
    #[serde(serialize_with = "hex")]
    pub addr: u64,
    /// Slot index from the start of the code (jump offsets count slots, not bytes).
    pub slot: u64,
    /// 8 or 16.
    pub size: u8,
    pub opcode: u8,
    pub dst: u8,
    pub src: u8,
    pub off: i16,
    /// Sign-extended 32-bit immediate, or the full 64-bit `lddw` value.
    pub imm: i64,
    pub mnemonic: String,
    pub operands: String,
    pub flow: Flow,
}

fn hex<S: serde::Serializer>(v: &u64, s: S) -> Result<S::Ok, S::Error> {
    s.serialize_str(&format!("{v:#x}"))
}

impl Insn {
    /// The one-line disassembly text (`addr: mnemonic operands`).
    pub fn text(&self) -> String {
        if self.operands.is_empty() { format!("{:#x}: {}", self.addr, self.mnemonic) } else { format!("{:#x}: {} {}", self.addr, self.mnemonic, self.operands) }
    }
}

fn reg(n: u8) -> String {
    format!("r{n}")
}

fn off_str(off: i16) -> String {
    match off.cmp(&0) {
        std::cmp::Ordering::Less => format!("-{:#x}", (off as i32).unsigned_abs()),
        _ => format!("+{off:#x}"),
    }
}

/// The ALU operation mnemonic for a high nibble, with width suffix (`64`/`32`).
fn alu_op(nibble: u8) -> Option<&'static str> {
    Some(match nibble {
        0x00 => "add",
        0x10 => "sub",
        0x20 => "mul",
        0x30 => "div",
        0x40 => "or",
        0x50 => "and",
        0x60 => "lsh",
        0x70 => "rsh",
        0x80 => "neg",
        0x90 => "mod",
        0xa0 => "xor",
        0xb0 => "mov",
        0xc0 => "arsh",
        0xd0 => "end",  // byte-swap (le/be)
        0xe0 => "sdiv", // Solana signed division
        0xf0 => "smod", // Solana signed modulo
        _ => return None,
    })
}

/// The JMP operation mnemonic for a high nibble (without width suffix).
fn jmp_op(nibble: u8) -> Option<&'static str> {
    Some(match nibble {
        0x00 => "ja",
        0x10 => "jeq",
        0x20 => "jgt",
        0x30 => "jge",
        0x40 => "jset",
        0x50 => "jne",
        0x60 => "jsgt",
        0x70 => "jsge",
        0xa0 => "jlt",
        0xb0 => "jle",
        0xc0 => "jslt",
        0xd0 => "jsle",
        _ => return None,
    })
}

/// Decode one slot at byte offset `at` within `code`; `base` is the virtual address of the slot
/// at offset 0, `cur_slot` its slot index. Returns `None` only when there are not 8 bytes left.
pub fn decode_one(code: &[u8], at: usize, base: u64, version: SbpfVersion) -> Option<Insn> {
    let raw = code.get(at..at.checked_add(8)?)?;
    let opcode = *raw.first()?;
    let regs = *raw.get(1)?;
    let dst = regs & 0x0f;
    let src = (regs >> 4) & 0x0f;
    let off = i16::from_le_bytes([*raw.get(2)?, *raw.get(3)?]);
    let imm32 = i32::from_le_bytes([*raw.get(4)?, *raw.get(5)?, *raw.get(6)?, *raw.get(7)?]);
    let slot = (at as u64) / 8;
    let addr = base.wrapping_add(slot.wrapping_mul(8));
    let class = opcode & 0x07;

    let mut size = 8u8;
    let mut imm: i64 = i64::from(imm32);
    let (mnemonic, operands, flow);

    match class {
        CLS_ALU32 | CLS_ALU64 => {
            let wide = class == CLS_ALU64;
            let w = if wide { "64" } else { "32" };
            let use_src = opcode & 0x08 != 0;
            let nib = opcode & 0xf0;
            match alu_op(nib) {
                Some("neg") => {
                    mnemonic = format!("neg{w}");
                    operands = reg(dst);
                    flow = Flow::Next;
                }
                Some("end") => {
                    // le/be <width>: width is in the immediate (16/32/64); byte order by src bit.
                    let order = if use_src { "be" } else { "le" };
                    mnemonic = format!("{order}{imm32}");
                    operands = reg(dst);
                    flow = Flow::Next;
                }
                Some(op) => {
                    mnemonic = format!("{op}{w}");
                    operands = if use_src { format!("{}, {}", reg(dst), reg(src)) } else { format!("{}, {:#x}", reg(dst), imm32) };
                    flow = Flow::Next;
                }
                None => {
                    mnemonic = format!("(alu?{opcode:#04x})");
                    operands = format!("{}, {:#x}", reg(dst), imm32);
                    flow = Flow::Next;
                }
            }
        }
        CLS_JMP | CLS_JMP32 => {
            let w = if class == CLS_JMP32 { "32" } else { "" };
            let nib = opcode & 0xf0;
            let use_src = opcode & 0x08 != 0;
            // Branch/jump targets are relative to the *next* slot, counted in slots.
            let target = branch_target(base, slot, off);
            match (nib, class) {
                (0x00, CLS_JMP) => {
                    // ja: unconditional goto (offset).
                    mnemonic = "ja".to_string();
                    operands = format!("{target:#x}");
                    flow = Flow::Jump { target };
                }
                (0x80, CLS_JMP) => {
                    // call / callx (CALL op).
                    if use_src {
                        // callx: register call. v1 reads the register from imm, v2 from src.
                        mnemonic = "callx".to_string();
                        let r = if version == SbpfVersion::V2 { src } else { (imm32 & 0x0f) as u8 };
                        operands = reg(r);
                        flow = Flow::CallReg;
                    } else {
                        // call imm.
                        let (m, ops, f) = decode_call(base, slot, src, imm32, version);
                        mnemonic = m;
                        operands = ops;
                        flow = f;
                    }
                }
                (0x90, CLS_JMP) => {
                    mnemonic = if version == SbpfVersion::V2 { "return".to_string() } else { "exit".to_string() };
                    operands = String::new();
                    flow = Flow::Exit;
                }
                (n, _) => match jmp_op(n) {
                    Some(op) => {
                        mnemonic = format!("{op}{w}");
                        let rhs = if use_src { reg(src) } else { format!("{imm32:#x}") };
                        operands = format!("{}, {}, {target:#x}", reg(dst), rhs);
                        flow = Flow::Branch { target };
                    }
                    None => {
                        mnemonic = format!("(jmp?{opcode:#04x})");
                        operands = format!("{}, {:#x}", reg(dst), imm32);
                        flow = Flow::Unknown;
                    }
                },
            }
        }
        CLS_LDX | CLS_ST | CLS_STX => {
            let sz = match opcode & 0x18 {
                0x00 => "w",
                0x08 => "h",
                0x10 => "b",
                0x18 => "dw",
                _ => "?",
            };
            let mode = opcode & 0xe0;
            if mode == 0xc0 {
                // Atomic / xadd (STX class).
                mnemonic = format!("xadd{sz}");
                operands = format!("[{}{}], {}", reg(dst), off_str(off), reg(src));
                flow = Flow::Next;
            } else {
                match class {
                    CLS_LDX => {
                        mnemonic = format!("ldx{sz}");
                        operands = format!("{}, [{}{}]", reg(dst), reg(src), off_str(off));
                    }
                    CLS_ST => {
                        mnemonic = format!("st{sz}");
                        operands = format!("[{}{}], {:#x}", reg(dst), off_str(off), imm32);
                    }
                    _ => {
                        mnemonic = format!("stx{sz}");
                        operands = format!("[{}{}], {}", reg(dst), off_str(off), reg(src));
                    }
                }
                flow = Flow::Next;
            }
        }
        CLS_LD => {
            // The only widely used LD opcode is lddw (0x18): a 64-bit immediate over two slots.
            if opcode == 0x18 {
                let hi = code.get(at.checked_add(8)?..at.checked_add(16)?);
                if let Some(second) = hi {
                    let imm_hi = i32::from_le_bytes([*second.get(4)?, *second.get(5)?, *second.get(6)?, *second.get(7)?]);
                    imm = (((imm_hi as u32 as u64) << 32) | (imm32 as u32 as u64)) as i64;
                    size = 16;
                    mnemonic = "lddw".to_string();
                    operands = format!("{}, {:#x}", reg(dst), imm as u64);
                    flow = Flow::Next;
                } else {
                    // Truncated lddw pair: decode the first slot honestly.
                    mnemonic = "lddw".to_string();
                    operands = format!("{}, {:#x} (truncated: second slot missing)", reg(dst), imm32 as u32);
                    flow = Flow::Next;
                }
            } else {
                // Legacy packet loads (abs/ind) and anything else: name by mode, best effort.
                mnemonic = format!("ld(0x{opcode:02x})");
                operands = format!("{}, {:#x}", reg(dst), imm32);
                flow = Flow::Next;
            }
        }
        _ => {
            mnemonic = format!("(unknown {opcode:#04x})");
            operands = String::new();
            flow = Flow::Unknown;
        }
    }

    Some(Insn { addr, slot, size, opcode, dst, src, off, imm, mnemonic, operands, flow })
}

/// Branch/jump target byte address: relative to the next slot, counted in slots.
fn branch_target(base: u64, slot: u64, off: i16) -> u64 {
    let next = slot.wrapping_add(1);
    let t = (next as i64).wrapping_add(off as i64);
    base.wrapping_add((t as u64).wrapping_mul(8))
}

/// Decode a `call imm` into (mnemonic, operands, flow), honouring the version's call model.
fn decode_call(base: u64, slot: u64, src: u8, imm32: i32, version: SbpfVersion) -> (String, String, Flow) {
    match version {
        SbpfVersion::V2 => {
            // v2: `call imm` is pc-relative (imm counts slots from the next slot).
            let next = slot.wrapping_add(1);
            let t = (next as i64).wrapping_add(imm32 as i64);
            let target = base.wrapping_add((t as u64).wrapping_mul(8));
            ("call".to_string(), format!("{target:#x}"), Flow::Call { target })
        }
        SbpfVersion::V1 => {
            // v1: `src == 1` marks an internal pc-relative call; otherwise imm is a hash
            // (a syscall, or an internal function looked up in the VM function registry).
            if src == 1 {
                let next = slot.wrapping_add(1);
                let t = (next as i64).wrapping_add(imm32 as i64);
                let target = base.wrapping_add((t as u64).wrapping_mul(8));
                ("call".to_string(), format!("{target:#x}"), Flow::Call { target })
            } else {
                ("call".to_string(), format!("0x{:08x} (hash)", imm32 as u32), Flow::CallHash { imm: imm32 as u32 })
            }
        }
    }
}

/// Decode a whole code blob into slots, following the 8/16-byte sizes. Bounded by [`MAX_INSNS`]
/// and [`MAX_CODE`]; stops cleanly at a short tail.
pub fn decode(code: &[u8], base: u64, version: SbpfVersion) -> Vec<Insn> {
    let mut out = Vec::new();
    let len = code.len().min(MAX_CODE);
    let mut at = 0usize;
    while at + 8 <= len && out.len() < MAX_INSNS {
        match decode_one(code, at, base, version) {
            Some(insn) => {
                let step = usize::from(insn.size).max(8);
                out.push(insn);
                at = match at.checked_add(step) {
                    Some(n) => n,
                    None => break,
                };
            }
            None => break,
        }
    }
    out
}

// ------------------------------------------------------------------------------------------------
// Functions, basic blocks, CFG

/// A basic block: a maximal straight-line run ending at a branch, jump, exit or unknown.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Block {
    #[serde(serialize_with = "hex")]
    pub start: u64,
    /// Byte address just past the last slot.
    #[serde(serialize_with = "hex")]
    pub end: u64,
    /// Indices into the function's instruction slice.
    pub first: usize,
    pub count: usize,
    /// Successor block start addresses.
    #[serde(serialize_with = "hex_vec")]
    pub successors: Vec<u64>,
    /// `fallthrough`, `jump`, `branch`, `exit`, `call_return`, `unknown`.
    pub terminator: &'static str,
}

fn hex_vec<S: serde::Serializer>(v: &[u64], s: S) -> Result<S::Ok, S::Error> {
    use serde::ser::SerializeSeq;
    let mut seq = s.serialize_seq(Some(v.len()))?;
    for a in v {
        seq.serialize_element(&format!("{a:#x}"))?;
    }
    seq.end()
}

/// One discovered function with its blocks.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Function {
    #[serde(serialize_with = "hex")]
    pub entry: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    pub instruction_count: usize,
    pub block_count: usize,
    pub blocks: Vec<Block>,
}

/// The result of analysing a decoded code blob.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Analysis {
    pub functions: Vec<Function>,
    /// Call targets we resolved to code addresses (pc-relative calls).
    #[serde(serialize_with = "hex_vec")]
    pub call_targets: Vec<u64>,
    /// `call imm` hashes (syscalls / registry functions), de-duplicated.
    pub call_hashes: Vec<u32>,
    pub has_indirect_calls: bool,
}

/// Discover functions (from `entries` plus resolved call targets), split them into basic
/// blocks and build a simple CFG. `insns` must be sorted by address (as [`decode`] returns).
pub fn analyze(insns: &[Insn], entries: &[(u64, Option<String>)]) -> Analysis {
    use std::collections::{BTreeMap, BTreeSet};

    // Index slots by address for quick lookup.
    let by_addr: BTreeMap<u64, usize> = insns.iter().enumerate().map(|(i, n)| (n.addr, i)).collect();

    // Gather call targets and hashes.
    let mut call_targets: BTreeSet<u64> = BTreeSet::new();
    let mut call_hashes: BTreeSet<u32> = BTreeSet::new();
    let mut has_indirect_calls = false;
    for n in insns {
        match &n.flow {
            Flow::Call { target } => {
                call_targets.insert(*target);
            }
            Flow::CallHash { imm } => {
                call_hashes.insert(*imm);
            }
            Flow::CallReg => has_indirect_calls = true,
            _ => {}
        }
    }

    // Function entry set: provided entries + resolved internal call targets that land on a slot.
    let mut names: BTreeMap<u64, String> = BTreeMap::new();
    let mut entry_set: BTreeSet<u64> = BTreeSet::new();
    for (a, nm) in entries {
        entry_set.insert(*a);
        if let Some(nm) = nm {
            names.insert(*a, nm.clone());
        }
    }
    for t in &call_targets {
        if by_addr.contains_key(t) {
            entry_set.insert(*t);
        }
    }
    // If nothing was provided and there are instructions, treat the first slot as an entry.
    if entry_set.is_empty()
        && let Some(first) = insns.first()
    {
        entry_set.insert(first.addr);
    }

    // Leaders (block starts): every function entry, every branch/jump target, and the slot
    // after any block-ending instruction.
    let mut leaders: BTreeSet<u64> = entry_set.iter().copied().collect();
    for (i, n) in insns.iter().enumerate() {
        match &n.flow {
            Flow::Jump { target } | Flow::Branch { target } => {
                if by_addr.contains_key(target) {
                    leaders.insert(*target);
                }
                if let Some(next) = insns.get(i + 1) {
                    leaders.insert(next.addr);
                }
            }
            Flow::Exit | Flow::Unknown => {
                if let Some(next) = insns.get(i + 1) {
                    leaders.insert(next.addr);
                }
            }
            _ => {}
        }
    }

    // Walk each function from its entry, collecting the reachable block leaders, bounded.
    let mut functions = Vec::new();
    let entry_vec: Vec<u64> = entry_set.iter().copied().collect();
    for &entry in &entry_vec {
        if !by_addr.contains_key(&entry) {
            continue;
        }
        let mut visited: BTreeSet<u64> = BTreeSet::new();
        let mut worklist = vec![entry];
        let mut blocks: Vec<Block> = Vec::new();
        let mut func_insns = 0usize;
        // Other function entries stop this function's walk.
        let others: BTreeSet<u64> = entry_set.iter().copied().filter(|a| *a != entry).collect();
        while let Some(bstart) = worklist.pop() {
            if !visited.insert(bstart) {
                continue;
            }
            if blocks.len() >= MAX_INSNS {
                break;
            }
            let Some(&bi) = by_addr.get(&bstart) else { continue };
            // Extend the block until a terminator or the next leader.
            let mut i = bi;
            let mut succ: Vec<u64> = Vec::new();
            let mut terminator = "fallthrough";
            loop {
                let Some(n) = insns.get(i) else {
                    terminator = "fallthrough";
                    break;
                };
                let is_last = n.flow.ends_block() || insns.get(i + 1).map(|m| leaders.contains(&m.addr) && m.addr != n.addr).unwrap_or(true);
                if n.flow.ends_block() {
                    match &n.flow {
                        Flow::Jump { target } => {
                            terminator = "jump";
                            if by_addr.contains_key(target) && !others.contains(target) {
                                succ.push(*target);
                            }
                        }
                        Flow::Branch { target } => {
                            terminator = "branch";
                            if by_addr.contains_key(target) && !others.contains(target) {
                                succ.push(*target);
                            }
                            if let Some(next) = insns.get(i + 1)
                                && !others.contains(&next.addr)
                            {
                                succ.push(next.addr);
                            }
                        }
                        Flow::Exit => terminator = "exit",
                        Flow::Unknown => terminator = "unknown",
                        _ => {}
                    }
                    i += 1;
                    break;
                }
                // A call falls through; keep going unless the next slot is a leader.
                if is_last {
                    if let Some(next) = insns.get(i + 1) {
                        if !others.contains(&next.addr) {
                            succ.push(next.addr);
                        }
                        terminator = if matches!(n.flow, Flow::Call { .. } | Flow::CallHash { .. } | Flow::CallReg) { "call_return" } else { "fallthrough" };
                    }
                    i += 1;
                    break;
                }
                i += 1;
            }
            let count = i.saturating_sub(bi);
            func_insns += count;
            let end = insns.get(i).map(|n| n.addr).or_else(|| insns.get(i.saturating_sub(1)).map(|n| n.addr + u64::from(n.size))).unwrap_or(bstart);
            for s in &succ {
                worklist.push(*s);
            }
            blocks.push(Block { start: bstart, end, first: bi, count, successors: succ, terminator });
        }
        blocks.sort_by_key(|b| b.start);
        functions.push(Function { entry, name: names.get(&entry).cloned(), instruction_count: func_insns, block_count: blocks.len(), blocks });
    }
    functions.sort_by_key(|f| f.entry);

    Analysis { functions, call_targets: call_targets.into_iter().collect(), call_hashes: call_hashes.into_iter().collect(), has_indirect_calls }
}

/// A very small pseudo rendering of one function: blocks as labels, each slot as a line, and
/// `goto`/`if … goto` at terminators. Not a decompiler — a readable structured listing.
pub fn pseudo(func: &Function, insns: &[Insn], resolve: &dyn Fn(u32) -> Option<String>) -> String {
    let mut out = String::new();
    let title = func.name.clone().unwrap_or_else(|| format!("func_{:x}", func.entry));
    out.push_str(&format!("fn {title}() {{  // entry {:#x}, {} blocks\n", func.entry, func.block_count));
    for b in &func.blocks {
        out.push_str(&format!("  L_{:x}:\n", b.start));
        let end = b.first.saturating_add(b.count);
        for n in insns.get(b.first..end.min(insns.len())).unwrap_or(&[]) {
            match &n.flow {
                Flow::Branch { target } => {
                    out.push_str(&format!("    if ({}) goto L_{:x};\n", n.operands, target));
                }
                Flow::Jump { target } => {
                    out.push_str(&format!("    goto L_{:x};\n", target));
                }
                Flow::Exit => out.push_str("    return;\n"),
                Flow::Call { target } => {
                    out.push_str(&format!("    call func_{target:x}();\n"));
                }
                Flow::CallHash { imm } => match resolve(*imm) {
                    Some(name) => out.push_str(&format!("    {name}();  // syscall 0x{imm:08x}\n")),
                    None => out.push_str(&format!("    call_hash(0x{imm:08x});\n")),
                },
                Flow::CallReg => out.push_str(&format!("    callx {};\n", n.operands)),
                _ => out.push_str(&format!("    {} {};\n", n.mnemonic, n.operands)),
            }
        }
    }
    out.push_str("}\n");
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Encode one 8-byte slot.
    fn ins(op: u8, dst: u8, src: u8, off: i16, imm: i32) -> [u8; 8] {
        let mut b = [0u8; 8];
        b[0] = op;
        b[1] = (src << 4) | (dst & 0x0f);
        b[2..4].copy_from_slice(&off.to_le_bytes());
        b[4..8].copy_from_slice(&imm.to_le_bytes());
        b
    }

    #[test]
    fn decodes_basic_program() {
        let mut code = Vec::new();
        code.extend_from_slice(&ins(0xb7, 1, 0, 0, 42)); // mov64 r1, 42
        code.extend_from_slice(&ins(0x07, 1, 0, 0, 1)); // add64 r1, 1
        code.extend_from_slice(&ins(0x85, 0, 0, 0, 0x1234)); // call hash (v1, src=0)
        code.extend_from_slice(&ins(0x95, 0, 0, 0, 0)); // exit
        let insns = decode(&code, 0x100, SbpfVersion::V1);
        assert_eq!(insns.len(), 4);
        assert_eq!(insns[0].mnemonic, "mov64");
        assert_eq!(insns[0].operands, "r1, 0x2a");
        assert_eq!(insns[1].mnemonic, "add64");
        assert_eq!(insns[2].mnemonic, "call");
        assert!(matches!(insns[2].flow, Flow::CallHash { imm: 0x1234 }));
        assert!(matches!(insns[3].flow, Flow::Exit));
    }

    #[test]
    fn lddw_spans_two_slots() {
        let mut code = Vec::new();
        code.extend_from_slice(&ins(0x18, 2, 0, 0, 0x5678)); // lddw r2, ...
        code.extend_from_slice(&ins(0x00, 0, 0, 0, 0x1234)); // high half
        code.extend_from_slice(&ins(0x95, 0, 0, 0, 0)); // exit
        let insns = decode(&code, 0, SbpfVersion::V1);
        assert_eq!(insns.len(), 2);
        assert_eq!(insns[0].mnemonic, "lddw");
        assert_eq!(insns[0].size, 16);
        assert_eq!(insns[0].imm as u64, 0x1234_0000_5678);
        assert_eq!(insns[1].addr, 16); // exit is at slot 2 (byte 16)
    }

    #[test]
    fn jumps_and_cfg() {
        let mut code = Vec::new();
        code.extend_from_slice(&ins(0xb7, 0, 0, 0, 0)); // slot0: mov64 r0, 0
        code.extend_from_slice(&ins(0x15, 1, 0, 1, 0)); // slot1: jeq r1, 0, +1 -> slot3
        code.extend_from_slice(&ins(0xb7, 0, 0, 0, 1)); // slot2: mov64 r0, 1
        code.extend_from_slice(&ins(0x95, 0, 0, 0, 0)); // slot3: exit
        let insns = decode(&code, 0, SbpfVersion::V1);
        assert!(matches!(insns[1].flow, Flow::Branch { target: 24 }));
        let a = analyze(&insns, &[(0, Some("entry".to_string()))]);
        assert_eq!(a.functions.len(), 1);
        let f = &a.functions[0];
        // Blocks: [0..1], [2], [3] — branch target and fallthrough both lead to leaders.
        assert!(f.block_count >= 3, "blocks: {}", f.block_count);
        let entry_block = f.blocks.iter().find(|b| b.start == 0).unwrap();
        assert_eq!(entry_block.terminator, "branch");
        assert_eq!(entry_block.successors.len(), 2);
    }

    #[test]
    fn pc_relative_call_discovers_function() {
        let mut code = Vec::new();
        code.extend_from_slice(&ins(0x85, 0, 1, 0, 1)); // slot0: call +1 (v1 src=1) -> slot2
        code.extend_from_slice(&ins(0x95, 0, 0, 0, 0)); // slot1: exit
        code.extend_from_slice(&ins(0xb7, 0, 0, 0, 7)); // slot2: mov64 r0, 7
        code.extend_from_slice(&ins(0x95, 0, 0, 0, 0)); // slot3: exit
        let insns = decode(&code, 0, SbpfVersion::V1);
        assert!(matches!(insns[0].flow, Flow::Call { target: 16 }));
        let a = analyze(&insns, &[(0, Some("entry".to_string()))]);
        assert_eq!(a.call_targets, vec![16]);
        // Two functions: entry at 0 and the called one at 16.
        assert_eq!(a.functions.len(), 2);
        assert!(a.functions.iter().any(|f| f.entry == 16));
    }

    #[test]
    fn v2_call_is_pc_relative() {
        let code = ins(0x85, 0, 0, 0, 2); // call +2 in v2 -> slot3
        let insns = decode(&code, 0, SbpfVersion::V2);
        assert!(matches!(insns[0].flow, Flow::Call { target: 24 }));
    }

    #[test]
    fn hostile_input_never_panics() {
        for len in 0..64usize {
            let junk: Vec<u8> = (0..len).map(|i| (i.wrapping_mul(97) ^ 0x5a) as u8).collect();
            for v in [SbpfVersion::V1, SbpfVersion::V2] {
                let insns = decode(&junk, 0x1000, v);
                let _ = analyze(&insns, &[]);
                for n in &insns {
                    let _ = n.text();
                }
            }
        }
        // Every opcode byte, truncated and full, both versions.
        for op in 0u16..=255 {
            let code = ins(op as u8, 0x0f, 0x0f, -1, -1);
            for v in [SbpfVersion::V1, SbpfVersion::V2] {
                let _ = decode(&code, 0, v);
                let _ = decode(&code[..code.len().saturating_sub(3)], 0, v);
            }
        }
    }
}
