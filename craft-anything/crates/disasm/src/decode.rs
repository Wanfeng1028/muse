//! Instruction decoding for x86 (16/32/64-bit, via iced-x86) and ARM (A64 and A32/T32, via
//! yaxpeax-arm), into one architecture-neutral [`Insn`].

use iced_x86::{ConditionCode, Decoder, DecoderOptions, FlowControl, Formatter, InstructionInfoFactory, IntelFormatter, Mnemonic, OpAccess, OpKind, Register};
use serde::Serialize;
use yaxpeax_arch::{Decoder as _, LengthedInstruction, U8Reader};

/// Decoding mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    X16,
    X32,
    X64,
    /// 32-bit ARM (A32).
    A32,
    /// Thumb-2.
    T32,
    A64,
}

impl Mode {
    pub fn name(self) -> &'static str {
        match self {
            Mode::X16 => "x86-16",
            Mode::X32 => "x86",
            Mode::X64 => "x86_64",
            Mode::A32 => "arm",
            Mode::T32 => "thumb",
            Mode::A64 => "arm64",
        }
    }

    pub fn is_x86(self) -> bool {
        matches!(self, Mode::X16 | Mode::X32 | Mode::X64)
    }

    /// Instruction alignment for prologue scans and pointer checks.
    pub fn align(self) -> u64 {
        match self {
            Mode::A64 | Mode::A32 => 4,
            Mode::T32 => 2,
            _ => 1,
        }
    }

    pub fn max_insn_len(self) -> usize {
        if self.is_x86() { 15 } else { 4 }
    }
}

/// How control leaves an instruction.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Flow {
    /// Falls through to the next instruction.
    Next,
    Jump {
        target: u64,
    },
    /// Conditional branch: `target` when taken, otherwise falls through.
    Cond {
        target: u64,
    },
    Call {
        target: u64,
    },
    /// Jump through a register or memory; `slot` is the memory address when it is static.
    IndirectJump {
        slot: Option<u64>,
    },
    IndirectCall {
        slot: Option<u64>,
    },
    Return,
    /// Stops execution (hlt, ud2, int3, brk).
    Stop,
}

impl Flow {
    pub fn ends_block(self) -> bool {
        !matches!(self, Flow::Next | Flow::Call { .. } | Flow::IndirectCall { .. })
    }
}

/// A branch condition, when the instruction has one.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Cond {
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    Below,
    BelowEq,
    Above,
    AboveEq,
    Sign,
    NotSign,
    Overflow,
    NotOverflow,
    Parity,
    NotParity,
    /// cbz / jcxz: register is zero.
    RegZero(String),
    RegNonZero(String),
    BitClear(String, u8),
    BitSet(String, u8),
}

impl Cond {
    /// The comparison operator for `a OP b` after a compare, if it is one.
    pub fn op(&self) -> Option<&'static str> {
        Some(match self {
            Cond::Eq => "==",
            Cond::Ne => "!=",
            Cond::Lt | Cond::Below => "<",
            Cond::Le | Cond::BelowEq => "<=",
            Cond::Gt | Cond::Above => ">",
            Cond::Ge | Cond::AboveEq => ">=",
            _ => return None,
        })
    }

    pub fn unsigned(&self) -> bool {
        matches!(self, Cond::Below | Cond::BelowEq | Cond::Above | Cond::AboveEq)
    }

    pub fn negate(&self) -> Cond {
        match self {
            Cond::Eq => Cond::Ne,
            Cond::Ne => Cond::Eq,
            Cond::Lt => Cond::Ge,
            Cond::Ge => Cond::Lt,
            Cond::Le => Cond::Gt,
            Cond::Gt => Cond::Le,
            Cond::Below => Cond::AboveEq,
            Cond::AboveEq => Cond::Below,
            Cond::BelowEq => Cond::Above,
            Cond::Above => Cond::BelowEq,
            Cond::Sign => Cond::NotSign,
            Cond::NotSign => Cond::Sign,
            Cond::Overflow => Cond::NotOverflow,
            Cond::NotOverflow => Cond::Overflow,
            Cond::Parity => Cond::NotParity,
            Cond::NotParity => Cond::Parity,
            Cond::RegZero(r) => Cond::RegNonZero(r.clone()),
            Cond::RegNonZero(r) => Cond::RegZero(r.clone()),
            Cond::BitClear(r, b) => Cond::BitSet(r.clone(), *b),
            Cond::BitSet(r, b) => Cond::BitClear(r.clone(), *b),
        }
    }
}

/// A memory operand.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MemOp {
    pub base: Option<String>,
    pub index: Option<String>,
    pub scale: u8,
    pub disp: i64,
    /// Access size in bytes (0 when unknown).
    pub size: u8,
    /// The absolute address when it doesn't depend on registers (RIP-relative or absolute).
    pub addr: Option<u64>,
    /// `fs`/`gs` for thread-local accesses.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub seg: Option<String>,
}

/// One operand.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum Op {
    Reg(String),
    Imm(i64),
    Mem(MemOp),
    /// A branch target.
    Addr(u64),
}

/// What an instruction does, coarsely (for the lifter and heuristics).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    Mov,
    MovSx,
    MovZx,
    Lea,
    Add,
    Sub,
    Mul,
    Div,
    And,
    Or,
    Xor,
    Shl,
    Shr,
    Sar,
    Not,
    Neg,
    Inc,
    Dec,
    Cmp,
    Test,
    Push,
    Pop,
    Load,
    Store,
    LoadPair,
    StorePair,
    Adrp,
    Adr,
    Nop,
    Leave,
    Branch,
    Call,
    Ret,
    Other,
}

/// A decoded instruction.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Insn {
    pub addr: u64,
    pub len: u8,
    pub mnemonic: String,
    pub operands: String,
    pub kind: Kind,
    pub flow: Flow,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cond: Option<Cond>,
    /// Addresses the operands point at (memory, address-like immediates), not branch targets.
    pub refs: Vec<u64>,
    pub ops: Vec<Op>,
    /// Registers read and written, by full-width name (`eax` counts as `rax`).
    pub reads: Vec<String>,
    pub writes: Vec<String>,
    pub sets_flags: bool,
}

impl Insn {
    pub fn text(&self) -> String {
        if self.operands.is_empty() { self.mnemonic.clone() } else { format!("{} {}", self.mnemonic, self.operands) }
    }

    pub fn end(&self) -> u64 {
        self.addr.wrapping_add(u64::from(self.len))
    }
}

/// Decode one instruction at `addr` from `bytes` (which start at `addr`). `fmt` adds the
/// mnemonic/operand text; without it only the structure is filled (faster).
pub fn decode(mode: Mode, bytes: &[u8], addr: u64, fmt: bool) -> Option<Insn> {
    match mode {
        Mode::X16 => decode_x86(16, bytes, addr, fmt),
        Mode::X32 => decode_x86(32, bytes, addr, fmt),
        Mode::X64 => decode_x86(64, bytes, addr, fmt),
        Mode::A64 => decode_a64(bytes, addr, fmt),
        Mode::A32 | Mode::T32 => decode_a32(mode, bytes, addr, fmt),
    }
}

