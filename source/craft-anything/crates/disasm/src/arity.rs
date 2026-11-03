//! How many arguments common library functions take, so a pseudo-C call into an import shows all
//! of them even when some were set outside the calling block. Data, not code: add a row to extend
//! it. Variadic functions list their fixed arguments.

/// (name, arguments).
const ARITY: &[(&str, u8)] = &[
    // C library
    ("puts", 1),
    ("printf", 1),
    ("fprintf", 2),
    ("sprintf", 2),
    ("snprintf", 3),
    ("scanf", 1),
    ("sscanf", 2),
    ("malloc", 1),
    ("calloc", 2),
    ("realloc", 2),
    ("free", 1),
    ("memcpy", 3),
    ("memmove", 3),
    ("memset", 3),
    ("memcmp", 3),
    ("strlen", 1),
    ("strcmp", 2),
    ("strncmp", 3),
    ("strcpy", 2),
    ("strncpy", 3),
    ("strcat", 2),
    ("strchr", 2),
    ("strrchr", 2),
    ("strstr", 2),
    ("strdup", 1),
    ("atoi", 1),
    ("strtol", 3),
    ("strtoul", 3),
    ("getenv", 1),
    ("exit", 1),
    ("abort", 0),
    ("fopen", 2),
    ("fclose", 1),
    ("fread", 4),
    ("fwrite", 4),
    ("fgets", 3),
    ("fputs", 2),
    ("open", 2),
    ("close", 1),
    ("read", 3),
    ("write", 3),
    ("socket", 3),
    ("connect", 3),
    ("bind", 3),
    ("listen", 2),
    ("accept", 3),
    ("send", 4),
    ("recv", 4),
    ("sendto", 6),
    ("recvfrom", 6),
    ("dlopen", 2),
    ("dlsym", 2),
    ("pthread_create", 4),
    // Windows
    ("MessageBoxA", 4),
    ("MessageBoxW", 4),
    ("CreateWindowExA", 12),
    ("CreateWindowExW", 12),
    ("DefWindowProcA", 4),
    ("DefWindowProcW", 4),
    ("RegisterClassExA", 1),
    ("RegisterClassExW", 1),
    ("ShowWindow", 2),
    ("UpdateWindow", 1),
    ("GetMessageA", 4),
    ("GetMessageW", 4),
    ("TranslateMessage", 1),
    ("DispatchMessageA", 1),
    ("DispatchMessageW", 1),
    ("PostQuitMessage", 1),
    ("SetWindowTextA", 2),
    ("SetWindowTextW", 2),
    ("GetWindowTextA", 3),
    ("GetWindowTextW", 3),
    ("CreateFileA", 7),
    ("CreateFileW", 7),
    ("ReadFile", 5),
    ("WriteFile", 5),
    ("CloseHandle", 1),
    ("DeleteFileA", 1),
    ("DeleteFileW", 1),
    ("GetProcAddress", 2),
    ("LoadLibraryA", 1),
    ("LoadLibraryW", 1),
    ("LoadLibraryExA", 3),
    ("LoadLibraryExW", 3),
    ("GetModuleHandleA", 1),
    ("GetModuleHandleW", 1),
    ("VirtualAlloc", 4),
    ("VirtualFree", 3),
    ("VirtualProtect", 4),
    ("ExitProcess", 1),
    ("Sleep", 1),
    ("GetLastError", 0),
    ("CreateThread", 6),
    ("WaitForSingleObject", 2),
    ("CreateProcessA", 10),
    ("CreateProcessW", 10),
    ("ShellExecuteA", 6),
    ("ShellExecuteW", 6),
    ("RegOpenKeyExA", 5),
    ("RegOpenKeyExW", 5),
    ("RegQueryValueExA", 6),
    ("RegQueryValueExW", 6),
    ("RegSetValueExA", 6),
    ("RegSetValueExW", 6),
    ("RegCloseKey", 1),
    ("InternetOpenA", 5),
    ("InternetOpenW", 5),
    ("InternetOpenUrlA", 6),
    ("InternetOpenUrlW", 6),
    ("InternetReadFile", 4),
    ("HttpSendRequestA", 5),
    ("HttpSendRequestW", 5),
    ("WinHttpOpen", 5),
    ("WinHttpConnect", 4),
    ("WinHttpOpenRequest", 7),
    ("WinHttpSendRequest", 7),
];

/// The argument count of an import, by name. Accepts the decorated spellings loaders use: a
/// leading `_` (Mach-O, 32-bit cdecl), `__imp_`, and a stdcall `@bytes` suffix, which gives the
/// count on its own (4 bytes an argument) when the name isn't in the table.
pub fn import_arity(name: &str) -> Option<usize> {
    let bare = name.strip_prefix("__imp_").unwrap_or(name);
    let (base, stdcall) = match bare.rsplit_once('@') {
        Some((b, n)) if !n.is_empty() && n.bytes().all(|c| c.is_ascii_digit()) => (b, n.parse::<usize>().ok().map(|bytes| bytes / 4)),
        _ => (bare, None),
    };
    let lookup = |n: &str| ARITY.iter().find(|(k, _)| *k == n).map(|(_, a)| usize::from(*a));
    lookup(base).or_else(|| lookup(base.trim_start_matches('_'))).or(stdcall)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_and_decorations() {
        assert_eq!(import_arity("puts"), Some(1));
        assert_eq!(import_arity("_puts"), Some(1), "Mach-O leading underscore");
        assert_eq!(import_arity("__imp_MessageBoxW"), Some(4));
        assert_eq!(import_arity("_MessageBoxW@16"), Some(4), "table wins over the stdcall suffix");
        assert_eq!(import_arity("_SomethingElse@12"), Some(3), "stdcall bytes / 4");
        assert_eq!(import_arity("CreateWindowExW"), Some(12));
        assert_eq!(import_arity("not_a_known_function"), None);
        assert_eq!(import_arity("odd@name"), None);
    }

    #[test]
    fn no_duplicate_rows() {
        let mut names: Vec<&str> = ARITY.iter().map(|(n, _)| *n).collect();
        names.sort_unstable();
        let n = names.len();
        names.dedup();
        assert_eq!(names.len(), n);
    }
}
