//! A small, honest pseudo-C lifter. It works at register level (no type recovery), turns each
//! basic block into C-like statements, and structures the control-flow graph into `if`/`else`
//! and `while` using dominators and post-dominators, falling back to labels and `goto` where the
//! graph isn't structured. Calls get resolved names and arguments from the calling convention;
//! string literals are inlined.

use crate::decode::{ArmConsts, Cond, Flow, Insn, Kind, MemOp, Mode, Op, canonical_reg};
use crate::image::Image;
use crate::program::{Function, Program};
use craft_anything_formats::Format;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

/// Blocks above this are listed linearly with labels instead of being structured.
const MAX_STRUCTURED_BLOCKS: usize = 1500;
const MAX_DEPTH: usize = 64;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Pseudo {
    pub signature: String,
    pub text: String,
    /// Names of everything called.
    pub calls: Vec<String>,
    /// String literals used.
    pub strings: Vec<String>,
    pub gotos: usize,
    /// Instructions shown as `__asm(...)` because the lifter has no rule for them.
    pub asm_fallbacks: usize,
    /// True when the control flow was fully structured (no gotos, no linear fallback).
    pub structured: bool,
    pub limitations: Vec<(String, String)>,
}

#[derive(Debug, Clone)]
struct Line {
    indent: usize,
    text: String,
    label: Option<u64>,
    loop_end: bool,
}

struct BlockCode {
    stmts: Vec<String>,
    cond: Option<String>,
    /// Condition is for the taken edge; `taken` is its target.
    taken: Option<u64>,
}

struct Lifter<'a> {
    img: &'a Image,
    prog: &'a Program,
    names: &'a dyn Fn(u64) -> Option<String>,
    mode: Mode,
    arg_regs: &'static [&'static str],
    /// Win64: calls take arguments 5+ from the stack at `[rsp+0x20]`, `[rsp+0x28]`, …
    win64: bool,
    /// Jump targets that leave the function (tail calls).
    tail_calls: &'a [u64],
    ret_reg: String,
    calls: BTreeSet<String>,
    strings: Vec<String>,
    asm_fallbacks: usize,
}

