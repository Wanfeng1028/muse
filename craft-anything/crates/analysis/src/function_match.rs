//! Pair the functions of two builds of a program, from what the built-in engine found in each.
//!
//! Each stage only looks at what earlier stages left: unique exact names that aren't generated,
//! then identical bytes, then bytes with addresses masked out, then a structural fingerprint. A
//! pair needs one candidate on each side; anything else stays unmatched and is listed as
//! ambiguous. Equal names say two functions correspond, not that the code is the same, so every
//! pair says what comparing the bodies found.

use craft_anything_disasm::{ArmConsts, Control, DisasmError, Flow, Function, Image, Mode, Op, Program, XrefKind};
use craft_anything_evidence::sha256_hex;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

/// Bodies smaller than this say too little to pair on bytes or structure alone.
pub const MIN_BODY_BYTES: u64 = 16;
/// Bodies at least this big make an identical-bytes pair a strong one.
const STRONG_BODY_BYTES: u64 = 64;

/// How a pair was made.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MatchMethod {
    ExactName,
    IdenticalBytes,
    MaskedBytes,
    Structure,
}

impl MatchMethod {
    pub fn name(self) -> &'static str {
        match self {
            MatchMethod::ExactName => "exact_name",
            MatchMethod::IdenticalBytes => "identical_bytes",
            MatchMethod::MaskedBytes => "masked_bytes",
            MatchMethod::Structure => "structure",
        }
    }
}

/// How far to trust that a pair is the same function.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MatchConfidence {
    High,
    Medium,
    Low,
}

/// What comparing the two bodies found.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BodyStatus {
    /// Every byte is the same.
    Identical,
    /// The same instructions, apart from addresses.
    SameApartFromAddresses,
    Changed,
    /// One body wasn't fully read, or the builds are for different processors.
    NotCompared,
}

/// A function as seen by the matcher.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FunctionRef {
    #[serde(with = "craft_anything_formats::hex_addr")]
    pub entry: u64,
    pub name: String,
    pub size: u64,
}

/// Two functions paired.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MatchedPair {
    pub left: FunctionRef,
    pub right: FunctionRef,
    pub method: MatchMethod,
    pub confidence: MatchConfidence,
    pub body: BodyStatus,
    /// Both have real names and they differ.
    pub renamed: bool,
    /// What differs beyond the bytes: `calls`, `strings`.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub differences: Vec<&'static str>,
}

/// Candidates a stage couldn't tell apart. None of them is paired.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct AmbiguousGroup {
    pub method: MatchMethod,
    pub left: Vec<FunctionRef>,
    pub right: Vec<FunctionRef>,
}

/// The whole result.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct MatchResult {
    pub pairs: Vec<MatchedPair>,
    pub ambiguous: Vec<AmbiguousGroup>,
    pub only_left: Vec<FunctionRef>,
    pub only_right: Vec<FunctionRef>,
}

/// One function's facts, computed once.
struct Print {
    entry: u64,
    name: String,
    generated: bool,
    size: u64,
    /// Every byte of every block was read.
    whole: bool,
    raw: String,
    /// `None` where this processor's address fields aren't masked.
    masked: Option<String>,
    blocks: usize,
    /// Called names in order, `None` for a call to something unnamed.
    calls: Vec<Option<String>>,
    strings: Vec<String>,
}

impl Print {
    fn as_ref(&self) -> FunctionRef {
        FunctionRef { entry: self.entry, name: self.name.clone(), size: self.size }
    }

    /// The structure stage's key; `None` when there's nothing distinctive in it.
    fn fingerprint(&self) -> Option<String> {
        let mut named: Vec<&str> = self.calls.iter().flatten().map(String::as_str).collect();
        named.sort_unstable();
        if named.is_empty() && self.strings.is_empty() {
            return None;
        }
        Some(sha256_hex(format!("{}\u{1}{}\u{1}{}", self.blocks, named.join("\u{2}"), self.strings.join("\u{2}")).as_bytes()))
    }
}

fn flow_target(f: &Flow) -> Option<u64> {
    match f {
        Flow::Jump { target } | Flow::Cond { target } | Flow::Call { target } => Some(*target),
        _ => None,
    }
}

