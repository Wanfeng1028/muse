//! The external engine table: one typed entry per optional program Craft Anything can use.
//!
//! Everything about an engine lives in its entry: the id, the name people see, the executables to
//! look for on each OS, standard install folders, what it is needed for, and how it gets installed
//! (by hand, a pinned download, or a guided setup). [`crate::locate`], the Settings → Engines page,
//! the `ToolPaths` overrides (checked against this table by a test in the engine crate), the doctor
//! and [`crate::install`] all read it. Adding an engine is one entry here, plus a pin if it is managed.
//!
//! The table is a `const` array rather than a data file: the strings are `'static` (no parsing, no
//! fallback path), a typo in a field is a compile error, and the SHA-256 pins can't be lost to a
//! file that failed to load.

/// The archive container of a pinned download.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ArchiveFormat {
    Zip,
    /// A gzip-compressed tar.
    TarGz,
    /// An xz-compressed tar.
    TarXz,
    /// Not an archive: the download itself, saved as `name` (a single `.jar`). [`crate::locate`]
    /// finds it in the engine's store folder by that name.
    File {
        name: &'static str,
    },
}

/// A pinned download for one engine on one host.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Pin {
    /// Host OS as in `std::env::consts::OS` (`linux`, `macos`, `windows`); `None` = any.
    pub os: Option<&'static str>,
    /// Host architecture as in `std::env::consts::ARCH` (`x86_64`, `aarch64`); `None` = any.
    pub arch: Option<&'static str>,
    /// The exact, versioned download URL (never a moving "latest" link).
    pub url: &'static str,
    /// The SHA-256 of that file (lowercase hex), checked against the publisher's own checksum.
    pub sha256: &'static str,
    pub format: ArchiveFormat,
    /// A leading archive folder to strip (platform-tools zips wrap everything in `platform-tools/`).
    pub strip_prefix: Option<&'static str>,
}

impl Pin {
    pub fn matches(&self, os: &str, arch: &str) -> bool {
        self.os.is_none_or(|o| o == os) && self.arch.is_none_or(|a| a == arch)
    }
}

/// How an engine gets onto the computer.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Install {
    /// The person installs it; we only find it.
    Manual,
    /// [`crate::install::install`] downloads, verifies and unpacks one of these pins.
    Pinned(&'static [Pin]),
    /// A dedicated setup flow uses these pins (Ghidra and the Java it runs on); `how` says where.
    Guided { pins: &'static [Pin], how: &'static str },
}

/// Where a standard install folder starts.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Base {
    /// An environment variable naming a folder (`ProgramFiles`, `LOCALAPPDATA`, `HOME`).
    Env(&'static str),
    /// A fixed folder (`/Applications`).
    Dir(&'static str),
}

/// A standard install location for a program that doesn't put itself on PATH.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KnownPath {
    /// Host OS as in `std::env::consts::OS`.
    pub os: &'static str,
    pub base: Base,
    /// The executable, relative to `base`.
    pub rel: &'static str,
}

/// One optional external engine.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExternalEngine {
    /// Stable id: settings keys, `Requires::Engine`, the engine store folder.
    pub id: &'static str,
    /// The name people see ("Install {name} from Settings → Engines").
    pub name: &'static str,
    /// What Craft Anything uses it for, in a few plain words.
    pub needed_for: &'static str,
    /// Executable names on macOS and Linux, preferred first.
    pub exes: &'static [&'static str],
    /// Executable names on Windows, preferred first.
    pub exes_windows: &'static [&'static str],
    /// Standard install locations, searched after PATH.
    pub known_paths: &'static [KnownPath],
    /// Whether Settings → Engines has a path override for it (`ToolPaths`). Ghidra has its own folder setting.
    pub path_setting: bool,
    pub install: Install,
}

impl ExternalEngine {
    /// The executable names to look for on this computer.
    pub fn host_exes(&self) -> &'static [&'static str] {
        if cfg!(windows) { self.exes_windows } else { self.exes }
    }

    /// The pins for this engine, whether a generic or a guided install uses them.
    pub fn pins(&self) -> &'static [Pin] {
        match self.install {
            Install::Manual => &[],
            Install::Pinned(p) | Install::Guided { pins: p, .. } => p,
        }
    }

    /// The pin for a host OS and architecture, if there is one.
    pub fn pin_for(&self, os: &str, arch: &str) -> Option<&'static Pin> {
        self.pins().iter().find(|p| p.matches(os, arch))
    }

    /// The pin for this computer, if there is one.
    pub fn host_pin(&self) -> Option<&'static Pin> {
        self.pin_for(std::env::consts::OS, std::env::consts::ARCH)
    }

    /// Standard install locations on this computer, most common first (they may not exist).
    pub fn known_install_paths(&self) -> Vec<std::path::PathBuf> {
        let os = std::env::consts::OS;
        self.known_paths
            .iter()
            .filter(|k| k.os == os)
            .filter_map(|k| match k.base {
                Base::Env(var) => std::env::var_os(var).map(|v| std::path::Path::new(&v).join(k.rel)),
                Base::Dir(dir) => Some(std::path::Path::new(dir).join(k.rel)),
            })
            .collect()
    }
}

