//! Slash commands in a project's prompt box: `/btw where are the files?`. A new command is a
//! [`Command`] and a row in [`COMMANDS`].

/// What a command does.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Command {
    /// Ask about the build without building (see `just_ask`).
    Btw,
}

/// Every command, by the name typed after the slash.
const COMMANDS: &[(&str, Command)] = &[("btw", Command::Btw)];

/// How a message reads.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Typed<'a> {
    /// Not a command: it goes as written.
    Message,
    /// A command, and what follows it.
    Command(Command, &'a str),
    /// Shaped like a command, but there's none of that name. It's stopped rather than sent, so a
    /// typo doesn't start a build.
    Unknown(&'a str),
}

pub fn read(text: &str) -> Typed<'_> {
    let Some(rest) = text.trim().strip_prefix('/') else { return Typed::Message };
    let (name, what) = rest.split_once(char::is_whitespace).unwrap_or((rest, ""));
    // A path ("/usr/bin is missing") isn't a command.
    if name.is_empty() || !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
        return Typed::Message;
    }
    match COMMANDS.iter().find(|(n, _)| n.eq_ignore_ascii_case(name)) {
        Some((_, command)) => Typed::Command(*command, what.trim()),
        None => Typed::Unknown(name),
    }
}

/// The commands, to say what can be typed: "/btw".
pub fn names() -> String {
    COMMANDS.iter().map(|(n, _)| format!("/{n}")).collect::<Vec<_>>().join(", ")
}

/// Complete a partial command name (without the leading slash) when there's exactly one match.
pub fn complete(name: &str) -> Option<&'static str> {
    if name.is_empty() {
        return None;
    }
    let matches: Vec<&str> = COMMANDS.iter().filter(|(n, _)| n.starts_with(name)).map(|(n, _)| *n).collect();
    if matches.len() == 1 { Some(matches[0]) } else { None }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_command_is_a_known_name_after_a_slash() {
        assert_eq!(read("/btw where are the files"), Typed::Command(Command::Btw, "where are the files"));
        assert_eq!(read("  /BTW\n where?  "), Typed::Command(Command::Btw, "where?"));
        assert_eq!(read("/btw"), Typed::Command(Command::Btw, ""));
        assert_eq!(read("/bwt where are the files"), Typed::Unknown("bwt"));
    }

    #[test]
    fn a_path_or_a_slash_in_a_sentence_is_a_message() {
        for text in ["make it blue", "use a/b testing", "/usr/bin is missing", "/", "/ a space", "/src/main.rs crashes"] {
            assert_eq!(read(text), Typed::Message, "{text}");
        }
    }

    #[test]
    fn a_partial_name_completes_only_when_one_command_matches() {
        assert_eq!(complete("b"), Some("btw"));
        assert_eq!(complete("bt"), Some("btw"));
        assert_eq!(complete(""), None);
        assert_eq!(complete("x"), None);
    }
}
