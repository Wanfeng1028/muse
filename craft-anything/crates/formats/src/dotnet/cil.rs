//! CIL: method body headers (tiny and fat), exception clauses, and an instruction decoder for
//! every one-byte and `0xFE`-prefixed opcode, plus a body hash that survives renames.

use crate::bytes::Reader;
use serde::Serialize;
use sha2::{Digest, Sha256};

/// Operand kinds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OperandKind {
    None,
    ShortI,
    I,
    I8,
    ShortR,
    R,
    ShortBr,
    Br,
    Switch,
    Method,
    Field,
    Type,
    Tok,
    String,
    Sig,
    ShortVar,
    Var,
}

impl OperandKind {
    fn size(self) -> usize {
        use OperandKind::*;
        match self {
            None => 0,
            ShortI | ShortBr | ShortVar => 1,
            Var => 2,
            I | ShortR | Br | Method | Field | Type | Tok | String | Sig => 4,
            I8 | R => 8,
            Switch => 4,
        }
    }

    pub fn name(self) -> &'static str {
        use OperandKind::*;
        match self {
            None => "none",
            ShortI => "short_i",
            I => "i",
            I8 => "i8",
            ShortR => "short_r",
            R => "r",
            ShortBr => "short_br",
            Br => "br",
            Switch => "switch",
            Method => "method",
            Field => "field",
            Type => "type",
            Tok => "tok",
            String => "string",
            Sig => "sig",
            ShortVar => "short_var",
            Var => "var",
        }
    }
}

use OperandKind as K;