fn escape(s: &str) -> String {
    let mut out = String::new();
    for (i, c) in s.chars().enumerate() {
        if i >= 120 {
            out.push_str("...");
            break;
        }
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn ty(size: u8) -> &'static str {
    match size {
        1 => "uint8_t",
        2 => "uint16_t",
        4 => "uint32_t",
        8 => "uint64_t",
        16 => "uint128_t",
        _ => "void",
    }
}

fn imm(v: i64) -> String {
    if (-16..=16).contains(&v) {
        v.to_string()
    } else if v < 0 {
        format!("-{:#x}", v.unsigned_abs())
    } else {
        format!("{v:#x}")
    }
}

impl Lifter<'_> {
    fn addr_name(&self, a: u64) -> Option<String> {
        (self.names)(a).or_else(|| self.prog.name_at(a))
    }

    fn string_lit(&mut self, a: u64) -> Option<String> {
        let s = self.prog.string_at(a)?;
        let off = a.checked_sub(s.addr)?;
        let text: String = if off == 0 { s.text.clone() } else { s.text.chars().skip(off as usize).collect() };
        if !self.strings.contains(&text) && self.strings.len() < 256 {
            self.strings.push(text.clone());
        }
        Some(format!("\"{}\"", escape(&text)))
    }

    /// `&thing` for an address-of.
    fn address_of(&mut self, a: u64) -> String {
        if let Some(s) = self.string_lit(a) {
            return s;
        }
        match self.addr_name(a) {
            Some(n) => format!("&{n}"),
            None => {
                if self.img.is_exec(a) {
                    format!("sub_{a:x}")
                } else {
                    format!("&data_{a:x}")
                }
            }
        }
    }

    /// The address arithmetic of a memory operand, without dereferencing it.
    fn mem_addr(&mut self, m: &MemOp) -> String {
        if let Some(a) = m.addr {
            return self.address_of(a);
        }
        let mut parts = Vec::new();
        if let Some(b) = &m.base {
            parts.push(b.clone());
        }
        if let Some(i) = &m.index {
            parts.push(if m.scale > 1 { format!("{i} * {}", m.scale) } else { i.clone() });
        }
        if m.disp != 0 || parts.is_empty() {
            parts.push(imm(m.disp));
        }
        parts.join(" + ").replace("+ -", "- ")
    }

    fn mem(&mut self, m: &MemOp) -> String {
        if let Some(seg) = &m.seg {
            return format!("{seg}:[{}]", self.mem_addr(m));
        }
        if let Some(a) = m.addr {
            if let Some(n) = self.addr_name(a) {
                return n;
            }
            return format!("*({}*){a:#x}", ty(m.size));
        }
        let frame = matches!(m.base.as_deref(), Some("rbp" | "ebp" | "bp" | "x29"));
        let stack = matches!(m.base.as_deref(), Some("rsp" | "esp" | "sp"));
        if m.index.is_none() && (frame || stack) {
            let prefix = if frame { if m.disp < 0 { "var" } else { "arg" } } else { "stack" };
            return format!("{prefix}_{:x}", m.disp.unsigned_abs());
        }
        let mut parts = Vec::new();
        if let Some(b) = &m.base {
            parts.push(b.clone());
        }
        if let Some(i) = &m.index {
            parts.push(if m.scale > 1 { format!("{i} * {}", m.scale) } else { i.clone() });
        }
        if m.disp != 0 || parts.is_empty() {
            parts.push(imm(m.disp));
        }
        format!("*({}*)({})", ty(m.size), parts.join(" + ").replace("+ -", "- "))
    }

    fn op(&mut self, o: &Op) -> String {
        match o {
            Op::Reg(r) => r.clone(),
            Op::Imm(v) => imm(*v),
            Op::Mem(m) => self.mem(m),
            Op::Addr(a) => self.address_of(*a),
        }
    }

    fn call_name(&self, i: &Insn) -> String {
        match i.flow {
            Flow::Call { target } => self.addr_name(target).unwrap_or_else(|| format!("sub_{target:x}")),
            Flow::IndirectCall { slot: Some(s) } => {
                self.prog.import_slots.get(&s).map(|x| x.name.clone()).or_else(|| self.addr_name(s)).unwrap_or_else(|| format!("(*{s:#x})"))
            }
            _ => match i.ops.first() {
                Some(Op::Reg(r)) => format!("(*{r})"),
                Some(Op::Mem(m)) => {
                    let m = m.clone();
                    let mut tmp = Lifter {
                        img: self.img,
                        prog: self.prog,
                        names: self.names,
                        mode: self.mode,
                        arg_regs: self.arg_regs,
                        win64: self.win64,
                        tail_calls: self.tail_calls,
                        ret_reg: String::new(),
                        calls: BTreeSet::new(),
                        strings: Vec::new(),
                        asm_fallbacks: 0,
                    };
                    format!("(*{})", tmp.mem(&m))
                }
                _ => "(*unknown)".into(),
            },
        }
    }

    /// Register arguments of a call: up to the last argument register assigned in this block (at
    /// least `min`). Their assignments are folded into the call.
    fn reg_args(&self, defs: &BTreeMap<String, (usize, String)>, dead: &mut BTreeSet<usize>, min: usize) -> Vec<String> {
        let n = self.arg_regs.iter().rposition(|r| defs.contains_key(*r)).map(|p| p + 1).unwrap_or(0).max(min).min(self.arg_regs.len());
        self.arg_regs
            .iter()
            .take(n)
            .map(|r| match defs.get(*r) {
                Some((idx, e)) => {
                    dead.insert(*idx);
                    e.clone()
                }
                None => (*r).to_string(),
            })
            .collect()
    }

    /// Statements for one block plus its branch condition.
    fn block(&mut self, insns: &[Insn], entry_or_exit: bool) -> BlockCode {
        let mut stmts: Vec<String> = Vec::new();
        // canonical reg → (statement index, expression) of its latest assignment in this block
        let mut defs: BTreeMap<String, (usize, String)> = BTreeMap::new();
        let mut pushes: Vec<String> = Vec::new();
        let mut flag_src: Option<&Insn> = None;
        let mut cond = None;
        let mut taken = None;
        let mut dead: BTreeSet<usize> = BTreeSet::new();
        // Win64 outgoing stack arguments stored in this block: rsp offset → (statement, value).
        let mut stack_args: BTreeMap<i64, (usize, String)> = BTreeMap::new();
        for (k, i) in insns.iter().enumerate() {
            // A register read by a later instruction keeps its assignment.
            if !matches!(i.flow, Flow::Call { .. } | Flow::IndirectCall { .. }) {
                for r in &i.reads {
                    defs.remove(r);
                }
            }
            // AArch64 page loads and import-slot loads are shown through what uses them.
            if i.kind == Kind::Adrp || (i.kind == Kind::Load && i.refs.first().is_some_and(|r| self.prog.import_slots.contains_key(r))) {
                continue;
            }
            let d = i.ops.first().map(|o| self.op(o));
            let s = i.ops.get(1).map(|o| self.op(o));
            let t = i.ops.get(2).map(|o| self.op(o));
            let mut stmt: Option<String> = None;
            let dest_reg = match i.ops.first() {
                Some(Op::Reg(r)) => Some(canonical_reg(r)),
                _ => None,
            };
            let frame_reg = |r: &str| matches!(canonical_reg(r).as_str(), "rsp" | "rbp" | "sp" | "x29" | "x30");
            match (i.kind, &i.flow) {
                (_, Flow::Call { .. } | Flow::IndirectCall { .. }) => {
                    let name = self.call_name(i);
                    if self.calls.len() < 512 {
                        self.calls.insert(name.trim_start_matches("(*").trim_end_matches(')').to_string());
                    }
                    let args = if self.mode == Mode::X32 || self.mode == Mode::X16 {
                        let a = pushes.iter().rev().cloned().collect();
                        pushes.clear();
                        a
                    } else {
                        // Win64 calls into imports: contiguous stores at [rsp+0x20], [rsp+0x28], …
                        // are arguments 5, 6, …
                        let import: Option<&str> = match i.flow {
                            Flow::IndirectCall { slot: Some(s) } => self.prog.import_slots.get(&s).map(|si| si.name.as_str()),
                            Flow::Call { target } => self
                                .prog
                                .import_slots
                                .get(&target)
                                .map(|si| si.name.as_str())
                                .or_else(|| self.prog.functions.get(&target).and_then(|f| f.thunk_of.as_deref())),
                            _ => None,
                        };
                        let mut stack = Vec::new();
                        if self.win64 && import.is_some() {
                            let mut off = 0x20i64;
                            while let Some((idx, v)) = stack_args.get(&off) {
                                dead.insert(*idx);
                                stack.push(v.clone());
                                off += 8;
                            }
                        }
                        // A known library function shows all its register arguments, even ones set
                        // outside this block (they read as the register itself).
                        let known = import.and_then(crate::arity::import_arity).unwrap_or(0);
                        let mut a = self.reg_args(&defs, &mut dead, if stack.is_empty() { known } else { known.max(4) });
                        a.extend(stack);
                        a
                    };
                    stack_args.clear();
                    let uses_ret = insns
                        .get(k + 1..)
                        .unwrap_or(&[])
                        .iter()
                        .take(6)
                        .take_while(|n| !matches!(n.flow, Flow::Call { .. } | Flow::IndirectCall { .. }))
                        .find_map(|n| {
                            let r = n.reads.iter().any(|x| *x == self.ret_canon());
                            let w = n.writes.iter().any(|x| *x == self.ret_canon());
                            if r {
                                Some(true)
                            } else if w {
                                Some(false)
                            } else {
                                None
                            }
                        });
                    let call = format!("{name}({})", args.join(", "));
                    stmt = Some(if uses_ret == Some(true) { format!("{} = {call};", self.ret_reg_name()) } else { format!("{call};") });
                    // Calls clobber argument registers.
                    defs.clear();
                }
                (_, Flow::Return) => {
                    stmt = Some(if self.ret_reg.is_empty() { "return;".into() } else { format!("return {};", self.ret_reg) });
                }
                (_, Flow::Jump { target }) if self.tail_calls.contains(target) => {
                    // A jump out of the function is a tail call: it returns what the callee returns.
                    let name = self.addr_name(*target).unwrap_or_else(|| format!("sub_{target:x}"));
                    if self.calls.len() < 512 {
                        self.calls.insert(name.clone());
                    }
                    let args = self.reg_args(&defs, &mut dead, 0);
                    stmt = Some(format!("return {name}({}); /* tail call */", args.join(", ")));
                }
                (_, Flow::Jump { .. } | Flow::Cond { .. } | Flow::Stop) => {
                    if let Flow::Cond { target } = i.flow {
                        cond = Some(self.condition(i.cond.as_ref(), flag_src));
                        taken = Some(target);
                    }
                    if matches!(i.flow, Flow::Stop) {
                        stmt = Some(if i.mnemonic.starts_with("int3") || i.mnemonic == "brk" {
                            "__debugbreak();".into()
                        } else {
                            "__halt(); /* stops here */".into()
                        });
                    }
                }
                (_, Flow::IndirectJump { slot }) => {
                    stmt = Some(match slot.and_then(|s| self.prog.import_slots.get(&s)) {
                        Some(si) => format!("return {}(); /* tail call */", si.name),
                        None => format!("goto *{}; /* computed jump */", d.clone().unwrap_or_default()),
                    });
                }
                (Kind::Nop | Kind::Leave, _) => {}
                (Kind::Push, _) => {
                    let v = d.clone().unwrap_or_default();
                    if !(entry_or_exit && matches!(i.ops.first(), Some(Op::Reg(_)))) {
                        pushes.push(v);
                    }
                }
                (Kind::Pop, _) => {
                    if !entry_or_exit {
                        stmt = Some(format!("{} = pop();", d.clone().unwrap_or_default()));
                    }
                }
                (Kind::Cmp | Kind::Test, _) => flag_src = Some(i),
                (Kind::Mov | Kind::MovSx | Kind::MovZx, _) if i.ops.len() >= 2 => {
                    let (dd, ss) = (d.clone().unwrap_or_default(), s.clone().unwrap_or_default());
                    if (frame_reg(&dd) && dest_reg.is_some()) || dd == ss {
                        // frame setup (mov rbp, rsp / mov x29, sp)
                    } else {
                        stmt = Some(format!("{dd} = {ss};"));
                    }
                }
                (Kind::Lea, _) => {
                    let e = match i.ops.get(1) {
                        Some(Op::Mem(m)) => match m.addr {
                            Some(a) => self.address_of(a),
                            None => {
                                let frame = matches!(m.base.as_deref(), Some("rbp" | "ebp" | "rsp" | "esp" | "x29" | "sp")) && m.index.is_none();
                                if frame { format!("&{}", self.mem(m)) } else { self.mem_addr(m) }
                            }
                        },
                        _ => s.clone().unwrap_or_default(),
                    };
                    stmt = Some(format!("{} = {e};", d.clone().unwrap_or_default()));
                }
                (Kind::Adrp | Kind::Adr, _) => {
                    let e = match i.ops.get(1) {
                        Some(Op::Addr(a)) if i.kind == Kind::Adr => self.address_of(*a),
                        Some(Op::Addr(a)) => format!("{a:#x} /* page */"),
                        _ => s.clone().unwrap_or_default(),
                    };
                    stmt = Some(format!("{} = {e};", d.clone().unwrap_or_default()));
                }
                (Kind::Add | Kind::Sub | Kind::And | Kind::Or | Kind::Xor | Kind::Shl | Kind::Shr | Kind::Sar | Kind::Mul, _) => {
                    let sym = match i.kind {
                        Kind::Add => "+",
                        Kind::Sub => "-",
                        Kind::And => "&",
                        Kind::Or => "|",
                        Kind::Xor => "^",
                        Kind::Shl => "<<",
                        Kind::Shr | Kind::Sar => ">>",
                        _ => "*",
                    };
                    let dd = d.clone().unwrap_or_default();
                    if i.sets_flags {
                        flag_src = Some(i);
                    }
                    if dest_reg.as_deref().is_some_and(frame_reg) && matches!(i.kind, Kind::Add | Kind::Sub) {
                        // stack frame adjustment
                    } else if i.kind == Kind::Xor && i.ops.len() == 2 && i.ops.first() == i.ops.get(1) {
                        stmt = Some(format!("{dd} = 0;"));
                    } else if self.mode == Mode::A64 && i.kind == Kind::Add && i.refs.first().is_some_and(|r| self.prog.string_at(*r).is_some()) {
                        let r = i.refs.first().copied().unwrap_or(0);
                        let lit = self.address_of(r);
                        stmt = Some(format!("{dd} = {lit};"));
                    } else if let Some(t) = t.clone() {
                        let ss = s.clone().unwrap_or_default();
                        stmt = Some(if ss == dd { format!("{dd} {sym}= {t};") } else { format!("{dd} = {ss} {sym} {t};") });
                    } else if let Some(ss) = s.clone() {
                        stmt = Some(format!("{dd} {sym}= {ss};"));
                    } else {
                        stmt = Some(format!("{dd} = {dd} {sym} ...; /* {} */", i.text()));
                    }
                    if self.mode.is_x86() && i.ops.len() == 1 && i.kind == Kind::Mul {
                        stmt = Some(format!("rdx:rax = rax * {dd};"));
                    }
                }
                (Kind::Inc, _) => {
                    flag_src = Some(i);
                    stmt = Some(format!("{}++;", d.clone().unwrap_or_default()));
                }
                (Kind::Dec, _) => {
                    flag_src = Some(i);
                    stmt = Some(format!("{}--;", d.clone().unwrap_or_default()));
                }
                (Kind::Not, _) => stmt = Some(format!("{0} = ~{0};", d.clone().unwrap_or_default())),
                (Kind::Neg, _) => stmt = Some(format!("{0} = -{0};", d.clone().unwrap_or_default())),
                (Kind::Load, _) if i.ops.len() >= 2 => {
                    let e = match i.refs.first() {
                        Some(&r) => self.addr_name(r).unwrap_or_else(|| format!("*(uint64_t*){r:#x}")),
                        None => s.clone().unwrap_or_default(),
                    };
                    let e = if e.starts_with("&") && i.refs.is_empty() { e.trim_start_matches('&').to_string() } else { e };
                    stmt = Some(format!("{} = {};", d.clone().unwrap_or_default(), e.trim_start_matches("&")));
                }
                (Kind::Store, _) if i.ops.len() >= 2 => {
                    let target = match i.refs.first() {
                        Some(&r) => self.addr_name(r).unwrap_or_else(|| format!("*(uint64_t*){r:#x}")),
                        None => s.clone().unwrap_or_default(),
                    };
                    stmt = Some(format!("{} = {};", target.trim_start_matches('&'), d.clone().unwrap_or_default()));
                }
                (Kind::LoadPair | Kind::StorePair, _) => {
                    let all_frame = i.ops.iter().take(2).all(|o| matches!(o, Op::Reg(r) if frame_reg(r)));
                    if !(entry_or_exit && all_frame) {
                        let (a, b) = (d.clone().unwrap_or_default(), s.clone().unwrap_or_default());
                        let m = t.clone().unwrap_or_default();
                        stmt = Some(if i.kind == Kind::LoadPair { format!("{a} = {m}[0]; {b} = {m}[1];") } else { format!("{m}[0] = {a}; {m}[1] = {b};") });
                    }
                }
                _ => {
                    if i.sets_flags {
                        flag_src = Some(i);
                    }
                    self.asm_fallbacks += 1;
                    stmt = Some(format!("__asm(\"{}\");", escape(&i.text())));
                }
            }
            if let Some(st) = stmt {
                stmts.push(st);
                if self.win64
                    && matches!(i.kind, Kind::Mov | Kind::Store)
                    && let Some(Op::Mem(m)) = i.ops.first()
                    && m.base.as_deref() == Some("rsp")
                    && m.index.is_none()
                    && m.seg.is_none()
                    && m.disp >= 0x20
                    && let Some(v) = stmts.last().and_then(|l| l.split_once(" = ")).map(|(_, e)| e.trim_end_matches(';').to_string())
                {
                    stack_args.insert(m.disp, (stmts.len() - 1, v));
                }
                if let Some(r) = &dest_reg {
                    let expr = stmts.last().and_then(|l| l.split_once(" = ").map(|(_, e)| e.trim_end_matches(';').to_string()));
                    match expr {
                        Some(e) if !e.contains(';') && !matches!(i.flow, Flow::Call { .. } | Flow::IndirectCall { .. }) => {
                            defs.insert(r.clone(), (stmts.len() - 1, e));
                        }
                        _ => {
                            defs.remove(r);
                        }
                    }
                }
            }
            for w in &i.writes {
                if dest_reg.as_ref() != Some(w) {
                    defs.remove(w);
                }
            }
            // Moving the stack pointer shifts every slot: forget the pending stack arguments.
            if i.writes.iter().any(|w| w == "rsp") {
                stack_args.clear();
            }
        }
        let stmts = stmts.into_iter().enumerate().filter(|(i, _)| !dead.contains(i)).map(|(_, s)| s).collect();
        BlockCode { stmts, cond, taken }
    }

    fn ret_canon(&self) -> String {
        match self.mode {
            Mode::A64 => "x0".into(),
            Mode::A32 | Mode::T32 => "r0".into(),
            _ => "rax".into(),
        }
    }

    fn ret_reg_name(&self) -> String {
        if self.ret_reg.is_empty() { self.ret_canon() } else { self.ret_reg.clone() }
    }

    fn condition(&mut self, c: Option<&Cond>, src: Option<&Insn>) -> String {
        let Some(c) = c else { return "/* condition */ flags".into() };
        match c {
            Cond::RegZero(r) => return format!("{r} == 0"),
            Cond::RegNonZero(r) => return format!("{r} != 0"),
            Cond::BitClear(r, b) => return format!("(({r} >> {b}) & 1) == 0"),
            Cond::BitSet(r, b) => return format!("(({r} >> {b}) & 1) != 0"),
            _ => {}
        }
        let opstr = match c {
            Cond::Sign => Some("<"),
            Cond::NotSign => Some(">="),
            other => other.op(),
        };
        let Some(src) = src else { return format!("/* {c:?} */ flags") };
        let a = src.ops.first().map(|o| self.op(o)).unwrap_or_default();
        // ARM compare aliases encode the zero register first.
        let (a, b) = if self.mode == Mode::A64 && matches!(src.kind, Kind::Cmp | Kind::Test) {
            (src.ops.get(1).map(|o| self.op(o)).unwrap_or_default(), src.ops.get(2).map(|o| self.op(o)).unwrap_or_default())
        } else {
            (a, src.ops.get(1).map(|o| self.op(o)).unwrap_or_default())
        };
        let Some(op) = opstr else { return format!("/* {c:?} after {} */ flags", src.mnemonic) };
        let unsigned = if c.unsigned() { " /* unsigned */" } else { "" };
        match src.kind {
            Kind::Cmp => {
                if matches!(c, Cond::Sign | Cond::NotSign) {
                    format!("{a} - {b} {op} 0")
                } else {
                    format!("{a} {op} {b}{unsigned}")
                }
            }
            Kind::Test => {
                if a == b || b.is_empty() {
                    format!("{a} {op} 0{unsigned}")
                } else {
                    format!("({a} & {b}) {op} 0")
                }
            }
            _ => format!("{a} {op} 0{unsigned}"),
        }
    }
}

