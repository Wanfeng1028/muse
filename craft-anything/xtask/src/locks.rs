//! `cargo xtask locks`: finds code that would wait on the engine's session lock while already
//! holding it. `.session()` hands back a guard, and a guard that isn't bound to a name still lives
//! until the end of the whole statement, so a second `.session()` in that statement waits forever.
//! At run time such a wait is caught and stopped (crates/platform/src/sync.rs); this finds it first.
//!
//! Flags, in non-test code:
//! - two `.session()` calls whose guards are alive together in one statement;
//! - `match`, `if let` or `while let` on a `.session()`, with another in its body;
//! - `let g = ….session();` followed in that block by `.session()` or `engine.call(…)`, before `drop(g)`.

use std::path::{Path, PathBuf};
use syn::visit::{self, Visit};

fn is_session(m: &syn::ExprMethodCall) -> bool {
    m.args.is_empty() && (m.method == "session" || m.method == "try_session")
}

fn is_engine_call(m: &syn::ExprMethodCall) -> bool {
    if m.method != "call" {
        return false;
    }
    match &*m.receiver {
        syn::Expr::Field(f) => matches!(&f.member, syn::Member::Named(n) if n == "engine"),
        syn::Expr::Path(p) => p.path.is_ident("engine"),
        _ => false,
    }
}

/// `.session()` calls anywhere under a node, closures aside (they run later, if at all).
#[derive(Default)]
struct Everywhere {
    lines: Vec<usize>,
    with_calls: bool,
}

impl Visit<'_> for Everywhere {
    fn visit_expr_closure(&mut self, _: &syn::ExprClosure) {}
    fn visit_item(&mut self, _: &syn::Item) {}
    fn visit_expr_method_call(&mut self, m: &syn::ExprMethodCall) {
        if is_session(m) || (self.with_calls && is_engine_call(m)) {
            self.lines.push(m.method.span().start().line);
        }
        visit::visit_expr_method_call(self, m);
    }
}

/// `.session()` calls whose guards live to the end of this statement: nested blocks have their own
/// statements, and a plain `if`'s condition ends before its body.
#[derive(Default)]
struct SameStatement {
    lines: Vec<usize>,
    /// (first, second) lines of scrutinee problems found on the way.
    held_into_body: Vec<(usize, usize)>,
}

impl SameStatement {
    fn scrutinee(&mut self, scrutinee: &syn::Expr, body: &dyn Fn(&mut Everywhere)) {
        let mut head = Everywhere::default();
        head.visit_expr(scrutinee);
        if let Some(first) = head.lines.first() {
            let mut rest = Everywhere::default();
            body(&mut rest);
            if let Some(second) = rest.lines.first() {
                self.held_into_body.push((*first, *second));
            }
        }
        self.visit_expr(scrutinee);
    }
}

impl Visit<'_> for SameStatement {
    fn visit_expr_closure(&mut self, _: &syn::ExprClosure) {}
    fn visit_item(&mut self, _: &syn::Item) {}
    fn visit_block(&mut self, _: &syn::Block) {}
    fn visit_expr_method_call(&mut self, m: &syn::ExprMethodCall) {
        if is_session(m) {
            self.lines.push(m.method.span().start().line);
        }
        visit::visit_expr_method_call(self, m);
    }
    fn visit_expr_if(&mut self, e: &syn::ExprIf) {
        if let syn::Expr::Let(l) = &*e.cond {
            self.scrutinee(&l.expr, &|rest| rest.visit_block(&e.then_branch));
        }
        // A plain condition is its own scope, checked as if it were a statement of its own.
    }
    fn visit_expr_while(&mut self, e: &syn::ExprWhile) {
        if let syn::Expr::Let(l) = &*e.cond {
            self.scrutinee(&l.expr, &|rest| rest.visit_block(&e.body));
        }
    }
    fn visit_expr_match(&mut self, e: &syn::ExprMatch) {
        self.scrutinee(&e.expr, &|rest| {
            for arm in &e.arms {
                rest.visit_arm(arm);
            }
        });
    }
}

/// The name a statement binds a session guard to, when it does.
fn bound_guard(stmt: &syn::Stmt) -> Option<(String, usize)> {
    let syn::Stmt::Local(local) = stmt else { return None };
    let syn::Pat::Ident(name) = &local.pat else { return None };
    let syn::Expr::MethodCall(m) = &*local.init.as_ref()?.expr else { return None };
    is_session(m).then(|| (name.ident.to_string(), m.method.span().start().line))
}

fn drops(stmt: &syn::Stmt, name: &str) -> bool {
    let syn::Stmt::Expr(syn::Expr::Call(c), _) = stmt else { return false };
    let syn::Expr::Path(f) = &*c.func else { return false };
    f.path.is_ident("drop") && matches!(c.args.first(), Some(syn::Expr::Path(a)) if a.path.is_ident(name))
}

#[derive(Default)]
struct Finder {
    found: Vec<String>,
}

impl Finder {
    fn plain_conditions(&mut self, e: &syn::Expr) {
        let mut one = SameStatement::default();
        one.visit_expr(e);
        self.report(one);
    }