/// One-byte opcodes (0x00..=0xE0).
const ONE: &[(u8, &str, OperandKind)] = &[
    (0x00, "nop", K::None),
    (0x01, "break", K::None),
    (0x02, "ldarg.0", K::None),
    (0x03, "ldarg.1", K::None),
    (0x04, "ldarg.2", K::None),
    (0x05, "ldarg.3", K::None),
    (0x06, "ldloc.0", K::None),
    (0x07, "ldloc.1", K::None),
    (0x08, "ldloc.2", K::None),
    (0x09, "ldloc.3", K::None),
    (0x0a, "stloc.0", K::None),
    (0x0b, "stloc.1", K::None),
    (0x0c, "stloc.2", K::None),
    (0x0d, "stloc.3", K::None),
    (0x0e, "ldarg.s", K::ShortVar),
    (0x0f, "ldarga.s", K::ShortVar),
    (0x10, "starg.s", K::ShortVar),
    (0x11, "ldloc.s", K::ShortVar),
    (0x12, "ldloca.s", K::ShortVar),
    (0x13, "stloc.s", K::ShortVar),
    (0x14, "ldnull", K::None),
    (0x15, "ldc.i4.m1", K::None),
    (0x16, "ldc.i4.0", K::None),
    (0x17, "ldc.i4.1", K::None),
    (0x18, "ldc.i4.2", K::None),
    (0x19, "ldc.i4.3", K::None),
    (0x1a, "ldc.i4.4", K::None),
    (0x1b, "ldc.i4.5", K::None),
    (0x1c, "ldc.i4.6", K::None),
    (0x1d, "ldc.i4.7", K::None),
    (0x1e, "ldc.i4.8", K::None),
    (0x1f, "ldc.i4.s", K::ShortI),
    (0x20, "ldc.i4", K::I),
    (0x21, "ldc.i8", K::I8),
    (0x22, "ldc.r4", K::ShortR),
    (0x23, "ldc.r8", K::R),
    (0x25, "dup", K::None),
    (0x26, "pop", K::None),
    (0x27, "jmp", K::Method),
    (0x28, "call", K::Method),
    (0x29, "calli", K::Sig),
    (0x2a, "ret", K::None),
    (0x2b, "br.s", K::ShortBr),
    (0x2c, "brfalse.s", K::ShortBr),
    (0x2d, "brtrue.s", K::ShortBr),
    (0x2e, "beq.s", K::ShortBr),
    (0x2f, "bge.s", K::ShortBr),
    (0x30, "bgt.s", K::ShortBr),
    (0x31, "ble.s", K::ShortBr),
    (0x32, "blt.s", K::ShortBr),
    (0x33, "bne.un.s", K::ShortBr),
    (0x34, "bge.un.s", K::ShortBr),
    (0x35, "bgt.un.s", K::ShortBr),
    (0x36, "ble.un.s", K::ShortBr),
    (0x37, "blt.un.s", K::ShortBr),
    (0x38, "br", K::Br),
    (0x39, "brfalse", K::Br),
    (0x3a, "brtrue", K::Br),
    (0x3b, "beq", K::Br),
    (0x3c, "bge", K::Br),
    (0x3d, "bgt", K::Br),
    (0x3e, "ble", K::Br),
    (0x3f, "blt", K::Br),
    (0x40, "bne.un", K::Br),
    (0x41, "bge.un", K::Br),
    (0x42, "bgt.un", K::Br),
    (0x43, "ble.un", K::Br),
    (0x44, "blt.un", K::Br),
    (0x45, "switch", K::Switch),
    (0x46, "ldind.i1", K::None),
    (0x47, "ldind.u1", K::None),
    (0x48, "ldind.i2", K::None),
    (0x49, "ldind.u2", K::None),
    (0x4a, "ldind.i4", K::None),
    (0x4b, "ldind.u4", K::None),
    (0x4c, "ldind.i8", K::None),
    (0x4d, "ldind.i", K::None),
    (0x4e, "ldind.r4", K::None),
    (0x4f, "ldind.r8", K::None),
    (0x50, "ldind.ref", K::None),
    (0x51, "stind.ref", K::None),
    (0x52, "stind.i1", K::None),
    (0x53, "stind.i2", K::None),
    (0x54, "stind.i4", K::None),
    (0x55, "stind.i8", K::None),
    (0x56, "stind.r4", K::None),
    (0x57, "stind.r8", K::None),
    (0x58, "add", K::None),
    (0x59, "sub", K::None),
    (0x5a, "mul", K::None),
    (0x5b, "div", K::None),
    (0x5c, "div.un", K::None),
    (0x5d, "rem", K::None),
    (0x5e, "rem.un", K::None),
    (0x5f, "and", K::None),
    (0x60, "or", K::None),
    (0x61, "xor", K::None),
    (0x62, "shl", K::None),
    (0x63, "shr", K::None),
    (0x64, "shr.un", K::None),
    (0x65, "neg", K::None),
    (0x66, "not", K::None),
    (0x67, "conv.i1", K::None),
    (0x68, "conv.i2", K::None),
    (0x69, "conv.i4", K::None),
    (0x6a, "conv.i8", K::None),
    (0x6b, "conv.r4", K::None),
    (0x6c, "conv.r8", K::None),
    (0x6d, "conv.u4", K::None),
    (0x6e, "conv.u8", K::None),
    (0x6f, "callvirt", K::Method),
    (0x70, "cpobj", K::Type),
    (0x71, "ldobj", K::Type),
    (0x72, "ldstr", K::String),
    (0x73, "newobj", K::Method),
    (0x74, "castclass", K::Type),
    (0x75, "isinst", K::Type),
    (0x76, "conv.r.un", K::None),
    (0x79, "unbox", K::Type),
    (0x7a, "throw", K::None),
    (0x7b, "ldfld", K::Field),
    (0x7c, "ldflda", K::Field),
    (0x7d, "stfld", K::Field),
    (0x7e, "ldsfld", K::Field),
    (0x7f, "ldsflda", K::Field),
    (0x80, "stsfld", K::Field),
    (0x81, "stobj", K::Type),
    (0x82, "conv.ovf.i1.un", K::None),
    (0x83, "conv.ovf.i2.un", K::None),
    (0x84, "conv.ovf.i4.un", K::None),
    (0x85, "conv.ovf.i8.un", K::None),
    (0x86, "conv.ovf.u1.un", K::None),
    (0x87, "conv.ovf.u2.un", K::None),
    (0x88, "conv.ovf.u4.un", K::None),
    (0x89, "conv.ovf.u8.un", K::None),
    (0x8a, "conv.ovf.i.un", K::None),
    (0x8b, "conv.ovf.u.un", K::None),
    (0x8c, "box", K::Type),
    (0x8d, "newarr", K::Type),
    (0x8e, "ldlen", K::None),
    (0x8f, "ldelema", K::Type),
    (0x90, "ldelem.i1", K::None),
    (0x91, "ldelem.u1", K::None),
    (0x92, "ldelem.i2", K::None),
    (0x93, "ldelem.u2", K::None),
    (0x94, "ldelem.i4", K::None),
    (0x95, "ldelem.u4", K::None),
    (0x96, "ldelem.i8", K::None),
    (0x97, "ldelem.i", K::None),
    (0x98, "ldelem.r4", K::None),
    (0x99, "ldelem.r8", K::None),
    (0x9a, "ldelem.ref", K::None),
    (0x9b, "stelem.i", K::None),
    (0x9c, "stelem.i1", K::None),
    (0x9d, "stelem.i2", K::None),
    (0x9e, "stelem.i4", K::None),
    (0x9f, "stelem.i8", K::None),
    (0xa0, "stelem.r4", K::None),
    (0xa1, "stelem.r8", K::None),
    (0xa2, "stelem.ref", K::None),
    (0xa3, "ldelem", K::Type),
    (0xa4, "stelem", K::Type),
    (0xa5, "unbox.any", K::Type),
    (0xb3, "conv.ovf.i1", K::None),
    (0xb4, "conv.ovf.u1", K::None),
    (0xb5, "conv.ovf.i2", K::None),
    (0xb6, "conv.ovf.u2", K::None),
    (0xb7, "conv.ovf.i4", K::None),
    (0xb8, "conv.ovf.u4", K::None),
    (0xb9, "conv.ovf.i8", K::None),
    (0xba, "conv.ovf.u8", K::None),
    (0xc2, "refanyval", K::Type),
    (0xc3, "ckfinite", K::None),
    (0xc6, "mkrefany", K::Type),
    (0xd0, "ldtoken", K::Tok),
    (0xd1, "conv.u2", K::None),
    (0xd2, "conv.u1", K::None),
    (0xd3, "conv.i", K::None),
    (0xd4, "conv.ovf.i", K::None),
    (0xd5, "conv.ovf.u", K::None),
    (0xd6, "add.ovf", K::None),
    (0xd7, "add.ovf.un", K::None),
    (0xd8, "mul.ovf", K::None),
    (0xd9, "mul.ovf.un", K::None),
    (0xda, "sub.ovf", K::None),
    (0xdb, "sub.ovf.un", K::None),
    (0xdc, "endfinally", K::None),
    (0xdd, "leave", K::Br),
    (0xde, "leave.s", K::ShortBr),
    (0xdf, "stind.i", K::None),
    (0xe0, "conv.u", K::None),
];

