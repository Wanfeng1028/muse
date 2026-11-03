//! A best-effort decompiler from JVM bytecode to structured pseudo-Java.
//!
//! It runs a symbolic stack simulation over a method's instructions to recover expressions (field
//! access, method calls with names, literals, `new`, arrays, arithmetic, casts) and statements,
//! then applies a light control-flow structurer that recognises the shapes `javac` emits:
//! forward `if`/`if`-`else`, `while` loops, `switch` (inlined cases) and `try`/`catch` from the
//! exception table. Anything it cannot structure degrades to explicit labels and `goto`s rather
//! than guessing.
//!
//! The result is honest: confidence is always [`Confidence::Inferred`], `fully_structured` says
//! whether any `goto`s remained, and the limitations spell out what is lost (generics are erased,
//! lambda/`invokedynamic` desugaring and synthetic members are not reconstructed, local names and
//! types are not recovered). Hostile or truncated code yields a readable fallback, never a panic.

use craft_anything_evidence::{Confidence, Limitation};
use craft_anything_formats::java_class::{self, ClassFile, Member};
use craft_anything_formats::java_ops::{self, Insn};
use std::collections::{BTreeMap, BTreeSet};

/// The decompilation of one method.
#[derive(Debug, Clone)]
pub struct MethodDecompile {
    pub signature: String,
    /// The `{ … }` body as pseudo-Java (already indented).
    pub body: String,
    pub confidence: Confidence,
    pub limitations: Vec<Limitation>,
    /// True when no `goto`/label fallbacks remained.
    pub fully_structured: bool,
}

/// The decompilation of a whole class.
#[derive(Debug, Clone)]
pub struct ClassDecompile {
    pub source: String,
    pub confidence: Confidence,
    pub limitations: Vec<Limitation>,
    pub fully_structured: bool,
}

// ---------------------------------------------------------------------------------------------
// Intermediate nodes

#[derive(Debug, Clone)]
enum Cmp {
    Eq,
    Ne,
    Lt,
    Ge,
    Gt,
    Le,
}

impl Cmp {
    fn op(&self) -> &'static str {
        match self {
            Cmp::Eq => "==",
            Cmp::Ne => "!=",
            Cmp::Lt => "<",
            Cmp::Ge => ">=",
            Cmp::Gt => ">",
            Cmp::Le => "<=",
        }
    }
    /// The negation (the source condition when `javac` branches to skip a block).
    fn negate(&self) -> Cmp {
        match self {
            Cmp::Eq => Cmp::Ne,
            Cmp::Ne => Cmp::Eq,
            Cmp::Lt => Cmp::Ge,
            Cmp::Ge => Cmp::Lt,
            Cmp::Gt => Cmp::Le,
            Cmp::Le => Cmp::Gt,
        }
    }
}

#[derive(Debug, Clone)]
struct Cond {
    left: String,
    cmp: Cmp,
    right: String,
}

impl Cond {
    fn render(&self, negate: bool) -> String {
        let cmp = if negate { self.cmp.negate() } else { self.cmp.clone() };
        format!("{} {} {}", self.left, cmp.op(), self.right)
    }
}

#[derive(Debug, Clone)]
enum Node {
    Stmt(String),
    If {
        cond: Cond,
        target: i64,
    },
    Goto(i64),
    Switch {
        expr: String,
        cases: Vec<(Option<i32>, i64)>,
    },
    Return(Option<String>),
    Throw(String),
    /// An opcode we could not model; kept as an annotation.
    Raw(String),
}

// ---------------------------------------------------------------------------------------------
// Symbolic simulation

struct Sim<'a> {
    cf: &'a ClassFile,
    is_static: bool,
    stack: Vec<String>,
    nodes: Vec<(u32, Node)>,
    lossy: bool,
}

fn simple_name(internal: &str) -> String {
    internal.rsplit('/').next().unwrap_or(internal).to_string()
}

impl<'a> Sim<'a> {
    fn pop(&mut self) -> String {
        match self.stack.pop() {
            Some(s) => s,
            None => {
                self.lossy = true;
                "?".to_string()
            }
        }
    }
    fn push(&mut self, s: String) {
        self.stack.push(s);
    }
    fn emit(&mut self, pc: u32, n: Node) {
        self.nodes.push((pc, n));
    }
    fn local(&self, n: u16) -> String {
        if !self.is_static && n == 0 { "this".to_string() } else { format!("v{n}") }
    }