// ---------------------------------------------------------------------------------------------
// x86

fn reg_name(r: Register) -> String {
    format!("{r:?}").to_ascii_lowercase()
}

fn full_name(r: Register) -> Option<String> {
    if r == Register::None || r == Register::RIP || r == Register::EIP {
        return None;
    }
    let f = r.full_register();
    Some(reg_name(f))
}

fn x86_kind(m: Mnemonic) -> Kind {
    use Mnemonic as M;
    match m {
        M::Mov | M::Cmove | M::Cmovne | M::Cmovl | M::Cmovle | M::Cmovg | M::Cmovge | M::Cmovb | M::Cmovbe | M::Cmova | M::Cmovae | M::Cmovs | M::Cmovns => {
            Kind::Mov
        }
        M::Movsx | M::Movsxd => Kind::MovSx,
        M::Movzx => Kind::MovZx,
        M::Lea => Kind::Lea,
        M::Add | M::Adc => Kind::Add,
        M::Sub | M::Sbb => Kind::Sub,
        M::Imul | M::Mul => Kind::Mul,
        M::Div | M::Idiv => Kind::Div,
        M::And => Kind::And,
        M::Or => Kind::Or,
        M::Xor => Kind::Xor,
        M::Shl | M::Sal => Kind::Shl,
        M::Shr => Kind::Shr,
        M::Sar => Kind::Sar,
        M::Not => Kind::Not,
        M::Neg => Kind::Neg,
        M::Inc => Kind::Inc,
        M::Dec => Kind::Dec,
        M::Cmp => Kind::Cmp,
        M::Test => Kind::Test,
        M::Push => Kind::Push,
        M::Pop => Kind::Pop,
        M::Nop | M::Endbr64 | M::Endbr32 => Kind::Nop,
        M::Leave => Kind::Leave,
        M::Call => Kind::Call,
        M::Ret | M::Retf => Kind::Ret,
        M::Jmp => Kind::Branch,
        _ => Kind::Other,
    }
}

fn x86_cond(c: ConditionCode) -> Option<Cond> {
    Some(match c {
        ConditionCode::e => Cond::Eq,
        ConditionCode::ne => Cond::Ne,
        ConditionCode::l => Cond::Lt,
        ConditionCode::le => Cond::Le,
        ConditionCode::g => Cond::Gt,
        ConditionCode::ge => Cond::Ge,
        ConditionCode::b => Cond::Below,
        ConditionCode::be => Cond::BelowEq,
        ConditionCode::a => Cond::Above,
        ConditionCode::ae => Cond::AboveEq,
        ConditionCode::s => Cond::Sign,
        ConditionCode::ns => Cond::NotSign,
        ConditionCode::o => Cond::Overflow,
        ConditionCode::no => Cond::NotOverflow,
        ConditionCode::p => Cond::Parity,
        ConditionCode::np => Cond::NotParity,
        _ => return None,
    })
}

fn decode_x86(bitness: u32, bytes: &[u8], addr: u64, fmt: bool) -> Option<Insn> {
    let mut dec = Decoder::with_ip(bitness, bytes, addr, DecoderOptions::NONE);
    if !dec.can_decode() {
        return None;
    }
    let ins = dec.decode();
    if ins.is_invalid() {
        return None;
    }
    let len = u8::try_from(ins.len()).ok()?;
    let mnem = ins.mnemonic();
    let mut kind = x86_kind(mnem);
    let mut ops = Vec::new();
    let mut refs = Vec::new();
    let mut mem_slot = None;
    for i in 0..ins.op_count() {
        match ins.op_kind(i) {
            OpKind::Register => ops.push(Op::Reg(reg_name(ins.op_register(i)))),
            OpKind::NearBranch16 | OpKind::NearBranch32 | OpKind::NearBranch64 => ops.push(Op::Addr(ins.near_branch_target())),
            OpKind::Memory => {
                let base = ins.memory_base();
                let index = ins.memory_index();
                let seg = match ins.memory_segment() {
                    Register::FS => Some("fs".to_string()),
                    Register::GS => Some("gs".to_string()),
                    _ => None,
                };
                let abs = if ins.is_ip_rel_memory_operand() {
                    Some(ins.ip_rel_memory_address())
                } else if base == Register::None && index == Register::None && seg.is_none() {
                    Some(ins.memory_displacement64())
                } else {
                    None
                };
                let disp = if ins.is_ip_rel_memory_operand() { 0 } else { ins.memory_displacement64() as i64 };
                if let Some(a) = abs {
                    refs.push(a);
                    mem_slot = Some(a);
                }
                ops.push(Op::Mem(MemOp {
                    base: if base == Register::None || base == Register::RIP || base == Register::EIP { None } else { Some(reg_name(base)) },
                    index: if index == Register::None { None } else { Some(reg_name(index)) },
                    scale: u8::try_from(ins.memory_index_scale()).unwrap_or(1),
                    disp,
                    size: u8::try_from(ins.memory_size().size()).unwrap_or(0),
                    addr: abs,
                    seg,
                }));
            }
            OpKind::Immediate8
            | OpKind::Immediate8_2nd
            | OpKind::Immediate16
            | OpKind::Immediate32
            | OpKind::Immediate64
            | OpKind::Immediate8to16
            | OpKind::Immediate8to32
            | OpKind::Immediate8to64
            | OpKind::Immediate32to64 => {
                let v = ins.try_immediate(i).unwrap_or(0);
                let signed = match ins.op_kind(i) {
                    OpKind::Immediate8to16 | OpKind::Immediate8to32 | OpKind::Immediate8to64 | OpKind::Immediate32to64 => v as i64,
                    OpKind::Immediate8 | OpKind::Immediate8_2nd => i64::from(v as u8),
                    OpKind::Immediate16 => i64::from(v as u16),
                    OpKind::Immediate32 => i64::from(v as u32),
                    _ => v as i64,
                };
                if v >= 0x100 {
                    refs.push(v);
                }
                ops.push(Op::Imm(signed));
            }
            _ => ops.push(Op::Imm(0)),
        }
    }
    let flow = match ins.flow_control() {
        FlowControl::Next | FlowControl::XbeginXabortXend => {
            if mnem == Mnemonic::Hlt {
                Flow::Stop
            } else {
                Flow::Next
            }
        }
        FlowControl::Interrupt => {
            if mnem == Mnemonic::Int3 || (mnem == Mnemonic::Int && ins.try_immediate(0).ok() == Some(0x29)) {
                Flow::Stop
            } else {
                Flow::Next
            }
        }
        FlowControl::Exception => Flow::Stop,
        FlowControl::UnconditionalBranch => match ins.op_kind(0) {
            OpKind::NearBranch16 | OpKind::NearBranch32 | OpKind::NearBranch64 => Flow::Jump { target: ins.near_branch_target() },
            _ => Flow::IndirectJump { slot: None },
        },
        FlowControl::ConditionalBranch => Flow::Cond { target: ins.near_branch_target() },
        FlowControl::IndirectBranch => Flow::IndirectJump { slot: mem_slot },
        FlowControl::Call => match ins.op_kind(0) {
            OpKind::NearBranch16 | OpKind::NearBranch32 | OpKind::NearBranch64 => Flow::Call { target: ins.near_branch_target() },
            _ => Flow::IndirectCall { slot: None },
        },
        FlowControl::IndirectCall => Flow::IndirectCall { slot: mem_slot },
        FlowControl::Return => Flow::Return,
    };
    if matches!(flow, Flow::Cond { .. }) {
        kind = Kind::Branch;
    }
    let cond = match flow {
        Flow::Cond { .. } => match mnem {
            Mnemonic::Jcxz | Mnemonic::Jecxz | Mnemonic::Jrcxz => Some(Cond::RegZero("rcx".into())),
            _ => x86_cond(ins.condition_code()),
        },
        _ => None,
    };
    // Branch targets are not data references.
    if matches!(flow, Flow::Jump { .. } | Flow::Cond { .. } | Flow::Call { .. }) {
        refs.retain(|r| Some(*r) != ops.first().and_then(|o| if let Op::Addr(a) = o { Some(*a) } else { None }));
    }
    let mut reads = Vec::new();
    let mut writes = Vec::new();
    let mut factory = InstructionInfoFactory::new();
    let info = factory.info(&ins);
    for u in info.used_registers() {
        let Some(n) = full_name(u.register()) else { continue };
        if n == "rsp" && matches!(kind, Kind::Push | Kind::Pop | Kind::Call | Kind::Ret) {
            continue;
        }
        match u.access() {
            OpAccess::Read | OpAccess::CondRead => push_unique(&mut reads, n),
            OpAccess::Write | OpAccess::CondWrite => push_unique(&mut writes, n),
            OpAccess::ReadWrite | OpAccess::ReadCondWrite => {
                push_unique(&mut reads, n.clone());
                push_unique(&mut writes, n);
            }
            _ => {}
        }
    }
    // xor r, r / sub r, r define r without reading it.
    if matches!(kind, Kind::Xor | Kind::Sub)
        && ops.len() == 2
        && ops.first() == ops.get(1)
        && let Some(Op::Reg(r)) = ops.first()
        && let Some(f) = full_name_str(r)
    {
        reads.retain(|x| *x != f);
    }
    let (mnemonic, operands) = if fmt {
        let mut f = IntelFormatter::new();
        let o = f.options_mut();
        o.set_hex_prefix("0x");
        o.set_hex_suffix("");
        o.set_uppercase_hex(false);
        o.set_space_after_operand_separator(true);
        o.set_branch_leading_zeros(false);
        o.set_leading_zeros(false);
        o.set_show_branch_size(false);
        let mut m = String::new();
        f.format_mnemonic(&ins, &mut m);
        let mut a = String::new();
        f.format_all_operands(&ins, &mut a);
        (m, a)
    } else {
        (format!("{mnem:?}").to_ascii_lowercase(), String::new())
    };
    Some(Insn { addr, len, mnemonic, operands, kind, flow, cond, refs, ops, reads, writes, sets_flags: ins.rflags_modified() != 0 })
}