/// `0xFE`-prefixed opcodes.
const TWO: &[(u8, &str, OperandKind)] = &[
    (0x00, "arglist", K::None),
    (0x01, "ceq", K::None),
    (0x02, "cgt", K::None),
    (0x03, "cgt.un", K::None),
    (0x04, "clt", K::None),
    (0x05, "clt.un", K::None),
    (0x06, "ldftn", K::Method),
    (0x07, "ldvirtftn", K::Method),
    (0x09, "ldarg", K::Var),
    (0x0a, "ldarga", K::Var),
    (0x0b, "starg", K::Var),
    (0x0c, "ldloc", K::Var),
    (0x0d, "ldloca", K::Var),
    (0x0e, "stloc", K::Var),
    (0x0f, "localloc", K::None),
    (0x11, "endfilter", K::None),
    (0x12, "unaligned.", K::ShortI),
    (0x13, "volatile.", K::None),
    (0x14, "tail.", K::None),
    (0x15, "initobj", K::Type),
    (0x16, "constrained.", K::Type),
    (0x17, "cpblk", K::None),
    (0x18, "initblk", K::None),
    (0x19, "no.", K::ShortI),
    (0x1a, "rethrow", K::None),
    (0x1c, "sizeof", K::Type),
    (0x1d, "refanytype", K::None),
    (0x1e, "readonly.", K::None),
];

/// Number of opcodes the decoder knows.
pub fn opcode_count() -> usize {
    ONE.len() + TWO.len()
}