fn cond_negate_text(c: &str) -> String {
    for (a, b) in [(" == ", " != "), (" != ", " == "), (" <= ", " > "), (" >= ", " < "), (" < ", " >= "), (" > ", " <= ")] {
        if let Some((l, r)) = c.split_once(a)
            && !r.contains(" == ")
            && !r.contains(" != ")
            && !l.contains(" == ")
        {
            return format!("{l}{b}{r}");
        }
    }
    format!("!({c})")
}

/// Bitset-backed dominator sets.
fn dominators(n: usize, entry: usize, preds: &[Vec<usize>]) -> Vec<Vec<u64>> {
    let words = n.div_ceil(64);
    let full = vec![u64::MAX; words];
    let mut dom: Vec<Vec<u64>> = vec![full; n];
    if let Some(d) = dom.get_mut(entry) {
        *d = vec![0; words];
        set(d, entry);
    }
    let mut changed = true;
    let mut rounds = 0;
    while changed && rounds < 200 {
        changed = false;
        rounds += 1;
        for b in 0..n {
            if b == entry {
                continue;
            }
            let mut new = vec![u64::MAX; words];
            let mut any = false;
            for &p in preds.get(b).map(Vec::as_slice).unwrap_or(&[]) {
                if let Some(pd) = dom.get(p) {
                    any = true;
                    for (x, y) in new.iter_mut().zip(pd) {
                        *x &= *y;
                    }
                }
            }
            if !any {
                new = vec![0; words];
            }
            set(&mut new, b);
            if dom.get(b) != Some(&new) {
                if let Some(d) = dom.get_mut(b) {
                    *d = new;
                }
                changed = true;
            }
        }
    }
    dom
}