fn full_name_str(r: &str) -> Option<String> {
    // Map a sub-register name to its 64-bit parent (eax → rax, r8d → r8, al → rax).
    let r = r.to_ascii_lowercase();
    let base = match r.as_str() {
        "al" | "ah" | "ax" | "eax" | "rax" => "rax",
        "bl" | "bh" | "bx" | "ebx" | "rbx" => "rbx",
        "cl" | "ch" | "cx" | "ecx" | "rcx" => "rcx",
        "dl" | "dh" | "dx" | "edx" | "rdx" => "rdx",
        "sil" | "si" | "esi" | "rsi" => "rsi",
        "dil" | "di" | "edi" | "rdi" => "rdi",
        "bpl" | "bp" | "ebp" | "rbp" => "rbp",
        "spl" | "sp" | "esp" | "rsp" => "rsp",
        other => {
            if let Some(n) = other.strip_prefix('r') {
                let digits: String = n.chars().take_while(|c| c.is_ascii_digit()).collect();
                if !digits.is_empty() {
                    return Some(format!("r{digits}"));
                }
            }
            if let Some(n) = other.strip_prefix('w').filter(|n| n.chars().all(|c| c.is_ascii_digit()) && !n.is_empty()) {
                return Some(format!("x{n}"));
            }
            return Some(other.to_string());
        }
    };
    Some(base.to_string())
}

/// The full-width register a name belongs to (`eax` → `rax`, `w3` → `x3`).
pub fn canonical_reg(r: &str) -> String {
    full_name_str(r).unwrap_or_else(|| r.to_string())
}

fn push_unique(v: &mut Vec<String>, s: String) {
    if !v.contains(&s) {
        v.push(s);
    }
}

// ---------------------------------------------------------------------------------------------
// AArch64

/// Replace yaxpeax's `$+0x…`/`$-0x…` relative operands with absolute `0x…` addresses.
fn absolutize(text: &str, base: u64) -> String {
    let mut out = String::with_capacity(text.len());
    let mut rest = text;
    while let Some(p) = rest.find('$') {
        out.push_str(rest.get(..p).unwrap_or(""));
        let tail = rest.get(p + 1..).unwrap_or("");
        let neg = tail.starts_with('-');
        let num = tail.get(1..).unwrap_or("");
        let hex = num.strip_prefix("0x").unwrap_or(num);
        let digits: String = hex.chars().take_while(|c| c.is_ascii_hexdigit()).collect();
        match u64::from_str_radix(&digits, 16) {
            Ok(v) if !digits.is_empty() => {
                let t = if neg { base.wrapping_sub(v) } else { base.wrapping_add(v) };
                out.push_str(&format!("{t:#x}"));
                let consumed = 1 + (num.len() - hex.len()) + digits.len();
                rest = tail.get(consumed..).unwrap_or("");
            }
            _ => {
                out.push('$');
                rest = tail;
            }
        }
    }
    out.push_str(rest);
    out
}

fn split_text(text: &str) -> (String, String) {
    match text.split_once(' ') {
        Some((m, o)) => (m.to_string(), o.trim().to_string()),
        None => (text.to_string(), String::new()),
    }
}

