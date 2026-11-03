//! A small built-in glossary: plain-English meanings for technical words, shown on hover in
//! Beginner mode. Our own wording.

/// `(word, meaning)`. Words are matched case-insensitively at word boundaries.
pub static GLOSSARY: &[(&str, &str)] = &[
    ("function", "A named piece of a program that does one job, like \"add two numbers\" or \"save the file\"."),
    ("decompile", "Turn a program's machine code back into something that reads like source code. It's a reconstruction, not the original."),
    ("pseudo-c", "Code reconstructed from a program that looks like the C language. Close to what the program does, but not its original source."),
    ("disassembly", "The program's machine code written out as one tiny instruction per line."),
    ("assembly", "The lowest-level human-readable form of machine code: one small instruction per line."),
    ("binary", "A file of machine code that a computer can run directly, like an .exe or an app."),
    ("executable", "A file that a computer can run as a program."),
    ("ipc", "Inter-process communication: how two parts of an app (or two apps) send messages to each other."),
    ("xref", "Cross-reference: a place in the program that uses or calls the thing you're looking at."),
    ("xrefs", "Cross-references: the places in the program that use or call the thing you're looking at."),
    ("string", "A piece of text stored inside a program, like a message, a web address or a file name."),
    ("strings", "Pieces of text stored inside a program, like messages, web addresses or file names."),
    ("import", "Something a program borrows from the operating system or a library, like \"open a file\"."),
    ("imports", "Things a program borrows from the operating system or libraries, like \"open a file\" or \"draw a window\"."),
    ("export", "Something a program or library offers for other programs to use."),
    ("exports", "Things a program or library offers for other programs to use."),
    ("section", "A region of a program file with one purpose: code, text, pictures, settings."),
    ("sections", "Regions of a program file, each with one purpose: code, text, pictures, settings."),
    ("segment", "A region of a program as it sits in memory while running."),
    ("library", "A bundle of ready-made code that many programs share."),
    ("electron", "A way to build desktop apps out of web pages. The app is basically a website with its own browser."),
    ("bundle", "Many source files packed into one big file so an app or web page loads faster."),
    ("source map", "A file that links packed web code back to the original, readable source files."),
    ("evidence", "A saved, checkable record of something we found, with how sure we are and where we found it."),
    ("entry point", "The first instruction a program runs when it starts."),
    ("address", "A number that says where something is in a program's memory, like a house number."),
    ("call graph", "A map of which functions call which other functions."),
    ("cfg", "Control-flow graph: a map of every path a function can take, like a flowchart."),
    ("sandbox", "A locked room for running a program so it can't touch the rest of your computer."),
    ("ghidra", "A free reverse-engineering tool from the NSA. Deep mode uses it for extra detail; Clean room mode never does."),
    (
        "clean room",
        "Nothing inside the original is read: not its code, files or page source. Craft Anything works from what you can see: pictures, the page as a visitor sees it, and watching it run.",
    ),
    ("deep mode", "Craft Anything reads the original's code, files and page source with every tool it has, and with Ghidra when it's installed."),
    ("hex", "A way of writing bytes as two-character codes (00 to FF). The rawest view of a file."),
    ("byte", "The smallest unit of data in a file: a number from 0 to 255."),
    ("bytes", "The smallest units of data in a file: numbers from 0 to 255."),
    ("symbol", "A name the program's author gave to a function or variable that survived in the file."),
    ("symbols", "Names the program's author gave to functions or variables that survived in the file."),
    ("stripped", "The names were removed from the program before it was shipped, so we have to work them out."),
    ("api", "A set of commands a program offers to other programs."),
    ("dex", "The code format Android apps use."),
    ("apk", "An Android app package: the file you install on a phone."),
    ("wasm", "WebAssembly: fast compiled code that runs inside web browsers."),
    ("heuristic", "A rule of thumb. Usually right, sometimes wrong, so we label the result as a best guess."),
    ("obfuscated", "Deliberately scrambled to make it hard to read, without changing what it does."),
    ("manifest", "A small file that lists what an app is called, what it needs and what it's allowed to do."),
];

/// The meaning of `word`, if it's in the glossary.
pub fn lookup(word: &str) -> Option<&'static str> {
    let w = word.trim().trim_matches(|c: char| !c.is_alphanumeric() && c != '-').to_ascii_lowercase();
    GLOSSARY.iter().find(|(k, _)| *k == w).map(|(_, v)| *v)
}

/// Split `text` into runs, marking the ones that are glossary words: `(run, meaning)`.
/// Multi-word entries ("call graph") are matched first. Each glossary term is marked once per text
/// so a long answer doesn't turn into a sea of underlines.
pub fn segments(text: &str) -> Vec<(String, Option<&'static str>)> {
    let lower = text.to_ascii_lowercase();
    let mut marks: Vec<(usize, usize, &'static str)> = Vec::new();
    for (term, meaning) in GLOSSARY {
        let mut from = 0;
        while let Some(pos) = lower.get(from..).and_then(|s| s.find(term)) {
            let start = from + pos;
            let end = start + term.len();
            let before_ok = lower.get(..start).and_then(|s| s.chars().next_back()).is_none_or(|c| !c.is_alphanumeric());
            let after_ok = lower.get(end..).and_then(|s| s.chars().next()).is_none_or(|c| !c.is_alphanumeric());
            let overlaps = marks.iter().any(|(s, e, _)| start < *e && end > *s);
            if before_ok && after_ok && !overlaps && text.is_char_boundary(start) && text.is_char_boundary(end) {
                marks.push((start, end, meaning));
                break;
            }
            from = end;
        }
    }
    marks.sort_by_key(|m| m.0);
    let mut out = Vec::new();
    let mut at = 0;
    for (s, e, m) in marks {
        if s > at {
            out.push((text.get(at..s).unwrap_or_default().to_string(), None));
        }
        out.push((text.get(s..e).unwrap_or_default().to_string(), Some(m)));
        at = e;
    }
    if at < text.len() {
        out.push((text.get(at..).unwrap_or_default().to_string(), None));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_words_at_boundaries_once() {
        let s = segments("This function calls a function. Functional? No. See the call graph.");
        let marked: Vec<&str> = s.iter().filter(|(_, m)| m.is_some()).map(|(t, _)| t.as_str()).collect();
        assert_eq!(marked, vec!["function", "call graph"]);
        let joined: String = s.iter().map(|(t, _)| t.as_str()).collect();
        assert_eq!(joined, "This function calls a function. Functional? No. See the call graph.");
        assert!(lookup("XREFS").is_some());
        assert!(lookup("banana").is_none());
    }

    #[test]
    fn unicode_text_is_safe() {
        let s = segments("日本語 function ünïcode bytes");
        let joined: String = s.iter().map(|(t, _)| t.as_str()).collect();
        assert_eq!(joined, "日本語 function ünïcode bytes");
    }
}