fn set(v: &mut [u64], i: usize) {
    if let Some(w) = v.get_mut(i / 64) {
        *w |= 1 << (i % 64);
    }
}

fn has(v: &[u64], i: usize) -> bool {
    v.get(i / 64).is_some_and(|w| w & (1 << (i % 64)) != 0)
}

fn count(v: &[u64]) -> u32 {
    v.iter().map(|w| w.count_ones()).sum()
}

/// Immediate (post-)dominator: the strict dominator with the largest dominator set.
fn immediate(sets: &[Vec<u64>], n: usize, b: usize) -> Option<usize> {
    let s = sets.get(b)?;
    if count(s) as usize >= n && n > 1 {
        return None; // unreachable / never reaches exit: set stayed full
    }
    (0..n).filter(|&d| d != b && has(s, d)).max_by_key(|&d| sets.get(d).map(|x| count(x)).unwrap_or(0))
}

struct Graph {
    starts: Vec<u64>,
    succs: Vec<Vec<usize>>,
    idom: Vec<Option<usize>>,
    ipdom: Vec<Option<usize>>,
    dom: Vec<Vec<u64>>,
    /// header → (loop body, follow)
    loops: BTreeMap<usize, (BTreeSet<usize>, Option<usize>)>,
}

fn build_graph(f: &Function) -> Graph {
    let n = f.blocks.len();
    let starts: Vec<u64> = f.blocks.iter().map(|b| b.start).collect();
    let index: BTreeMap<u64, usize> = starts.iter().enumerate().map(|(i, s)| (*s, i)).collect();
    let succs: Vec<Vec<usize>> = f.blocks.iter().map(|b| b.succs.iter().filter_map(|s| index.get(s).copied()).collect()).collect();
    let mut preds = vec![Vec::new(); n];
    for (i, ss) in succs.iter().enumerate() {
        for &s in ss {
            if let Some(p) = preds.get_mut(s) {
                p.push(i);
            }
        }
    }
    let entry = index.get(&f.entry).copied().unwrap_or(0);
    let dom = dominators(n, entry, &preds);
    // Post-dominators: reverse graph with a virtual exit (index n).
    let mut rpreds: Vec<Vec<usize>> = succs.clone();
    for (i, ss) in succs.iter().enumerate() {
        if ss.is_empty()
            && let Some(r) = rpreds.get_mut(i)
        {
            r.push(n);
        }
    }
    rpreds.push(Vec::new());
    let pdom = dominators(n + 1, n, &rpreds);
    let idom = (0..n).map(|b| immediate(&dom, n, b)).collect();
    let ipdom = (0..n).map(|b| immediate(&pdom, n + 1, b).filter(|&d| d < n)).collect();
    // Natural loops from back edges u → h where h dominates u.
    let mut loops: BTreeMap<usize, (BTreeSet<usize>, Option<usize>)> = BTreeMap::new();
    for (u, ss) in succs.iter().enumerate() {
        for &h in ss {
            if dom.get(u).is_some_and(|d| has(d, h)) {
                let body = &mut loops.entry(h).or_insert_with(|| (BTreeSet::from([h]), None)).0;
                let mut stack = vec![u];
                while let Some(x) = stack.pop() {
                    if body.insert(x) {
                        for &p in preds.get(x).map(Vec::as_slice).unwrap_or(&[]) {
                            stack.push(p);
                        }
                    }
                }
            }
        }
    }
    let ipd: Vec<Option<usize>> = (0..n).map(|b| immediate(&pdom, n + 1, b).filter(|&d| d < n)).collect();
    for (h, (body, follow)) in loops.iter_mut() {
        let exits: BTreeSet<usize> = body.iter().flat_map(|&b| succs.get(b).cloned().unwrap_or_default()).filter(|s| !body.contains(s)).collect();
        *follow = ipd
            .get(*h)
            .copied()
            .flatten()
            .filter(|p| !body.contains(p))
            .or_else(|| exits.iter().min_by_key(|&&e| starts.get(e).copied().unwrap_or(0)).copied());
    }
    Graph { starts, succs, idom, ipdom, dom, loops }
}