fn lookup(prefixed: bool, b: u8) -> Option<(&'static str, OperandKind)> {
    let table = if prefixed { TWO } else { ONE };
    table.binary_search_by_key(&b, |e| e.0).ok().and_then(|i| table.get(i)).map(|e| (e.1, e.2))
}

/// A decoded operand.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(untagged)]
pub enum Operand {
    None,
    Int(i64),
    Float(f64),
    /// Branch target offset(s) within the body.
    Targets(Vec<u32>),
    Token(u32),
}

/// One instruction.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Instr {
    pub offset: u32,
    pub opcode: &'static str,
    pub kind: OperandKind,
    pub operand: Operand,
}

/// Why decoding stopped early.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DecodeIssue {
    pub offset: u32,
    pub reason: String,
}

/// Decode IL bytes. Stops at the first undecodable byte (reported) or after `max` instructions.
pub fn decode(code: &[u8], max: usize) -> (Vec<Instr>, Option<DecodeIssue>) {
    let r = Reader::new(code);
    let mut out = Vec::new();
    let mut pc = 0usize;
    while pc < code.len() {
        if out.len() >= max {
            return (out, Some(DecodeIssue { offset: pc as u32, reason: format!("stopped after {max} instructions") }));
        }
        let start = pc;
        let Some(b0) = r.u8(pc) else { break };
        let (name, kind) = if b0 == 0xfe {
            let Some(b1) = r.u8(pc + 1) else {
                return (out, Some(DecodeIssue { offset: start as u32, reason: "truncated two-byte opcode".into() }));
            };
            pc += 2;
            match lookup(true, b1) {
                Some(x) => x,
                None => return (out, Some(DecodeIssue { offset: start as u32, reason: format!("unknown opcode 0xfe {b1:#04x}") })),
            }
        } else {
            pc += 1;
            match lookup(false, b0) {
                Some(x) => x,
                None => return (out, Some(DecodeIssue { offset: start as u32, reason: format!("unknown opcode {b0:#04x}") })),
            }
        };
        let trunc = || Some(DecodeIssue { offset: start as u32, reason: format!("operand of {name} runs past the body") });
        let operand = match kind {
            K::None => Operand::None,
            K::ShortI => match r.u8(pc) {
                Some(v) => Operand::Int(i64::from(v as i8)),
                None => return (out, trunc()),
            },
            K::ShortVar => match r.u8(pc) {
                Some(v) => Operand::Int(i64::from(v)),
                None => return (out, trunc()),
            },
            K::Var => match r.u16_le(pc) {
                Some(v) => Operand::Int(i64::from(v)),
                None => return (out, trunc()),
            },
            K::I => match r.u32_le(pc) {
                Some(v) => Operand::Int(i64::from(v as i32)),
                None => return (out, trunc()),
            },
            K::I8 => match r.u64_le(pc) {
                Some(v) => Operand::Int(v as i64),
                None => return (out, trunc()),
            },
            K::ShortR => match r.u32_le(pc) {
                Some(v) => Operand::Float(f64::from(f32::from_bits(v))),
                None => return (out, trunc()),
            },
            K::R => match r.u64_le(pc) {
                Some(v) => Operand::Float(f64::from_bits(v)),
                None => return (out, trunc()),
            },
            K::ShortBr => match r.u8(pc) {
                Some(v) => Operand::Targets(vec![((pc + 1) as i64 + i64::from(v as i8)) as u32]),
                None => return (out, trunc()),
            },
            K::Br => match r.u32_le(pc) {
                Some(v) => Operand::Targets(vec![((pc + 4) as i64 + i64::from(v as i32)) as u32]),
                None => return (out, trunc()),
            },
            K::Switch => {
                let Some(n) = r.u32_le(pc) else { return (out, trunc()) };
                let n = n as usize;
                let Some(table_len) = n.checked_mul(4) else { return (out, trunc()) };
                let Some(end) = pc.checked_add(4).and_then(|x| x.checked_add(table_len)) else { return (out, trunc()) };
                if end > code.len() {
                    return (out, trunc());
                }
                let targets = (0..n).filter_map(|i| r.u32_le(pc + 4 + i * 4)).map(|d| (end as i64 + i64::from(d as i32)) as u32).collect();
                pc = end;
                out.push(Instr { offset: start as u32, opcode: name, kind, operand: Operand::Targets(targets) });
                continue;
            }
            K::Method | K::Field | K::Type | K::Tok | K::String | K::Sig => match r.u32_le(pc) {
                Some(v) => Operand::Token(v),
                None => return (out, trunc()),
            },
        };
        pc += kind.size();
        out.push(Instr { offset: start as u32, opcode: name, kind, operand });
    }
    (out, None)
}