fn a64_reg(size: yaxpeax_arm::armv8::a64::SizeCode, n: u16, sp: bool) -> String {
    use yaxpeax_arm::armv8::a64::SizeCode;
    match (size, n) {
        (SizeCode::X, 31) => {
            if sp {
                "sp".into()
            } else {
                "xzr".into()
            }
        }
        (SizeCode::W, 31) => {
            if sp {
                "wsp".into()
            } else {
                "wzr".into()
            }
        }
        (SizeCode::X, n) => format!("x{n}"),
        (SizeCode::W, n) => format!("w{n}"),
    }
}

fn a64_canon(n: u16, sp: bool) -> Option<String> {
    if n == 31 {
        return if sp { Some("sp".into()) } else { None };
    }
    Some(format!("x{n}"))
}

fn decode_a64(bytes: &[u8], addr: u64, fmt: bool) -> Option<Insn> {
    use yaxpeax_arm::armv8::a64::{InstDecoder, Opcode, Operand};
    let word = bytes.get(..4)?;
    let mut reader = U8Reader::new(word);
    let inst = InstDecoder::default().decode(&mut reader).ok()?;
    let op_name = format!("{:?}", inst.opcode);
    let mut ops = Vec::new();
    let mut refs = Vec::new();
    let mut reads: Vec<String> = Vec::new();
    let mut writes: Vec<String> = Vec::new();
    let mut target = None;
    let mut first_reg: Option<String> = None;
    let mut regs_in_order: Vec<String> = Vec::new();
    let is_store =
        op_name.starts_with("ST") && !op_name.starts_with("STR") || op_name.starts_with("STR") || op_name.starts_with("STP") || op_name.starts_with("STUR");
    for o in inst.operands.iter() {
        match *o {
            Operand::Nothing => break,
            Operand::Register(s, n) => {
                ops.push(Op::Reg(a64_reg(s, n, false)));
                if let Some(c) = a64_canon(n, false) {
                    if first_reg.is_none() {
                        first_reg = Some(c.clone());
                    }
                    regs_in_order.push(c);
                } else if first_reg.is_none() {
                    first_reg = Some("zr".into());
                }
            }
            Operand::RegisterOrSP(s, n) => {
                ops.push(Op::Reg(a64_reg(s, n, true)));
                if let Some(c) = a64_canon(n, true) {
                    if first_reg.is_none() {
                        first_reg = Some(c.clone());
                    }
                    regs_in_order.push(c);
                }
            }
            Operand::RegisterPair(s, n) => {
                ops.push(Op::Reg(a64_reg(s, n, false)));
                if let Some(c) = a64_canon(n, false) {
                    regs_in_order.push(c);
                }
            }
            Operand::RegShift(_, _, s, n) => {
                ops.push(Op::Reg(a64_reg(s, n, false)));
                if let Some(c) = a64_canon(n, false) {
                    push_unique(&mut reads, c);
                }
            }
            Operand::PCOffset(off) => {
                let t = if inst.opcode == Opcode::ADRP { (addr & !0xfff).wrapping_add(off as u64) } else { addr.wrapping_add(off as u64) };
                target = Some(t);
                ops.push(Op::Addr(t));
            }
            Operand::Immediate(v) => ops.push(Op::Imm(i64::from(v))),
            Operand::Imm64(v) => ops.push(Op::Imm(v as i64)),
            Operand::Imm16(v) => ops.push(Op::Imm(i64::from(v))),
            Operand::ImmShift(v, s) => ops.push(Op::Imm(i64::from(v).checked_shl(u32::from(s)).unwrap_or(0))),
            Operand::RegPreIndex(n, off, wb) => {
                ops.push(Op::Mem(MemOp { base: a64_canon(n, true), index: None, scale: 1, disp: i64::from(off), size: 0, addr: None, seg: None }));
                if let Some(c) = a64_canon(n, true) {
                    push_unique(&mut reads, c.clone());
                    if wb {
                        push_unique(&mut writes, c);
                    }
                }
            }
            Operand::RegPostIndex(n, off) => {
                ops.push(Op::Mem(MemOp { base: a64_canon(n, true), index: None, scale: 1, disp: 0, size: 0, addr: None, seg: None }));
                let _ = off;
                if let Some(c) = a64_canon(n, true) {
                    push_unique(&mut reads, c.clone());
                    push_unique(&mut writes, c);
                }
            }
            Operand::RegRegOffset(n, m, _, _, sh) => {
                ops.push(Op::Mem(MemOp {
                    base: a64_canon(n, true),
                    index: a64_canon(m, false),
                    scale: 1u8.checked_shl(u32::from(sh)).unwrap_or(1),
                    disp: 0,
                    size: 0,
                    addr: None,
                    seg: None,
                }));
                for c in [a64_canon(n, true), a64_canon(m, false)].into_iter().flatten() {
                    push_unique(&mut reads, c);
                }
            }
            Operand::RegPostIndexReg(n, m) => {
                ops.push(Op::Mem(MemOp { base: a64_canon(n, true), index: None, scale: 1, disp: 0, size: 0, addr: None, seg: None }));
                for c in [a64_canon(n, true), a64_canon(m, false)].into_iter().flatten() {
                    push_unique(&mut reads, c);
                }
            }
            _ => ops.push(Op::Imm(0)),
        }
    }
    let (flow, cond) = match inst.opcode {
        Opcode::B => (Flow::Jump { target: target.unwrap_or(addr) }, None),
        Opcode::Bcc(c) => {
            let cond = match c {
                0 => Cond::Eq,
                1 => Cond::Ne,
                2 => Cond::AboveEq,
                3 => Cond::Below,
                4 => Cond::Sign,
                5 => Cond::NotSign,
                6 => Cond::Overflow,
                7 => Cond::NotOverflow,
                8 => Cond::Above,
                9 => Cond::BelowEq,
                10 => Cond::Ge,
                11 => Cond::Lt,
                12 => Cond::Gt,
                13 => Cond::Le,
                _ => Cond::Eq,
            };
            if c >= 14 { (Flow::Jump { target: target.unwrap_or(addr) }, None) } else { (Flow::Cond { target: target.unwrap_or(addr) }, Some(cond)) }
        }
        Opcode::CBZ | Opcode::CBNZ => {
            let r = ops.iter().find_map(|o| if let Op::Reg(r) = o { Some(r.clone()) } else { None }).unwrap_or_default();
            (Flow::Cond { target: target.unwrap_or(addr) }, Some(if inst.opcode == Opcode::CBZ { Cond::RegZero(r) } else { Cond::RegNonZero(r) }))
        }
        Opcode::TBZ | Opcode::TBNZ => {
            let r = ops.iter().find_map(|o| if let Op::Reg(r) = o { Some(r.clone()) } else { None }).unwrap_or_default();
            let bit = ops.iter().find_map(|o| if let Op::Imm(v) = o { Some(*v as u8) } else { None }).unwrap_or(0);
            (Flow::Cond { target: target.unwrap_or(addr) }, Some(if inst.opcode == Opcode::TBZ { Cond::BitClear(r, bit) } else { Cond::BitSet(r, bit) }))
        }
        Opcode::BL => (Flow::Call { target: target.unwrap_or(addr) }, None),
        Opcode::BLR | Opcode::BLRAA | Opcode::BLRAAZ | Opcode::BLRAB | Opcode::BLRABZ => (Flow::IndirectCall { slot: None }, None),
        Opcode::BR | Opcode::BRAA | Opcode::BRAAZ | Opcode::BRAB | Opcode::BRABZ => (Flow::IndirectJump { slot: None }, None),
        Opcode::RET | Opcode::RETAA | Opcode::RETAB => (Flow::Return, None),
        Opcode::BRK | Opcode::HLT | Opcode::UDF => (Flow::Stop, None),
        _ => (Flow::Next, None),
    };
    let kind = match inst.opcode {
        Opcode::ADRP => Kind::Adrp,
        Opcode::ADR => Kind::Adr,
        Opcode::ADD | Opcode::ADDS => Kind::Add,
        Opcode::SUB | Opcode::SUBS => Kind::Sub,
        Opcode::AND | Opcode::ANDS => Kind::And,
        Opcode::ORR => Kind::Or,
        Opcode::EOR => Kind::Xor,
        Opcode::MOVZ | Opcode::MOVN | Opcode::MOVK => Kind::Mov,
        Opcode::MADD | Opcode::MSUB | Opcode::SMULL | Opcode::UMULL => Kind::Mul,
        Opcode::SDIV | Opcode::UDIV => Kind::Div,
        Opcode::LDP | Opcode::LDPSW => Kind::LoadPair,
        Opcode::STP => Kind::StorePair,
        Opcode::B | Opcode::Bcc(_) | Opcode::CBZ | Opcode::CBNZ | Opcode::TBZ | Opcode::TBNZ | Opcode::BR => Kind::Branch,
        Opcode::BL | Opcode::BLR => Kind::Call,
        Opcode::RET => Kind::Ret,
        Opcode::HINT => Kind::Nop,
        _ => {
            if op_name.starts_with("LDR") || op_name.starts_with("LDUR") || op_name.starts_with("LDAR") || op_name.starts_with("LDX") {
                Kind::Load
            } else if is_store {
                Kind::Store
            } else {
                Kind::Other
            }
        }
    };
    // Literal loads and adr point at data.
    if let Some(t) = target
        && (matches!(kind, Kind::Adr | Kind::Load))
    {
        refs.push(t);
    }
    // Reads/writes: stores and branches read everything; otherwise the first register is the
    // destination and the rest are sources.
    match kind {
        Kind::Store | Kind::StorePair | Kind::Branch | Kind::Call => {
            for r in regs_in_order {
                push_unique(&mut reads, r);
            }
        }
        Kind::LoadPair => {
            for r in regs_in_order {
                push_unique(&mut writes, r);
            }
        }
        _ => {
            let mut it = regs_in_order.into_iter();
            if let Some(d) = it.next() {
                if op_name.ends_with('S') && first_reg.as_deref() == Some("zr") {
                    push_unique(&mut reads, d);
                } else {
                    push_unique(&mut writes, d);
                }
            }
            for r in it {
                push_unique(&mut reads, r);
            }
            if matches!(inst.opcode, Opcode::MOVK)
                && let Some(w) = writes.first().cloned()
            {
                push_unique(&mut reads, w);
            }
        }
    }
    if matches!(flow, Flow::Return) {
        push_unique(&mut reads, "x30".into());
    }
    if matches!(flow, Flow::Call { .. } | Flow::IndirectCall { .. }) {
        push_unique(&mut writes, "x30".into());
    }
    let sets_flags = matches!(inst.opcode, Opcode::SUBS | Opcode::ADDS | Opcode::ANDS | Opcode::CCMP | Opcode::CCMN) || op_name.starts_with("FCMP");
    let (mnemonic, operands) = if fmt {
        let (m, o) = split_text(&inst.to_string());
        (m, absolutize(&o, if inst.opcode == Opcode::ADRP { addr & !0xfff } else { addr }))
    } else {
        (op_name.to_ascii_lowercase(), String::new())
    };
    let kind = if matches!(kind, Kind::Sub) && sets_flags && first_reg.as_deref() == Some("zr") {
        Kind::Cmp
    } else if matches!(kind, Kind::And) && sets_flags && first_reg.as_deref() == Some("zr") {
        Kind::Test
    } else if matches!(kind, Kind::Or | Kind::Add) && mnemonic == "mov" {
        Kind::Mov
    } else {
        kind
    };
    Some(Insn { addr, len: 4, mnemonic, operands, kind, flow, cond, refs, ops, reads, writes, sets_flags })
}