enum Edge {
    Continue,
    Break,
    To(usize),
}

struct Emitter<'a> {
    g: &'a Graph,
    code: &'a [BlockCode],
    emitted: Vec<bool>,
    lines: Vec<Line>,
    labels: BTreeSet<u64>,
    gotos: usize,
    loop_stack: Vec<(usize, Option<usize>)>,
    pending_label: Option<u64>,
}

impl Emitter<'_> {
    fn push(&mut self, indent: usize, text: impl Into<String>) {
        let label = self.pending_label.take();
        self.lines.push(Line { indent, text: text.into(), label, loop_end: false });
    }

    fn edge(&self, to: usize) -> Edge {
        if let Some(&(h, follow)) = self.loop_stack.last() {
            if to == h {
                return Edge::Continue;
            }
            if Some(to) == follow {
                return Edge::Break;
            }
        }
        Edge::To(to)
    }

    fn goto(&mut self, indent: usize, b: usize) {
        let s = self.g.starts.get(b).copied().unwrap_or(0);
        self.labels.insert(s);
        self.gotos += 1;
        self.push(indent, format!("goto label_{s:x};"));
    }

    fn in_current_loop(&self, b: usize) -> bool {
        match self.loop_stack.last() {
            Some((h, _)) => self.g.loops.get(h).is_some_and(|(body, _)| body.contains(&b)),
            None => true,
        }
    }

    /// Emit from block `b` until `stop`.
    fn region(&mut self, mut b: Option<usize>, stop: Option<usize>, indent: usize, depth: usize) {
        while let Some(cur) = b {
            if Some(cur) == stop {
                return;
            }
            if depth > MAX_DEPTH || indent > MAX_DEPTH {
                self.goto(indent, cur);
                return;
            }
            if !self.in_current_loop(cur) {
                // Leaving the loop other than through its follow.
                self.goto(indent, cur);
                return;
            }
            if self.emitted.get(cur).copied().unwrap_or(true) {
                let tiny_exit = self.g.succs.get(cur).is_some_and(|s| s.is_empty()) && self.code.get(cur).is_some_and(|c| c.stmts.len() <= 4);
                if tiny_exit {
                    for st in self.code.get(cur).map(|c| c.stmts.clone()).unwrap_or_default() {
                        self.push(indent, st);
                    }
                } else {
                    self.goto(indent, cur);
                }
                return;
            }
            let is_header = self.g.loops.contains_key(&cur) && self.loop_stack.last().map(|(h, _)| *h) != Some(cur);
            if is_header {
                let follow = self.g.loops.get(&cur).and_then(|(_, f)| *f);
                self.push(indent, "while (true) {");
                self.loop_stack.push((cur, follow));
                self.body(cur, indent + 1, depth + 1);
                self.loop_stack.pop();
                // drop a trailing continue
                if self.lines.last().is_some_and(|l| l.text == "continue;" && l.indent == indent + 1) {
                    self.lines.pop();
                }
                self.lines.push(Line { indent, text: "}".into(), label: None, loop_end: true });
                b = follow;
                continue;
            }
            b = self.body(cur, indent, depth);
        }
    }

    /// Emit one block and its branch; returns where straight-line emission continues.
    fn body(&mut self, cur: usize, indent: usize, depth: usize) -> Option<usize> {
        if let Some(e) = self.emitted.get_mut(cur) {
            *e = true;
        }
        let start = self.g.starts.get(cur).copied().unwrap_or(0);
        let first_line = self.lines.len();
        let (stmts, cond, taken) = match self.code.get(cur) {
            Some(c) => (c.stmts.clone(), c.cond.clone(), c.taken),
            None => (Vec::new(), None, None),
        };
        for s in stmts {
            self.push(indent, s);
        }
        if let Some(l) = self.lines.get_mut(first_line) {
            l.label = Some(start);
        } else {
            self.pending_label = Some(start);
        }
        let succs = self.g.succs.get(cur).cloned().unwrap_or_default();
        match succs.as_slice() {
            [] => None,
            [s] => match self.edge(*s) {
                Edge::Continue => {
                    self.push(indent, "continue;");
                    None
                }
                Edge::Break => {
                    self.push(indent, "break;");
                    None
                }
                Edge::To(t) => Some(t),
            },
            _ => {
                let taken_idx = taken.and_then(|t| self.g.starts.iter().position(|s| *s == t));
                let Some(t) = taken_idx.filter(|t| succs.contains(t)) else {
                    // switch / multiway: one case per target
                    let selector = match self.lines.last() {
                        Some(l) if l.text.starts_with("goto *") && l.label.is_none() => {
                            let sel = l.text.trim_start_matches("goto *").split(';').next().unwrap_or("").to_string();
                            self.lines.pop();
                            sel
                        }
                        _ => "/* computed */".to_string(),
                    };
                    self.push(indent, format!("switch ({selector}) {{"));
                    for s in succs {
                        let st = self.g.starts.get(s).copied().unwrap_or(0);
                        self.push(indent + 1, format!("case_{st:x}:"));
                        match self.edge(s) {
                            Edge::Continue => self.push(indent + 2, "continue;"),
                            Edge::Break => self.push(indent + 2, "break;"),
                            Edge::To(x) => {
                                if self.emitted.get(x).copied().unwrap_or(true) {
                                    self.goto(indent + 2, x);
                                } else {
                                    let join = self.g.ipdom.get(cur).copied().flatten();
                                    self.region(Some(x), join, indent + 2, depth + 1);
                                    if !self.lines.last().is_some_and(|l| l.text.starts_with("return") || l.text.starts_with("goto ")) {
                                        self.push(indent + 2, "break;");
                                    }
                                }
                            }
                        }
                    }
                    self.push(indent, "}");
                    return self.g.ipdom.get(cur).copied().flatten().filter(|j| !self.emitted.get(*j).copied().unwrap_or(true));
                };
                let f = succs.iter().copied().find(|s| *s != t).unwrap_or(t);
                let cond = cond.unwrap_or_else(|| "/* condition */ flags".into());
                let join =
                    self.g.ipdom.get(cur).copied().flatten().filter(|j| self.in_current_loop(*j) || self.loop_stack.last().and_then(|(_, f)| *f) == Some(*j));
                let arm = |me: &mut Self, x: usize, ind: usize| -> bool {
                    // returns true when something was emitted
                    match me.edge(x) {
                        Edge::Continue => {
                            me.push(ind, "continue;");
                            true
                        }
                        Edge::Break => {
                            me.push(ind, "break;");
                            true
                        }
                        Edge::To(y) => {
                            if Some(y) == join {
                                false
                            } else {
                                let before = me.lines.len();
                                me.region(Some(y), join, ind, depth + 1);
                                me.lines.len() > before
                            }
                        }
                    }
                };
                let jumpy = |e: &Edge| matches!(e, Edge::Continue | Edge::Break);
                let (et, ef) = (self.edge(t), self.edge(f));
                if jumpy(&et) && jumpy(&ef) {
                    let word = |e: &Edge| if matches!(e, Edge::Break) { "break;" } else { "continue;" };
                    if matches!(et, Edge::Break) {
                        self.push(indent, format!("if ({cond}) {}", word(&et)));
                        self.push(indent, word(&ef));
                    } else {
                        self.push(indent, format!("if ({}) {}", cond_negate_text(&cond), word(&ef)));
                        self.push(indent, word(&et));
                    }
                    return None;
                }
                let t_empty = matches!(self.edge(t), Edge::To(y) if Some(y) == join);
                let f_empty = matches!(self.edge(f), Edge::To(y) if Some(y) == join);
                if t_empty && f_empty {
                    // both go to the join: nothing to branch on
                } else if t_empty {
                    self.push(indent, format!("if ({}) {{", cond_negate_text(&cond)));
                    arm(self, f, indent + 1);
                    self.push(indent, "}");
                } else if f_empty {
                    self.push(indent, format!("if ({cond}) {{"));
                    arm(self, t, indent + 1);
                    self.push(indent, "}");
                } else {
                    self.push(indent, format!("if ({cond}) {{"));
                    arm(self, t, indent + 1);
                    self.push(indent, "} else {");
                    arm(self, f, indent + 1);
                    self.push(indent, "}");
                }
                match join {
                    Some(j) => match self.edge(j) {
                        Edge::Continue => None,
                        Edge::Break => {
                            self.push(indent, "break;");
                            None
                        }
                        Edge::To(j) => Some(j),
                    },
                    None => None,
                }
            }
        }
    }
}