    fn report(&mut self, s: SameStatement) {
        if let [first, second, ..] = s.lines[..] {
            self.found.push(format!("{first}: this statement takes the session lock again on line {second} while still holding it"));
        }
        for (first, second) in s.held_into_body {
            self.found.push(format!("{first}: the session lock taken here is held through its body, which takes it again on line {second}"));
        }
    }
}

impl Visit<'_> for Finder {
    fn visit_item_mod(&mut self, m: &syn::ItemMod) {
        let test = m.attrs.iter().any(|a| a.path().is_ident("cfg") && a.meta.to_token_stream_string().contains("test"));
        if !test {
            visit::visit_item_mod(self, m);
        }
    }
    fn visit_item_fn(&mut self, f: &syn::ItemFn) {
        if !f.attrs.iter().any(|a| a.path().is_ident("test")) {
            visit::visit_item_fn(self, f);
        }
    }
    fn visit_expr_if(&mut self, e: &syn::ExprIf) {
        if !matches!(&*e.cond, syn::Expr::Let(_)) {
            self.plain_conditions(&e.cond);
        }
        visit::visit_expr_if(self, e);
    }
    fn visit_block(&mut self, block: &syn::Block) {
        for (i, stmt) in block.stmts.iter().enumerate() {
            let mut one = SameStatement::default();
            one.visit_stmt(stmt);
            self.report(one);
            if let Some((name, line)) = bound_guard(stmt) {
                for later in block.stmts.iter().skip(i + 1) {
                    if drops(later, &name) {
                        break;
                    }
                    let mut rest = Everywhere { with_calls: true, ..Default::default() };
                    rest.visit_stmt(later);
                    if let Some(second) = rest.lines.first() {
                        self.found.push(format!("{line}: `{name}` holds the session lock, and line {second} needs it again; drop it first"));
                        break;
                    }
                }
            }
        }
        visit::visit_block(self, block);
    }
}

trait MetaText {
    fn to_token_stream_string(&self) -> String;
}

impl MetaText for syn::Meta {
    fn to_token_stream_string(&self) -> String {
        match self {
            syn::Meta::List(l) => l.tokens.to_string(),
            _ => String::new(),
        }
    }
}

fn problems_in(source: &str) -> Result<Vec<String>, String> {
    let file = syn::parse_file(source).map_err(|e| e.to_string())?;
    let mut f = Finder::default();
    f.visit_file(&file);
    Ok(f.found)
}

fn rust_files(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    for e in entries.flatten() {
        let p = e.path();
        let name = e.file_name().to_string_lossy().into_owned();
        if p.is_dir() {
            if !matches!(name.as_str(), "tests" | "examples" | "target") {
                rust_files(&p, out);
            }
        } else if name.ends_with(".rs") && name != "tests.rs" {
            out.push(p);
        }
    }
}

pub fn check(root: &Path) -> bool {
    let mut files = Vec::new();
    rust_files(&root.join("crates"), &mut files);
    rust_files(&root.join("apps"), &mut files);
    let mut bad = 0;
    for file in &files {
        let Ok(source) = std::fs::read_to_string(file) else { continue };
        if !source.contains("session()") {
            continue;
        }
        let shown = file.strip_prefix(root).unwrap_or(file).display().to_string();
        match problems_in(&source) {
            Ok(found) => {
                for f in found {
                    eprintln!("{shown}:{f}");
                    bad += 1;
                }
            }
            Err(e) => {
                eprintln!("{shown}: couldn't read it: {e}");
                bad += 1;
            }
        }
    }
    if bad == 0 {
        println!("locks: ok ({} files)", files.len());
    } else {
        eprintln!("locks: {bad} place(s) would wait on a lock they already hold");
    }
    bad == 0
}

#[cfg(test)]
mod tests {
    use super::problems_in;

    fn flagged(body: &str) -> bool {
        !problems_in(&format!("fn f() {{ {body} }}")).unwrap().is_empty()
    }

    #[test]
    fn finds_a_lock_held_into_a_second() {
        // The bug that started this: both guards live until the struct expression ends.
        assert!(flagged("let s = Spec { a: !e.session().x(), b: e.session().y() };"));
        assert!(flagged("let n = e.session().a() + e.session().b();"));
        assert!(flagged("match e.session().x() { A => e.session().y(), B => 0 };"));
        assert!(flagged("if let Some(x) = e.session().x() { e.session().y(); }"));
        assert!(flagged("let g = e.session(); e.session().y();"));
        assert!(flagged("let g = self.engine.session(); self.engine.call(\"t\", p, o);"));
        assert!(flagged("if e.session().a() && e.session().b() { }"));
    }

    #[test]
    fn leaves_correct_code_alone() {
        assert!(!flagged("let a = e.session().x(); let b = e.session().y();"));
        assert!(!flagged("if e.session().a() { e.session().b(); }"), "a plain condition's guard ends before the body");
        assert!(!flagged("let g = e.session(); g.a(); drop(g); e.session().y();"));
        assert!(!flagged("let (a, b) = { let s = e.session(); (s.a(), s.b()) }; e.session().y();"));
        assert!(!flagged("let g = e.session(); let f = move || other.session();"), "a closure runs later");
        assert!(!flagged("match x { A => e.session().y(), B => e.session().z() };"), "only one arm runs");
    }
}