    /// Simulate one instruction.
    fn step(&mut self, i: &Insn) {
        let pc = i.pc;
        let op = i.opcode;
        match op {
            0x00 => {} // nop
            0x01 => self.push("null".into()),
            0x02 => self.push("-1".into()),
            0x03..=0x08 => self.push(format!("{}", i32::from(op) - 0x03)),
            0x09 | 0x0a => self.push(format!("{}L", op - 0x09)),
            0x0b..=0x0d => self.push(format!("{}.0f", op - 0x0b)),
            0x0e | 0x0f => self.push(format!("{}.0", op - 0x0e)),
            0x10 | 0x11 => self.push(format!("{}", i.int.unwrap_or(0))),
            0x12..=0x14 => self.push(self.cf.format_insn(i).trim_start_matches(i.name).trim().to_string()),
            0x15..=0x19 => self.push(self.local(i.local.unwrap_or(0))), // *load
            0x1a..=0x1d => self.push(self.local(u16::from(op) - 0x1a)), // iload_0..3
            0x1e..=0x21 => self.push(self.local(u16::from(op) - 0x1e)), // lload_0..3
            0x22..=0x25 => self.push(self.local(u16::from(op) - 0x22)), // fload_0..3
            0x26..=0x29 => self.push(self.local(u16::from(op) - 0x26)), // dload_0..3
            0x2a..=0x2d => self.push(self.local(u16::from(op) - 0x2a)), // aload_0..3
            0x2e..=0x35 => {
                let idx = self.pop();
                let arr = self.pop();
                self.push(format!("{arr}[{idx}]"));
            }
            0x36..=0x3a => {
                let v = self.pop();
                let name = self.local(i.local.unwrap_or(0));
                self.emit(pc, Node::Stmt(format!("{name} = {v};")));
            }
            0x3b..=0x3e => self.store(pc, u16::from(op) - 0x3b), // istore_0..3
            0x3f..=0x42 => self.store(pc, u16::from(op) - 0x3f),
            0x43..=0x46 => self.store(pc, u16::from(op) - 0x43),
            0x47..=0x4a => self.store(pc, u16::from(op) - 0x47),
            0x4b..=0x4e => self.store(pc, u16::from(op) - 0x4b), // astore_0..3
            0x4f..=0x56 => {
                let v = self.pop();
                let idx = self.pop();
                let arr = self.pop();
                self.emit(pc, Node::Stmt(format!("{arr}[{idx}] = {v};")));
            }
            0x57 | 0x58 => {
                // pop/pop2: if the discarded value is a call, keep it as a statement for its effect.
                let v = self.pop();
                if v.contains('(') {
                    self.emit(pc, Node::Stmt(format!("{v};")));
                }
            }
            0x59 => {
                let v = self.pop();
                self.push(v.clone());
                self.push(v);
            }
            0x5a..=0x5e => self.lossy = true, // dup_x1/dup2/… — stack shuffles we don't model precisely
            0x5f => {
                let a = self.pop();
                let b = self.pop();
                self.push(a);
                self.push(b);
            }
            0x60..=0x73 => self.binop(op),
            0x74..=0x77 => {
                let a = self.pop();
                self.push(format!("(-{a})"));
            }
            0x78..=0x83 => self.binop(op),
            0x84 => {
                let name = self.local(i.local.unwrap_or(0));
                let k = i.int.unwrap_or(0);
                if k >= 0 {
                    self.emit(pc, Node::Stmt(format!("{name} += {k};")));
                } else {
                    self.emit(pc, Node::Stmt(format!("{name} -= {};", -k)));
                }
            }
            0x85..=0x93 => self.cast(op),
            0x94..=0x98 => {
                let b = self.pop();
                let a = self.pop();
                self.push(format!("Double.compare({a}, {b})"));
            }
            0x99..=0x9e => self.if_zero(pc, op, i.branch),
            0x9f..=0xa4 => self.if_icmp(pc, op, i.branch),
            0xa5 | 0xa6 => {
                let b = self.pop();
                let a = self.pop();
                let cmp = if op == 0xa5 { Cmp::Eq } else { Cmp::Ne };
                self.emit(pc, Node::If { cond: Cond { left: a, cmp, right: b }, target: i.branch.unwrap_or(0) });
            }
            0xa7 | 0xc8 => self.emit(pc, Node::Goto(i.branch.unwrap_or(0))),
            0xa8 | 0xa9 | 0xc9 => {
                // jsr/ret: old-style finally. We cannot structure these.
                self.lossy = true;
                self.emit(pc, Node::Raw(format!("// {}", self.cf.format_insn(i))));
            }
            0xaa | 0xab => {
                let expr = self.pop();
                let cases = match &i.switch {
                    Some(sw) => {
                        let mut v: Vec<(Option<i32>, i64)> = sw.pairs.iter().map(|(k, t)| (Some(*k), *t)).collect();
                        v.push((None, sw.default));
                        v
                    }
                    None => Vec::new(),
                };
                self.emit(pc, Node::Switch { expr, cases });
            }
            0xac..=0xb0 => {
                let v = self.pop();
                self.emit(pc, Node::Return(Some(v)));
            }
            0xb1 => self.emit(pc, Node::Return(None)),
            0xb2 => self.getstatic(i),
            0xb3 => self.putstatic(pc, i),
            0xb4 => self.getfield(i),
            0xb5 => self.putfield(pc, i),
            0xb6 | 0xb9 => self.invoke_instance(pc, i, false),
            0xb7 => self.invoke_instance(pc, i, true),
            0xb8 => self.invoke_static(pc, i),
            0xba => self.invoke_dynamic(pc, i),
            0xbb => self.push(format!("new {}", self.ref_class(i))),
            0xbc => {
                let n = self.pop();
                let ty = java_ops::array_type(i.int.unwrap_or(0));
                self.push(format!("new {ty}[{n}]"));
            }
            0xbd => {
                let n = self.pop();
                self.push(format!("new {}[{n}]", self.ref_class(i)));
            }
            0xbe => {
                let a = self.pop();
                self.push(format!("{a}.length"));
            }
            0xbf => {
                let v = self.pop();
                self.emit(pc, Node::Throw(v));
            }
            0xc0 => {
                let a = self.pop();
                self.push(format!("({}) {a}", self.ref_class(i)));
            }
            0xc1 => {
                let a = self.pop();
                self.push(format!("({a} instanceof {})", self.ref_class(i)));
            }
            0xc2 => self.emit(pc, Node::Stmt("// monitorenter".into())),
            0xc3 => self.emit(pc, Node::Stmt("// monitorexit".into())),
            0xc5 => {
                // multianewarray: pop `dims` counts
                let dims = i.int.unwrap_or(0).max(0) as usize;
                let mut idx = String::new();
                for _ in 0..dims.min(64) {
                    idx = format!("[{}]{idx}", self.pop());
                }
                self.push(format!("new {}{idx}", self.ref_class(i)));
            }
            0xc6 => self.if_null(pc, Cmp::Eq, i.branch),
            0xc7 => self.if_null(pc, Cmp::Ne, i.branch),
            _ => {
                self.lossy = true;
                self.emit(pc, Node::Raw(format!("// {}", self.cf.format_insn(i))));
            }
        }
    }