fn simplify(lines: &mut Vec<Line>) {
    // `} else {` directly followed by `}` → `}`; `if (c) {` directly followed by `}` → nothing.
    let mut changed = true;
    while changed {
        changed = false;
        let mut i = 0;
        while i + 1 < lines.len() {
            let (Some(a), Some(b)) = (lines.get(i), lines.get(i + 1)) else { break };
            if b.text == "}" && a.indent == b.indent && a.label.is_none() && b.label.is_none() && !b.loop_end {
                if a.text == "} else {" {
                    lines.remove(i);
                    changed = true;
                    continue;
                }
                if a.text.starts_with("if (") && a.text.ends_with(") {") {
                    lines.drain(i..i + 2);
                    changed = true;
                    continue;
                }
            }
            i += 1;
        }
    }
    // `if (c) { break; }` → `if (c) break;`
    let mut out: Vec<Line> = Vec::with_capacity(lines.len());
    let mut i = 0;
    while i < lines.len() {
        if let (Some(a), Some(b), Some(c)) = (lines.get(i), lines.get(i + 1), lines.get(i + 2))
            && a.text.starts_with("if (")
            && a.text.ends_with(") {")
            && matches!(b.text.as_str(), "break;" | "continue;" | "return;")
            && c.text == "}"
            && c.indent == a.indent
            && b.label.is_none()
        {
            let head = a.text.trim_end_matches(" {");
            out.push(Line { indent: a.indent, text: format!("{head} {}", b.text), label: a.label, loop_end: false });
            i += 3;
            continue;
        }
        if let Some(l) = lines.get(i) {
            out.push(l.clone());
        }
        i += 1;
    }
    *lines = out;
}

