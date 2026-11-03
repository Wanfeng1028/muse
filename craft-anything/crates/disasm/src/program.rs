//! Whole-program analysis: function discovery, basic blocks and control flow, jump tables,
//! cross-references, strings and their uses, import thunks, and the call graph.

use crate::decode::{ArmConsts, Flow, Insn, Kind, Mode, Op};
use crate::image::Image;
use crate::{Control, DisasmError};
use craft_anything_formats::hex_addr;
use craft_anything_formats::strings::Encoding;
use craft_anything_formats::{Format, SymbolKind};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

/// Bounds on one analysis run.
#[derive(Debug, Clone)]
pub struct Limits {
    pub max_functions: usize,
    pub max_insns_per_function: usize,
    pub max_total_insns: usize,
    pub max_xrefs: usize,
    pub max_strings: usize,
    pub string_min_len: usize,
    /// Bytes of data sections scanned for strings and pointers.
    pub max_data_scan: usize,
    pub scan_prologues: bool,
}

impl Default for Limits {
    fn default() -> Self {
        Limits {
            max_functions: 50_000,
            max_insns_per_function: 60_000,
            max_total_insns: 6_000_000,
            max_xrefs: 4_000_000,
            max_strings: 200_000,
            string_min_len: 4,
            max_data_scan: 96 << 20,
            scan_prologues: true,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum XrefKind {
    Call,
    Jump,
    Data,
    String,
    /// A pointer stored in data (vtables, callback tables, string tables).
    Pointer,
    /// Through an import slot.
    Import,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize)]
pub struct Xref {
    #[serde(with = "hex_addr")]
    pub from: u64,
    #[serde(with = "hex_addr")]
    pub to: u64,
    pub kind: XrefKind,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Term {
    /// Falls into the next block.
    Fall,
    Jump,
    Cond,
    Return,
    /// Indirect jump (a resolved jump table lists its successors).
    Indirect,
    Stop,
    /// Jumps to another function.
    Tail,
    /// Code ran off the end of what we could decode.
    Unknown,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Block {
    #[serde(with = "hex_addr")]
    pub start: u64,
    #[serde(with = "hex_addr")]
    pub end: u64,
    pub insns: u32,
    #[serde(with = "hex_addr::vec")]
    pub succs: Vec<u64>,
    pub term: Term,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CallSite {
    #[serde(with = "hex_addr")]
    pub site: u64,
    #[serde(with = "hex_addr::opt")]
    pub target: Option<u64>,
    /// Import called through a slot or stub.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub import: Option<String>,
    pub indirect: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct JumpTable {
    #[serde(with = "hex_addr")]
    pub site: u64,
    #[serde(with = "hex_addr")]
    pub table: u64,
    pub entry_size: u8,
    #[serde(with = "hex_addr::vec")]
    pub targets: Vec<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Function {
    #[serde(with = "hex_addr")]
    pub entry: u64,
    pub name: String,
    /// symbol, export, objc, go_pclntab, import_thunk, entry_point, heuristic, generated
    pub name_source: &'static str,
    /// entry_point, symbol, export, function_starts, objc, go_pclntab, stub, call, code_pointer, prologue
    pub discovered_by: &'static str,
    pub blocks: Vec<Block>,
    pub calls: Vec<CallSite>,
    pub insn_count: u32,
    #[serde(with = "hex_addr")]
    pub end: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub thunk_of: Option<String>,
    pub truncated: bool,
    pub jump_tables: Vec<JumpTable>,
    pub unresolved_indirect_jumps: u32,
    #[serde(with = "hex_addr::vec")]
    pub tail_calls: Vec<u64>,
    /// At least one return instruction was reached.
    pub returns: bool,
}

impl Function {
    pub fn size(&self) -> u64 {
        self.blocks.iter().map(|b| b.end.saturating_sub(b.start)).sum()
    }

    pub fn contains(&self, addr: u64) -> bool {
        self.blocks.iter().any(|b| addr >= b.start && addr < b.end)
    }

    pub fn block_at(&self, addr: u64) -> Option<&Block> {
        self.blocks.iter().find(|b| addr >= b.start && addr < b.end)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ProgString {
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub file_offset: u64,
    pub byte_len: u64,
    pub encoding: Encoding,
    pub text: String,
    pub section: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SlotInfo {
    pub name: String,
    pub library: Option<String>,
    /// slot or stub
    pub kind: &'static str,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct Stats {
    pub functions: usize,
    pub blocks: usize,
    pub instructions: usize,
    pub xrefs: usize,
    pub strings: usize,
    pub discovered_by: BTreeMap<String, usize>,
    pub unresolved_indirect_jumps: usize,
    pub jump_tables: usize,
    pub truncated_functions: usize,
}

/// The analysed program.
#[derive(Debug, Clone)]
pub struct Program {
    pub mode: Mode,
    pub functions: BTreeMap<u64, Function>,
    pub strings: Vec<ProgString>,
    pub xrefs_to: BTreeMap<u64, Vec<Xref>>,
    pub xrefs_from: BTreeMap<u64, Vec<Xref>>,
    pub import_slots: BTreeMap<u64, SlotInfo>,
    pub data_names: BTreeMap<u64, String>,
    pub stats: Stats,
    /// (code, message) pairs: what the analysis couldn't do.
    pub limitations: Vec<(String, String)>,
    /// block start → (end, function entry)
    block_index: BTreeMap<u64, (u64, u64)>,
    name_index: BTreeMap<String, u64>,
}

const NORETURN: &[&str] = &[
    "exit",
    "_exit",
    "_Exit",
    "abort",
    "__stack_chk_fail",
    "__assert_fail",
    "__assert_rtn",
    "__cxa_throw",
    "__cxa_rethrow",
    "_Unwind_Resume",
    "longjmp",
    "siglongjmp",
    "pthread_exit",
    "err",
    "errx",
    "verr",
    "verrx",
    "__libc_start_main",
    "__fortify_fail",
    "__chk_fail",
    "ExitProcess",
    "ExitThread",
    "FatalExit",
    "RaiseFailFastException",
    "_invalid_parameter_noinfo_noreturn",
    "__report_gsfailure",
    "_CxxThrowException",
    "objc_exception_throw",
    "swift_unexpectedError",
    "_ZSt9terminatev",
];

fn bare(name: &str) -> &str {
    let n = name.split('@').next().unwrap_or(name);
    n.strip_prefix("__imp_").unwrap_or(n)
}

fn is_noreturn(name: &str) -> bool {
    let b = bare(name);
    NORETURN.contains(&b) || NORETURN.contains(&b.strip_prefix('_').unwrap_or(b)) || b.contains("panicking5panic") || b.starts_with("core::panicking::")
}

struct Scan {
    insns: BTreeMap<u64, (u8, Flow)>,
    leaders: BTreeSet<u64>,
    calls: Vec<CallSite>,
    xrefs: Vec<Xref>,
    jump_tables: Vec<JumpTable>,
    tails: Vec<u64>,
    code_ptrs: Vec<u64>,
    truncated: bool,
    unresolved: u32,
    thunk_of: Option<String>,
    returns: bool,
}

struct Ctx<'a> {
    img: &'a Image,
    mode: Mode,
    limits: &'a Limits,
    slots: &'a BTreeMap<u64, SlotInfo>,
    stubs: &'a BTreeMap<u64, String>,
    sym_noreturn: &'a BTreeSet<u64>,
}

impl Program {
    /// Analyse a whole image.
    pub fn analyze(img: &Image, limits: &Limits, ctl: &dyn Control) -> Result<Program, DisasmError> {
        let mode = img.mode.ok_or_else(|| DisasmError::Unsupported(format!("{} code isn't supported by the built-in decoder yet", img.bin.arch_name)))?;
        let bin = &img.bin;
        let mut limitations: Vec<(String, String)> = Vec::new();
        // Import slots and stubs.
        let mut slots: BTreeMap<u64, SlotInfo> = BTreeMap::new();
        for s in &bin.import_slots {
            slots.entry(s.addr).or_insert(SlotInfo { name: s.name.clone(), library: s.library.clone(), kind: s.kind });
        }
        ctl.progress(0.02, "finding strings");
        let strings = collect_strings(img, limits);
        if strings.len() >= limits.max_strings {
            limitations.push(("strings_capped".into(), format!("kept the first {} strings", limits.max_strings)));
        }
        // Stubs: Mach-O stub entries from the indirect symbol table, plus PLT entries.
        let mut stubs: BTreeMap<u64, String> = BTreeMap::new();
        for (a, s) in &slots {
            if s.kind == "stub" {
                stubs.insert(*a, s.name.clone());
            }
        }
        scan_plt(img, mode, &slots, &mut stubs);
        let mut sym_noreturn = BTreeSet::new();
        for s in bin.symbols.iter().filter(|s| s.defined && s.kind == SymbolKind::Function) {
            if is_noreturn(&s.name) {
                sym_noreturn.insert(s.addr);
            }
        }
        // Seeds.
        let mut seeds: Vec<(u64, &'static str)> = Vec::new();
        let thumb = mode == Mode::T32;
        let clean = |a: u64| if thumb { a & !1 } else { a };
        if let Some(e) = bin.entry {
            seeds.push((clean(e), "entry_point"));
        }
        for s in &bin.symbols {
            if s.defined && s.kind == SymbolKind::Function && s.addr != 0 {
                seeds.push((clean(s.addr), "symbol"));
            }
        }
        for e in &bin.exports {
            seeds.push((clean(e.addr), "export"));
        }
        for &f in &bin.function_starts {
            seeds.push((clean(f), "function_starts"));
        }
        for a in stubs.keys() {
            seeds.push((*a, "stub"));
        }
        // Names a language's own metadata keeps even in a stripped program, with where they came from.
        let mut meta_names: BTreeMap<u64, (String, &'static str)> = BTreeMap::new();
        for f in craft_anything_formats::go::functions(&img.data) {
            if f.entry != 0 {
                meta_names.entry(f.entry).or_insert((f.name, "go_pclntab"));
                seeds.push((f.entry, "go_pclntab"));
            }
        }
        if bin.format == Format::MachO {
            let meta = craft_anything_formats::macho::objc_metadata(&img.data, bin);
            for c in &meta.classes {
                for m in &c.methods {
                    if let Some(imp) = m.imp {
                        let class = match &c.category {
                            Some(cat) => format!("{}({cat})", c.name),
                            None => c.name.clone(),
                        };
                        meta_names.entry(imp).or_insert_with(|| (format!("{}[{class} {}]", m.kind, m.selector), "objc"));
                        seeds.push((imp, "objc"));
                    }
                }
            }
        }
        let ctx = Ctx { img, mode, limits, slots: &slots, stubs: &stubs, sym_noreturn: &sym_noreturn };
        let mut known: BTreeSet<u64> = BTreeSet::new();
        let mut queue: VecDeque<(u64, &'static str)> = VecDeque::new();
        for (a, src) in seeds {
            if img.is_exec(a) && known.insert(a) {
                queue.push_back((a, src));
            }
        }
        let mut functions: BTreeMap<u64, Function> = BTreeMap::new();
        let mut all_xrefs: Vec<Xref> = Vec::new();
        let mut total_insns = 0usize;
        let mut hit_function_cap = false;
        let mut hit_insn_cap = false;
        let mut covered: BTreeMap<u64, u64> = BTreeMap::new();
        for round in 0..2 {
            while let Some((entry, src)) = queue.pop_front() {
                if functions.len().is_multiple_of(64) {
                    if ctl.cancelled() {
                        return Err(DisasmError::Cancelled);
                    }
                    let done = functions.len() as f32;
                    ctl.progress(0.05 + 0.85 * done / (done + queue.len() as f32 + 1.0), &format!("{} functions", functions.len()));
                }
                if functions.len() >= limits.max_functions {
                    hit_function_cap = true;
                    break;
                }
                if total_insns >= limits.max_total_insns {
                    hit_insn_cap = true;
                    break;
                }
                let scan = scan_function(&ctx, entry, &known);
                total_insns += scan.insns.len();
                for c in &scan.calls {
                    if let Some(t) = c.target
                        && img.is_exec(t)
                        && known.insert(t)
                    {
                        queue.push_back((t, "call"));
                    }
                }
                for &t in &scan.tails {
                    if img.is_exec(t) && known.insert(t) {
                        queue.push_back((t, "call"));
                    }
                }
                for &p in &scan.code_ptrs {
                    if !scan.insns.contains_key(&p) && p % mode.align() == 0 && known.insert(p) {
                        queue.push_back((p, "code_pointer"));
                    }
                }
                let f = build_function(entry, src, scan, &mut all_xrefs, limits.max_xrefs);
                for b in &f.blocks {
                    covered.insert(b.start, b.end);
                }
                functions.insert(entry, f);
            }
            if round == 0 && limits.scan_prologues && !hit_function_cap && !hit_insn_cap {
                if ctl.cancelled() {
                    return Err(DisasmError::Cancelled);
                }
                ctl.progress(0.9, "scanning for functions nothing calls");
                for a in prologue_scan(img, mode, &covered) {
                    if known.insert(a) {
                        queue.push_back((a, "prologue"));
                    }
                }
            }
        }
        // A function scanned before a later-found entry was known may have run on into it, or read
        // a switch table past its end into the next function; scan those again now that every
        // entry is known, so each keeps only its own body.
        let overran: Vec<(u64, &'static str)> = functions
            .values()
            .filter(|f| {
                let next = known.range(f.entry.saturating_add(1)..).next().copied().unwrap_or(u64::MAX);
                f.blocks.iter().any(|b| known.range(b.start..b.end.max(b.start)).any(|&k| k != f.entry) || (!f.jump_tables.is_empty() && b.start >= next))
            })
            .map(|f| (f.entry, f.discovered_by))
            .collect();
        for (i, (entry, src)) in overran.into_iter().enumerate() {
            if i % 64 == 0 && ctl.cancelled() {
                return Err(DisasmError::Cancelled);
            }
            let scan = scan_function(&ctx, entry, &known);
            functions.insert(entry, build_function(entry, src, scan, &mut all_xrefs, limits.max_xrefs));
        }
        if hit_function_cap {
            limitations.push((
                "function_limit".into(),
                format!("function discovery stopped after {} functions; the function list is incomplete and some code is not analysed", limits.max_functions),
            ));
        }
        if hit_insn_cap {
            limitations.push((
                "instruction_limit".into(),
                format!(
                    "function discovery stopped after {} instructions; the function list is incomplete and some code is not analysed",
                    limits.max_total_insns
                ),
            ));
        }
        // Data → code and data → string pointers.
        ctl.progress(0.93, "scanning data for pointers");
        let string_index: BTreeMap<u64, usize> = strings.iter().enumerate().map(|(i, s)| (s.addr, i)).collect();
        pointer_scan(img, limits, &functions, &string_index, &mut all_xrefs);
        let strings = split_at_references(strings, &all_xrefs);
        let string_index: BTreeMap<u64, usize> = strings.iter().enumerate().map(|(i, s)| (s.addr, i)).collect();
        // Re-classify references that land on strings.
        for x in all_xrefs.iter_mut() {
            if matches!(x.kind, XrefKind::Data)
                && let Some((&start, &i)) = string_index.range(..=x.to).next_back()
                && let Some(s) = strings.get(i)
                && x.to < start.saturating_add(s.byte_len.max(1))
            {
                x.kind = XrefKind::String;
                x.to = start;
            }
        }
        all_xrefs.sort_unstable();
        all_xrefs.dedup();
        if all_xrefs.len() >= limits.max_xrefs {
            limitations.push(("xref_limit".into(), format!("kept the first {} cross-references", limits.max_xrefs)));
        }
        let mut xrefs_to: BTreeMap<u64, Vec<Xref>> = BTreeMap::new();
        let mut xrefs_from: BTreeMap<u64, Vec<Xref>> = BTreeMap::new();
        for x in &all_xrefs {
            xrefs_to.entry(x.to).or_default().push(*x);
            xrefs_from.entry(x.from).or_default().push(*x);
        }
        // Names.
        let mut data_names = BTreeMap::new();
        for s in bin.symbols.iter().filter(|s| s.defined && s.kind == SymbolKind::Data && s.addr != 0) {
            data_names.entry(s.addr).or_insert_with(|| s.name.clone());
        }
        let main_guess = guess_main(img, mode, &functions, &slots);
        let mut names_taken: BTreeSet<String> = BTreeSet::new();
        for f in functions.values_mut() {
            let (name, source) = function_name(img, f, &stubs, &meta_names, main_guess);
            f.name = name;
            f.name_source = source;
            names_taken.insert(f.name.clone());
        }
        let mut name_index = BTreeMap::new();
        for f in functions.values() {
            name_index.entry(f.name.clone()).or_insert(f.entry);
        }
        for s in bin.symbols.iter().filter(|s| s.defined && s.kind == SymbolKind::Function) {
            if functions.contains_key(&clean(s.addr)) {
                name_index.entry(s.name.clone()).or_insert(clean(s.addr));
                if let Some(d) = &s.demangled {
                    name_index.entry(d.clone()).or_insert(clean(s.addr));
                }
            }
        }
        let mut block_index = BTreeMap::new();
        let mut stats = Stats { functions: functions.len(), strings: strings.len(), xrefs: all_xrefs.len(), ..Default::default() };
        for f in functions.values() {
            *stats.discovered_by.entry(f.discovered_by.to_string()).or_default() += 1;
            stats.blocks += f.blocks.len();
            stats.instructions += f.insn_count as usize;
            stats.unresolved_indirect_jumps += f.unresolved_indirect_jumps as usize;
            stats.jump_tables += f.jump_tables.len();
            stats.truncated_functions += usize::from(f.truncated);
            for b in &f.blocks {
                block_index.entry(b.start).or_insert((b.end, f.entry));
            }
        }
        if stats.unresolved_indirect_jumps > 0 {
            limitations.push((
                "indirect_jumps_unresolved".into(),
                format!("{} indirect jumps could not be resolved; code they reach may be missing", stats.unresolved_indirect_jumps),
            ));
        }
        if stats.truncated_functions > 0 {
            limitations.push(("functions_truncated".into(), format!("{} functions hit the per-function instruction limit", stats.truncated_functions)));
        }
        if bin.mitigations.stripped {
            limitations.push(("stripped_binary".into(), "no local symbols: most function names are generated (sub_…)".into()));
        }
        limitations.push((
            "static_analysis_only".into(),
            "functions reached only through computed pointers or at run time may be missing; absence is not proof".into(),
        ));
        ctl.progress(1.0, "done");
        Ok(Program { mode, functions, strings, xrefs_to, xrefs_from, import_slots: slots, data_names, stats, limitations, block_index, name_index })
    }

    /// True when function discovery stopped at the function or instruction cap, so the function
    /// list (and everything derived from it) is incomplete.
    pub fn discovery_capped(&self) -> bool {
        self.limitations.iter().any(|(c, _)| c == "function_limit" || c == "instruction_limit")
    }

    /// The function whose blocks contain `addr` (or whose range does).
    pub fn function_containing(&self, addr: u64) -> Option<&Function> {
        if let Some((_, &(end, f))) = self.block_index.range(..=addr).next_back()
            && addr < end
        {
            return self.functions.get(&f);
        }
        self.functions.range(..=addr).next_back().map(|(_, f)| f).filter(|f| f.contains(addr))
    }

    pub fn function_by_name(&self, name: &str) -> Option<&Function> {
        self.name_index.get(name).and_then(|e| self.functions.get(e))
    }

    /// The string whose bytes contain `addr`.
    pub fn string_at(&self, addr: u64) -> Option<&ProgString> {
        let i = self.strings.partition_point(|s| s.addr <= addr);
        let s = self.strings.get(i.checked_sub(1)?)?;
        (addr < s.addr.saturating_add(s.byte_len.max(1))).then_some(s)
    }

    /// The default name of an address: function, data symbol, import slot, string label.
    pub fn name_at(&self, addr: u64) -> Option<String> {
        if let Some(f) = self.functions.get(&addr) {
            return Some(f.name.clone());
        }
        if let Some(n) = self.data_names.get(&addr) {
            return Some(n.clone());
        }
        if let Some(s) = self.import_slots.get(&addr) {
            return Some(slot_label(s));
        }
        None
    }

    /// Calls and tail jumps into `entry`: (call site, caller function entry).
    pub fn callers(&self, entry: u64) -> Vec<(u64, Option<u64>)> {
        let mut out: Vec<(u64, Option<u64>)> = self
            .xrefs_to
            .get(&entry)
            .map(|v| {
                v.iter()
                    .filter(|x| matches!(x.kind, XrefKind::Call | XrefKind::Jump))
                    .map(|x| (x.from, self.function_containing(x.from).map(|f| f.entry)))
                    .collect()
            })
            .unwrap_or_default();
        // Jumps inside the function itself are not callers.
        out.retain(|(_, f)| *f != Some(entry));
        out.dedup();
        out
    }

    /// Direct callees of a function: (site, target function or import name).
    pub fn callees(&self, f: &Function) -> Vec<Callee> {
        let mut out = Vec::new();
        for c in &f.calls {
            let name = match (c.target, &c.import) {
                (_, Some(i)) => Some(i.clone()),
                (Some(t), None) => self.name_at(t),
                _ => None,
            };
            out.push(Callee { site: c.site, target: c.target, name, import: c.import.is_some(), indirect: c.indirect && c.import.is_none() });
        }
        for &t in &f.tail_calls {
            out.push(Callee { site: f.end, target: Some(t), name: self.name_at(t), import: false, indirect: false });
        }
        out
    }

    /// Every instruction of a function, in address order, with the given formatting.
    pub fn instructions(&self, img: &Image, f: &Function, fmt: bool) -> Vec<Insn> {
        let mut out = Vec::new();
        for b in &f.blocks {
            let mut consts = ArmConsts::default();
            let mut a = b.start;
            while a < b.end && out.len() < 200_000 {
                let Some(mut i) = img.decode(a, fmt) else { break };
                if self.mode == Mode::A64 {
                    consts.apply(&mut i);
                }
                a = i.end();
                if i.len == 0 {
                    break;
                }
                out.push(i);
            }
        }
        out
    }

    pub fn function_names(&self) -> impl Iterator<Item = (&String, &u64)> {
        self.name_index.iter()
    }
}

/// A resolved callee.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Callee {
    #[serde(with = "hex_addr")]
    pub site: u64,
    #[serde(with = "hex_addr::opt")]
    pub target: Option<u64>,
    pub name: Option<String>,
    pub import: bool,
    pub indirect: bool,
}

/// Display label of an import slot (`__imp_CreateFileW`, `puts@got`).
pub fn slot_label(s: &SlotInfo) -> String {
    if s.kind == "stub" {
        format!("{}@stub", s.name)
    } else if s.library.as_deref().is_some_and(|l| l.to_ascii_lowercase().ends_with(".dll")) {
        format!("__imp_{}", s.name)
    } else {
        format!("{}@got", s.name)
    }
}

/// Packed strings (Rust and Go keep text without terminators, back to back): where code points
/// into the middle of one, a new string starts there.
fn split_at_references(strings: Vec<ProgString>, xrefs: &[Xref]) -> Vec<ProgString> {
    let targets: BTreeSet<u64> = xrefs.iter().filter(|x| matches!(x.kind, XrefKind::Data | XrefKind::String)).map(|x| x.to).collect();
    let mut out = Vec::with_capacity(strings.len());
    for s in strings {
        let end = s.addr.saturating_add(s.byte_len);
        let mut cuts: Vec<usize> = targets
            .range(s.addr.saturating_add(1)..end.max(s.addr.saturating_add(1)))
            .filter_map(|&t| usize::try_from(t - s.addr).ok())
            .filter(|&at| s.text.is_char_boundary(at) && at < s.text.len())
            .collect();
        if cuts.is_empty() || !matches!(s.encoding, Encoding::Ascii | Encoding::Utf8) || s.text.len() as u64 != s.byte_len {
            out.push(s);
            continue;
        }
        cuts.push(s.text.len());
        let mut from = 0usize;
        for to in cuts {
            let Some(text) = s.text.get(from..to) else { continue };
            let at = from as u64;
            out.push(ProgString {
                addr: s.addr.saturating_add(at),
                file_offset: s.file_offset.saturating_add(at),
                byte_len: (to - from) as u64,
                encoding: if text.is_ascii() { Encoding::Ascii } else { Encoding::Utf8 },
                text: text.to_string(),
                section: s.section.clone(),
            });
            from = to;
        }
    }
    out
}

fn collect_strings(img: &Image, limits: &Limits) -> Vec<ProgString> {
    let bin = &img.bin;
    let mut out = Vec::new();
    let raw = matches!(bin.format, Format::Raw | Format::DosCom | Format::DosMz);
    let mut budget = limits.max_data_scan;
    for s in &bin.sections {
        if out.len() >= limits.max_strings || budget == 0 {
            break;
        }
        if (s.exec && !raw) || !s.alloc || matches!(s.kind, "debug" | "bss") {
            continue;
        }
        let Some(off) = s.file_offset.and_then(|o| usize::try_from(o).ok()) else { continue };
        let n = usize::try_from(s.file_size).unwrap_or(0).min(budget);
        budget -= n;
        let Some(bytes) = img.data.get(off..off.saturating_add(n).min(img.data.len())) else { continue };
        for f in craft_anything_formats::strings::extract(bytes, 0, limits.string_min_len, limits.max_strings - out.len()) {
            out.push(ProgString {
                addr: s.addr.wrapping_add(f.offset),
                file_offset: off as u64 + f.offset,
                byte_len: f.byte_len,
                encoding: f.encoding,
                text: f.text,
                section: s.name.clone(),
            });
        }
    }
    out.sort_by_key(|s| s.addr);
    out.dedup_by_key(|s| s.addr);
    out
}

/// Name PLT-style stubs: each `jmp [slot]` in a `.plt*` section is the stub for that import.
fn scan_plt(img: &Image, mode: Mode, slots: &BTreeMap<u64, SlotInfo>, stubs: &mut BTreeMap<u64, String>) {
    for s in img.bin.sections.iter().filter(|s| s.exec && (s.name.starts_with(".plt") || s.name == "__stubs" || s.name == "__auth_stubs")) {
        let mut a = s.addr;
        let end = s.addr.saturating_add(s.size.min(4 << 20));
        let mut consts = ArmConsts::default();
        let mut stub_start = a;
        while a < end {
            let Some(mut i) = img.decode(a, false) else {
                // At the top of the address space the step would wrap to 0 and walk it all again.
                let Some(next) = a.checked_add(mode.align().max(1)) else { break };
                a = next;
                stub_start = a;
                continue;
            };
            if mode == Mode::A64 {
                consts.apply(&mut i);
            }
            if let Flow::IndirectJump { slot: Some(slot) } = i.flow {
                if let Some(si) = slots.get(&slot) {
                    let start = if s.name.starts_with(".plt") && mode.is_x86() { a & !0xf } else { stub_start };
                    stubs.entry(start.max(s.addr)).or_insert_with(|| si.name.clone());
                }
                stub_start = i.end();
                consts.reset();
            } else if i.flow.ends_block() {
                stub_start = i.end();
                consts.reset();
            }
            a = i.end().max(a + 1);
        }
    }
}

fn scan_function(ctx: &Ctx<'_>, entry: u64, known: &BTreeSet<u64>) -> Scan {
    let img = ctx.img;
    let mut sc = Scan {
        insns: BTreeMap::new(),
        leaders: BTreeSet::new(),
        calls: Vec::new(),
        xrefs: Vec::new(),
        jump_tables: Vec::new(),
        tails: Vec::new(),
        code_ptrs: Vec::new(),
        truncated: false,
        unresolved: 0,
        thunk_of: None,
        returns: false,
    };
    sc.leaders.insert(entry);
    let mut work = vec![entry];
    let mut consts = ArmConsts::default();
    let mut recent: VecDeque<Insn> = VecDeque::new();
    let first = first_real(img, entry);
    while let Some(start) = work.pop() {
        let mut a = start;
        recent.clear();
        consts.reset();
        loop {
            if sc.insns.contains_key(&a) {
                break;
            }
            if sc.insns.len() >= ctx.limits.max_insns_per_function {
                sc.truncated = true;
                break;
            }
            if a != entry && a != start && known.contains(&a) && !sc.leaders.contains(&a) {
                // Fell through into another function's entry: treat as a tail.
                sc.tails.push(a);
                break;
            }
            if !img.is_exec(a) {
                break;
            }
            let Some(mut ins) = img.decode(a, false) else { break };
            if ctx.mode == Mode::A64 {
                consts.apply(&mut ins);
            }
            sc.insns.insert(a, (ins.len, ins.flow));
            for &r in &ins.refs {
                if img.is_mapped(r) {
                    let kind = if ctx.slots.contains_key(&r) { XrefKind::Import } else { XrefKind::Data };
                    sc.xrefs.push(Xref { from: a, to: r, kind });
                    if matches!(ins.kind, Kind::Lea | Kind::Mov | Kind::Push | Kind::Adr | Kind::Add) && img.is_exec(r) && !ctx.slots.contains_key(&r) {
                        sc.code_ptrs.push(r);
                    }
                }
            }
            let next = ins.end();
            match ins.flow {
                Flow::Next => {}
                Flow::Jump { target } => {
                    sc.xrefs.push(Xref { from: a, to: target, kind: XrefKind::Jump });
                    if let Some(name) = ctx.stubs.get(&target).filter(|_| a == first) {
                        sc.thunk_of = Some(name.clone());
                    }
                    if target != entry && (known.contains(&target) || !img.is_exec(target)) {
                        sc.tails.push(target);
                    } else {
                        sc.leaders.insert(target);
                        work.push(target);
                    }
                    break;
                }
                Flow::Cond { target } => {
                    sc.xrefs.push(Xref { from: a, to: target, kind: XrefKind::Jump });
                    sc.leaders.insert(next);
                    // A branch to another function's entry is a conditional tail call, not this body.
                    if target != entry && known.contains(&target) {
                        sc.tails.push(target);
                    } else {
                        sc.leaders.insert(target);
                        work.push(target);
                    }
                }
                Flow::Call { target } => {
                    sc.xrefs.push(Xref { from: a, to: target, kind: XrefKind::Call });
                    let import = ctx.stubs.get(&target).cloned();
                    let noreturn = import.as_deref().is_some_and(is_noreturn) || ctx.sym_noreturn.contains(&target);
                    sc.calls.push(CallSite { site: a, target: Some(target), import, indirect: false });
                    if noreturn {
                        break;
                    }
                }
                Flow::IndirectCall { slot } => {
                    let import = slot.and_then(|s| ctx.slots.get(&s)).map(|s| s.name.clone());
                    if let Some(s) = slot {
                        sc.xrefs.push(Xref { from: a, to: s, kind: if import.is_some() { XrefKind::Import } else { XrefKind::Data } });
                    }
                    let noreturn = import.as_deref().is_some_and(is_noreturn);
                    sc.calls.push(CallSite { site: a, target: None, import, indirect: true });
                    if noreturn {
                        break;
                    }
                }
                Flow::IndirectJump { slot } => {
                    if let Some(si) = slot.and_then(|s| ctx.slots.get(&s)) {
                        if a == first {
                            sc.thunk_of = Some(si.name.clone());
                        }
                        sc.calls.push(CallSite { site: a, target: None, import: Some(si.name.clone()), indirect: true });
                    } else if let Some(mut jt) = jump_table(img, &recent, &ins) {
                        // A switch stays inside its own function: entries outside the known
                        // function starts around the jump were read past the table's end.
                        let lo = known.range(..=a).next_back().copied().unwrap_or(entry).min(entry);
                        let hi = known.range(a.saturating_add(1)..).next().copied().unwrap_or(u64::MAX);
                        jt.targets.retain(|&t| t >= lo && t < hi);
                        for &t in &jt.targets {
                            sc.xrefs.push(Xref { from: a, to: t, kind: XrefKind::Jump });
                            // A table entry on another function's entry is a tail (or the table was
                            // read past its end): never this function's body.
                            if t != entry && known.contains(&t) {
                                sc.tails.push(t);
                            } else {
                                sc.leaders.insert(t);
                                work.push(t);
                            }
                        }
                        if jt.targets.is_empty() {
                            sc.unresolved += 1;
                        } else {
                            sc.jump_tables.push(jt);
                        }
                    } else {
                        sc.unresolved += 1;
                    }
                    break;
                }
                Flow::Return => {
                    sc.returns = true;
                    break;
                }
                Flow::Stop => break,
            }
            if recent.len() >= 12 {
                recent.pop_front();
            }
            recent.push_back(ins);
            if next <= a {
                break;
            }
            a = next;
        }
    }
    sc
}

/// The first instruction of the function that isn't a landing pad (`endbr64`, `bti`).
fn first_real(img: &Image, entry: u64) -> u64 {
    match img.decode(entry, false) {
        Some(i) if i.kind == Kind::Nop => i.end(),
        _ => entry,
    }
}

/// Recover a jump table for an indirect jump, from the instructions just before it.
fn jump_table(img: &Image, recent: &VecDeque<Insn>, jmp: &Insn) -> Option<JumpTable> {
    let bound = recent
        .iter()
        .rev()
        .find_map(|i| match (i.kind, i.ops.get(1)) {
            (Kind::Cmp, Some(Op::Imm(n))) if *n >= 0 && *n < 4096 => Some(*n as usize + 1),
            _ => None,
        })
        .unwrap_or(256);
    let ptr = img.pointer_size();
    // Absolute table: jmp [table + idx*ptr].
    if let Some(Op::Mem(m)) = jmp.ops.first()
        && m.index.is_some()
        && m.base.is_none()
        && (m.scale as u64 == ptr)
    {
        let table = m.disp as u64;
        return read_table(img, jmp.addr, table, ptr as u8, bound, |v| v);
    }
    let Some(Op::Reg(_)) = jmp.ops.first() else { return None };
    // Absolute table loaded into a register: mov reg, [table + idx*ptr]; jmp reg.
    if let Some(m) = recent.iter().rev().find_map(|i| match (i.kind, i.ops.get(1)) {
        (Kind::Mov, Some(Op::Mem(m))) if m.base.is_none() && m.index.is_some() && u64::from(m.scale) == ptr => Some(m.clone()),
        _ => None,
    }) {
        return read_table(img, jmp.addr, m.disp as u64, ptr as u8, bound, |v| v);
    }
    // Relative table (PIC): lea base, [rip+T]; movsxd r, [base + idx*4]; add r, base; jmp r.
    let has_movsx = recent.iter().any(|i| matches!((i.kind, i.ops.get(1)), (Kind::MovSx, Some(Op::Mem(m))) if m.index.is_some() && m.scale == 4));
    let table = recent.iter().rev().find_map(|i| match (i.kind, i.ops.get(1)) {
        (Kind::Lea, Some(Op::Mem(m))) => m.addr,
        _ => None,
    })?;
    if !has_movsx {
        return None;
    }
    read_table(img, jmp.addr, table, 4, bound, move |v| table.wrapping_add(v as u32 as i32 as i64 as u64))
}

fn read_table(img: &Image, site: u64, table: u64, size: u8, bound: usize, decode: impl Fn(u64) -> u64) -> Option<JumpTable> {
    let mut targets = Vec::new();
    for i in 0..bound.min(1024) as u64 {
        let at = table.checked_add(i * u64::from(size))?;
        let Some(raw) = img.read(at, usize::from(size)) else { break };
        let v = match raw.len() {
            8 => u64::from_le_bytes(raw.try_into().ok()?),
            4 => u64::from(u32::from_le_bytes(raw.try_into().ok()?)),
            _ => break,
        };
        let t = decode(v);
        if !img.is_exec(t) {
            break;
        }
        targets.push(t);
    }
    if targets.is_empty() {
        return None;
    }
    let mut uniq = targets.clone();
    uniq.sort_unstable();
    uniq.dedup();
    Some(JumpTable { site, table, entry_size: size, targets: uniq })
}

fn build_function(entry: u64, src: &'static str, sc: Scan, all_xrefs: &mut Vec<Xref>, max_xrefs: usize) -> Function {
    let jt_targets: BTreeMap<u64, Vec<u64>> = sc.jump_tables.iter().map(|j| (j.site, j.targets.clone())).collect();
    let mut blocks: Vec<Block> = Vec::new();
    let mut cur: Option<Block> = None;
    let mut prev_end: Option<u64> = None;
    let mut prev_flow = Flow::Next;
    let mut prev_addr = 0u64;
    let finish = |b: &mut Block, flow: Flow, last: u64, contains: &dyn Fn(u64) -> bool| {
        let (succs, term) = match flow {
            Flow::Next | Flow::Call { .. } | Flow::IndirectCall { .. } => {
                if contains(b.end) {
                    (vec![b.end], Term::Fall)
                } else {
                    (vec![], Term::Unknown)
                }
            }
            Flow::Jump { target } => {
                if contains(target) {
                    (vec![target], Term::Jump)
                } else {
                    (vec![], Term::Tail)
                }
            }
            Flow::Cond { target } => {
                let mut s = Vec::new();
                if contains(target) {
                    s.push(target);
                }
                if contains(b.end) && b.end != target {
                    s.push(b.end);
                }
                (s, Term::Cond)
            }
            Flow::IndirectJump { .. } => (jt_targets.get(&last).cloned().unwrap_or_default(), Term::Indirect),
            Flow::Return => (vec![], Term::Return),
            Flow::Stop => (vec![], Term::Stop),
        };
        b.succs = succs;
        b.term = term;
    };
    let contains = |a: u64| sc.insns.contains_key(&a);
    for (&a, &(len, flow)) in &sc.insns {
        let new_block = cur.is_none() || sc.leaders.contains(&a) || prev_end != Some(a) || prev_flow.ends_block();
        if new_block {
            if let Some(mut b) = cur.take() {
                finish(&mut b, prev_flow, prev_addr, &contains);
                blocks.push(b);
            }
            cur = Some(Block { start: a, end: a, insns: 0, succs: Vec::new(), term: Term::Fall });
        }
        // Wrapping, as `Insn::end` is: an instruction at the top of the address space ends at 0.
        let end = a.wrapping_add(u64::from(len));
        if let Some(b) = cur.as_mut() {
            b.end = end;
            b.insns += 1;
        }
        prev_end = Some(end);
        prev_flow = flow;
        prev_addr = a;
    }
    if let Some(mut b) = cur.take() {
        finish(&mut b, prev_flow, prev_addr, &contains);
        blocks.push(b);
    }
    let room = max_xrefs.saturating_sub(all_xrefs.len());
    all_xrefs.extend(sc.xrefs.iter().take(room).copied());
    let end = blocks.iter().map(|b| b.end).max().unwrap_or(entry);
    Function {
        entry,
        name: String::new(),
        name_source: "generated",
        discovered_by: src,
        insn_count: sc.insns.len() as u32,
        blocks,
        calls: sc.calls,
        end,
        thunk_of: sc.thunk_of,
        truncated: sc.truncated,
        jump_tables: sc.jump_tables,
        unresolved_indirect_jumps: sc.unresolved,
        tail_calls: sc.tails,
        returns: sc.returns,
    }
}

/// Addresses in executable gaps that start like a function.
fn prologue_scan(img: &Image, mode: Mode, covered: &BTreeMap<u64, u64>) -> Vec<u64> {
    let mut out = Vec::new();
    let step = match mode {
        Mode::X64 | Mode::X32 => 16,
        Mode::A64 | Mode::A32 => 4,
        _ => return out,
    };
    let is_covered = |a: u64| covered.range(..=a).next_back().is_some_and(|(_, &end)| a < end);
    // (start, bytes in the file) of each executable range: sections, or the segments when the file has none.
    let mut ranges: Vec<(u64, u64)> = img
        .bin
        .sections
        .iter()
        .filter(|s| s.alloc && s.exec && s.file_offset.is_some())
        .filter(|s| !(s.name.starts_with(".plt") || s.name == "__stubs" || s.name == ".init" || s.name == ".fini"))
        .map(|s| (s.addr, s.file_size))
        .collect();
    if img.bin.sections.is_empty() {
        ranges.extend(img.bin.segments.iter().filter(|s| s.exec && s.file_size > 0).map(|s| (s.addr, s.file_size)));
    }
    for (start, size) in ranges {
        let Some(mut a) = start.checked_add(step - 1).map(|a| a & !(step - 1)) else { continue };
        let end = start.saturating_add(size);
        while a.checked_add(4).is_some_and(|e| e <= end) && out.len() < 200_000 {
            if !is_covered(a)
                && let Some(b) = img.read(a, 8)
            {
                let prev_ok = a == start || img.read(a - 1, 1).is_some_and(|p| matches!(p.first(), Some(0xc3 | 0xcc | 0x90 | 0x00 | 0xc2)));
                let hit = match mode {
                    Mode::X64 => {
                        prev_ok
                            && (b.starts_with(&[0x55, 0x48, 0x89, 0xe5])
                                || b.starts_with(&[0x55, 0x48, 0x8b, 0xec])
                                || b.starts_with(&[0xf3, 0x0f, 0x1e, 0xfa])
                                || b.starts_with(&[0x48, 0x83, 0xec])
                                || b.starts_with(&[0x48, 0x81, 0xec])
                                || b.starts_with(&[0x41, 0x57, 0x41, 0x56])
                                || b.starts_with(&[0x53, 0x48, 0x83, 0xec]))
                    }
                    Mode::X32 => {
                        prev_ok && (b.starts_with(&[0x55, 0x89, 0xe5]) || b.starts_with(&[0x55, 0x8b, 0xec]) || b.starts_with(&[0x8b, 0xff, 0x55, 0x8b, 0xec]))
                    }
                    Mode::A64 => {
                        let w = u32::from_le_bytes([
                            b.first().copied().unwrap_or(0),
                            b.get(1).copied().unwrap_or(0),
                            b.get(2).copied().unwrap_or(0),
                            b.get(3).copied().unwrap_or(0),
                        ]);
                        (w & 0xffc0_7fff) == 0xa980_7bfd || w == 0xd503_233f || w == 0xd503_245f || (w & 0xff80_03ff) == 0xd100_03ff
                    }
                    Mode::A32 => {
                        let w = u32::from_le_bytes([
                            b.first().copied().unwrap_or(0),
                            b.get(1).copied().unwrap_or(0),
                            b.get(2).copied().unwrap_or(0),
                            b.get(3).copied().unwrap_or(0),
                        ]);
                        (w & 0xffff_4000) == 0xe92d_4000 // push {…, lr}
                    }
                    _ => false,
                };
                if hit {
                    out.push(a);
                }
            }
            // At the top of the address space the step would wrap to 0 and walk it all again.
            let Some(next) = a.checked_add(step) else { break };
            a = next;
        }
    }
    out
}

fn pointer_scan(img: &Image, limits: &Limits, functions: &BTreeMap<u64, Function>, strings: &BTreeMap<u64, usize>, xrefs: &mut Vec<Xref>) {
    let bin = &img.bin;
    let ptr = img.pointer_size();
    if ptr < 4 {
        return;
    }
    let mut budget = limits.max_data_scan;
    for s in bin.sections.iter().filter(|s| s.alloc && !s.exec && matches!(s.kind, "data" | "rodata" | "other" | "metadata")) {
        let Some(off) = s.file_offset.and_then(|o| usize::try_from(o).ok()) else { continue };
        let n = usize::try_from(s.file_size).unwrap_or(0).min(budget);
        budget -= n;
        let Some(bytes) = img.data.get(off..off.saturating_add(n).min(img.data.len())) else { continue };
        let first = (ptr - (s.addr % ptr)) % ptr;
        let mut i = first as usize;
        while i + ptr as usize <= bytes.len() {
            if xrefs.len() >= limits.max_xrefs {
                return;
            }
            let Some(w) = bytes.get(i..i + ptr as usize) else { break };
            let v = if ptr == 8 { w.try_into().ok().map(u64::from_le_bytes) } else { w.try_into().ok().map(|x| u64::from(u32::from_le_bytes(x))) };
            if let Some(v) = v
                && v != 0
            {
                let Some(from) = s.addr.checked_add(i as u64) else { break };
                if functions.contains_key(&v) {
                    xrefs.push(Xref { from, to: v, kind: XrefKind::Pointer });
                } else if strings.contains_key(&v) {
                    xrefs.push(Xref { from, to: v, kind: XrefKind::String });
                }
            }
            i += ptr as usize;
        }
        if budget == 0 {
            break;
        }
    }
}

/// `_start` passes `main` to `__libc_start_main` in the first argument register.
fn guess_main(img: &Image, mode: Mode, functions: &BTreeMap<u64, Function>, slots: &BTreeMap<u64, SlotInfo>) -> Option<u64> {
    let entry = img.bin.entry?;
    let f = functions.get(&entry)?;
    let call = f.calls.iter().find(|c| c.import.as_deref().map(bare) == Some("__libc_start_main"))?;
    let arg = match mode {
        Mode::X64 => "rdi",
        Mode::A64 => "x0",
        _ => return None,
    };
    let _ = slots;
    let mut consts = ArmConsts::default();
    let mut found = None;
    let mut a = entry;
    while a < call.site {
        let mut i = img.decode(a, false)?;
        if mode == Mode::A64 {
            consts.apply(&mut i);
        }
        if i.writes.iter().any(|w| w == arg) {
            found = i.refs.iter().copied().find(|r| functions.contains_key(r));
        }
        a = i.end();
    }
    found
}

fn function_name(
    img: &Image,
    f: &Function,
    stubs: &BTreeMap<u64, String>,
    meta: &BTreeMap<u64, (String, &'static str)>,
    main_guess: Option<u64>,
) -> (String, &'static str) {
    let bin = &img.bin;
    let mut syms: Vec<&craft_anything_formats::Symbol> =
        bin.symbols.iter().filter(|s| s.defined && s.kind == SymbolKind::Function && (s.addr == f.entry || s.addr == f.entry | 1)).collect();
    syms.sort_by_key(|s| (!s.global, s.name.starts_with('$'), s.name.len()));
    if let Some(s) = syms.first() {
        return (s.name.clone(), "symbol");
    }
    if let Some(e) = bin.exports.iter().find(|e| e.addr == f.entry) {
        return (e.name.clone(), "export");
    }
    if let Some((n, source)) = meta.get(&f.entry) {
        return (n.clone(), source);
    }
    let stub = stubs.get(&f.entry).or(f.thunk_of.as_ref());
    if let Some(n) = stub {
        let suffix = match bin.format {
            Format::Elf => "@plt",
            Format::MachO => "@stub",
            _ => "@thunk",
        };
        return (format!("{n}{suffix}"), "import_thunk");
    }
    if Some(f.entry) == main_guess {
        return ("main".into(), "heuristic");
    }
    if Some(f.entry) == bin.entry {
        return ("entry".into(), "entry_point");
    }
    (format!("sub_{:x}", f.entry), "generated")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::NoControl;
    use craft_anything_testkit as tk;
    use std::sync::Arc;

    fn analyze(bytes: Vec<u8>) -> (Image, Program) {
        let img = Image::parse(Arc::from(bytes)).unwrap();
        let p = Program::analyze(&img, &Limits::default(), &NoControl).unwrap();
        (img, p)
    }

    #[test]
    fn a_stripped_go_program_keeps_its_function_names() {
        let (_, p) = analyze(tk::formats::go_elf());
        for (name, off) in tk::formats::GO_FUNCS {
            let f = p.functions.get(&(tk::formats::GO_TEXT_VA + off)).unwrap_or_else(|| panic!("{name} not found"));
            assert_eq!((f.name.as_str(), f.name_source), (*name, "go_pclntab"));
        }
        // Found through the table itself, not only by being called.
        assert_eq!(p.functions.get(&(tk::formats::GO_TEXT_VA + 0x40)).map(|f| f.discovered_by), Some("go_pclntab"));
    }

    #[test]
    fn elf_functions_calls_strings() {
        let (elf, l) = tk::elf64(tk::ElfArch::X86_64, true);
        let (img, p) = analyze(elf);
        let main = p.function_by_name("main").unwrap();
        assert_eq!(main.entry, l.code_va);
        let helper = p.function_by_name("helper").unwrap();
        let hidden = p.functions.get(&(l.code_va + tk::x64::HIDDEN)).expect("prologue scan finds hidden");
        assert_eq!(hidden.discovered_by, "prologue");
        assert_eq!(hidden.name, format!("sub_{:x}", l.code_va + tk::x64::HIDDEN));
        // helper: entry block, loop body, exit → 3 blocks with a back edge
        assert_eq!(helper.blocks.len(), 3, "{:?}", helper.blocks);
        assert!(helper.blocks.iter().any(|b| b.succs.contains(&b.start)));
        // main calls puts (import), helper and dispatch
        let callees = p.callees(main);
        let names: Vec<_> = callees.iter().filter_map(|c| c.name.clone()).collect();
        assert!(names.contains(&"puts".to_string()), "{names:?}");
        assert!(names.contains(&"helper".to_string()));
        assert!(names.contains(&"dispatch".to_string()));
        // callers
        assert_eq!(p.callers(helper.entry), vec![(l.code_va + 26, Some(main.entry))]);
        // strings and string xrefs
        let hello = p.strings.iter().find(|s| s.text == tk::HELLO).unwrap();
        assert_eq!(hello.addr, l.rodata_va);
        let refs = p.xrefs_to.get(&hello.addr).unwrap();
        assert!(refs.iter().any(|x| x.kind == XrefKind::String && x.from == l.code_va + 8));
        // jump table
        let d = p.function_by_name("dispatch").unwrap();
        assert_eq!(d.jump_tables.len(), 1);
        assert_eq!(d.jump_tables[0].targets, tk::dispatch_cases(l.code_va).to_vec());
        assert_eq!(d.blocks.len(), 6, "{:?}", d.blocks);
        // containing function
        assert_eq!(p.function_containing(l.code_va + 0x45).unwrap().entry, helper.entry);
        let asm = p.instructions(&img, main, true);
        assert_eq!(asm.first().unwrap().text(), "push rbp");
    }

    #[test]
    fn a_program_with_no_section_headers_is_found_by_its_dynamic_symbols() {
        for table in [tk::flutter::SymbolTable::DynamicHash, tk::flutter::SymbolTable::DynamicGnuHash] {
            let names = ["inflate", "deflate", "adler32"];
            let (img, p) = analyze(tk::sectionless::sectionless_elf(true, false, &names, table));
            assert!(img.bin.sections.is_empty());
            for name in names {
                let f = p.function_by_name(name).unwrap_or_else(|| panic!("{name} not found"));
                assert_eq!(f.discovered_by, "symbol");
            }
            assert_eq!(p.functions.len(), 3);
        }
    }

    #[test]
    fn the_prologue_scan_walks_executable_segments_when_there_are_no_sections() {
        let (mut elf, l) = tk::elf64(tk::ElfArch::X86_64, false);
        // Remove the section header table: offset, count and name-table index.
        elf[40..48].fill(0);
        elf[60..64].fill(0);
        let (img, p) = analyze(elf);
        assert!(img.bin.sections.is_empty());
        let hidden = p.functions.get(&(l.code_va + tk::x64::HIDDEN)).expect("the scan finds it without sections");
        assert_eq!(hidden.discovered_by, "prologue");
    }

    #[test]
    fn instruction_cap_marks_discovery_incomplete() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let img = Image::parse(Arc::from(elf)).unwrap();
        let full = Program::analyze(&img, &Limits::default(), &NoControl).unwrap();
        assert!(!full.discovery_capped());
        let tiny = Limits { max_total_insns: 3, ..Limits::default() };
        let p = Program::analyze(&img, &tiny, &NoControl).unwrap();
        assert!(p.discovery_capped());
        let (_, msg) = p.limitations.iter().find(|(c, _)| c == "instruction_limit").unwrap();
        assert!(msg.contains("function list is incomplete"), "{msg}");
    }

    #[test]
    fn stripped_elf_and_entry() {
        let (elf, l) = tk::elf64(tk::ElfArch::X86_64, false);
        let (_, p) = analyze(elf);
        let e = p.functions.get(&l.entry).unwrap();
        assert_eq!(e.name, "entry");
        assert!(p.limitations.iter().any(|(c, _)| c == "stripped_binary"));
        assert!(p.functions.contains_key(&(l.code_va + tk::x64::HELPER)));
    }

    #[test]
    fn pe_imports_and_exports() {
        let (_, p) = analyze(tk::pe64());
        let code = tk::PE_BASE + tk::PE_TEXT_RVA;
        assert_eq!(p.functions.get(&(code + tk::x64::HELPER)).unwrap().name, "helper");
        let main = p.functions.get(&code).unwrap();
        assert!(main.calls.iter().any(|c| c.import.as_deref() == Some("puts")));
        let slot = tk::PE_BASE + tk::PE_IAT_RVA;
        assert_eq!(p.name_at(slot).as_deref(), Some("__imp_puts"));
        assert!(p.xrefs_to.get(&slot).unwrap().iter().any(|x| x.kind == XrefKind::Import));
    }

    #[test]
    fn macho_objc_and_function_starts() {
        let (_, p) = analyze(tk::macho64());
        let code = tk::MACHO_BASE + tk::MACHO_TEXT_OFF;
        assert_eq!(p.functions.get(&code).unwrap().name, "_main");
        let hidden = p.functions.get(&(code + tk::x64::HIDDEN)).unwrap();
        assert_eq!(hidden.name, "-[CAWidget tapButton:]");
        let main = p.functions.get(&code).unwrap();
        assert!(main.calls.iter().any(|c| c.import.as_deref() == Some("_puts")));
    }

    #[test]
    fn aarch64_adrp_strings_and_got_calls() {
        let (elf, l) = tk::elf64(tk::ElfArch::Aarch64, true);
        let (img, p) = analyze(elf);
        let main = p.function_by_name("main").unwrap();
        assert!(main.calls.iter().any(|c| c.import.as_deref() == Some("puts")), "{:?}", main.calls);
        assert!(main.calls.iter().any(|c| c.target == Some(l.code_va + tk::a64::HELPER)));
        let hello = p.strings.iter().find(|s| s.text == tk::HELLO).unwrap();
        assert!(p.xrefs_to.get(&hello.addr).is_some_and(|v| v.iter().any(|x| x.from == l.code_va + 0xc)));
        let helper = p.function_by_name("helper").unwrap();
        assert_eq!(helper.blocks.len(), 3);
        assert!(!p.instructions(&img, helper, true).is_empty());
    }

    #[test]
    fn dos_com_and_raw() {
        let img = Image::dos_com(Arc::from(tk::dos_com())).unwrap();
        let p = Program::analyze(&img, &Limits::default(), &NoControl).unwrap();
        let f = p.functions.get(&0x100).unwrap();
        assert!(f.insn_count >= 4);
        let raw = Image::raw(Arc::from(tk::x86_64_code(0x1000, 0x2000, 0x3000)), craft_anything_formats::Arch::X86_64, 0x1000);
        let p = Program::analyze(&raw, &Limits::default(), &NoControl).unwrap();
        assert!(p.functions.contains_key(&0x1000));
        assert!(p.functions.contains_key(&(0x1000 + tk::x64::HELPER)));
    }

    #[test]
    fn a_branch_to_another_functions_entry_ends_at_it() {
        // 0x1000: test eax,eax; jz 0x1010; call 0x1010; ret      0x1010: mov eax,1; ret
        // The callee is only found while the caller is scanned, so the caller first runs into it.
        let mut code = vec![0xcc; 0x20];
        code[..10].copy_from_slice(&[0x85, 0xc0, 0x74, 0x0c, 0xe8, 0x07, 0, 0, 0, 0xc3]);
        code[0x10..0x16].copy_from_slice(&[0xb8, 1, 0, 0, 0, 0xc3]);
        let raw = Image::raw(Arc::from(code), craft_anything_formats::Arch::X86_64, 0x1000);
        let p = Program::analyze(&raw, &Limits::default(), &NoControl).unwrap();
        let caller = p.functions.get(&0x1000).unwrap();
        assert!(caller.blocks.iter().all(|b| b.end <= 0x1010), "{:?}", caller.blocks);
        assert_eq!((caller.insn_count, caller.tail_calls.as_slice()), (4, [0x1010].as_slice()));
        assert_eq!(p.functions.get(&0x1010).map(|f| f.insn_count), Some(2));
        assert_eq!(p.stats.instructions, 6, "each instruction counted once");
    }

    #[test]
    fn a_reference_into_a_packed_string_starts_a_new_one() {
        // 0x1000: lea rax, [rip+0xe] (0x1015); ret       0x1010: "HelloWorld" (no terminator between)
        let mut code = vec![0u8; 0x20];
        code[..8].copy_from_slice(&[0x48, 0x8d, 0x05, 0x0e, 0, 0, 0, 0xc3]);
        code[0x10..0x1a].copy_from_slice(b"HelloWorld");
        let raw = Image::raw(Arc::from(code), craft_anything_formats::Arch::X86_64, 0x1000);
        let p = Program::analyze(&raw, &Limits::default(), &NoControl).unwrap();
        let at = |a: u64| p.strings.iter().find(|s| s.addr == a).map(|s| s.text.as_str());
        assert_eq!((at(0x1010), at(0x1015)), (Some("Hello"), Some("World")), "{:?}", p.strings);
    }

    #[test]
    fn a_switch_table_read_past_its_end_stays_in_its_function() {
        // 0x1000: call 0x1080; jmp [rax*8 + 0x1100]      cases: 0x1010, 0x1011 (ret each)
        // 0x1080: 8 nops; ret                            table: 0x1010, 0x1011, 0x1085, 0x1088, 0
        // No bound before the jump, so the table is read on into the callee's body.
        let mut code = vec![0xcc; 0x140];
        code[..12].copy_from_slice(&[0xe8, 0x7b, 0, 0, 0, 0xff, 0x24, 0xc5, 0x00, 0x11, 0, 0]);
        code[0x10..0x12].copy_from_slice(&[0xc3, 0xc3]);
        code[0x80..0x89].copy_from_slice(&[0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0xc3]);
        for (i, t) in [0x1010u64, 0x1011, 0x1085, 0x1088, 0].iter().enumerate() {
            code[0x100 + i * 8..0x108 + i * 8].copy_from_slice(&t.to_le_bytes());
        }
        let raw = Image::raw(Arc::from(code), craft_anything_formats::Arch::X86_64, 0x1000);
        let p = Program::analyze(&raw, &Limits::default(), &NoControl).unwrap();
        let caller = p.functions.get(&0x1000).unwrap();
        assert!(caller.blocks.iter().all(|b| b.end <= 0x1080), "{:?}", caller.blocks);
        assert_eq!(caller.jump_tables.first().map(|t| t.targets.clone()), Some(vec![0x1010, 0x1011]));
        assert_eq!(p.functions.get(&0x1080).map(|f| f.insn_count), Some(9));
    }

    #[test]
    fn cancellation_is_honoured() {
        struct Stop;
        impl Control for Stop {
            fn cancelled(&self) -> bool {
                true
            }
        }
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let img = Image::parse(Arc::from(elf)).unwrap();
        assert!(matches!(Program::analyze(&img, &Limits::default(), &Stop), Err(DisasmError::Cancelled)));
    }

    #[test]
    fn code_at_the_top_of_the_address_space_ends_without_wrapping() {
        // Each scan used to step past u64::MAX: a panic in debug builds, and in release a wrap to
        // 0 that walked the whole address space (never ending). Run on a thread with a deadline so
        // a regression fails instead of hanging the test run.
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            use craft_anything_formats::Arch;
            let base = u64::MAX - 63;
            for arch in [Arch::X86, Arch::X86_64, Arch::Arm, Arch::Aarch64, Arch::X86_16] {
                for seed in 0..4 {
                    let mut img = Image::raw(Arc::from(tk::noise(seed, 64)), arch, base);
                    let _ = Program::analyze(&img, &Limits::default(), &NoControl);
                    img.bin.sections[0].name = ".plt".into();
                    let _ = Program::analyze(&img, &Limits::default(), &NoControl);
                }
            }
            let _ = tx.send(());
        });
        assert!(rx.recv_timeout(std::time::Duration::from_secs(60)).is_ok(), "analysis at the top of the address space never ended");
    }

    #[test]
    fn damaged_binaries_never_panic() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let (a64, _) = tk::elf64(tk::ElfArch::Aarch64, false);
        for sample in [elf, a64, tk::pe64(), tk::macho64()] {
            for m in tk::mutations(&sample) {
                if let Ok(img) = Image::parse(Arc::from(m)) {
                    let _ = Program::analyze(&img, &Limits::default(), &NoControl);
                }
            }
        }
        for seed in 0..16 {
            let raw = Image::raw(Arc::from(tk::noise(seed, 4096)), craft_anything_formats::Arch::X86_64, 0x1000);
            let _ = Program::analyze(&raw, &Limits::default(), &NoControl);
            let raw = Image::raw(Arc::from(tk::noise(seed, 4096)), craft_anything_formats::Arch::Aarch64, 0x1000);
            let _ = Program::analyze(&raw, &Limits::default(), &NoControl);
        }
    }

    #[test]
    fn real_system_binary_if_present() {
        let Ok(bytes) = std::fs::read("/bin/ls") else { return };
        let img = Image::parse(Arc::from(bytes)).unwrap();
        let p = Program::analyze(&img, &Limits::default(), &NoControl).unwrap();
        assert!(p.functions.len() > 50, "{}", p.functions.len());
        assert!(p.strings.len() > 100);
    }
}