// ---------------------------------------------------------------------------------------------
// ARM (A32 / T32): decode and control flow; operand structure is coarse.

fn decode_a32(mode: Mode, bytes: &[u8], addr: u64, fmt: bool) -> Option<Insn> {
    use yaxpeax_arm::armv7::{ConditionCode as C, InstDecoder, Opcode, Operand};
    let dec = if mode == Mode::T32 { InstDecoder::default_thumb() } else { InstDecoder::default() };
    let window = bytes.get(..bytes.len().min(4))?;
    if mode == Mode::A32 {
        let word = u32::from_le_bytes(window.try_into().ok()?);
        // A32 extra load/store: L=0 and SH=10/11 select LDRD/STRD.
        // Rt=15 would make yaxpeax construct the nonexistent second register r16.
        if word & 0x0e10_00d0 == 0x0000_00d0 && (word >> 12) & 0xf == 15 {
            return None;
        }
    }
    let mut reader = U8Reader::new(window);
    let inst = dec.decode(&mut reader).ok()?;
    let len = u8::try_from(inst.len().to_const()).ok().filter(|l| *l > 0)?;
    let pc_bias = if mode == Mode::T32 { 4 } else { 8 };
    let mut target = None;
    let mut ops = Vec::new();
    let mut reads = Vec::new();
    let mut writes = Vec::new();
    let mut pops_pc = false;
    let mut reg_ops: Vec<u8> = Vec::new();
    // A memory operand no C statement says whole (write-back, a subtracted or shifted index): the
    // lifter shows the instruction as written rather than a wrong expression (#277).
    let mut exact = true;
    let size = if matches!(inst.opcode, Opcode::LDR | Opcode::STR) { 4 } else { 0 };
    let mem = |base: u8, index: Option<u8>, disp: i64| {
        // A literal load reads from the word-aligned PC.
        let pc = (base == 15).then(|| (addr.wrapping_add(pc_bias) & !3).wrapping_add(disp as u64));
        let (base, disp) = if pc.is_some() { (None, 0) } else { (Some(format!("r{base}")), disp) };
        Op::Mem(MemOp { base, index: index.map(|i| format!("r{i}")), scale: 1, disp, size, addr: pc, seg: None })
    };
    for o in inst.operands.iter() {
        match *o {
            Operand::Nothing => break,
            Operand::RegDerefPreindexOffset(r, off, add, false) => {
                ops.push(mem(r.number(), None, if add { i64::from(off) } else { -i64::from(off) }));
                if r.number() != 15 {
                    push_unique(&mut reads, format!("r{}", r.number()));
                }
            }
            Operand::RegDerefPreindexReg(r, m, true, false) if r.number() != 15 => {
                ops.push(mem(r.number(), Some(m.number()), 0));
                push_unique(&mut reads, format!("r{}", r.number()));
                push_unique(&mut reads, format!("r{}", m.number()));
            }
            Operand::RegDerefPreindexOffset(r, ..)
            | Operand::RegDerefPostindexOffset(r, ..)
            | Operand::RegDerefPreindexReg(r, ..)
            | Operand::RegDerefPostindexReg(r, ..)
            | Operand::RegDerefPreindexRegShift(r, ..)
            | Operand::RegDerefPostindexRegShift(r, ..) => {
                exact = false;
                ops.push(mem(r.number(), None, 0));
                push_unique(&mut reads, format!("r{}", r.number()));
            }
            Operand::BranchOffset(off) => {
                let t = (addr.wrapping_add(pc_bias - 8)).wrapping_add((i64::from(off) * 4) as u64);
                target = Some(t);
                ops.push(Op::Addr(t));
            }
            Operand::BranchThumbOffset(off) => {
                // The PC reads as the instruction address plus 4 (Thumb) or 8 (A32).
                // yaxpeax already counts one halfword into CBZ/CBNZ and 16-bit conditional B offsets.
                let counted = matches!(inst.opcode, Opcode::CBZ | Opcode::CBNZ) || (inst.opcode == Opcode::B && len == 2 && inst.condition != C::AL);
                let mut pc = addr.wrapping_add(pc_bias).wrapping_sub(if counted { 2 } else { 0 });
                // Thumb BLX switches to A32 and branches from the word-aligned PC.
                if mode == Mode::T32 && inst.opcode == Opcode::BLX {
                    pc &= !3;
                }
                let t = pc.wrapping_add((i64::from(off) * 2) as u64);
                target = Some(t);
                ops.push(Op::Addr(t));
            }
            Operand::Reg(r) | Operand::RegWBack(r, _) | Operand::RegDeref(r) => {
                reg_ops.push(r.number());
                ops.push(Op::Reg(format!("r{}", r.number())));
            }
            Operand::RegList(list) => {
                if list & 0x8000 != 0 {
                    pops_pc = true;
                }
                for i in 0..16u8 {
                    if list & (1 << i) != 0 {
                        reg_ops.push(i);
                    }
                }
            }
            Operand::Imm12(v) => ops.push(Op::Imm(i64::from(v))),
            Operand::Imm32(v) => ops.push(Op::Imm(i64::from(v))),
            _ => ops.push(Op::Imm(0)),
        }
    }
    let conditional = inst.condition != C::AL;
    let first_is_pc = reg_ops.first() == Some(&15);
    let flow = match inst.opcode {
        Opcode::B => match (target, conditional) {
            (Some(t), true) => Flow::Cond { target: t },
            (Some(t), false) => Flow::Jump { target: t },
            _ => Flow::IndirectJump { slot: None },
        },
        Opcode::CBZ | Opcode::CBNZ => target.map_or(Flow::Next, |t| Flow::Cond { target: t }),
        Opcode::BL | Opcode::BLX => match target {
            Some(t) => Flow::Call { target: t },
            None => Flow::IndirectCall { slot: None },
        },
        Opcode::BX => {
            if reg_ops.first() == Some(&14) {
                Flow::Return
            } else {
                Flow::IndirectJump { slot: None }
            }
        }
        Opcode::POP | Opcode::LDM(..) if pops_pc => Flow::Return,
        Opcode::LDR if first_is_pc => Flow::IndirectJump { slot: None },
        Opcode::MOV if first_is_pc && reg_ops.get(1) == Some(&14) => Flow::Return,
        Opcode::UDF | Opcode::BKPT => Flow::Stop,
        _ => Flow::Next,
    };
    let flow = if conditional && matches!(flow, Flow::Return | Flow::IndirectJump { .. }) {
        // A conditional return can fall through; treat as an unresolved branch that continues.
        Flow::Next
    } else {
        flow
    };
    let name = format!("{:?}", inst.opcode).to_ascii_lowercase();
    let kind = match inst.opcode {
        Opcode::MOV => Kind::Mov,
        Opcode::ADD => Kind::Add,
        Opcode::SUB => Kind::Sub,
        Opcode::CMP => Kind::Cmp,
        Opcode::TST => Kind::Test,
        Opcode::PUSH => Kind::Push,
        Opcode::POP => Kind::Pop,
        Opcode::LDR => Kind::Load,
        Opcode::STR => Kind::Store,
        Opcode::B | Opcode::BX | Opcode::CBZ | Opcode::CBNZ => Kind::Branch,
        Opcode::BL | Opcode::BLX => Kind::Call,
        _ => Kind::Other,
    };
    for (i, r) in reg_ops.iter().enumerate() {
        let n = format!("r{r}");
        if i == 0 && !matches!(kind, Kind::Store | Kind::Cmp | Kind::Test | Kind::Push | Kind::Branch | Kind::Call) {
            push_unique(&mut writes, n);
        } else {
            push_unique(&mut reads, n);
        }
    }
    let kind = if exact { kind } else { Kind::Other };
    let cond = if matches!(flow, Flow::Cond { .. }) {
        Some(match inst.condition {
            C::EQ => Cond::Eq,
            C::NE => Cond::Ne,
            C::HS => Cond::AboveEq,
            C::LO => Cond::Below,
            C::MI => Cond::Sign,
            C::PL => Cond::NotSign,
            C::VS => Cond::Overflow,
            C::VC => Cond::NotOverflow,
            C::HI => Cond::Above,
            C::LS => Cond::BelowEq,
            C::GE => Cond::Ge,
            C::LT => Cond::Lt,
            C::GT => Cond::Gt,
            C::LE => Cond::Le,
            _ => Cond::Eq,
        })
    } else {
        None
    };
    let (mnemonic, operands) = if fmt { split_text(&inst.to_string()) } else { (name, String::new()) };
    let operands = absolutize(&operands, addr.wrapping_add(pc_bias));
    Some(Insn {
        addr,
        len,
        mnemonic,
        operands,
        kind,
        flow,
        cond,
        refs: Vec::new(),
        ops,
        reads,
        writes,
        sets_flags: inst.s || matches!(kind, Kind::Cmp | Kind::Test),
    })
}