/// Lift `f` to pseudo-C. `names` resolves user-given names (annotations) first.
pub fn lift(img: &Image, prog: &Program, f: &Function, names: &dyn Fn(u64) -> Option<String>) -> Pseudo {
    let mode = prog.mode;
    let arg_regs: &'static [&'static str] = match mode {
        Mode::X64 if img.bin.format == Format::Pe => &["rcx", "rdx", "r8", "r9"],
        Mode::X64 => &["rdi", "rsi", "rdx", "rcx", "r8", "r9"],
        Mode::A64 => &["x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7"],
        Mode::A32 | Mode::T32 => &["r0", "r1", "r2", "r3"],
        _ => &[],
    };
    let mut limitations: Vec<(String, String)> = vec![
        ("register_level".into(), "variables are machine registers and stack slots; types are not recovered".into()),
        ("calling_convention_assumed".into(), format!("call arguments follow the usual {} convention and may be wrong for unusual functions", mode.name())),
        ("conditions_from_flags".into(), "branch conditions are rebuilt from the last compare and may be approximate".into()),
    ];
    // Decode every block.
    let mut per_block: Vec<Vec<Insn>> = Vec::new();
    for b in &f.blocks {
        let mut v = Vec::new();
        let mut consts = ArmConsts::default();
        let mut a = b.start;
        while a < b.end && v.len() < 20_000 {
            let Some(mut i) = img.decode(a, true) else { break };
            if mode == Mode::A64 {
                consts.apply(&mut i);
            }
            a = i.end();
            v.push(i);
        }
        per_block.push(v);
    }
    // Return register: the widest name written to the return register anywhere.
    let ret_canon = if mode == Mode::A64 {
        "x0"
    } else if matches!(mode, Mode::A32 | Mode::T32) {
        "r0"
    } else {
        "rax"
    };
    let mut ret_reg = String::new();
    'outer: for v in per_block.iter().rev() {
        for i in v.iter().rev() {
            if matches!(i.flow, Flow::Call { .. } | Flow::IndirectCall { .. }) {
                ret_reg = ret_canon.into();
                break 'outer;
            }
            if i.writes.iter().any(|w| w == ret_canon)
                && let Some(Op::Reg(r)) = i.ops.first()
            {
                ret_reg = r.clone();
                break 'outer;
            }
        }
    }
    // Parameters: argument registers read before written in the entry block.
    let mut params = Vec::new();
    if let Some(entry_block) = per_block.first() {
        let mut written: BTreeSet<String> = BTreeSet::new();
        for i in entry_block {
            if matches!(i.flow, Flow::Call { .. } | Flow::IndirectCall { .. }) {
                break;
            }
            for r in &i.reads {
                if arg_regs.contains(&r.as_str()) && !written.contains(r) && !params.contains(r) {
                    params.push(r.clone());
                }
            }
            written.extend(i.writes.iter().cloned());
        }
    }
    params.sort_by_key(|p| arg_regs.iter().position(|r| r == p).unwrap_or(99));
    let name = names(f.entry).unwrap_or_else(|| f.name.clone());
    let ret_ty = if ret_reg.is_empty() {
        "void"
    } else if ret_reg.starts_with('e') || ret_reg.starts_with('w') {
        "int32_t"
    } else {
        "int64_t"
    };
    let signature = format!("{ret_ty} {name}({})", params.iter().map(|p| format!("int64_t {p}")).collect::<Vec<_>>().join(", "));
    let win64 = mode == Mode::X64 && img.bin.format == Format::Pe;
    let mut lifter =
        Lifter { img, prog, names, mode, arg_regs, win64, tail_calls: &f.tail_calls, ret_reg, calls: BTreeSet::new(), strings: Vec::new(), asm_fallbacks: 0 };
    let n = f.blocks.len();
    let codes: Vec<BlockCode> = per_block
        .iter()
        .zip(&f.blocks)
        .map(|(v, b)| {
            let edge = b.start == f.entry || b.succs.is_empty();
            lifter.block(v, edge)
        })
        .collect();
    let structured_ok = n <= MAX_STRUCTURED_BLOCKS;
    let graph = if structured_ok {
        build_graph(f)
    } else {
        Graph { starts: f.blocks.iter().map(|b| b.start).collect(), succs: vec![], idom: vec![], ipdom: vec![], dom: vec![], loops: BTreeMap::new() }
    };
    let mut emitter = Emitter {
        g: &graph,
        code: &codes,
        emitted: vec![false; n],
        lines: Vec::new(),
        labels: BTreeSet::new(),
        gotos: 0,
        loop_stack: Vec::new(),
        pending_label: None,
    };
    if structured_ok {
        let entry = graph.starts.iter().position(|s| *s == f.entry).unwrap_or(0);
        emitter.region(Some(entry), None, 1, 0);
        // Anything unreachable from the entry (e.g. only via unresolved jumps) goes after.
        for i in 0..n {
            if !emitter.emitted.get(i).copied().unwrap_or(true) {
                emitter.region(Some(i), None, 1, 0);
            }
        }
    } else {
        limitations.push(("not_structured".into(), format!("{n} blocks is above the structuring limit; shown as labelled blocks with gotos")));
        for (i, b) in f.blocks.iter().enumerate() {
            let first = emitter.lines.len();
            for s in codes.get(i).map(|c| c.stmts.clone()).unwrap_or_default() {
                emitter.push(1, s);
            }
            if let Some(c) = codes.get(i)
                && let (Some(cond), Some(t)) = (&c.cond, c.taken)
            {
                emitter.labels.insert(t);
                emitter.gotos += 1;
                emitter.push(1, format!("if ({cond}) goto label_{t:x};"));
            }
            if emitter.lines.len() == first {
                emitter.push(1, ";");
            }
            if let Some(l) = emitter.lines.get_mut(first) {
                l.label = Some(b.start);
            }
            emitter.labels.insert(b.start);
        }
    }
    let _ = (&graph.idom, &graph.dom);
    if emitter.pending_label.is_some() {
        emitter.push(1, ";");
    }
    let mut lines = std::mem::take(&mut emitter.lines);
    simplify(&mut lines);
    let mut text = format!("{signature}\n{{\n");
    for l in &lines {
        if let Some(lab) = l.label
            && emitter.labels.contains(&lab)
        {
            text.push_str(&format!("label_{lab:x}:\n"));
        }
        let _ = l.loop_end;
        text.push_str(&"    ".repeat(l.indent));
        text.push_str(&l.text);
        text.push('\n');
    }
    text.push_str("}\n");
    if emitter.gotos > 0 {
        limitations.push(("unstructured_flow".into(), format!("{} gotos remain where the control flow isn't a simple if/loop", emitter.gotos)));
    }
    if lifter.asm_fallbacks > 0 {
        limitations.push(("inline_asm".into(), format!("{} instructions have no C rule and are shown as __asm(...)", lifter.asm_fallbacks)));
    }
    if f.unresolved_indirect_jumps > 0 {
        limitations.push(("indirect_jumps_unresolved".into(), "some indirect jumps were not resolved, so code may be missing".into()));
    }
    if f.truncated {
        limitations.push(("function_truncated".into(), "the function hit the instruction limit; the end is missing".into()));
    }
    Pseudo {
        signature,
        text,
        calls: lifter.calls.into_iter().collect(),
        strings: lifter.strings,
        gotos: emitter.gotos,
        asm_fallbacks: lifter.asm_fallbacks,
        structured: structured_ok && emitter.gotos == 0,
        limitations,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::NoControl;
    use crate::program::Limits;
    use craft_anything_testkit as tk;
    use std::sync::Arc;

    fn setup(bytes: Vec<u8>) -> (Image, Program) {
        let img = Image::parse(Arc::from(bytes)).unwrap();
        let p = Program::analyze(&img, &Limits::default(), &NoControl).unwrap();
        (img, p)
    }

    #[test]
    fn calls_into_known_imports_show_their_arguments() {
        // pe64 reuses the System V code, so nothing loads rcx before `puts`: Win64's first argument
        // register. The call still has its one argument, shown as the register.
        let (img, p) = setup(tk::pe64());
        let none = |_: u64| None;
        let entry = img.bin.entry.unwrap();
        let f = p.functions.get(&entry).unwrap();
        let text = lift(&img, &p, f, &none).text;
        assert!(text.contains("puts(rcx)"), "{text}");
        assert!(!text.contains("puts()"), "{text}");
    }

    #[test]
    fn main_and_helper_read_like_c() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let (img, p) = setup(elf);
        let none = |_: u64| None;
        let main = lift(&img, &p, p.function_by_name("main").unwrap(), &none);
        assert!(main.text.contains("puts(\"Hello, Craft!\")"), "{}", main.text);
        assert!(main.text.contains("helper(5)"), "{}", main.text);
        assert!(main.calls.contains(&"dispatch".to_string()));
        assert_eq!(main.strings, vec![tk::HELLO.to_string()]);
        let helper = lift(&img, &p, p.function_by_name("helper").unwrap(), &none);
        assert!(helper.text.contains("while (true)"), "{}", helper.text);
        assert!(helper.text.contains("if (edi"), "{}", helper.text);
        assert!(helper.signature.contains("edi") || helper.signature.contains("rdi"), "{}", helper.signature);
        assert!(helper.structured, "{}", helper.text);
        let renamed = |a: u64| (a == p.function_by_name("helper").unwrap().entry).then(|| "sum_to".to_string());
        let main2 = lift(&img, &p, p.function_by_name("main").unwrap(), &renamed);
        assert!(main2.text.contains("sum_to(5)"), "{}", main2.text);
        let d = lift(&img, &p, p.function_by_name("dispatch").unwrap(), &none);
        assert!(d.text.contains("return"), "{}", d.text);
    }

    #[test]
    fn win64_stack_args_and_tail_call() {
        // main, patched: six arguments to the `puts` import (four in registers, two on the
        // stack), then a tail jump to `helper`.
        let mut pe = tk::pe64();
        let code: [u8; 58] = [
            0x48, 0x83, 0xec, 0x68, // sub rsp, 0x68
            0x48, 0xc7, 0x44, 0x24, 0x28, 0x07, 0x00, 0x00, 0x00, // mov qword [rsp+0x28], 7
            0xc7, 0x44, 0x24, 0x20, 0x05, 0x00, 0x00, 0x00, // mov dword [rsp+0x20], 5
            0x41, 0xb9, 0x04, 0x00, 0x00, 0x00, // mov r9d, 4
            0x41, 0xb8, 0x03, 0x00, 0x00, 0x00, // mov r8d, 3
            0xba, 0x02, 0x00, 0x00, 0x00, // mov edx, 2
            0xb9, 0x01, 0x00, 0x00, 0x00, // mov ecx, 1
            0xff, 0x15, 0x2f, 0x11, 0x00, 0x00, // call [rip+0x112f] (the puts IAT slot)
            0x48, 0x83, 0xc4, 0x68, // add rsp, 0x68
            0xe9, 0x06, 0x00, 0x00, 0x00, // jmp helper
        ];
        pe[0x400..0x400 + code.len()].copy_from_slice(&code);
        let (img, p) = setup(pe);
        let main = p.functions.get(&(tk::PE_BASE + tk::PE_TEXT_RVA)).unwrap();
        let out = lift(&img, &p, main, &|_| None);
        assert!(out.text.contains("puts(1, 2, 3, 4, 5, 7);"), "{}", out.text);
        assert!(!out.text.contains("stack_20"), "{}", out.text);
        assert!(out.text.contains("return helper();"), "{}", out.text);
        assert!(out.calls.contains(&"helper".to_string()));
    }

    #[test]
    fn aarch64_lifts() {
        let (elf, _) = tk::elf64(tk::ElfArch::Aarch64, true);
        let (img, p) = setup(elf);
        let none = |_: u64| None;
        let main = lift(&img, &p, p.function_by_name("main").unwrap(), &none);
        assert!(main.text.contains("puts(\"Hello, Craft!\")"), "{}", main.text);
        let helper = lift(&img, &p, p.function_by_name("helper").unwrap(), &none);
        assert!(helper.text.contains("w0 == 0") || helper.text.contains("w0 != 0"), "{}", helper.text);
    }

    #[test]
    fn every_function_of_damaged_inputs_lifts_without_panicking() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, false);
        for m in tk::mutations(&elf).into_iter().step_by(3) {
            if let Ok(img) = Image::parse(Arc::from(m))
                && let Ok(p) = Program::analyze(&img, &Limits::default(), &NoControl)
            {
                for f in p.functions.values() {
                    let _ = lift(&img, &p, f, &|_| None);
                }
            }
        }
        for seed in 0..12 {
            let raw = Image::raw(Arc::from(tk::noise(seed, 2048)), craft_anything_formats::Arch::X86_64, 0x1000);
            if let Ok(p) = Program::analyze(&raw, &Limits::default(), &NoControl) {
                for f in p.functions.values().take(50) {
                    let _ = lift(&raw, &p, f, &|_| None);
                }
            }
        }
    }

    #[test]
    fn arm32_calls_keep_their_return_value_in_r0() {
        use craft_anything_formats::Arch;
        fn words(ws: &[u32]) -> Vec<u8> {
            ws.iter().flat_map(|w| w.to_le_bytes()).collect()
        }
        fn arm_elf(code: &[u8], thumb: bool) -> Vec<u8> {
            let mut b = vec![0u8; 0x100];
            b[0..7].copy_from_slice(b"\x7fELF\x01\x01\x01");
            for (o, v) in [(16, 2u16), (18, 40), (40, 52), (42, 32), (44, 1)] {
                b[o..o + 2].copy_from_slice(&v.to_le_bytes());
            }
            let n = code.len() as u32;
            for (o, v) in [(20, 1u32), (24, 0x1000 | u32::from(thumb)), (28, 52), (36, 0x0500_0000), (52, 1)] {
                b[o..o + 4].copy_from_slice(&v.to_le_bytes());
            }
            for (o, v) in [(56, 0x100u32), (60, 0x1000), (64, 0x1000), (68, n), (72, n), (76, 5), (80, 0x100)] {
                b[o..o + 4].copy_from_slice(&v.to_le_bytes());
            }
            b.extend_from_slice(code);
            b
        }
        fn lift_entry(image: Image) -> String {
            let program = Program::analyze(&image, &Limits::default(), &NoControl).unwrap();
            let f = program.functions.get(&0x1000).unwrap();
            lift(&image, &program, f, &|_| None).text
        }

        let call_ret = words(&[0xe92d_4010, 0xeb00_0001, 0xe8bd_8010, 0xe320_f000, 0xe3a0_0007, 0xe12f_ff1e]);
        let used_call = words(&[0xe92d_4010, 0xeb00_0002, 0xe280_1001, 0xe1a0_0001, 0xe8bd_8010, 0xe3a0_0007, 0xe12f_ff1e]);
        let leaf = words(&[0xe3a0_0007, 0xe12f_ff1e]);

        let ar = lift_entry(Image::raw(Arc::from(call_ret.clone()), Arch::Arm, 0x1000));
        let au = lift_entry(Image::raw(Arc::from(used_call), Arch::Arm, 0x1000));
        let al = lift_entry(Image::raw(Arc::from(leaf), Arch::Arm, 0x1000));
        let ae = lift_entry(Image::parse(Arc::from(arm_elf(&call_ret, false))).unwrap());
        let tr = lift_entry(Image::parse(Arc::from(arm_elf(&[0x10, 0xb5, 0x98, 0x47, 0x10, 0xbd], true))).unwrap());

        assert!(ar.contains("return r0;") && !ar.contains("rax"), "{ar}");
        assert!(ae.contains("return r0;") && !ae.contains("rax"), "{ae}");
        assert!(tr.contains("return r0;") && !tr.contains("rax"), "{tr}");
        assert!(au.contains("r0 = sub_1014();") && au.contains("r1 = r0 + 1;") && au.contains("return r0;"), "{au}");
        assert!(al.contains("r0 = 7;") && al.contains("return r0;") && !al.contains("rax"), "{al}");
    }

    /// #277: ARM32 loads and stores came out as `r0 = 0;` and `0 = r0;`.
    #[test]
    fn arm32_loads_and_stores_keep_their_addresses() {
        use craft_anything_formats::Arch;
        let lift_words = |ws: &[u32]| {
            let bytes: Vec<u8> = ws.iter().flat_map(|w| w.to_le_bytes()).collect();
            let image = Image::raw(Arc::from(bytes), Arch::Arm, 0x1000);
            let program = Program::analyze(&image, &Limits::default(), &NoControl).unwrap();
            let f = program.functions.get(&0x1000).unwrap();
            lift(&image, &program, f, &|_| None)
        };
        // ldr r0, [r1, #4]; str r0, [r2]; bx lr
        let p = lift_words(&[0xe591_0004, 0xe582_0000, 0xe12f_ff1e]);
        assert!(p.text.contains("r0 = *(uint32_t*)(r1 + 4);") && p.text.contains("*(uint32_t*)(r2) = r0;"), "{}", p.text);
        assert_eq!(p.asm_fallbacks, 0);
        // ldr r0, [r1, #-8]
        let p = lift_words(&[0xe511_0008, 0xe12f_ff1e]);
        assert!(p.text.contains("r0 = *(uint32_t*)(r1 - 8);"), "{}", p.text);
        // ldr r0, [r1], #4 also moves r1, which no statement here says: it's shown as written.
        let p = lift_words(&[0xe491_0004, 0xe12f_ff1e]);
        assert!(p.text.contains("__asm(") && !p.text.contains("r0 = 0;") && p.asm_fallbacks == 1, "{}", p.text);
        let i = crate::decode::decode(Mode::A32, &0xe591_0004u32.to_le_bytes(), 0x1000, false).unwrap();
        assert!(i.reads.contains(&"r1".to_string()) && i.writes == ["r0"], "{i:?}");
    }
}