/// Zero `pattern` in `bytes` where it ends closest to the instruction's end.
fn zero_last(bytes: &mut [u8], pattern: &[u8]) -> bool {
    if pattern.is_empty() || bytes.len() < pattern.len() {
        return false;
    }
    for start in (0..=bytes.len() - pattern.len()).rev() {
        if let Some(w) = bytes.get_mut(start..start + pattern.len())
            && w == pattern
        {
            w.fill(0);
            return true;
        }
    }
    false
}

fn mask_x86(insn: &craft_anything_disasm::Insn, f: &Function, bytes: &mut [u8]) {
    let end = insn.end();
    let mask_addr = |a: u64, bytes: &mut [u8]| {
        let rel = a.wrapping_sub(end) as u32;
        if !zero_last(bytes, &rel.to_le_bytes()) && !zero_last(bytes, &(a as u32).to_le_bytes()) {
            zero_last(bytes, &a.to_le_bytes());
        }
    };
    if let Some(t) = flow_target(&insn.flow)
        && !f.contains(t)
    {
        let rel = t.wrapping_sub(end);
        if !zero_last(bytes, &(rel as u32).to_le_bytes())
            && let Some(last) = bytes.last_mut()
            && *last == rel as u8
        {
            *last = 0;
        }
    }
    for op in &insn.ops {
        if let Op::Mem(m) = op
            && let Some(a) = m.addr
        {
            mask_addr(a, bytes);
        }
    }
    for a in &insn.refs {
        if !f.contains(*a) {
            mask_addr(*a, bytes);
        }
    }
}

/// The instruction word with its address field cleared, for the encodings that hold one.
fn mask_a64(insn: &craft_anything_disasm::Insn, f: &Function, word: u32) -> u32 {
    let leaves = flow_target(&insn.flow).is_some_and(|t| !f.contains(t));
    if word & 0x7c00_0000 == 0x1400_0000 {
        // b, bl
        return if leaves { word & 0xfc00_0000 } else { word };
    }
    if word & 0xff00_0010 == 0x5400_0000 || word & 0x7e00_0000 == 0x3400_0000 {
        // b.cond, cbz, cbnz
        return if leaves { word & 0xff00_001f } else { word };
    }
    if word & 0x7e00_0000 == 0x3600_0000 {
        // tbz, tbnz
        return if leaves { word & 0xfff8_001f } else { word };
    }
    if word & 0x1f00_0000 == 0x1000_0000 {
        // adr, adrp
        return word & 0x9f00_001f;
    }
    if word & 0x3b00_0000 == 0x1800_0000 {
        // ldr (literal)
        return word & 0xff00_001f;
    }
    if !insn.refs.is_empty() && (word & 0x7f80_0000 == 0x1100_0000 || word & 0x3b00_0000 == 0x3900_0000) {
        // add or load/store: the low half of an address started by adrp.
        return word & 0xffc0_03ff;
    }
    word
}

fn print_function(img: &Image, prog: &Program, f: &Function) -> Print {
    let mut blocks: Vec<_> = f.blocks.iter().collect();
    blocks.sort_by_key(|b| b.start);
    let can_mask = matches!(prog.mode, Mode::X32 | Mode::X64 | Mode::A64);
    let mut raw = Vec::new();
    let mut masked = Vec::new();
    let mut whole = !f.truncated;
    for b in &blocks {
        let len = b.end.saturating_sub(b.start);
        let Ok(want) = usize::try_from(len) else {
            whole = false;
            continue;
        };
        let bytes = img.read(b.start, want).unwrap_or(&[]);
        if bytes.len() != want {
            whole = false;
        }
        raw.extend_from_slice(bytes);
        if !can_mask {
            continue;
        }
        let mut consts = ArmConsts::default();
        let mut a = b.start;
        while a < b.end {
            let Some(mut insn) = img.decode(a, false) else {
                whole = false;
                break;
            };
            if insn.len == 0 {
                whole = false;
                break;
            }
            if prog.mode == Mode::A64 {
                consts.apply(&mut insn);
            }
            let Some(ib) = img.read(a, usize::from(insn.len)) else {
                whole = false;
                break;
            };
            let mut ib = ib.to_vec();
            if prog.mode == Mode::A64 {
                if let Ok(w) = <[u8; 4]>::try_from(ib.as_slice()) {
                    masked.extend_from_slice(&mask_a64(&insn, f, u32::from_le_bytes(w)).to_le_bytes());
                } else {
                    masked.extend_from_slice(&ib);
                }
            } else {
                mask_x86(&insn, f, &mut ib);
                masked.extend_from_slice(&ib);
            }
            a = insn.end();
        }
    }
    let calls = prog
        .callees(f)
        .into_iter()
        .map(|c| {
            let generated = c.target.and_then(|t| prog.functions.get(&t)).is_some_and(|t| t.name_source == "generated");
            if generated { None } else { c.name }
        })
        .collect();
    let mut strings = BTreeSet::new();
    for b in &blocks {
        for (_, xs) in prog.xrefs_from.range(b.start..b.end) {
            for x in xs.iter().filter(|x| x.kind == XrefKind::String) {
                if let Some(s) = prog.string_at(x.to) {
                    strings.insert(s.text.clone());
                }
            }
        }
    }
    Print {
        entry: f.entry,
        name: f.name.clone(),
        generated: f.name_source == "generated",
        size: raw.len() as u64,
        whole,
        raw: sha256_hex(&raw),
        masked: can_mask.then(|| sha256_hex(&masked)),
        blocks: blocks.len(),
        calls,
        strings: strings.into_iter().collect(),
    }
}