    fn store(&mut self, pc: u32, n: u16) {
        let v = self.pop();
        let name = self.local(n);
        self.emit(pc, Node::Stmt(format!("{name} = {v};")));
    }

    fn binop(&mut self, op: u8) {
        let sym = match op {
            0x60..=0x63 => "+",
            0x64..=0x67 => "-",
            0x68..=0x6b => "*",
            0x6c..=0x6f => "/",
            0x70..=0x73 => "%",
            0x78 | 0x79 => "<<",
            0x7a | 0x7b => ">>",
            0x7c | 0x7d => ">>>",
            0x7e | 0x7f => "&",
            0x80 | 0x81 => "|",
            0x82 | 0x83 => "^",
            _ => "?",
        };
        let b = self.pop();
        let a = self.pop();
        self.push(format!("({a} {sym} {b})"));
    }

    fn cast(&mut self, op: u8) {
        let ty = match op {
            0x85 | 0x8c | 0x8f => "long",
            0x86 | 0x89 | 0x90 => "float",
            0x87 | 0x8a | 0x8d => "double",
            0x88 | 0x8b | 0x8e => "int",
            0x91 => "byte",
            0x92 => "char",
            0x93 => "short",
            _ => "?",
        };
        let a = self.pop();
        self.push(format!("({ty}) {a}"));
    }

    fn if_zero(&mut self, pc: u32, op: u8, branch: Option<i64>) {
        let cmp = match op {
            0x99 => Cmp::Eq,
            0x9a => Cmp::Ne,
            0x9b => Cmp::Lt,
            0x9c => Cmp::Ge,
            0x9d => Cmp::Gt,
            _ => Cmp::Le,
        };
        let a = self.pop();
        self.emit(pc, Node::If { cond: Cond { left: a, cmp, right: "0".into() }, target: branch.unwrap_or(0) });
    }

    fn if_icmp(&mut self, pc: u32, op: u8, branch: Option<i64>) {
        let cmp = match op {
            0x9f => Cmp::Eq,
            0xa0 => Cmp::Ne,
            0xa1 => Cmp::Lt,
            0xa2 => Cmp::Ge,
            0xa3 => Cmp::Gt,
            _ => Cmp::Le,
        };
        let b = self.pop();
        let a = self.pop();
        self.emit(pc, Node::If { cond: Cond { left: a, cmp, right: b }, target: branch.unwrap_or(0) });
    }

    fn if_null(&mut self, pc: u32, cmp: Cmp, branch: Option<i64>) {
        let a = self.pop();
        self.emit(pc, Node::If { cond: Cond { left: a, cmp, right: "null".into() }, target: branch.unwrap_or(0) });
    }

