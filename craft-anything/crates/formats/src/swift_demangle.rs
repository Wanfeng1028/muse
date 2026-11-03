//! A Swift symbol demangler for the common manglings (`$s`, `_$s`, `$S`, `$e`, `_T0`, and runtime
//! class names `_Tt…`). The mangling is postfix: operands are pushed on a stack and operators pop
//! them. We cover identifiers with word substitutions, substitutions, standard types, nominal
//! types, extensions, bound generics with sugar, tuples, function types (throws/async),
//! generic parameters and simple signatures, functions, initialisers, deinitialisers, variables
//! and subscripts with accessors, closures, static members, metadata and witness-table globals
//! and common thunks. Anything else is reported as invalid rather than guessed.

use serde::Serialize;

const MAX_LEN: usize = 4096;
const MAX_STACK: usize = 1024;
const MAX_SUBST: usize = 4096;
const MAX_RENDER_DEPTH: usize = 160;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Demangled,
    /// Not a Swift mangling: returned as is.
    Unchanged,
    /// Looks like a Swift mangling but could not be decoded.
    Invalid,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Demangled {
    pub symbol: String,
    pub status: Status,
    pub demangled: Option<String>,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
enum N {
    Ident(String),
    Module(String),
    Nominal {
        kind: char,
        ctx: Box<N>,
        name: String,
    },
    Extension {
        module: Box<N>,
        ty: Box<N>,
    },
    Bound {
        base: Box<N>,
        args: Vec<N>,
    },
    Tuple(Vec<(Option<String>, N)>),
    Func {
        params: Box<N>,
        result: Box<N>,
        throws: bool,
        is_async: bool,
    },
    Metatype(Box<N>),
    Existential(Vec<N>),
    Param(u64, u64),
    Member {
        base: Box<N>,
        name: String,
    },
    Inout(Box<N>),
    Builtin(String),
    EmptyList,
    FirstMarker,
    Throws,
    Async,
    Requirement(String),
    Sig {
        reqs: Vec<String>,
    },
    Generic {
        sig: Box<N>,
        ty: Box<N>,
    },
    /// Functions, initialisers, variables, subscripts, closures.
    Entity {
        kind: EKind,
        ctx: Box<N>,
        name: Option<String>,
        labels: Vec<Option<String>>,
        ty: Option<Box<N>>,
        accessor: Option<&'static str>,
        is_static: bool,
    },
    Conformance {
        ty: Box<N>,
        proto: Box<N>,
        module: Box<N>,
    },
    Global {
        prefix: String,
        inner: Box<N>,
        suffix: String,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum EKind {
    Func,
    AllocInit,
    Init,
    Deinit,
    DeallocDeinit,
    Var,
    Subscript,
    Closure(u64, bool),
    DefaultArg(u64),
    VarInit,
    IvarDestroyer,
    IvarInitializer,
}

struct D<'a> {
    s: &'a [u8],
    pos: usize,
    stack: Vec<N>,
    subs: Vec<N>,
    words: Vec<String>,
    max_param: Option<u64>,
    /// Nodes we may still copy out of substitutions (guards against exponential growth).
    budget: usize,
}

type R<T> = Result<T, String>;

fn is_lower(c: u8) -> bool {
    c.is_ascii_lowercase()
}

impl<'a> D<'a> {
    fn new(s: &'a [u8]) -> Self {
        D { s, pos: 0, stack: Vec::new(), subs: Vec::new(), words: Vec::new(), max_param: None, budget: 200_000 }
    }

    fn peek(&self) -> Option<u8> {
        self.s.get(self.pos).copied()
    }

    fn next(&mut self) -> R<u8> {
        let c = self.peek().ok_or("unexpected end")?;
        self.pos += 1;
        Ok(c)
    }

    fn next_if(&mut self, c: u8) -> bool {
        if self.peek() == Some(c) {
            self.pos += 1;
            true
        } else {
            false
        }
    }

    fn natural(&mut self) -> Option<u64> {
        let start = self.pos;
        let mut v: u64 = 0;
        while let Some(c) = self.peek().filter(u8::is_ascii_digit) {
            v = v.checked_mul(10)?.checked_add(u64::from(c - b'0'))?;
            self.pos += 1;
        }
        if self.pos == start { None } else { Some(v) }
    }

    /// INDEX ::= '_' | NATURAL '_'  →  0 | n+1
    fn index(&mut self) -> R<u64> {
        if self.next_if(b'_') {
            return Ok(0);
        }
        let n = self.natural().ok_or("expected an index")?;
        if !self.next_if(b'_') {
            return Err("index not terminated".into());
        }
        n.checked_add(1).ok_or_else(|| "index overflow".into())
    }

    fn push(&mut self, n: N) -> R<()> {
        if self.stack.len() >= MAX_STACK {
            return Err("too many nodes".into());
        }
        self.stack.push(n);
        Ok(())
    }

    fn add_sub(&mut self, n: &N) -> R<()> {
        if self.subs.len() >= MAX_SUBST {
            return Err("too many substitutions".into());
        }
        self.subs.push(n.clone());
        Ok(())
    }

    fn pop(&mut self) -> R<N> {
        self.stack.pop().ok_or_else(|| "operator without operand".into())
    }

    fn pop_if(&mut self, f: impl Fn(&N) -> bool) -> Option<N> {
        if self.stack.last().is_some_and(f) { self.stack.pop() } else { None }
    }

    fn pop_type(&mut self) -> R<N> {
        match self.pop()? {
            N::Ident(_) | N::EmptyList | N::FirstMarker | N::Throws | N::Async | N::Requirement(_) | N::Sig { .. } => Err("expected a type".into()),
            N::Module(m) => Err(format!("expected a type, found module {m}")),
            other => Ok(other),
        }
    }

    fn pop_context(&mut self) -> R<N> {
        match self.pop()? {
            N::Ident(i) => Ok(N::Module(i)),
            n @ (N::Module(_) | N::Nominal { .. } | N::Extension { .. } | N::Entity { .. } | N::Bound { .. }) => Ok(n),
            _ => Err("expected a context".into()),
        }
    }

    fn pop_name(&mut self) -> R<String> {
        match self.pop()? {
            N::Ident(i) => Ok(i),
            _ => Err("expected a name".into()),
        }
    }

    fn identifier(&mut self) -> R<N> {
        let mut has_words = false;
        let mut puny = false;
        if self.next_if(b'0') {
            if self.next_if(b'0') {
                puny = true;
            } else {
                has_words = true;
            }
        }
        if puny {
            return Err("punycode identifiers are not supported".into());
        }
        let mut id = String::new();
        loop {
            while has_words && self.peek().is_some_and(|c| c.is_ascii_alphabetic()) {
                let c = self.next()?;
                let idx = if is_lower(c) {
                    usize::from(c - b'a')
                } else {
                    has_words = false;
                    usize::from(c - b'A')
                };
                let w = self.words.get(idx).ok_or("word substitution out of range")?;
                id.push_str(w);
            }
            if self.next_if(b'0') {
                break;
            }
            let n = self.natural().ok_or("expected identifier length")?;
            let n = usize::try_from(n).map_err(|_| "identifier too long")?;
            if n == 0 {
                return Err("empty identifier".into());
            }
            let end = self.pos.checked_add(n).ok_or("identifier too long")?;
            let slice = self.s.get(self.pos..end).ok_or("identifier runs past the end")?;
            self.pos = end;
            let text = std::str::from_utf8(slice).map_err(|_| "identifier is not UTF-8")?;
            id.push_str(text);
            // Record words for later word substitutions.
            let bytes = text.as_bytes();
            let mut start: Option<usize> = None;
            for i in 0..=bytes.len() {
                let c = bytes.get(i).copied().unwrap_or(0);
                if let Some(st) = start {
                    let prev = bytes.get(i.wrapping_sub(1)).copied().unwrap_or(0);
                    let end_word = c == b'_' || c == 0 || (!prev.is_ascii_uppercase() && c.is_ascii_uppercase());
                    if end_word {
                        if i - st >= 2
                            && self.words.len() < 26
                            && let Some(w) = text.get(st..i)
                        {
                            self.words.push(w.to_string());
                        }
                        start = None;
                    }
                }
                if start.is_none() && c != 0 && c != b'_' && !c.is_ascii_digit() {
                    start = Some(i);
                }
            }
            if !has_words {
                break;
            }
        }
        if id.is_empty() {
            return Err("empty identifier".into());
        }
        let n = N::Ident(id);
        self.add_sub(&n)?;
        Ok(n)
    }

    fn substitution(&mut self) -> R<()> {
        let mut repeat: Option<u64> = None;
        loop {
            let c = self.next()?;
            if c.is_ascii_digit() {
                self.pos -= 1;
                repeat = self.natural();
                if self.peek() == Some(b'_') {
                    self.pos += 1;
                    let idx = repeat.ok_or("bad substitution")?.checked_add(27).ok_or("overflow")?;
                    return self.push_sub(idx, 1);
                }
                continue;
            }
            if c == b'_' {
                return self.push_sub(26, 1);
            }
            if c.is_ascii_lowercase() {
                self.push_sub(u64::from(c - b'a'), repeat.take().unwrap_or(1))?;
                continue;
            }
            if c.is_ascii_uppercase() {
                return self.push_sub(u64::from(c - b'A'), repeat.unwrap_or(1));
            }
            return Err("bad substitution".into());
        }
    }

    fn push_sub(&mut self, idx: u64, count: u64) -> R<()> {
        let n = usize::try_from(idx).ok().and_then(|i| self.subs.get(i)).cloned().ok_or("substitution out of range")?;
        if count > 64 {
            return Err("substitution repeat too large".into());
        }
        let cost = weight(&n, 0).saturating_mul(usize::try_from(count).unwrap_or(usize::MAX));
        self.budget = self.budget.checked_sub(cost).ok_or("symbol expands too much")?;
        for _ in 0..count {
            self.push(n.clone())?;
        }
        Ok(())
    }

    fn standard(&mut self) -> R<()> {
        let count = self.natural().unwrap_or(1);
        if count > 64 {
            return Err("standard type repeat too large".into());
        }
        let c = self.next()?;
        let (kind, name) = match c {
            b'g' => {
                let t = self.pop_type()?;
                return self.push(N::Bound { base: Box::new(Self::swift_enum("Optional")), args: vec![t] });
            }
            b'o' => return self.push(N::Module("__C".into())),
            b'C' => return self.push(N::Module("__C_Synthesized".into())),
            b'a' => ('V', "Array"),
            b'b' => ('V', "Bool"),
            b'c' => return Err("concurrency standard types are not supported".into()),
            b'D' => ('V', "Dictionary"),
            b'd' => ('V', "Double"),
            b'f' => ('V', "Float"),
            b'h' => ('V', "Set"),
            b'I' => ('V', "DefaultIndices"),
            b'i' => ('V', "Int"),
            b'J' => ('V', "Character"),
            b'N' => ('V', "ClosedRange"),
            b'n' => ('V', "Range"),
            b'O' => ('V', "ObjectIdentifier"),
            b'P' => ('V', "UnsafePointer"),
            b'p' => ('V', "UnsafeMutablePointer"),
            b'Q' => ('O', "ImplicitlyUnwrappedOptional"),
            b'q' => ('O', "Optional"),
            b'R' => ('V', "UnsafeBufferPointer"),
            b'r' => ('V', "UnsafeMutableBufferPointer"),
            b'S' => ('V', "String"),
            b's' => ('V', "Substring"),
            b'u' => ('V', "UInt"),
            b'V' => ('V', "UnsafeRawPointer"),
            b'v' => ('V', "UnsafeMutableRawPointer"),
            b'W' => ('V', "UnsafeRawBufferPointer"),
            b'w' => ('V', "UnsafeMutableRawBufferPointer"),
            b'A' => ('V', "AutoreleasingUnsafeMutablePointer"),
            b'B' => ('P', "BinaryFloatingPoint"),
            b'E' => ('P', "Encodable"),
            b'e' => ('P', "Decodable"),
            b'F' => ('P', "FloatingPoint"),
            b'G' => ('P', "RandomNumberGenerator"),
            b'H' => ('P', "Hashable"),
            b'j' => ('P', "Numeric"),
            b'K' => ('P', "BidirectionalCollection"),
            b'k' => ('P', "RandomAccessCollection"),
            b'L' => ('P', "Comparable"),
            b'l' => ('P', "Collection"),
            b'M' => ('P', "MutableCollection"),
            b'm' => ('P', "RangeReplaceableCollection"),
            b'T' => ('P', "Sequence"),
            b't' => ('P', "IteratorProtocol"),
            b'U' => ('P', "UnsignedInteger"),
            b'X' => ('P', "RangeExpression"),
            b'x' => ('P', "Strideable"),
            b'Y' => ('P', "RawRepresentable"),
            b'y' => ('P', "StringProtocol"),
            b'Z' => ('P', "SignedInteger"),
            b'z' => ('P', "BinaryInteger"),
            other => return Err(format!("unknown standard type S{}", char::from(other))),
        };
        let n = N::Nominal { kind, ctx: Box::new(N::Module("Swift".into())), name: name.into() };
        for _ in 0..count {
            self.push(n.clone())?;
        }
        Ok(())
    }

    fn swift_enum(name: &str) -> N {
        N::Nominal { kind: 'O', ctx: Box::new(N::Module("Swift".into())), name: name.into() }
    }

    fn pop_params(&mut self) -> R<N> {
        match self.pop()? {
            N::EmptyList => Ok(N::Tuple(Vec::new())),
            N::Ident(_) | N::FirstMarker | N::Throws | N::Async | N::Requirement(_) | N::Sig { .. } | N::Module(_) => Err("expected parameter types".into()),
            other => Ok(other),
        }
    }

    fn pop_func_type(&mut self) -> R<N> {
        let mut throws = false;
        let mut is_async = false;
        loop {
            if self.pop_if(|n| matches!(n, N::Throws)).is_some() {
                throws = true;
            } else if self.pop_if(|n| matches!(n, N::Async)).is_some() {
                is_async = true;
            } else {
                break;
            }
        }
        let params = self.pop_params()?;
        let result = self.pop_params()?;
        Ok(N::Func { params: Box::new(params), result: Box::new(result), throws, is_async })
    }

    fn param_count(f: &N) -> usize {
        match f {
            N::Func { params, .. } => match params.as_ref() {
                N::Tuple(t) => t.len(),
                _ => 1,
            },
            N::Generic { ty, .. } => Self::param_count(ty),
            _ => 0,
        }
    }

    fn pop_labels(&mut self, n: usize) -> R<Vec<Option<String>>> {
        if self.pop_if(|x| matches!(x, N::EmptyList)).is_some() {
            return Ok(vec![None; n]);
        }
        let mut out = Vec::new();
        for _ in 0..n {
            match self.stack.last() {
                Some(N::Ident(_)) => {
                    if let Some(N::Ident(l)) = self.stack.pop() {
                        out.push(Some(l));
                    }
                }
                Some(N::FirstMarker) => {
                    self.stack.pop();
                    out.push(None);
                }
                _ => return Err("expected argument labels".into()),
            }
        }
        out.reverse();
        Ok(out)
    }

    /// The function type of an entity, wrapped in its generic signature when one is present.
    /// Whether the stack holds an entity's (signature, labels, name, context) in one of the two
    /// layouts: a separate result and parameter list, or one function type built with `c`.
    fn shape_ok(&self, top_func: bool, need_name: bool) -> bool {
        let st = &self.stack;
        let at = |i: usize| i.checked_sub(1).and_then(|j| st.get(j));
        let typeish = |n: Option<&N>| matches!(n, Some(n) if !matches!(n, N::Ident(_) | N::FirstMarker | N::Throws | N::Async | N::Requirement(_) | N::Sig { .. } | N::Module(_)));
        let mut i = st.len();
        if matches!(at(i), Some(N::Sig { .. })) {
            i -= 1;
        }
        let n_params = if top_func {
            match at(i) {
                Some(f @ N::Func { .. }) => {
                    i -= 1;
                    Self::param_count(f)
                }
                _ => return false,
            }
        } else {
            while matches!(at(i), Some(N::Throws | N::Async)) {
                i -= 1;
            }
            let n = match at(i) {
                Some(N::EmptyList) => 0,
                Some(N::Tuple(t)) => t.len(),
                p if typeish(p) => 1,
                _ => return false,
            };
            i -= 1;
            if !typeish(at(i)) {
                return false;
            }
            i -= 1;
            n
        };
        if n_params > 0 {
            if matches!(at(i), Some(N::EmptyList)) {
                i -= 1;
            } else {
                for _ in 0..n_params {
                    if matches!(at(i), Some(N::Ident(_) | N::FirstMarker)) {
                        i -= 1;
                    } else {
                        return false;
                    }
                }
            }
        }
        if need_name {
            if !matches!(at(i), Some(N::Ident(_))) {
                return false;
            }
            i -= 1;
        }
        matches!(at(i), Some(N::Ident(_) | N::Module(_) | N::Nominal { .. } | N::Extension { .. } | N::Entity { .. } | N::Bound { .. }))
    }

    fn pop_entity_type(&mut self, need_name: bool) -> R<N> {
        let top_func = !self.shape_ok(false, need_name) && self.shape_ok(true, need_name);
        let sig = self.pop_if(|n| matches!(n, N::Sig { .. }));
        let f = if top_func { self.pop()? } else { self.pop_func_type()? };
        Ok(match sig {
            Some(s) => N::Generic { sig: Box::new(s), ty: Box::new(f) },
            None => f,
        })
    }

    fn accessor(&mut self) -> Option<&'static str> {
        let a = match self.peek()? {
            b'g' => "getter",
            b's' => "setter",
            b'G' => "global getter",
            b'w' => "willset",
            b'W' => "didset",
            b'm' => "materializeForSet",
            b'M' => "modify",
            b'r' => "read",
            b'a' => "unsafeMutableAddressor",
            b'l' => "unsafeAddressor",
            b'i' => "init",
            b'p' => "",
            _ => return None,
        };
        self.pos += 1;
        Some(a)
    }

    fn conformance(&mut self) -> R<N> {
        let module = self.pop_context()?;
        let proto = match self.pop()? {
            n @ N::Nominal { kind: 'P', .. } => n,
            N::Ident(name) => {
                let ctx = self.pop_context()?;
                N::Nominal { kind: 'P', ctx: Box::new(ctx), name }
            }
            _ => return Err("expected a protocol".into()),
        };
        let ty = self.pop_type()?;
        Ok(N::Conformance { ty: Box::new(ty), proto: Box::new(proto), module: Box::new(module) })
    }

    fn global(&mut self, prefix: &str) -> R<()> {
        let inner = self.pop()?;
        self.push(N::Global { prefix: prefix.into(), inner: Box::new(inner), suffix: String::new() })
    }

    fn note_param(&mut self, idx: u64) {
        self.max_param = Some(self.max_param.map_or(idx, |m| m.max(idx)));
    }

    fn operator(&mut self) -> R<()> {
        let c = self.next()?;
        match c {
            b'0'..=b'9' => {
                self.pos -= 1;
                let n = self.identifier()?;
                self.push(n)
            }
            b'A' => self.substitution(),
            b'B' => {
                let t = match self.next()? {
                    b'b' => "Builtin.BridgeObject".to_string(),
                    b'o' => "Builtin.NativeObject".into(),
                    b'O' => "Builtin.UnknownObject".into(),
                    b'p' => "Builtin.RawPointer".into(),
                    b't' => "Builtin.SILToken".into(),
                    b'w' => "Builtin.Word".into(),
                    b'B' => "Builtin.UnsafeValueBuffer".into(),
                    b'i' => {
                        let n = self.natural().ok_or("builtin width")?;
                        self.next_if(b'_');
                        format!("Builtin.Int{n}")
                    }
                    b'f' => {
                        let n = self.natural().ok_or("builtin width")?;
                        self.next_if(b'_');
                        format!("Builtin.FPIEEE{n}")
                    }
                    _ => return Err("unsupported builtin type".into()),
                };
                self.push(N::Builtin(t))
            }
            b'C' | b'V' | b'O' | b'P' | b'a' => {
                let name = self.pop_name()?;
                let ctx = self.pop_context()?;
                let n = N::Nominal { kind: char::from(c), ctx: Box::new(ctx), name };
                self.add_sub(&n)?;
                self.push(n)
            }
            b'D' => {
                let t = self.pop_type()?;
                self.push(t)
            }
            b'E' => {
                let _sig = self.pop_if(|n| matches!(n, N::Sig { .. }));
                let module = self.pop_context()?;
                let ty = self.pop_type()?;
                let n = N::Extension { module: Box::new(module), ty: Box::new(ty) };
                self.add_sub(&n)?;
                self.push(n)
            }
            b'F' => {
                let ty = self.pop_entity_type(true)?;
                let labels = self.pop_labels(Self::param_count(&ty))?;
                let name = self.pop_name()?;
                let ctx = self.pop_context()?;
                self.push(N::Entity {
                    kind: EKind::Func,
                    ctx: Box::new(ctx),
                    name: Some(name),
                    labels,
                    ty: Some(Box::new(ty)),
                    accessor: None,
                    is_static: false,
                })
            }
            b'G' => {
                let mut args = Vec::new();
                loop {
                    if self.pop_if(|n| matches!(n, N::EmptyList)).is_some() {
                        break;
                    }
                    if args.len() > 64 {
                        return Err("too many generic arguments".into());
                    }
                    args.push(self.pop_type()?);
                }
                args.reverse();
                let base = self.pop_type()?;
                let n = N::Bound { base: Box::new(base), args };
                self.add_sub(&n)?;
                self.push(n)
            }
            b'K' => self.push(N::Throws),
            b'M' => {
                let p = match self.next()? {
                    b'a' => "type metadata accessor for",
                    b'n' => "nominal type descriptor for",
                    b'N' => "type metadata for",
                    b'm' => "metaclass for",
                    b'f' => "full type metadata for",
                    b'p' => "protocol descriptor for",
                    b'o' => "class metadata base offset for",
                    b'l' | b'L' => "lazy cache variable for type metadata for",
                    b'r' => "type metadata completion function for",
                    b'i' => "type metadata instantiation function for",
                    b'I' => "type metadata instantiation cache for",
                    b'u' => "method lookup function for",
                    b'V' => "property descriptor for",
                    b'c' => "protocol conformance descriptor for",
                    b'j' => "module descriptor",
                    b'X' => "extension descriptor for",
                    b'z' => "type metadata heap reference for",
                    _ => return Err("unsupported metadata kind".into()),
                };
                if p.starts_with("protocol descriptor")
                    && let Some(N::Ident(_)) = self.stack.last()
                {
                    let name = self.pop_name()?;
                    let ctx = self.pop_context()?;
                    let proto = N::Nominal { kind: 'P', ctx: Box::new(ctx), name };
                    return self.push(N::Global { prefix: p.into(), inner: Box::new(proto), suffix: String::new() });
                }
                if p.starts_with("protocol conformance") {
                    let conf = self.conformance()?;
                    return self.push(N::Global { prefix: p.into(), inner: Box::new(conf), suffix: String::new() });
                }
                self.global(p)
            }
            b'N' => self.global("type metadata for"),
            b'Q' => match self.next()? {
                b'z' => {
                    let name = self.pop_name()?;
                    self.note_param(0);
                    self.push(N::Member { base: Box::new(N::Param(0, 0)), name })
                }
                b'y' => {
                    let i = self.index()?;
                    let name = self.pop_name()?;
                    self.note_param(i);
                    self.push(N::Member { base: Box::new(N::Param(0, i)), name })
                }
                _ => Err("unsupported associated type".into()),
            },
            b'R' => {
                let (param, idx) = match self.next()? {
                    b'z' => ("A".to_string(), 0),
                    b'_' => ("B".into(), 1),
                    d if d.is_ascii_digit() => {
                        self.pos -= 1;
                        let n = self.natural().ok_or("requirement index")?;
                        if !self.next_if(b'_') {
                            return Err("requirement index".into());
                        }
                        let i = n.checked_add(2).ok_or("overflow")?;
                        (param_name(0, i), i)
                    }
                    _ => return Err("unsupported requirement kind".into()),
                };
                self.note_param(idx);
                let proto = self.pop_type()?;
                let text = format!("{param}: {}", render(&proto, 0));
                self.push(N::Requirement(text))
            }
            b'S' => self.standard(),
            b'T' => {
                let k = self.next()?;
                let prefix = match k {
                    b'o' => "@objc",
                    b'O' => "@nonobjc",
                    b'q' => "method descriptor for",
                    b'j' => "dispatch thunk of",
                    b'D' => "dynamic",
                    b'd' => "direct method reference to",
                    b'A' => "partial apply forwarder for",
                    b'm' => "merged",
                    b'W' => {
                        let entity = self.pop()?;
                        let conf = self.conformance()?;
                        let text = format!("protocol witness for {} in conformance {}", render(&entity, 0), render(&conf, 0));
                        return self.push(N::Global { prefix: text, inner: Box::new(N::EmptyList), suffix: String::new() });
                    }
                    b'R' | b'r' => {
                        let to = self.pop_type()?;
                        let from = self.pop_type()?;
                        let text = format!("reabstraction thunk helper from {} to {}", render(&from, 0), render(&to, 0));
                        return self.push(N::Global { prefix: text, inner: Box::new(N::EmptyList), suffix: String::new() });
                    }
                    _ => return Err("unsupported thunk or specialization".into()),
                };
                self.global(prefix)
            }
            b'W' => {
                let k = self.next()?;
                match k {
                    b'P' | b'p' | b'a' | b'G' => {
                        let conf = self.conformance()?;
                        let p = match k {
                            b'P' => "protocol witness table for",
                            b'p' => "protocol witness table pattern for",
                            b'a' => "protocol witness table accessor for",
                            _ => "generic protocol witness table for",
                        };
                        self.push(N::Global { prefix: p.into(), inner: Box::new(conf), suffix: String::new() })
                    }
                    b'V' => self.global("value witness table for"),
                    b'v' => {
                        let p = match self.next()? {
                            b'd' => "direct field offset for",
                            b'i' => "indirect field offset for",
                            _ => return Err("unsupported field offset".into()),
                        };
                        self.global(p)
                    }
                    b'L' => self.global("lazy protocol witness table cache variable for"),
                    _ => Err("unsupported witness kind".into()),
                }
            }
            b'X' => Err("unsupported special type".into()),
            b'Y' => match self.next()? {
                b'a' => self.push(N::Async),
                _ => Err("unsupported function attribute".into()),
            },
            b'Z' => {
                let mut e = self.pop()?;
                match &mut e {
                    N::Entity { is_static, .. } => *is_static = true,
                    _ => return Err("static applied to a non-member".into()),
                }
                self.push(e)
            }
            b'_' => self.push(N::FirstMarker),
            b'c' => {
                let f = self.pop_func_type()?;
                self.push(f)
            }
            b'f' => {
                let k = self.next()?;
                let kind = match k {
                    b'C' => EKind::AllocInit,
                    b'c' => EKind::Init,
                    b'D' => EKind::DeallocDeinit,
                    b'd' => EKind::Deinit,
                    b'E' => EKind::IvarDestroyer,
                    b'e' => EKind::IvarInitializer,
                    b'U' | b'u' => {
                        let i = self.index()?;
                        let ty = self.pop_type()?;
                        let ctx = self.pop_context()?;
                        return self.push(N::Entity {
                            kind: EKind::Closure(i, k == b'U'),
                            ctx: Box::new(ctx),
                            name: None,
                            labels: Vec::new(),
                            ty: Some(Box::new(ty)),
                            accessor: None,
                            is_static: false,
                        });
                    }
                    b'A' => {
                        let i = self.index()?;
                        let ctx = self.pop()?;
                        return self.push(N::Entity {
                            kind: EKind::DefaultArg(i),
                            ctx: Box::new(ctx),
                            name: None,
                            labels: Vec::new(),
                            ty: None,
                            accessor: None,
                            is_static: false,
                        });
                    }
                    b'i' => {
                        let ctx = self.pop()?;
                        return self.push(N::Entity {
                            kind: EKind::VarInit,
                            ctx: Box::new(ctx),
                            name: None,
                            labels: Vec::new(),
                            ty: None,
                            accessor: None,
                            is_static: false,
                        });
                    }
                    _ => return Err("unsupported function entity".into()),
                };
                match kind {
                    EKind::AllocInit | EKind::Init => {
                        let ty = self.pop_entity_type(false)?;
                        let labels = self.pop_labels(Self::param_count(&ty))?;
                        let ctx = self.pop_context()?;
                        self.push(N::Entity { kind, ctx: Box::new(ctx), name: None, labels, ty: Some(Box::new(ty)), accessor: None, is_static: false })
                    }
                    _ => {
                        let ctx = self.pop_context()?;
                        self.push(N::Entity { kind, ctx: Box::new(ctx), name: None, labels: Vec::new(), ty: None, accessor: None, is_static: false })
                    }
                }
            }
            b'i' => {
                let ty = self.pop_entity_type(false)?;
                let labels = self.pop_labels(Self::param_count(&ty))?;
                let ctx = self.pop_context()?;
                let accessor = self.accessor();
                self.push(N::Entity { kind: EKind::Subscript, ctx: Box::new(ctx), name: None, labels, ty: Some(Box::new(ty)), accessor, is_static: false })
            }
            b'l' => {
                let mut reqs = Vec::new();
                while let Some(N::Requirement(r)) = self.pop_if(|n| matches!(n, N::Requirement(_))) {
                    reqs.push(r);
                }
                reqs.reverse();
                self.note_param(0);
                self.push(N::Sig { reqs })
            }
            b'm' => {
                let t = self.pop_type()?;
                self.push(N::Metatype(Box::new(t)))
            }
            b'p' => {
                let mut protos = Vec::new();
                if self.pop_if(|n| matches!(n, N::EmptyList)).is_none() {
                    loop {
                        if protos.len() > 32 {
                            return Err("too many protocols".into());
                        }
                        let first = self.pop_if(|n| matches!(n, N::FirstMarker)).is_some();
                        protos.push(self.pop_type()?);
                        if first {
                            break;
                        }
                    }
                    protos.reverse();
                }
                self.push(N::Existential(protos))
            }
            b'q' => {
                let i = self.index()?.checked_add(1).ok_or("overflow")?;
                self.note_param(i);
                self.push(N::Param(0, i))
            }
            b's' => self.push(N::Module("Swift".into())),
            b't' => {
                let mut elems = Vec::new();
                if self.pop_if(|n| matches!(n, N::EmptyList)).is_none() {
                    loop {
                        if elems.len() > 256 {
                            return Err("tuple too large".into());
                        }
                        let first = self.pop_if(|n| matches!(n, N::FirstMarker)).is_some();
                        let label = match self.stack.last() {
                            Some(N::Ident(_)) => match self.stack.pop() {
                                Some(N::Ident(l)) => Some(l),
                                _ => None,
                            },
                            _ => None,
                        };
                        let ty = self.pop_type()?;
                        elems.push((label, ty));
                        if first {
                            break;
                        }
                    }
                    elems.reverse();
                }
                self.push(N::Tuple(elems))
            }
            b'u' => {
                let ty = self.pop_type()?;
                let sig = self.pop_if(|n| matches!(n, N::Sig { .. })).ok_or("generic type without signature")?;
                self.push(N::Generic { sig: Box::new(sig), ty: Box::new(ty) })
            }
            b'v' => {
                let ty = self.pop_type()?;
                let name = self.pop_name()?;
                let ctx = self.pop_context()?;
                let accessor = self.accessor();
                self.push(N::Entity {
                    kind: EKind::Var,
                    ctx: Box::new(ctx),
                    name: Some(name),
                    labels: Vec::new(),
                    ty: Some(Box::new(ty)),
                    accessor,
                    is_static: false,
                })
            }
            b'x' => {
                self.note_param(0);
                self.push(N::Param(0, 0))
            }
            b'y' => self.push(N::EmptyList),
            b'z' => {
                let t = self.pop_type()?;
                self.push(N::Inout(Box::new(t)))
            }
            other => Err(format!("unsupported operator '{}'", char::from(other))),
        }
    }
}

/// Approximate node count of a tree (bounded).
fn weight(n: &N, depth: usize) -> usize {
    if depth > MAX_RENDER_DEPTH {
        return usize::MAX / 4;
    }
    let d = depth + 1;
    let kids: usize = match n {
        N::Nominal { ctx, .. } => weight(ctx, d),
        N::Extension { module, ty } => weight(module, d).saturating_add(weight(ty, d)),
        N::Bound { base, args } => args.iter().fold(weight(base, d), |a, x| a.saturating_add(weight(x, d))),
        N::Tuple(t) => t.iter().fold(0usize, |a, (_, x)| a.saturating_add(weight(x, d))),
        N::Func { params, result, .. } => weight(params, d).saturating_add(weight(result, d)),
        N::Metatype(x) | N::Inout(x) => weight(x, d),
        N::Member { base, .. } => weight(base, d),
        N::Existential(v) => v.iter().fold(0usize, |a, x| a.saturating_add(weight(x, d))),
        N::Generic { sig, ty } => weight(sig, d).saturating_add(weight(ty, d)),
        N::Entity { ctx, ty, .. } => weight(ctx, d).saturating_add(ty.as_ref().map_or(0, |t| weight(t, d))),
        N::Conformance { ty, proto, module } => weight(ty, d).saturating_add(weight(proto, d)).saturating_add(weight(module, d)),
        N::Global { inner, .. } => weight(inner, d),
        _ => 0,
    };
    kids.saturating_add(1)
}

fn param_name(depth: u64, index: u64) -> String {
    let letter = u8::try_from(index % 26).map(|i| char::from(b'A' + i)).unwrap_or('A');
    let round = index / 26;
    match (depth, round) {
        (0, 0) => letter.to_string(),
        (0, r) => format!("{letter}{r}"),
        (d, _) => format!("{letter}{d}"),
    }
}

fn path(n: &N, depth: usize) -> String {
    if depth > MAX_RENDER_DEPTH {
        return "…".into();
    }
    match n {
        N::Module(m) | N::Ident(m) => m.clone(),
        N::Nominal { ctx, name, .. } => format!("{}.{name}", path(ctx, depth + 1)),
        N::Extension { ty, .. } => path(ty, depth + 1),
        other => render(other, depth + 1),
    }
}

fn params_text(p: &N, labels: &[Option<String>], depth: usize) -> String {
    let items: Vec<String> = match p {
        N::Tuple(t) => t
            .iter()
            .enumerate()
            .map(|(i, (l, ty))| {
                let label = labels.get(i).cloned().flatten().or_else(|| l.clone());
                match label {
                    Some(l) => format!("{l}: {}", render(ty, depth + 1)),
                    None => render(ty, depth + 1),
                }
            })
            .collect(),
        other => {
            let t = render(other, depth + 1);
            match labels.first().cloned().flatten() {
                Some(l) => vec![format!("{l}: {t}")],
                None => vec![t],
            }
        }
    };
    format!("({})", items.join(", "))
}

fn sig_text(sig: &N, max_param: u64) -> String {
    let N::Sig { reqs } = sig else { return String::new() };
    let params: Vec<String> = (0..=max_param.min(25)).map(|i| param_name(0, i)).collect();
    if reqs.is_empty() { format!("<{}>", params.join(", ")) } else { format!("<{} where {}>", params.join(", "), reqs.join(", ")) }
}

fn max_param(n: &N, depth: usize) -> u64 {
    if depth > MAX_RENDER_DEPTH {
        return 0;
    }
    match n {
        N::Param(_, i) => *i,
        N::Func { params, result, .. } => max_param(params, depth + 1).max(max_param(result, depth + 1)),
        N::Tuple(t) => t.iter().map(|(_, x)| max_param(x, depth + 1)).max().unwrap_or(0),
        N::Bound { base, args } => args.iter().map(|x| max_param(x, depth + 1)).max().unwrap_or(0).max(max_param(base, depth + 1)),
        N::Metatype(x) | N::Inout(x) => max_param(x, depth + 1),
        N::Member { base, .. } => max_param(base, depth + 1),
        _ => 0,
    }
}

fn func_text(ty: &N, labels: &[Option<String>], depth: usize) -> String {
    match ty {
        N::Func { params, result, throws, is_async } => {
            let mut s = params_text(params, labels, depth);
            if *is_async {
                s.push_str(" async");
            }
            if *throws {
                s.push_str(" throws");
            }
            s.push_str(" -> ");
            s.push_str(&render(result, depth + 1));
            s
        }
        N::Generic { sig, ty } => format!("{}{}", sig_text(sig, max_param(ty, depth + 1)), func_text(ty, labels, depth + 1)),
        other => render(other, depth + 1),
    }
}

fn render(n: &N, depth: usize) -> String {
    if depth > MAX_RENDER_DEPTH {
        return "…".into();
    }
    let d = depth + 1;
    match n {
        N::Ident(s) | N::Module(s) | N::Builtin(s) => s.clone(),
        N::Nominal { .. } | N::Extension { .. } => path(n, d),
        N::Bound { base, args } => {
            let b = path(base, d);
            match (b.as_str(), args.as_slice()) {
                ("Swift.Array", [t]) => format!("[{}]", render(t, d)),
                ("Swift.Dictionary", [k, v]) => format!("[{} : {}]", render(k, d), render(v, d)),
                ("Swift.Optional", [t]) => format!("{}?", render(t, d)),
                ("Swift.ImplicitlyUnwrappedOptional", [t]) => format!("{}!", render(t, d)),
                _ => format!("{b}<{}>", args.iter().map(|a| render(a, d)).collect::<Vec<_>>().join(", ")),
            }
        }
        N::Tuple(t) => params_text(&N::Tuple(t.clone()), &[], d),
        N::Func { .. } | N::Generic { .. } => func_text(n, &[], d),
        N::Metatype(t) => format!("{}.Type", render(t, d)),
        N::Existential(ps) => {
            if ps.is_empty() {
                "Any".into()
            } else {
                ps.iter().map(|p| render(p, d)).collect::<Vec<_>>().join(" & ")
            }
        }
        N::Param(dp, i) => param_name(*dp, *i),
        N::Member { base, name } => format!("{}.{name}", render(base, d)),
        N::Inout(t) => format!("inout {}", render(t, d)),
        N::EmptyList | N::FirstMarker | N::Throws | N::Async => String::new(),
        N::Requirement(r) => r.clone(),
        N::Sig { .. } => sig_text(n, 0),
        N::Conformance { ty, proto, module } => format!("{} : {} in {}", render(ty, d), path(proto, d), path(module, d)),
        N::Global { prefix, inner, suffix } => {
            let inner = render(inner, d);
            let mut s = if inner.is_empty() { prefix.clone() } else { format!("{prefix} {inner}") };
            s.push_str(suffix);
            s
        }
        N::Entity { kind, ctx, name, labels, ty, accessor, is_static } => {
            let c = path(ctx, d);
            let st = if *is_static { "static " } else { "" };
            let ty_text = |t: &Option<Box<N>>| t.as_ref().map(|t| func_text(t, labels, d)).unwrap_or_default();
            let body = match kind {
                EKind::Func => format!("{c}.{}{}", name.clone().unwrap_or_default(), ty_text(ty)),
                EKind::AllocInit => format!("{c}.__allocating_init{}", ty_text(ty)),
                EKind::Init => format!("{c}.init{}", ty_text(ty)),
                EKind::Deinit => format!("{c}.deinit"),
                EKind::DeallocDeinit => format!("{c}.__deallocating_deinit"),
                EKind::IvarDestroyer => format!("{c}.__ivar_destroyer"),
                EKind::IvarInitializer => format!("{c}.__ivar_initializer"),
                EKind::Var => {
                    let acc = accessor.filter(|a| !a.is_empty()).map(|a| format!(".{a}")).unwrap_or_default();
                    format!("{c}.{}{acc} : {}", name.clone().unwrap_or_default(), ty.as_ref().map(|t| render(t, d)).unwrap_or_default())
                }
                EKind::Subscript => {
                    let acc = accessor.filter(|a| !a.is_empty()).map(|a| format!(".{a}")).unwrap_or_default();
                    format!("{c}.subscript{}{acc}", ty_text(ty))
                }
                EKind::Closure(i, explicit) => {
                    format!(
                        "{} #{} {} in {c}",
                        if *explicit { "closure" } else { "implicit closure" },
                        i + 1,
                        ty.as_ref().map(|t| render(t, d)).unwrap_or_default()
                    )
                }
                EKind::DefaultArg(i) => format!("default argument {i} of {c}"),
                EKind::VarInit => format!("variable initialization expression of {c}"),
            };
            format!("{st}{body}")
        }
    }
}

/// True when the name uses a Swift mangling prefix.
pub fn looks_swift(sym: &str) -> bool {
    let s = sym.strip_prefix('_').unwrap_or(sym);
    s.starts_with("$s") || s.starts_with("$S") || s.starts_with("$e") || s.starts_with("T0") || s.starts_with("Tt")
}

fn runtime_name(body: &str) -> Result<String, String> {
    // _Tt<kinds><module><names…>
    let b = body.as_bytes();
    let mut i = 0;
    let mut kinds = 0usize;
    while let Some(&c) = b.get(i) {
        if matches!(c, b'C' | b'V' | b'O' | b'P') {
            kinds += 1;
            i += 1;
        } else {
            break;
        }
    }
    if kinds == 0 {
        return Err("unsupported runtime name".into());
    }
    let mut parts = Vec::new();
    if b.get(i) == Some(&b's') {
        parts.push("Swift".to_string());
        i += 1;
    } else if b.get(i..i + 2) == Some(b"So") {
        parts.push("__C".to_string());
        i += 2;
    }
    let mut d = D::new(b);
    d.pos = i;
    while d.peek().is_some_and(|c| c.is_ascii_digit()) {
        match d.identifier()? {
            N::Ident(s) => parts.push(s),
            _ => return Err("bad runtime name".into()),
        }
        if parts.len() > 64 {
            return Err("runtime name too long".into());
        }
    }
    let rest = body.get(d.pos..).unwrap_or("");
    if parts.len() != kinds + 1 || !(rest.is_empty() || rest == "_") {
        return Err("unsupported runtime name".into());
    }
    Ok(parts.join("."))
}

/// Demangle one symbol.
pub fn demangle(sym: &str) -> Demangled {
    let out = |status, demangled: Option<String>, reason: Option<String>| Demangled { symbol: sym.to_string(), status, demangled, reason };
    if !looks_swift(sym) {
        return out(Status::Unchanged, None, None);
    }
    if sym.len() > MAX_LEN {
        return out(Status::Invalid, None, Some(format!("longer than {MAX_LEN} characters")));
    }
    let s = sym.strip_prefix('_').unwrap_or(sym);
    if let Some(body) = s.strip_prefix("Tt") {
        return match runtime_name(body) {
            Ok(t) => out(Status::Demangled, Some(t), None),
            Err(e) => out(Status::Invalid, None, Some(e)),
        };
    }
    let body = s.get(2..).unwrap_or("");
    // A suffix after '.' (e.g. `.cold.1`) is not part of the mangling.
    let (body, suffix) = match body.find('.') {
        Some(p) => (body.get(..p).unwrap_or(""), body.get(p..).unwrap_or("")),
        None => (body, ""),
    };
    let mut d = D::new(body.as_bytes());
    let res = (|| -> R<String> {
        while d.pos < d.s.len() {
            d.operator()?;
        }
        if d.stack.len() != 1 {
            return Err(format!("{} nodes left after decoding", d.stack.len()));
        }
        let top = d.stack.first().ok_or("nothing decoded")?;
        let mut text = render(top, 0);
        if text.is_empty() {
            return Err("nothing decoded".into());
        }
        let _ = d.max_param;
        if !suffix.is_empty() {
            text.push_str(&format!(" with unmangled suffix \"{suffix}\""));
        }
        Ok(text)
    })();
    match res {
        Ok(t) => out(Status::Demangled, Some(t), None),
        Err(e) => out(Status::Invalid, None, Some(e)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dm(s: &str) -> String {
        let d = demangle(s);
        assert_eq!(d.status, Status::Demangled, "{s}: {:?}", d.reason);
        d.demangled.unwrap()
    }

    #[test]
    fn common_symbols() {
        assert_eq!(dm("$s4main3fooyyF"), "main.foo() -> ()");
        assert_eq!(dm("_$s4main3fooyySiF"), "main.foo(Swift.Int) -> ()");
        assert_eq!(dm("$s4main3foo1xySi_tF"), "main.foo(x: Swift.Int) -> ()");
        assert_eq!(dm("$s4main3addyS2i_SitF"), "main.add(Swift.Int, Swift.Int) -> Swift.Int");
        assert_eq!(dm("$s4main6WidgetCMa"), "type metadata accessor for main.Widget");
        assert_eq!(dm("$s4main6WidgetCMn"), "nominal type descriptor for main.Widget");
        assert_eq!(dm("$s4main6WidgetCN"), "type metadata for main.Widget");
        assert_eq!(dm("$s4main8DelegateMp"), "protocol descriptor for main.Delegate");
        assert_eq!(dm("$s4main6WidgetC3tapyyF"), "main.Widget.tap() -> ()");
        assert_eq!(dm("$s4main6WidgetC3tapyyFTo"), "@objc main.Widget.tap() -> ()");
        assert_eq!(dm("$s4main6WidgetC5countSivg"), "main.Widget.count.getter : Swift.Int");
        assert_eq!(dm("$s4main6WidgetC5countSivs"), "main.Widget.count.setter : Swift.Int");
        assert_eq!(dm("$s4main6WidgetC5countSivpWvd"), "direct field offset for main.Widget.count : Swift.Int");
        assert_eq!(dm("$s4main6WidgetCACycfC"), "main.Widget.__allocating_init() -> main.Widget");
        assert_eq!(dm("$s4main6WidgetCfD"), "main.Widget.__deallocating_deinit");
        assert_eq!(dm("$s4main6WidgetC6sharedACvpZ"), "static main.Widget.shared : main.Widget");
        assert_eq!(dm("$s4main5namesSaySSGvp"), "main.names : [Swift.String]");
        assert_eq!(dm("$s4main3mapSDySSSiGvp"), "main.map : [Swift.String : Swift.Int]");
        assert_eq!(dm("$s4main4nameSSSgvp"), "main.name : Swift.String?");
        assert_eq!(dm("$s4main3fooyyxlF"), "main.foo<A>(A) -> ()");
        assert_eq!(dm("$s4main3fooyyxSHRzlF"), "main.foo<A where A: Swift.Hashable>(A) -> ()");
        assert_eq!(dm("$s4main4loadSSyKF"), "main.load() throws -> Swift.String");
        assert_eq!(dm("$s4main4loadSSyYaKF"), "main.load() async throws -> Swift.String");
        assert_eq!(dm("$sSi4mainE6doubleSiyF"), "Swift.Int.double() -> Swift.Int");
        assert_eq!(dm("$s4main6WidgetCAA8DelegateAAWP"), "protocol witness table for main.Widget : main.Delegate in main");
        assert_eq!(dm("$s4main5PointVMn"), "nominal type descriptor for main.Point");
        assert_eq!(dm("$s4main4ModeOMa"), "type metadata accessor for main.Mode");
        assert_eq!(dm("$sSo8NSObjectCMa"), "type metadata accessor for __C.NSObject");
        assert_eq!(dm("$s4main3fooyyF.cold.1"), "main.foo() -> () with unmangled suffix \".cold.1\"");
        assert_eq!(dm("_TtC4main6Widget"), "main.Widget");
        assert_eq!(dm("_TtCC4main5Outer5Inner"), "main.Outer.Inner");
        assert_eq!(dm("$s4main3runyyyycF"), "main.run(() -> ()) -> ()");
        assert_eq!(dm("$s4main6WidgetC4tick5timesySi_tF"), "main.Widget.tick(times: Swift.Int) -> ()");
        // Word substitution: "SettingsPanel" then "Settings" reused as word 0
        assert_eq!(dm("$s4main13SettingsPanelC0B0VMn"), "nominal type descriptor for main.SettingsPanel.Settings");
        assert_eq!(dm("$s4main3fooyyypF"), "main.foo(Any) -> ()");
        assert_eq!(dm("$s4main3fooyyAA8DelegateP_pF"), "main.foo(main.Delegate) -> ()");
        assert_eq!(dm("$s4main6WidgetCSgMa"), "type metadata accessor for main.Widget?");
    }

    #[test]
    fn statuses() {
        assert_eq!(demangle("_main").status, Status::Unchanged);
        assert_eq!(demangle("objc_msgSend").status, Status::Unchanged);
        assert_eq!(demangle("$s").status, Status::Invalid);
        assert_eq!(demangle("$s4mai").status, Status::Invalid);
        assert_eq!(demangle("$s4mainXz").status, Status::Invalid);
        assert_eq!(demangle(&format!("$s{}", "A".repeat(5000))).status, Status::Invalid);
    }

    #[test]
    fn never_panics() {
        let seeds = ["$s4main3foo1xySi_tF", "$s4main6WidgetCACycfC", "$s4main3fooyyxSHRzlF", "$s4main6WidgetCAA8DelegateAAWP", "_TtCC4main5Outer5Inner"];
        for s in seeds {
            for i in 0..=s.len() {
                if let Some(p) = s.get(..i) {
                    let _ = demangle(p);
                }
            }
            let b = s.as_bytes();
            for i in 2..b.len() {
                for c in *b"09AZ_yGtlSqR" {
                    let mut m = b.to_vec();
                    m[i] = c;
                    if let Ok(t) = String::from_utf8(m) {
                        let _ = demangle(&t);
                    }
                }
            }
        }
        for seed in 0..2000u64 {
            let n = craft_anything_testkit::noise(seed, 40);
            let t: String = n.iter().map(|b| char::from(b"0123456789ABCDGFKMNSTWVyztlpqcfvx_aiuOPEQRZmsYo"[usize::from(*b) % 47])).collect();
            let _ = demangle(&format!("$s{t}"));
        }
        let deep = format!("$s{}", "Si".repeat(1000) + &"t".repeat(1000));
        let _ = demangle(&deep);
        let nested = format!("$s{}", "SaySi".repeat(600) + &"G".repeat(600));
        let _ = demangle(&nested);
    }
}