/// SHA-256 over `[opcode, operand_kind, operand]` tuples (tokens as `0x%08x`, branches as target
/// offsets), so the identity survives renames and re-layout of the heaps.
pub fn normalized_hash(instrs: &[Instr]) -> String {
    let mut h = Sha256::new();
    h.update(b"[");
    for (i, ins) in instrs.iter().enumerate() {
        if i > 0 {
            h.update(b",");
        }
        let operand = match &ins.operand {
            Operand::None => "null".to_string(),
            Operand::Int(v) => v.to_string(),
            Operand::Float(f) => serde_json::to_string(f).unwrap_or_else(|_| "null".into()),
            Operand::Targets(t) => format!("[{}]", t.iter().map(u32::to_string).collect::<Vec<_>>().join(",")),
            Operand::Token(t) => format!("\"0x{t:08x}\""),
        };
        h.update(format!("[\"{}\",\"{}\",{operand}]", ins.opcode, ins.kind.name()).as_bytes());
    }
    h.update(b"]");
    hex(&h.finalize())
}

pub fn sha256(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

/// An exception-handling clause.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EhClause {
    /// catch, filter, finally, fault
    pub kind: &'static str,
    pub try_offset: u32,
    pub try_length: u32,
    pub handler_offset: u32,
    pub handler_length: u32,
    /// Catch type token or filter offset.
    pub class_token_or_filter: u32,
}

/// A parsed method body.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MethodBody {
    /// tiny or fat
    pub header: &'static str,
    pub max_stack: u16,
    pub code_size: u32,
    pub local_var_sig_token: u32,
    pub init_locals: bool,
    pub exception_clauses: Vec<EhClause>,
    /// Offset of the IL code within the input.
    pub code_offset: usize,
    pub warnings: Vec<String>,
}

const MAX_CLAUSES: usize = 4096;