fn prints(img: &Image, prog: &Program, ctl: &dyn Control, what: &str) -> Result<Vec<Print>, DisasmError> {
    let total = prog.functions.len().max(1) as f32;
    let mut out = Vec::with_capacity(prog.functions.len());
    for (i, f) in prog.functions.values().enumerate() {
        if ctl.cancelled() {
            return Err(DisasmError::Cancelled);
        }
        if i % 1024 == 0 {
            ctl.progress(i as f32 / total, &format!("reading the bodies of {what}"));
        }
        out.push(print_function(img, prog, f));
    }
    Ok(out)
}

/// What comparing two bodies found, and what differs beyond the bytes.
fn compare(l: &Print, r: &Print, same_processor: bool) -> (BodyStatus, Vec<&'static str>) {
    if !same_processor || !l.whole || !r.whole {
        return (BodyStatus::NotCompared, Vec::new());
    }
    let mut differences = Vec::new();
    // The bytes hide which function a masked call reaches, and what a masked string says.
    let calls_differ = l.calls.len() != r.calls.len() || l.calls.iter().zip(&r.calls).any(|(a, b)| matches!((a, b), (Some(x), Some(y)) if x != y));
    if calls_differ {
        differences.push("calls");
    }
    if l.strings != r.strings {
        differences.push("strings");
    }
    let body = if l.raw == r.raw && l.size == r.size {
        BodyStatus::Identical
    } else if l.masked.is_some() && l.masked == r.masked {
        BodyStatus::SameApartFromAddresses
    } else {
        BodyStatus::Changed
    };
    // Equal bytes that reach different things are different code once it is linked.
    if body == BodyStatus::SameApartFromAddresses && !differences.is_empty() {
        return (BodyStatus::Changed, differences);
    }
    (body, differences)
}

/// One stage: group what's still unpaired by `key`. A key with one candidate on each side pairs
/// them; a key with candidates on both sides and more than one on either is noted as ambiguous.
struct Matcher<'a> {
    left: &'a [Print],
    right: &'a [Print],
    left_free: Vec<bool>,
    right_free: Vec<bool>,
    same_processor: bool,
    out: MatchResult,
    noted: Vec<(MatchMethod, Vec<usize>, Vec<usize>)>,
}