const fn win(base: &'static str, rel: &'static str) -> KnownPath {
    KnownPath { os: "windows", base: Base::Env(base), rel }
}

const fn mac(base: Base, rel: &'static str) -> KnownPath {
    KnownPath { os: "macos", base, rel }
}

const fn linux(dir: &'static str, rel: &'static str) -> KnownPath {
    KnownPath { os: "linux", base: Base::Dir(dir), rel }
}

const NO_PATHS: &[KnownPath] = &[];

/// Linux packages put Ghidra in a folder of its own and only a start script on PATH (`/usr/bin/ghidra`):
/// Arch and its derivatives in `/opt/ghidra`, Debian and Kali in `/usr/share/ghidra` (#85).
const GHIDRA_PATHS: &[KnownPath] = &[linux("/opt/ghidra", "support/analyzeHeadless"), linux("/usr/share/ghidra", "support/analyzeHeadless")];

/// Browsers on Windows and macOS rarely put themselves on PATH.
const CHROMIUM_PATHS: &[KnownPath] = &[
    win("ProgramFiles", "Google/Chrome/Application/chrome.exe"),
    win("ProgramFiles(x86)", "Google/Chrome/Application/chrome.exe"),
    win("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"),
    win("ProgramFiles", "Microsoft/Edge/Application/msedge.exe"),
    win("ProgramFiles(x86)", "Microsoft/Edge/Application/msedge.exe"),
    win("LOCALAPPDATA", "Microsoft/Edge/Application/msedge.exe"),
    win("ProgramFiles", "BraveSoftware/Brave-Browser/Application/brave.exe"),
    win("ProgramFiles(x86)", "BraveSoftware/Brave-Browser/Application/brave.exe"),
    win("LOCALAPPDATA", "BraveSoftware/Brave-Browser/Application/brave.exe"),
    win("ProgramFiles", "Chromium/Application/chrome.exe"),
    win("ProgramFiles(x86)", "Chromium/Application/chrome.exe"),
    win("LOCALAPPDATA", "Chromium/Application/chrome.exe"),
    mac(Base::Dir("/Applications"), "Google Chrome.app/Contents/MacOS/Google Chrome"),
    mac(Base::Env("HOME"), "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    mac(Base::Dir("/Applications"), "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    mac(Base::Env("HOME"), "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    mac(Base::Dir("/Applications"), "Chromium.app/Contents/MacOS/Chromium"),
    mac(Base::Env("HOME"), "Applications/Chromium.app/Contents/MacOS/Chromium"),
    mac(Base::Dir("/Applications"), "Brave Browser.app/Contents/MacOS/Brave Browser"),
    mac(Base::Env("HOME"), "Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
];

/// Android platform-tools r37.0.1. SHA-256 computed from Google's files, whose size and SHA-1
/// match Google's SDK repository manifest (`dl.google.com/android/repository/repository2-3.xml`).
const ADB_PINS: &[Pin] = &[
    Pin {
        os: Some("linux"),
        arch: None,
        url: "https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip",
        sha256: "d230f13842f60f782a8645f9c813f8f845bf36089ea7289f28c48f17979313f1",
        format: ArchiveFormat::Zip,
        strip_prefix: Some("platform-tools/"),
    },
    Pin {
        os: Some("macos"),
        arch: None,
        url: "https://dl.google.com/android/repository/platform-tools_r37.0.1-darwin.zip",
        sha256: "ee39ad5967e95c2a07f04dbcbde96b1a0c916ba376096db5d2f498b7727a5d1d",
        format: ArchiveFormat::Zip,
        strip_prefix: Some("platform-tools/"),
    },
    Pin {
        os: Some("windows"),
        arch: None,
        url: "https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip",
        sha256: "45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99",
        format: ArchiveFormat::Zip,
        strip_prefix: Some("platform-tools/"),
    },
];

/// Vineflower 1.12.0 (runs on Java; one .jar for every OS). SHA-256 as published on Maven Central
/// (`.jar.sha256`), the same as the GitHub release's asset digest.
const VINEFLOWER_PINS: &[Pin] = &[Pin {
    os: None,
    arch: None,
    url: "https://github.com/Vineflower/vineflower/releases/download/1.12.0/vineflower-1.12.0.jar",
    sha256: "1dfcfe974395734fa467ce620661c7623d05ba83670de0529b1fbd63ff548b9d",
    format: ArchiveFormat::File { name: "vineflower.jar" },
    strip_prefix: None,
}];

/// Rizin 0.9.1 for Windows x64 (the static build: one zip of 652 files, `rizin.exe` in its
/// `bin/`). SHA-256 as published in the GitHub release's asset digest. Other hosts install it by
/// hand: the Linux tar.xz unpacks to ~800 MB, more than an archive is unpacked in memory.
const RIZIN_PINS: &[Pin] = &[Pin {
    os: Some("windows"),
    arch: Some("x86_64"),
    url: "https://github.com/rizinorg/rizin/releases/download/v0.9.1/rizin-windows-static-v0.9.1.zip",
    sha256: "2d14e0a6ecba1196dcd742d63de83bbaffed2a7a78ef5a0a9b4e92a0f73d1d28",
    format: ArchiveFormat::Zip,
    strip_prefix: Some("rizin-win-installer-vs2019_static-64/"),
}];

/// Apktool 3.0.3 (runs on Java; one .jar for every OS). SHA-256 as published in the GitHub
/// release's asset digest.
const APKTOOL_PINS: &[Pin] = &[Pin {
    os: None,
    arch: None,
    url: "https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar",
    sha256: "dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423",
    format: ArchiveFormat::File { name: "apktool.jar" },
    strip_prefix: None,
}];

/// JADX 1.5.6 (runs on Java; one zip for every OS). SHA-256 as published in the GitHub release's
/// asset digest.
const JADX_PINS: &[Pin] = &[Pin {
    os: None,
    arch: None,
    url: "https://github.com/skylot/jadx/releases/download/v1.5.6/jadx-1.5.6.zip",
    sha256: "545ea2be9c242511bc145755cf4bda2485ade42966e096f8b4d3da2a230e8974",
    format: ArchiveFormat::Zip,
    strip_prefix: None,
}];

/// Ghidra 12.1.4 (any OS), as published in Ghidra's release notes. Installed by `ghidra::get`.
const GHIDRA_PINS: &[Pin] = &[Pin {
    os: None,
    arch: None,
    url: "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip",
    sha256: "ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db",
    format: ArchiveFormat::Zip,
    strip_prefix: None,
}];

/// Temurin JDK 21 for Ghidra, as published in Adoptium's `.sha256.txt` (the same as the GitHub
/// asset digests). Installed by `ghidra::get` into `<store>/jdk/<one folder>/bin/java`: the archives
/// hold `jdk-21.0.12.1+1/`, and on macOS the JDK itself is in its `Contents/Home/`, so that part is
/// stripped down to `Home/`.
const JAVA_PINS: &[Pin] = &[
    Pin {
        os: Some("windows"),
        arch: Some("x86_64"),
        url: "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip",
        sha256: "f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e",
        format: ArchiveFormat::Zip,
        strip_prefix: None,
    },
    Pin {
        os: Some("linux"),
        arch: Some("x86_64"),
        url: "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz",
        sha256: "ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94",
        format: ArchiveFormat::TarGz,
        strip_prefix: None,
    },
    Pin {
        os: Some("linux"),
        arch: Some("aarch64"),
        url: "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_aarch64_linux_hotspot_21.0.12.1_1.tar.gz",
        sha256: "23e37e026f12f3e706f18938ff611db3032d075b09d0879a25d06718c773e223",
        format: ArchiveFormat::TarGz,
        strip_prefix: None,
    },
    Pin {
        os: Some("macos"),
        arch: Some("x86_64"),
        url: "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_mac_hotspot_21.0.12.1_1.tar.gz",
        sha256: "44db0f08196daf19a47f90d13388b0c943b67663cb537f998fe29e836fa842ce",
        format: ArchiveFormat::TarGz,
        strip_prefix: Some("jdk-21.0.12.1+1/Contents/"),
    },
    Pin {
        os: Some("macos"),
        arch: Some("aarch64"),
        url: "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_aarch64_mac_hotspot_21.0.12.1_1.tar.gz",
        sha256: "3623232f33a9c3baadf304480b2535f9a3cba8a58d42ecbb438ba267315d9998",
        format: ArchiveFormat::TarGz,
        strip_prefix: Some("jdk-21.0.12.1+1/Contents/"),
    },
];

const GHIDRA_SETUP: &str = "Set up Ghidra from Settings → Engines (Deep mode); it brings its own Java.";

const fn manual(
    id: &'static str,
    name: &'static str,
    needed_for: &'static str,
    exes: &'static [&'static str],
    exes_windows: &'static [&'static str],
) -> ExternalEngine {
    ExternalEngine { id, name, needed_for, exes, exes_windows, known_paths: NO_PATHS, path_setting: true, install: Install::Manual }
}

/// Every external engine. Ghidra first, then in the order of the Settings → Engines path list
/// (the `tool_paths!` list in the engine crate, which a test keeps identical to this order).
pub const ENGINES: &[ExternalEngine] = &[
    ExternalEngine {
        id: crate::ghidra::get::ID,
        name: "Ghidra",
        needed_for: "Deep mode: richer decompiled code",
        exes: &["analyzeHeadless"],
        exes_windows: &["analyzeHeadless.bat"],
        known_paths: GHIDRA_PATHS,
        path_setting: false,
        install: Install::Guided { pins: GHIDRA_PINS, how: GHIDRA_SETUP },
    },
    ExternalEngine {
        id: "adb",
        name: "Android platform tools (adb)",
        needed_for: "Android devices: apps, logs, screenshots",
        exes: &["adb"],
        exes_windows: &["adb.exe"],
        known_paths: NO_PATHS,
        path_setting: true,
        install: Install::Pinned(ADB_PINS),
    },
    ExternalEngine {
        id: "jadx",
        name: "JADX",
        needed_for: "Decompiling Android apps to Java (needs Java)",
        exes: &["jadx"],
        exes_windows: &["jadx.bat"],
        known_paths: NO_PATHS,
        path_setting: true,
        install: Install::Pinned(JADX_PINS),
    },
    ExternalEngine {
        id: "apktool",
        name: "Apktool",
        needed_for: "Decoding Android resources (needs Java)",
        exes: &["apktool"],
        exes_windows: &["apktool.bat"],
        known_paths: NO_PATHS,
        path_setting: true,
        install: Install::Pinned(APKTOOL_PINS),
    },
    ExternalEngine {
        id: "chromium",
        name: "a Chromium-based browser",
        needed_for: "Studying websites in a live browser",
        exes: &["chromium", "chromium-browser", "google-chrome", "chrome", "msedge", "brave"],
        exes_windows: &["chrome.exe", "msedge.exe", "brave.exe"],
        known_paths: CHROMIUM_PATHS,
        path_setting: true,
        install: Install::Manual,
    },
    manual("frida", "Frida", "Tracing apps while they run", &["frida"], &["frida.exe"]),
    manual("gdb", "GDB", "Debugging native programs", &["gdb"], &["gdb.exe"]),
    manual("lldb", "LLDB", "Debugging Apple apps", &["lldb"], &["lldb.exe"]),
    manual("mitmdump", "mitmproxy (mitmdump)", "Recording an app's network traffic", &["mitmdump"], &["mitmdump.exe"]),
    manual("binwalk", "Binwalk", "Firmware carving (a second opinion)", &["binwalk"], &["binwalk.exe"]),
    manual("unblob", "Unblob", "Firmware unpacking (a second opinion)", &["unblob"], &[]),
    manual("ilspy", "ILSpy command line (ilspycmd)", ".NET decompiling (a second opinion)", &["ilspycmd"], &["ilspycmd.exe"]),
    ExternalEngine {
        id: "java",
        name: "Java runtime",
        needed_for: "Runs Ghidra, JADX and Apktool",
        exes: &["java"],
        exes_windows: &["java.exe"],
        known_paths: NO_PATHS,
        path_setting: true,
        install: Install::Guided { pins: JAVA_PINS, how: GHIDRA_SETUP },
    },
    manual("tshark", "Wireshark (tshark)", "Reading packet captures (a second opinion)", &["tshark"], &["tshark.exe"]),
    manual("objdump", "objdump (GNU binutils or LLVM)", "Disassembly (a second opinion)", &["objdump", "llvm-objdump"], &["objdump.exe", "llvm-objdump.exe"]),
    ExternalEngine {
        id: "rizin",
        name: "Rizin",
        needed_for: "Disassembly (a second opinion)",
        exes: &["rizin"],
        exes_windows: &["rizin.exe"],
        known_paths: NO_PATHS,
        path_setting: true,
        install: Install::Pinned(RIZIN_PINS),
    },
    manual("rtl433", "rtl_433", "Decoding radio recordings", &["rtl_433"], &["rtl_433.exe"]),
    ExternalEngine {
        id: "vineflower",
        name: "Vineflower",
        needed_for: "Decompiling Java classes and JARs (needs Java)",
        exes: &["vineflower"],
        exes_windows: &["vineflower.bat", "vineflower.cmd"],
        known_paths: NO_PATHS,
        path_setting: true,
        install: Install::Pinned(VINEFLOWER_PINS),
    },
];

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    #[test]
    fn ids_are_unique_and_well_formed() {
        let mut seen = HashSet::new();
        for e in ENGINES {
            assert!(seen.insert(e.id), "duplicate engine id {}", e.id);
            assert!(!e.id.is_empty() && e.id.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit()), "bad id {}", e.id);
            assert!(!e.name.is_empty() && !e.needed_for.is_empty(), "{} needs a name and a purpose", e.id);
            assert!(!e.exes.is_empty() || !e.exes_windows.is_empty(), "{} has no executables", e.id);
            assert!(e.exes_windows.iter().all(|x| x.ends_with(".exe") || x.ends_with(".bat") || x.ends_with(".cmd")), "{}", e.id);
            assert!(e.exes.iter().all(|x| !x.contains('.')), "{}: unix names have no extension", e.id);
        }
        // Ghidra's folder is its own setting; every other engine has a path override.
        assert!(ENGINES.iter().all(|e| e.path_setting == (e.id != "ghidra")));
    }

    #[test]
    fn every_pin_is_versioned_https_with_a_sha256() {
        for e in ENGINES {
            if let Install::Pinned(p) | Install::Guided { pins: p, .. } = e.install {
                assert!(!p.is_empty(), "{} is managed but has no pins", e.id);
            }
            for p in e.pins() {
                assert!(p.url.starts_with("https://"), "{}: {}", e.id, p.url);
                assert!(!p.url.contains("latest"), "{}: moving link {}", e.id, p.url);
                assert_eq!(p.sha256.len(), 64, "{}: {}", e.id, p.url);
                assert!(p.sha256.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)), "{}: sha256 must be lowercase hex", e.id);
                assert!(p.os.is_none_or(|o| ["linux", "macos", "windows"].contains(&o)), "{}", e.id);
                assert!(p.arch.is_none_or(|a| ["x86_64", "aarch64"].contains(&a)), "{}", e.id);
            }
        }
    }

    #[test]
    fn a_single_file_pin_installs_and_is_found_by_its_name() {
        let vf = ENGINES.iter().find(|e| e.id == "vineflower").unwrap();
        let pin = vf.host_pin().unwrap();
        assert_eq!(pin.format, ArchiveFormat::File { name: "vineflower.jar" });
        let store = tempfile::tempdir().unwrap();
        let dir = store.path().join("vineflower");
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(crate::install::unpack(b"PK jar bytes", pin.format, &dir, None, None, &|_| {}).unwrap(), 1);
        assert_eq!(std::fs::read(dir.join("vineflower.jar")).unwrap(), b"PK jar bytes");
        assert!(crate::install::unpack(b"x", ArchiveFormat::File { name: "../evil.jar" }, &dir, None, None, &|_| {}).is_err());
        struct None_;
        impl crate::ToolPathLookup for None_ {
            fn override_for(&self, _: &str) -> Option<std::path::PathBuf> {
                None
            }
        }
        assert_eq!(crate::locate("vineflower", &None_, store.path()), Some(dir.join("vineflower.jar")));
    }

    #[test]
    fn pins_pick_the_host() {
        let adb = ENGINES.iter().find(|e| e.id == "adb").unwrap();
        for os in ["linux", "macos", "windows"] {
            assert!(adb.pin_for(os, "x86_64").is_some_and(|p| p.os == Some(os)));
        }
        assert!(adb.pin_for("freebsd", "x86_64").is_none());
        let java = ENGINES.iter().find(|e| e.id == "java").unwrap();
        assert!(java.pin_for("windows", "x86_64").is_some());
        assert!(java.pin_for("windows", "aarch64").is_none());
        let jadx = ENGINES.iter().find(|e| e.id == "jadx").unwrap();
        assert!(jadx.pin_for("freebsd", "riscv64").is_some());
        assert!(ENGINES.iter().find(|e| e.id == "gdb").unwrap().host_pin().is_none());
    }
}