// ---------------------------------------------------------------------------------------------
// AArch64 constant tracking (adrp/add/ldr pairs), used by the analysis and the lifter.

/// Tracks registers holding known addresses within a straight-line run of AArch64 code, so
/// `adrp x0, page; add x0, x0, #off` resolves to an address and `ldr x16, [x16, #off]; br x16`
/// resolves to the pointer slot it jumps through.
#[derive(Debug, Clone, Default)]
pub struct ArmConsts {
    vals: [Option<u64>; 32],
    /// Registers loaded from a known memory slot (value unknown, slot known).
    slots: [Option<u64>; 32],
}

fn xnum(r: &str) -> Option<usize> {
    let n = r.strip_prefix('x').or_else(|| r.strip_prefix('w'))?;
    let v: usize = n.parse().ok()?;
    (v < 31).then_some(v)
}

impl ArmConsts {
    pub fn reset(&mut self) {
        *self = ArmConsts::default();
    }

    pub fn value(&self, reg: &str) -> Option<u64> {
        self.vals.get(xnum(reg)?).copied().flatten()
    }

    /// Update state with `insn`, adding resolved references and slots to it.
    pub fn apply(&mut self, insn: &mut Insn) {
        let dst = insn.ops.first().and_then(|o| if let Op::Reg(r) = o { xnum(r) } else { None });
        match insn.kind {
            Kind::Adrp | Kind::Adr => {
                if let (Some(d), Some(Op::Addr(t))) = (dst, insn.ops.get(1)) {
                    if let Some(v) = self.vals.get_mut(d) {
                        *v = Some(*t);
                    }
                    if let Some(s) = self.slots.get_mut(d) {
                        *s = None;
                    }
                    return;
                }
            }
            Kind::Add | Kind::Mov => {
                let src = insn.ops.get(1).and_then(|o| if let Op::Reg(r) = o { xnum(r) } else { None });
                let imm = insn.ops.get(2).and_then(|o| if let Op::Imm(v) = o { Some(*v) } else { None });
                if let (Some(d), Some(s)) = (dst, src)
                    && let Some(base) = self.vals.get(s).copied().flatten()
                {
                    let v = base.wrapping_add(imm.unwrap_or(0) as u64);
                    insn.refs.push(v);
                    if let Some(x) = self.vals.get_mut(d) {
                        *x = Some(v);
                    }
                    if let Some(x) = self.slots.get_mut(d) {
                        *x = None;
                    }
                    return;
                }
            }
            Kind::Load | Kind::Store => {
                if let Some(Op::Mem(m)) = insn.ops.get(1)
                    && let Some(b) = m.base.as_deref().and_then(xnum)
                    && let Some(base) = self.vals.get(b).copied().flatten()
                {
                    let a = base.wrapping_add(m.disp as u64);
                    insn.refs.push(a);
                    if insn.kind == Kind::Load
                        && let Some(d) = dst
                    {
                        if let Some(x) = self.vals.get_mut(d) {
                            *x = None;
                        }
                        if let Some(x) = self.slots.get_mut(d) {
                            *x = Some(a);
                        }
                        return;
                    }
                }
            }
            _ => {}
        }
        match insn.flow {
            Flow::IndirectCall { slot: None } | Flow::IndirectJump { slot: None } => {
                let r = insn.ops.first().and_then(|o| if let Op::Reg(r) = o { xnum(r) } else { None });
                if let Some(s) = r.and_then(|r| self.slots.get(r).copied().flatten()) {
                    insn.flow = match insn.flow {
                        Flow::IndirectCall { .. } => Flow::IndirectCall { slot: Some(s) },
                        _ => Flow::IndirectJump { slot: Some(s) },
                    };
                }
            }
            _ => {}
        }
        if matches!(insn.flow, Flow::Call { .. } | Flow::IndirectCall { .. }) {
            // Calls clobber the argument and temporary registers.
            for i in 0..19 {
                if let Some(v) = self.vals.get_mut(i) {
                    *v = None;
                }
                if let Some(v) = self.slots.get_mut(i) {
                    *v = None;
                }
            }
            return;
        }
        for w in &insn.writes {
            if let Some(n) = xnum(w) {
                if let Some(v) = self.vals.get_mut(n) {
                    *v = None;
                }
                if let Some(v) = self.slots.get_mut(n) {
                    *v = None;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn x86_basics() {
        // call rel32
        let i = decode(Mode::X64, &[0xe8, 0x10, 0, 0, 0], 0x1000, true).unwrap();
        assert_eq!(i.flow, Flow::Call { target: 0x1015 });
        assert_eq!(i.mnemonic, "call");
        // lea rdi, [rip+0x100]
        let i = decode(Mode::X64, &[0x48, 0x8d, 0x3d, 0, 1, 0, 0], 0x1000, true).unwrap();
        assert_eq!(i.refs, vec![0x1107]);
        assert_eq!(i.kind, Kind::Lea);
        assert!(i.writes.contains(&"rdi".to_string()));
        // call [rip+x]
        let i = decode(Mode::X64, &[0xff, 0x15, 0, 1, 0, 0], 0x1000, false).unwrap();
        assert_eq!(i.flow, Flow::IndirectCall { slot: Some(0x1106) });
        // jle
        let i = decode(Mode::X64, &[0x7e, 0x09], 0x1000, false).unwrap();
        assert_eq!(i.flow, Flow::Cond { target: 0x100b });
        assert_eq!(i.cond, Some(Cond::Le));
        // xor eax, eax defines rax without reading it
        let i = decode(Mode::X64, &[0x31, 0xc0], 0, false).unwrap();
        assert!(i.writes.contains(&"rax".to_string()) && !i.reads.contains(&"rax".to_string()));
        assert_eq!(decode(Mode::X64, &[0xc3], 0, false).unwrap().flow, Flow::Return);
        assert_eq!(decode(Mode::X64, &[0xcc], 0, false).unwrap().flow, Flow::Stop);
        assert!(decode(Mode::X64, &[], 0, false).is_none());
        assert!(decode(Mode::X64, &[0x0f], 0, false).is_none());
        // 16-bit int 21h continues
        assert_eq!(decode(Mode::X16, &[0xcd, 0x21], 0x100, false).unwrap().flow, Flow::Next);
    }

    #[test]
    fn a64_basics() {
        let w = |x: u32| x.to_le_bytes();
        let i = decode(Mode::A64, &w(0x9400_0008), 0x1000, true).unwrap();
        assert_eq!(i.flow, Flow::Call { target: 0x1020 });
        let i = decode(Mode::A64, &w(0xd65f03c0), 0x1000, true).unwrap();
        assert_eq!(i.flow, Flow::Return);
        let i = decode(Mode::A64, &w(0x3400_0060), 0x1000, true).unwrap();
        assert_eq!(i.flow, Flow::Cond { target: 0x100c });
        assert_eq!(i.cond, Some(Cond::RegZero("w0".into())));
        // adrp x0, +1 page; add x0, x0, #0x10 → 0x2010
        let mut c = ArmConsts::default();
        let mut a = decode(Mode::A64, &w(0xb000_0000), 0x1000, true).unwrap();
        assert!(a.operands.contains("0x2000"), "{}", a.operands);
        c.apply(&mut a);
        let mut b = decode(Mode::A64, &w(0x9100_4000), 0x1004, true).unwrap();
        c.apply(&mut b);
        assert_eq!(b.refs, vec![0x2010]);
        assert_eq!(c.value("x0"), Some(0x2010));
    }

    #[test]
    fn a_thumb_bl_call_targets_its_destination() {
        for fmt in [false, true] {
            let i = decode(Mode::T32, &[0x00, 0xf0, 0x05, 0xf8], 0x1002, fmt).unwrap();
            assert_eq!(i.flow, Flow::Call { target: 0x1010 });
            assert_eq!(i.ops, vec![Op::Addr(0x1010)]);
            let i = decode(Mode::T32, &[0xff, 0xf7, 0xf7, 0xff], 0x1010, fmt).unwrap();
            assert_eq!(i.flow, Flow::Call { target: 0x1002 });
        }
    }

    #[test]
    fn arm_and_thumb_branches_target_what_llvm_objdump_reports() {
        // Bytes and targets from clang-assembled code disassembled by llvm-objdump.
        let cases: &[(Mode, &str, &[u8], u64, u64)] = &[
            (Mode::T32, "b", &[0x14, 0xe0], 0x1000, 0x102c),
            (Mode::T32, "beq", &[0x13, 0xd0], 0x1002, 0x102c),
            (Mode::T32, "b.w", &[0x00, 0xf0, 0x12, 0xb8], 0x1004, 0x102c),
            (Mode::T32, "beq.w", &[0x00, 0xf0, 0x10, 0x80], 0x1008, 0x102c),
            (Mode::T32, "bl", &[0x00, 0xf0, 0x0e, 0xf8], 0x100c, 0x102c),
            (Mode::T32, "cbz", &[0x60, 0xb1], 0x1010, 0x102c),
            (Mode::T32, "cbnz", &[0x59, 0xb9], 0x1012, 0x102c),
            (Mode::T32, "blx", &[0xff, 0xf7, 0xfe, 0xef], 0x1016, 0x1014),
            (Mode::T32, "bne.w", &[0x40, 0xf0, 0x06, 0x80], 0x1024, 0x1034),
            (Mode::T32, "bne", &[0x03, 0xd1], 0x102a, 0x1034),
            (Mode::A32, "b", &[0x04, 0x00, 0x00, 0xea], 0x1000, 0x1018),
            (Mode::A32, "beq", &[0x03, 0x00, 0x00, 0x0a], 0x1004, 0x1018),
            (Mode::A32, "bl", &[0xfe, 0xff, 0xff, 0xeb], 0x1008, 0x1008),
            (Mode::A32, "blx", &[0xfe, 0xff, 0xff, 0xfa], 0x100c, 0x100c),
            (Mode::A32, "b back", &[0xfa, 0xff, 0xff, 0xea], 0x1010, 0x1000),
        ];
        for (mode, name, bytes, at, want) in cases {
            let i = decode(*mode, bytes, *at, false).unwrap();
            let got = match i.flow {
                Flow::Call { target } | Flow::Jump { target } | Flow::Cond { target } => target,
                other => panic!("{mode:?} {name}: {other:?}"),
            };
            assert_eq!(got, *want, "{mode:?} {name}");
        }
        let cbz = decode(Mode::T32, &[0x60, 0xb1], 0x1010, false).unwrap();
        assert_eq!(cbz.reads, vec!["r0".to_string()]);
        assert!(cbz.writes.is_empty());
    }

    #[test]
    fn a_thumb_bl_discovers_the_callee_instead_of_padding() {
        use crate::{Image, Limits, NoControl, Program};
        use craft_anything_formats::{Arch, Binary};
        use std::sync::Arc;

        let bytes = [0x10, 0xb5, 0x00, 0xf0, 0x05, 0xf8, 0x10, 0xbd, 0, 0, 0, 0, 0, 0, 0, 0, 0x70, 0x47];
        let mut bin = Binary::raw(Arch::Arm, 0x1000, bytes.len() as u64, 0);
        bin.entry = Some(0x1001);
        let img = Image::from_binary(Arc::from(bytes), bin);
        assert_eq!(img.mode, Some(Mode::T32));
        let p = Program::analyze(&img, &Limits::default(), &NoControl).unwrap();
        let caller = p.functions.get(&0x1000).unwrap();
        assert_eq!(caller.calls.first().unwrap().target, Some(0x1010));
        assert!(p.functions.contains_key(&0x1010));
        assert!(!p.functions.contains_key(&0x100c));
    }

    #[test]
    fn a32_doubleword_rt15_is_invalid() {
        assert!(decode(Mode::A32, &[0xf3, 0xfe, 0xc7, 0xc0], 0, true).is_none());
        for word in [0xe1c0_f0d0u32, 0xe1c0_f0f0, 0xe180_f0d1, 0xe180_f0f1] {
            assert!(decode(Mode::A32, &word.to_le_bytes(), 0, true).is_none());
        }
    }

    #[test]
    fn a32_doubleword_other_registers_still_decode() {
        // LDRD/STRD immediate and register forms, including valid Rt=2.
        for base in [0xe1c0_00d0u32, 0xe1c0_00f0, 0xe180_00d1, 0xe180_00f1] {
            for rt in 0..15 {
                let word = base | (rt << 12);
                assert!(decode(Mode::A32, &word.to_le_bytes(), 0, true).is_some());
            }
        }
    }

    #[test]
    fn a32_single_register_loads_and_stores_still_decode() {
        // Ordinary LDR/STR, plus extra halfword/signed loads with Rt=15.
        for word in [0xe590_2000u32, 0xe580_2000, 0xe1d0_f0b0, 0xe1d0_f0d0, 0xe1d0_f0f0] {
            assert!(decode(Mode::A32, &word.to_le_bytes(), 0, true).is_some());
        }
    }

    #[test]
    fn junk_never_panics() {
        for seed in 0..64u64 {
            let bytes = craft_anything_testkit::noise(seed, 64);
            for mode in [Mode::X16, Mode::X32, Mode::X64, Mode::A32, Mode::T32, Mode::A64] {
                for off in 0..bytes.len() {
                    let _ = decode(mode, &bytes[off..], 0x1000 + off as u64, true);
                }
            }
        }
    }

    #[test]
    fn absolutize_rewrites_relative_operands() {
        assert_eq!(absolutize("$+0x20", 0x1000), "0x1020");
        assert_eq!(absolutize("x0, $-0x8", 0x1000), "x0, 0xff8");
        assert_eq!(absolutize("$zz", 0), "$zz");
    }
}