    fn ref_class(&self, i: &Insn) -> String {
        i.cp_index.map(|c| simple_name(self.cf.class_dotted(c).replace('.', "/").as_str())).unwrap_or_else(|| "Object".into())
    }

    fn pop_args(&mut self, desc: &str) -> Vec<String> {
        let (params, _) = java_class::method_params(desc);
        let mut args: Vec<String> = (0..params.len()).map(|_| self.pop()).collect();
        args.reverse();
        args
    }

    fn getstatic(&mut self, i: &Insn) {
        match i.cp_index.and_then(|c| self.cf.resolve_ref(c)) {
            Some(r) => self.push(format!("{}.{}", simple_name(&r.owner), r.name)),
            None => self.push("?".into()),
        }
    }
    fn putstatic(&mut self, pc: u32, i: &Insn) {
        let v = self.pop();
        match i.cp_index.and_then(|c| self.cf.resolve_ref(c)) {
            Some(r) => self.emit(pc, Node::Stmt(format!("{}.{} = {v};", simple_name(&r.owner), r.name))),
            None => self.emit(pc, Node::Stmt(format!("? = {v};"))),
        }
    }
    fn getfield(&mut self, i: &Insn) {
        let recv = self.pop();
        match i.cp_index.and_then(|c| self.cf.resolve_ref(c)) {
            Some(r) => self.push(format!("{recv}.{}", r.name)),
            None => self.push(format!("{recv}.?")),
        }
    }
    fn putfield(&mut self, pc: u32, i: &Insn) {
        let v = self.pop();
        let recv = self.pop();
        match i.cp_index.and_then(|c| self.cf.resolve_ref(c)) {
            Some(r) => self.emit(pc, Node::Stmt(format!("{recv}.{} = {v};", r.name))),
            None => self.emit(pc, Node::Stmt(format!("{recv}.? = {v};"))),
        }
    }

    fn invoke_instance(&mut self, pc: u32, i: &Insn, special: bool) {
        let Some(r) = i.cp_index.and_then(|c| self.cf.resolve_ref(c)) else {
            self.lossy = true;
            return;
        };
        let args = self.pop_args(&r.descriptor);
        let recv = self.pop();
        let (_, ret) = java_class::method_params(&r.descriptor);
        if special && r.name == "<init>" {
            let call = format!("new {}({})", simple_name(&r.owner), args.join(", "));
            // Collapse the preceding `new`/`dup` placeholder if it is still on the stack.
            if self.stack.last().map(|s| s.starts_with("new ")).unwrap_or(false) {
                self.stack.pop();
            }
            self.push(call);
            return;
        }
        let recv_txt = if special && self.cf.super_class.as_deref() == Some(r.owner.as_str()) { "super".to_string() } else { recv };
        let call = format!("{recv_txt}.{}({})", r.name, args.join(", "));
        if ret == "void" {
            self.emit(pc, Node::Stmt(format!("{call};")));
        } else {
            self.push(call);
        }
    }

    fn invoke_static(&mut self, pc: u32, i: &Insn) {
        let Some(r) = i.cp_index.and_then(|c| self.cf.resolve_ref(c)) else {
            self.lossy = true;
            return;
        };
        let args = self.pop_args(&r.descriptor);
        let (_, ret) = java_class::method_params(&r.descriptor);
        let call = format!("{}.{}({})", simple_name(&r.owner), r.name, args.join(", "));
        if ret == "void" {
            self.emit(pc, Node::Stmt(format!("{call};")));
        } else {
            self.push(call);
        }
    }