/// Parse a method body starting at `off` in `data`.
pub fn parse_body(data: &[u8], off: usize) -> Option<MethodBody> {
    let r = Reader::new(data);
    let b0 = r.u8(off)?;
    match b0 & 3 {
        2 => {
            let size = u32::from(b0 >> 2);
            r.slice(off + 1, size as usize)?;
            Some(MethodBody {
                header: "tiny",
                max_stack: 8,
                code_size: size,
                local_var_sig_token: 0,
                init_locals: false,
                exception_clauses: Vec::new(),
                code_offset: off + 1,
                warnings: Vec::new(),
            })
        }
        3 => {
            let fl = r.u16_le(off)?;
            let hsize = usize::from(fl >> 12) * 4;
            if hsize < 12 {
                return None;
            }
            let max_stack = r.u16_le(off + 2)?;
            let code_size = r.u32_le(off + 4)?;
            let local_var_sig_token = r.u32_le(off + 8)?;
            let code_offset = off.checked_add(hsize)?;
            r.slice(code_offset, code_size as usize)?;
            let mut body = MethodBody {
                header: "fat",
                max_stack,
                code_size,
                local_var_sig_token,
                init_locals: fl & 0x10 != 0,
                exception_clauses: Vec::new(),
                code_offset,
                warnings: Vec::new(),
            };
            if fl & 0x8 != 0 {
                let mut sect = (code_offset.checked_add(code_size as usize)?.checked_add(3)?) & !3;
                for _ in 0..64 {
                    let Some(kind) = r.u8(sect) else {
                        body.warnings.push("extra data section runs past the file".into());
                        break;
                    };
                    let fat = kind & 0x40 != 0;
                    let (size, hdr) = if fat {
                        let v = r.u32_le(sect).unwrap_or(0) >> 8;
                        (v as usize, 4usize)
                    } else {
                        (usize::from(r.u8(sect + 1).unwrap_or(0)), 4usize)
                    };
                    if size < hdr {
                        body.warnings.push("empty extra data section".into());
                        break;
                    }
                    if kind & 0x1 != 0 {
                        let csize = if fat { 24 } else { 12 };
                        let n = (size - hdr) / csize;
                        for i in 0..n.min(MAX_CLAUSES) {
                            let c = sect + hdr + i * csize;
                            let (flags, to, tl, ho, hl, tok) = if fat {
                                (r.u32_le(c), r.u32_le(c + 4), r.u32_le(c + 8), r.u32_le(c + 12), r.u32_le(c + 16), r.u32_le(c + 20))
                            } else {
                                (
                                    r.u16_le(c).map(u32::from),
                                    r.u16_le(c + 2).map(u32::from),
                                    r.u8(c + 4).map(u32::from),
                                    r.u16_le(c + 5).map(u32::from),
                                    r.u8(c + 7).map(u32::from),
                                    r.u32_le(c + 8),
                                )
                            };
                            let (Some(flags), Some(to), Some(tl), Some(ho), Some(hl), Some(tok)) = (flags, to, tl, ho, hl, tok) else {
                                body.warnings.push("exception clause runs past the file".into());
                                break;
                            };
                            let kind = match flags & 7 {
                                0 => "catch",
                                1 => "filter",
                                2 => "finally",
                                4 => "fault",
                                _ => "unknown",
                            };
                            if to.checked_add(tl).is_none_or(|e| e > code_size) || ho.checked_add(hl).is_none_or(|e| e > code_size) {
                                body.warnings.push(format!("{kind} clause at {i} lies outside the code"));
                            }
                            body.exception_clauses.push(EhClause {
                                kind,
                                try_offset: to,
                                try_length: tl,
                                handler_offset: ho,
                                handler_length: hl,
                                class_token_or_filter: tok,
                            });
                        }
                    }
                    if kind & 0x80 == 0 {
                        break;
                    }
                    sect = (sect.checked_add(size)?.checked_add(3)?) & !3;
                }
            }
            Some(body)
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tables_are_sorted_and_complete() {
        assert!(ONE.windows(2).all(|w| w[0].0 < w[1].0));
        assert!(TWO.windows(2).all(|w| w[0].0 < w[1].0));
        assert_eq!(opcode_count(), 219);
    }

    #[test]
    fn decodes_branches_switch_and_tokens() {
        // ldc.i4.s -1; br.s +0; switch(2) [+1, -2]; call 0x0a000001; ldarg 3 (0xfe 0x09)
        let code = [0x1f, 0xff, 0x2b, 0x00, 0x45, 2, 0, 0, 0, 1, 0, 0, 0, 0xfe, 0xff, 0xff, 0xff, 0x28, 1, 0, 0, 0x0a, 0xfe, 0x09, 3, 0];
        let (ins, issue) = decode(&code, 100);
        assert!(issue.is_none(), "{issue:?}");
        assert_eq!(ins[0].operand, Operand::Int(-1));
        assert_eq!(ins[1].operand, Operand::Targets(vec![4]));
        assert_eq!(ins[2].operand, Operand::Targets(vec![18, 15]));
        assert_eq!(ins[3].operand, Operand::Token(0x0a00_0001));
        assert_eq!(ins[4].opcode, "ldarg");
        let (_, issue) = decode(&[0x24], 10);
        assert!(issue.is_some());
        for len in 0..code.len() {
            let _ = decode(&code[..len], 100);
        }
        assert_eq!(normalized_hash(&ins).len(), 64);
    }

    #[test]
    fn bodies() {
        let tiny = [0x0a, 0x02, 0x2a];
        let b = parse_body(&tiny, 0).unwrap();
        assert_eq!((b.header, b.code_size), ("tiny", 2));
        assert!(parse_body(&[0x0e], 0).is_none());
        for x in 0..=255u8 {
            let _ = parse_body(&[x, 0x30, 8, 0, 0xff, 0xff, 0, 0, 0, 0, 0, 0], 0);
        }
    }
}