impl Matcher<'_> {
    fn stage(&mut self, method: MatchMethod, key: impl Fn(&Print) -> Option<String>) {
        let group = |prints: &[Print], free: &[bool]| {
            let mut m: BTreeMap<String, Vec<usize>> = BTreeMap::new();
            for (i, p) in prints.iter().enumerate() {
                if free.get(i).copied().unwrap_or(false)
                    && let Some(k) = key(p)
                {
                    m.entry(k).or_default().push(i);
                }
            }
            m
        };
        let ls = group(self.left, &self.left_free);
        let rs = group(self.right, &self.right_free);
        for (k, l) in &ls {
            let Some(r) = rs.get(k) else { continue };
            if let ([li], [ri]) = (l.as_slice(), r.as_slice()) {
                self.pair(*li, *ri, method);
            } else {
                self.noted.push((method, l.clone(), r.clone()));
            }
        }
    }

    fn pair(&mut self, li: usize, ri: usize, method: MatchMethod) {
        let (Some(l), Some(r)) = (self.left.get(li), self.right.get(ri)) else { return };
        if let Some(x) = self.left_free.get_mut(li) {
            *x = false;
        }
        if let Some(x) = self.right_free.get_mut(ri) {
            *x = false;
        }
        let (body, differences) = compare(l, r, self.same_processor);
        let confidence = match method {
            MatchMethod::ExactName => MatchConfidence::High,
            MatchMethod::IdenticalBytes if l.size >= STRONG_BODY_BYTES => MatchConfidence::High,
            MatchMethod::IdenticalBytes | MatchMethod::MaskedBytes => MatchConfidence::Medium,
            MatchMethod::Structure => MatchConfidence::Low,
        };
        self.out.pairs.push(MatchedPair {
            left: l.as_ref(),
            right: r.as_ref(),
            method,
            confidence,
            body,
            renamed: !l.generated && !r.generated && l.name != r.name,
            differences,
        });
    }

    /// Keep each still-unpaired function in the first group that named it; the rest are alone.
    fn finish(mut self) -> MatchResult {
        let mut left_seen = self.left_free.clone();
        let mut right_seen = self.right_free.clone();
        for (method, l, r) in std::mem::take(&mut self.noted) {
            let open = |ids: &[usize], seen: &[bool]| ids.iter().copied().filter(|i| seen.get(*i).copied().unwrap_or(false)).collect::<Vec<_>>();
            let (lk, rk) = (open(&l, &left_seen), open(&r, &right_seen));
            // With one side used up there's nothing left to confuse them with.
            if lk.is_empty() || rk.is_empty() {
                continue;
            }
            let take = |ids: &[usize], seen: &mut [bool], prints: &[Print]| {
                let mut v = Vec::new();
                for i in ids {
                    if let Some(s) = seen.get_mut(*i) {
                        *s = false;
                    }
                    if let Some(p) = prints.get(*i) {
                        v.push(p.as_ref());
                    }
                }
                v
            };
            let left = take(&lk, &mut left_seen, self.left);
            let right = take(&rk, &mut right_seen, self.right);
            self.out.ambiguous.push(AmbiguousGroup { method, left, right });
        }
        let alone = |prints: &[Print], seen: &[bool]| prints.iter().zip(seen).filter(|(_, s)| **s).map(|(p, _)| p.as_ref()).collect::<Vec<_>>();
        self.out.only_left = alone(self.left, &left_seen);
        self.out.only_right = alone(self.right, &right_seen);
        self.out.pairs.sort_by_key(|p| p.left.entry);
        self.out
    }
}

/// Pair the functions of two analysed programs. Nothing runs; only `ctl` can stop it early.
pub fn match_programs(left: (&Image, &Program), right: (&Image, &Program), ctl: &dyn Control) -> Result<MatchResult, DisasmError> {
    let lp = prints(left.0, left.1, ctl, "the first program")?;
    let rp = prints(right.0, right.1, ctl, "the second program")?;
    let same_processor = left.1.mode == right.1.mode;
    let mut m = Matcher {
        left: &lp,
        right: &rp,
        left_free: vec![true; lp.len()],
        right_free: vec![true; rp.len()],
        same_processor,
        out: MatchResult::default(),
        noted: Vec::new(),
    };
    m.stage(MatchMethod::ExactName, |p| (!p.generated).then(|| p.name.clone()));
    if ctl.cancelled() {
        return Err(DisasmError::Cancelled);
    }
    if same_processor {
        let eligible = |p: &Print| p.whole && p.size >= MIN_BODY_BYTES;
        m.stage(MatchMethod::IdenticalBytes, |p| eligible(p).then(|| p.raw.clone()));
        m.stage(MatchMethod::MaskedBytes, |p| if eligible(p) { p.masked.clone() } else { None });
        m.stage(MatchMethod::Structure, |p| if eligible(p) { p.fingerprint() } else { None });
    }
    Ok(m.finish())
}