    fn invoke_dynamic(&mut self, pc: u32, i: &Insn) {
        self.lossy = true;
        let (name, desc) = match i.cp_index {
            Some(c) => match self.cf.name_and_type_of_indy(c) {
                Some(nt) => nt,
                None => ("lambda".into(), "()".into()),
            },
            None => ("lambda".into(), "()".into()),
        };
        let (params, ret) = java_class::method_params(&desc);
        let args: Vec<String> = (0..params.len()).map(|_| self.pop()).rev().collect();
        let call = format!("{name}({}) /* invokedynamic */", args.join(", "));
        if ret == "void" {
            self.emit(pc, Node::Stmt(format!("{call};")));
        } else {
            self.push(call);
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Structuring

struct Structurer {
    nodes: Vec<(u32, Node)>,
    pc_to_idx: BTreeMap<u32, usize>,
    used_labels: BTreeSet<u32>,
    fully: bool,
    /// Where the current `render_if` tells its caller to continue.
    after_if: usize,
}

impl Structurer {
    fn new(nodes: Vec<(u32, Node)>) -> Self {
        let pc_to_idx = nodes.iter().enumerate().map(|(i, (pc, _))| (*pc, i)).collect();
        Structurer { nodes, pc_to_idx, used_labels: BTreeSet::new(), fully: true, after_if: 0 }
    }

    /// Index of the first node at or after the byte offset `target` (may be `nodes.len()`).
    fn idx_of(&self, target: i64) -> Option<usize> {
        let p = u32::try_from(target).ok()?;
        Some(self.nodes.partition_point(|(pc, _)| *pc < p))
    }

    /// The byte offset of the node we would branch to (for a readable label name).
    fn node_pc(&self, idx: usize) -> Option<u32> {
        self.nodes.get(idx).map(|(pc, _)| *pc)
    }

    fn label(pc: u32) -> String {
        format!("L{pc:x}")
    }

    fn pad(indent: usize) -> String {
        "    ".repeat(indent)
    }

    /// Record and render an unstructured jump to `target`.
    fn goto_fallback(&mut self, target: i64) -> String {
        self.fully = false;
        match self.idx_of(target).and_then(|idx| self.node_pc(idx)) {
            Some(pc) => {
                self.used_labels.insert(pc);
                Self::label(pc)
            }
            None => "end".to_string(),
        }
    }

    /// Render nodes `[lo, hi)` at `indent`.
    fn render(&mut self, lo: usize, hi: usize, indent: usize, out: &mut String) {
        let hi = hi.min(self.nodes.len());
        let mut i = lo;
        while i < hi {
            let Some((pc, node)) = self.nodes.get(i).cloned() else { break };
            if self.used_labels.contains(&pc) {
                out.push_str(&format!("{}{}:\n", Self::pad(indent), Self::label(pc)));
            }
            match node {
                Node::If { cond, target } if self.idx_of(target).is_some_and(|t| t > i && t <= hi) => {
                    self.render_if(i, hi, indent, &cond, target, out);
                    i = self.after_if;
                }
                Node::Switch { expr, cases } => {
                    i = self.render_switch(&expr, &cases, i, hi, indent, out);
                }
                Node::If { cond, target } => {
                    // Backward or out-of-range branch: honest labelled fallback.
                    let l = self.goto_fallback(target);
                    out.push_str(&format!("{}if ({}) goto {l};\n", Self::pad(indent), cond.render(false)));
                    i += 1;
                }
                Node::Goto(target) => {
                    let l = self.goto_fallback(target);
                    out.push_str(&format!("{}goto {l};\n", Self::pad(indent)));
                    i += 1;
                }
                Node::Return(Some(v)) => {
                    out.push_str(&format!("{}return {v};\n", Self::pad(indent)));
                    i += 1;
                }
                Node::Return(None) => {
                    out.push_str(&format!("{}return;\n", Self::pad(indent)));
                    i += 1;
                }
                Node::Throw(v) => {
                    out.push_str(&format!("{}throw {v};\n", Self::pad(indent)));
                    i += 1;
                }
                Node::Stmt(s) | Node::Raw(s) => {
                    out.push_str(&format!("{}{s}\n", Self::pad(indent)));
                    i += 1;
                }
            }
        }
    }

    /// Render a forward `if` (with an optional `else`); `after_if` is set to the continue index.
    fn render_if(&mut self, i: usize, hi: usize, indent: usize, cond: &Cond, target: i64, out: &mut String) {
        let tidx = self.idx_of(target).unwrap_or(hi).min(hi);
        // An `else` branch: the node right before the then-block's end is a forward goto.
        let mut then_end = tidx;
        let mut else_end = None;
        if tidx > i + 1
            && let Some((_, Node::Goto(g))) = self.nodes.get(tidx - 1).cloned()
            && let Some(gidx) = self.idx_of(g)
            && gidx >= tidx
            && gidx <= hi
        {
            then_end = tidx - 1;
            else_end = Some(gidx);
        }
        out.push_str(&format!("{}if ({}) {{\n", Self::pad(indent), cond.render(true)));
        self.render(i + 1, then_end, indent + 1, out);
        if let Some(eidx) = else_end {
            out.push_str(&format!("{}}} else {{\n", Self::pad(indent)));
            self.render(tidx, eidx, indent + 1, out);
            out.push_str(&format!("{}}}\n", Self::pad(indent)));
            self.after_if = eidx;
        } else {
            out.push_str(&format!("{}}}\n", Self::pad(indent)));
            self.after_if = tidx;
        }
    }

    /// Render a `switch` with inlined case bodies; returns the index to continue from.
    fn render_switch(&mut self, expr: &str, cases: &[(Option<i32>, i64)], at: usize, hi: usize, indent: usize, out: &mut String) -> usize {
        // Boundaries: the first node at or after each case target, sorted, bounded by hi.
        let mut bounds: Vec<(Option<i32>, usize)> = cases.iter().filter_map(|(k, t)| self.idx_of(*t).map(|idx| (*k, idx.min(hi)))).collect();
        bounds.sort_by_key(|(_, idx)| *idx);
        // Inline case bodies only when every case target is forward and each body ends in a
        // return/throw (so the switch is terminal and nothing after it is lost).
        let terminal = !bounds.is_empty()
            && bounds.iter().all(|(_, idx)| *idx > at)
            && bounds.iter().enumerate().all(|(n, (_, start))| {
                let end = bounds.get(n + 1).map(|(_, e)| *e).unwrap_or(hi).min(hi);
                end > *start && matches!(self.nodes.get(end - 1), Some((_, Node::Return(_))) | Some((_, Node::Throw(_))) | Some((_, Node::Goto(_))))
            });
        if !terminal {
            // Fall back to a readable case→label mapping; the bodies render in the linear flow after.
            self.fully = false;
            out.push_str(&format!("{}switch ({expr}) {{\n", Self::pad(indent)));
            for (k, t) in cases {
                let l = self.goto_fallback(*t);
                match k {
                    Some(k) => out.push_str(&format!("{}case {k}: goto {l};\n", Self::pad(indent + 1))),
                    None => out.push_str(&format!("{}default: goto {l};\n", Self::pad(indent + 1))),
                }
            }
            out.push_str(&format!("{}}}\n", Self::pad(indent)));
            return at + 1;
        }
        out.push_str(&format!("{}switch ({expr}) {{\n", Self::pad(indent)));
        for (n, (key, start)) in bounds.iter().enumerate() {
            let end = bounds.get(n + 1).map(|(_, e)| *e).unwrap_or(hi).min(hi);
            match key {
                Some(k) => out.push_str(&format!("{}case {k}:\n", Self::pad(indent + 1))),
                None => out.push_str(&format!("{}default:\n", Self::pad(indent + 1))),
            }
            self.render(*start, end, indent + 2, out);
        }
        out.push_str(&format!("{}}}\n", Self::pad(indent)));
        hi
    }
}

// ---------------------------------------------------------------------------------------------
// Public entry points

/// Decompile one method body to pseudo-Java.
pub fn decompile_method(cf: &ClassFile, m: &Member) -> MethodDecompile {
    let signature = cf.method_signature(m);
    let mut limitations = base_limitations();
    let Some(code) = &m.code else {
        let body = if m.access & 0x0100 != 0 {
            "{ /* native method: no bytecode */ }".to_string()
        } else if m.access & 0x0400 != 0 {
            "; // abstract".to_string()
        } else {
            "{ }".to_string()
        };
        return MethodDecompile { signature, body, confidence: Confidence::Inferred, limitations, fully_structured: true };
    };
    let (insns, complete) = java_ops::decode(&code.bytecode, 200_000);
    if !complete {
        limitations.push(Limitation::new("listing_incomplete", "The bytecode could not be fully decoded; the tail is omitted."));
    }
    let is_static = m.access & 0x0008 != 0;
    let mut sim = Sim { cf, is_static, stack: Vec::new(), nodes: Vec::new(), lossy: false };
    for ins in &insns {
        sim.step(ins);
    }
    let lossy = sim.lossy;
    let (inner, fully) = structure_body(sim.nodes, &code.exceptions, cf);
    if !fully {
        limitations
            .push(Limitation::new("control_flow_partly_structured", "Some control flow could not be recovered and is shown with labels and goto statements."));
    }
    if lossy {
        limitations.push(Limitation::new(
            "stack_reconstruction_approximate",
            "Some stack operations (complex dup/swap, invokedynamic/lambda, jsr/ret) are approximated; read the bytecode listing for the exact behaviour.",
        ));
    }
    let body = format!("{{\n{inner}}}");
    MethodDecompile { signature, body, confidence: Confidence::Inferred, limitations, fully_structured: fully }
}

fn base_limitations() -> Vec<Limitation> {
    vec![
        Limitation::new(
            "decompiler_inferred",
            "This pseudo-Java is reconstructed from bytecode by Craft Anything's built-in decompiler; it is a best guess, not the original source. The bytecode disassembly is the evidence.",
        ),
        Limitation::new("generics_erased", "Generic type arguments are erased in bytecode and are not shown."),
        Limitation::new("names_and_types_inferred", "Local variables are named v0, v1, … (no debug names); their declared types are not reconstructed."),
        Limitation::new(
            "desugaring_not_reversed",
            "Synthetic members, lambda/invokedynamic desugaring, enum scaffolding and string-switch hashing are not turned back into source.",
        ),
    ]
}

/// Build the indented body text and whether it is fully structured, wrapping try/catch ranges.
fn structure_body(nodes: Vec<(u32, Node)>, exceptions: &[java_class::ExceptionEntry], cf: &ClassFile) -> (String, bool) {
    let mut s = Structurer::new(nodes);
    s.after_if = 0;
    let n = s.nodes.len();
    let mut out = String::new();
    // Try a single clean try/catch wrap when the exception table has one tidy handler.
    if let Some(wrapped) = try_wrap_single_handler(&mut s, exceptions, cf, n, &mut out) {
        return (wrapped, s.fully);
    }
    if !exceptions.is_empty() {
        s.fully = false;
        out.push_str(&format!("    // {} exception handler(s) in the table; try/catch structure not reconstructed here.\n", exceptions.len()));
    }
    s.render(0, n, 1, &mut out);
    (out, s.fully)
}

/// Recognise the common `try { … } catch (T e) { … }` shape and render it; `None` otherwise.
fn try_wrap_single_handler(s: &mut Structurer, exceptions: &[java_class::ExceptionEntry], cf: &ClassFile, n: usize, out: &mut String) -> Option<String> {
    if exceptions.len() != 1 {
        return None;
    }
    let e = exceptions.first()?;
    // Resolve each pc to the first node at or after it (instructions without a node, like a load,
    // leave gaps in pc_to_idx).
    let first_ge = |s: &Structurer, pc: u16| s.pc_to_idx.range(u32::from(pc)..).next().map(|(_, i)| *i);
    let start_idx = first_ge(s, e.start_pc)?;
    // The protected region [start_pc, end_pc) ends just before the node at/after end_pc, which for
    // compiled try blocks is the goto that skips the handler on the normal path.
    let exit_idx = first_ge(s, e.end_pc)?;
    let rejoin_idx = match s.nodes.get(exit_idx) {
        Some((_, Node::Goto(g))) => s.idx_of(*g)?,
        _ => return None,
    };
    let handler_idx = first_ge(s, e.handler_pc)?;
    // The handler must follow the skipping goto directly: nodes in between would be dropped.
    if !(start_idx < exit_idx && exit_idx + 1 == handler_idx && handler_idx <= rejoin_idx && rejoin_idx <= n) {
        return None;
    }
    let ty = e.catch_type.as_deref().map(java_class::internal_to_dotted).unwrap_or_else(|| "Throwable".to_string());
    let _ = cf;
    // What runs before the protected region (#232).
    s.render(0, start_idx, 1, out);
    out.push_str("    try {\n");
    s.render(start_idx, exit_idx, 2, out);
    out.push_str("    } catch (");
    out.push_str(&ty);
    out.push_str(" e) {\n");
    // The handler's first instruction stores the caught exception (astore); skip that noise.
    let handler_body_start = match s.nodes.get(handler_idx) {
        Some((_, Node::Stmt(st))) if st.trim_end().ends_with("= ?;") => handler_idx + 1,
        _ => handler_idx,
    };
    s.render(handler_body_start, rejoin_idx, 2, out);
    out.push_str("    }\n");
    s.render(rejoin_idx, n, 1, out);
    Some(std::mem::take(out))
}

/// Decompile a whole class to a pseudo-Java skeleton with field declarations and method bodies.
pub fn decompile_class(cf: &ClassFile) -> ClassDecompile {
    let mut out = String::new();
    if let Some(src) = &cf.source_file {
        out.push_str(&format!("// decompiled from {src}\n"));
    }
    if !cf.annotations.is_empty() {
        for a in &cf.annotations {
            out.push_str(&format!("@{}\n", a.split_whitespace().next().unwrap_or(a)));
        }
    }
    // class header
    let flags = java_class::access_flags(cf.access, java_class::AccessKind::Class).join(" ");
    let kind = if cf.access & 0x0200 != 0 {
        "interface"
    } else if cf.access & 0x4000 != 0 {
        "enum"
    } else {
        "class"
    };
    out.push_str(&flags);
    if !flags.is_empty() {
        out.push(' ');
    }
    out.push_str(&format!("{kind} {}", cf.name_dotted()));
    if let Some(sup) = &cf.super_class
        && sup != "java/lang/Object"
    {
        out.push_str(&format!(" extends {}", java_class::internal_to_dotted(sup)));
    }
    if !cf.interfaces.is_empty() {
        let keyword = if kind == "interface" { "extends" } else { "implements" };
        let ifaces: Vec<String> = cf.interfaces.iter().map(|i| java_class::internal_to_dotted(i)).collect();
        out.push_str(&format!(" {keyword} {}", ifaces.join(", ")));
    }
    out.push_str(" {\n");
    // fields
    for f in &cf.fields {
        let fflags = java_class::access_flags(f.access, java_class::AccessKind::Field).join(" ");
        let init = f.constant_value.as_ref().map(|v| format!(" = {v}")).unwrap_or_default();
        out.push_str(&format!("    {}{}{} {}{init};\n", fflags, if fflags.is_empty() { "" } else { " " }, java_class::field_type(&f.descriptor), f.name));
    }
    if !cf.fields.is_empty() {
        out.push('\n');
    }
    // methods
    let mut limitations = base_limitations();
    let mut fully = true;
    let mut lossy_methods = 0;
    for (n, m) in cf.methods.iter().enumerate() {
        if m.access & 0x1000 != 0 {
            // skip synthetic methods in the skeleton
            continue;
        }
        let d = decompile_method(cf, m);
        if !d.fully_structured {
            fully = false;
        }
        if d.limitations.iter().any(|l| l.code == "stack_reconstruction_approximate") {
            lossy_methods += 1;
        }
        let indented: String = d.body.lines().map(|l| format!("    {l}\n")).collect();
        out.push_str(&format!("    {}{}\n", d.signature, if d.body.starts_with('{') { indented.trim_start().to_string() } else { d.body.clone() }));
        if n + 1 < cf.methods.len() {
            out.push('\n');
        }
    }
    out.push_str("}\n");
    if lossy_methods > 0 {
        limitations
            .push(Limitation::new("stack_reconstruction_approximate", format!("{lossy_methods} method(s) contain stack operations that were approximated.")));
    }
    if !fully {
        limitations.push(Limitation::new("control_flow_partly_structured", "Some methods contain control flow shown with labels and goto statements."));
    }
    ClassDecompile { source: out, confidence: Confidence::Inferred, limitations, fully_structured: fully }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_formats::java_class::parse;
    use craft_anything_testkit::java as fx;

    fn method<'a>(cf: &'a ClassFile, name: &str) -> &'a Member {
        cf.methods.iter().find(|m| m.name == name).unwrap()
    }

    #[test]
    fn decompiles_hello() {
        let data = fx::hello_class();
        let cf = parse(&data).unwrap();
        let run = decompile_method(&cf, method(&cf, "run"));
        assert_eq!(run.signature, "public void run()");
        assert!(run.body.contains("System.out.println(\"Hello, Craft!\");"), "{}", run.body);
        assert_eq!(run.confidence, Confidence::Inferred);
        assert!(run.fully_structured);

        let pick = decompile_method(&cf, method(&cf, "pick"));
        assert!(pick.body.contains("switch (v1)"), "{}", pick.body);
        assert!(pick.body.contains("case 0:"), "{}", pick.body);
        assert!(pick.body.contains("return 10;"), "{}", pick.body);
        assert!(pick.body.contains("default:"), "{}", pick.body);

        let guarded = decompile_method(&cf, method(&cf, "guarded"));
        assert!(guarded.body.contains("try {"), "{}", guarded.body);
        assert!(guarded.body.contains("catch (java.lang.RuntimeException e)"), "{}", guarded.body);
    }

    /// #232: `v0 = 7; try { v1 = 2; } catch (RuntimeException e) {} return v0;` kept the return
    /// and dropped the assignment before the `try`.
    #[test]
    fn code_before_a_try_is_kept() {
        let hex = "cafebabe00000031000a0100065072655472790700010100106a6176612f6c616e672f4f626a656374070003010004436f64650100016d01000328294901001a6a6176612f6c616e672f52756e74696d65457863657074696f6e070008002100020004000000000001000900060007000100050000001f000100030000000b10073b053ca700044d1aac0001000300050008000900000000";
        let data: Vec<u8> = (0..hex.len()).step_by(2).map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap()).collect();
        let cf = parse(&data).unwrap();
        let m = decompile_method(&cf, method(&cf, "m"));
        let (init, try_at) = (m.body.find("v0 = 7;"), m.body.find("try {"));
        assert!(init.is_some() && init < try_at, "{}", m.body);
        assert!(m.body.contains("v1 = 2;") && m.body.contains("return v0;"), "{}", m.body);
        assert!(decompile_class(&cf).source.contains("v0 = 7;"));
    }

    #[test]
    fn decompiles_helper_new_and_calls() {
        let cf = parse(&fx::helper_class()).unwrap();
        let go = decompile_method(&cf, method(&cf, "go"));
        assert!(go.body.contains("new Hello()"), "{}", go.body);
        assert!(go.body.contains(".run()"), "{}", go.body);
        let class = decompile_class(&cf);
        assert!(class.source.contains("class com.example.Helper"), "{}", class.source);
    }

    #[test]
    fn hostile_never_panics() {
        let data = fx::hello_class();
        for m in craft_anything_testkit::mutations(&data) {
            if let Ok(cf) = parse(&m) {
                for method in &cf.methods {
                    let _ = decompile_method(&cf, method);
                }
                let _ = decompile_class(&cf);
            }
        }
        for len in 0..data.len() {
            if let Ok(cf) = parse(&data[..len]) {
                let _ = decompile_class(&cf);
            }
        }
    }
}
