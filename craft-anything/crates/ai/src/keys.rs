//! API keys: the OS keychain first, then a clearly labelled owner-only fallback file, then the
//! usual environment variables. Keys are never logged or written to project files.

use crate::BackendKind;
use craft_anything_engine::tools::asset_tools::AssetKeys;
use craft_anything_engines::assets::{AssetProvider, AssetProviders};
use craft_anything_evidence::{ErrorCode, ToolError};
use std::path::PathBuf;
use std::time::Duration;

/// Service name in the OS keychain.
pub const SERVICE: &str = "ai.storyteller.craft-anything";
/// Set to `1` to skip the OS keychain (tests, headless servers).
pub const NO_KEYCHAIN_ENV: &str = "CRAFT_ANYTHING_NO_KEYCHAIN";
/// The keychain can block (a locked desktop keyring); never wait longer than this.
const KEYCHAIN_TIMEOUT: Duration = Duration::from_secs(3);

const FILE_HEADER: &str = "# Craft Anything AI keys: FALLBACK STORE.\n# These keys are here because no OS keychain was available when they were saved.\n# This file is readable only by you (0600). Delete a line to forget a key.\n";

/// Where the fal.ai key for generated game assets is stored.
pub const FAL_KEY: &str = "assets:fal";

/// Where an asset provider's key is stored (`assets:<provider id>`).
pub fn asset_key_name(provider: &str) -> String {
    format!("assets:{provider}")
}

/// An asset provider's key: stored, else the provider's own environment variable.
pub fn asset_key(store: &KeyStore, provider: &dyn AssetProvider) -> Option<String> {
    store.get(&asset_key_name(provider.id())).or_else(|| provider.key_env().and_then(|v| std::env::var(v).ok())).filter(|k| !k.trim().is_empty())
}

/// Every provider's key that is set up, for the builder's tool server.
pub fn asset_keys(store: &KeyStore, providers: &AssetProviders) -> AssetKeys {
    AssetKeys(
        providers.ids().into_iter().filter_map(|id| providers.get(id)).filter_map(|p| asset_key(store, p.as_ref()).map(|k| (p.id().to_string(), k))).collect(),
    )
}

/// The fal.ai key for game assets: stored, else fal's environment variable.
pub fn fal_key(store: &KeyStore) -> Option<String> {
    asset_key(store, &craft_anything_engines::assets::fal::Fal::default())
}

/// The environment variable conventionally holding a key for this kind.
pub fn env_var(kind: BackendKind) -> Option<&'static str> {
    match kind {
        BackendKind::Anthropic => Some("ANTHROPIC_API_KEY"),
        BackendKind::Openai => Some("OPENAI_API_KEY"),
        BackendKind::Openrouter => Some("OPENROUTER_API_KEY"),
        BackendKind::OpenaiCompatible | BackendKind::AgentCli => None,
    }
}

/// Where keys live.
#[derive(Debug, Clone)]
pub struct KeyStore {
    file: PathBuf,
    use_keychain: bool,
}

impl KeyStore {
    /// The default store: keychain + `<config dir>/ai-keys.toml`.
    pub fn system() -> Self {
        let no_chain = std::env::var(NO_KEYCHAIN_ENV).is_ok_and(|v| v == "1");
        KeyStore { file: craft_anything_engine::settings::config_dir().join("ai-keys.toml"), use_keychain: !no_chain }
    }

    /// A file-only store (tests).
    pub fn file_only(file: PathBuf) -> Self {
        KeyStore { file, use_keychain: false }
    }

    fn read_file(&self) -> toml::Table {
        std::fs::read_to_string(&self.file).ok().and_then(|t| toml::from_str(&t).ok()).unwrap_or_default()
    }

    /// The file's keys before changing them: none when it doesn't exist, an error when it can't be
    /// read, so a save never replaces a file it couldn't read and drops the other keys (#262).
    fn read_file_to_change(&self) -> Result<toml::Table, ToolError> {
        let unreadable = |why: String| {
            ToolError::new(ErrorCode::FileError, format!("Couldn't read the key file {}: {why}", self.file.display()))
                .with_remediation("Fix or move that file (it was left untouched), then save the key again.")
        };
        match std::fs::read(&self.file) {
            Ok(b) => {
                let text = String::from_utf8(b).map_err(|_| unreadable("it isn't valid UTF-8".into()))?;
                toml::from_str(&text).map_err(|e| unreadable(e.to_string()))
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(toml::Table::new()),
            Err(e) => Err(unreadable(e.to_string())),
        }
    }

    fn write_file(&self, t: &toml::Table) -> Result<(), ToolError> {
        let body = toml::to_string(t).map_err(|e| ToolError::internal(e.to_string()))?;
        craft_anything_platform::write_atomic_private(&self.file, format!("{FILE_HEADER}{body}").as_bytes())
    }

    /// The stored key for a backend (keychain, then fallback file).
    pub fn get(&self, backend: &str) -> Option<String> {
        if self.use_keychain
            && let Some(k) = keychain::get(backend)
        {
            return Some(k);
        }
        self.read_file().get(backend).and_then(|v| v.as_str()).map(str::to_string).filter(|k| !k.is_empty())
    }

    /// The key to use: stored, else the kind's environment variable.
    pub fn resolve(&self, backend: &str, kind: BackendKind) -> Option<String> {
        self.get(backend).or_else(|| env_var(kind).and_then(|v| std::env::var(v).ok()).filter(|k| !k.trim().is_empty()))
    }

    /// Save a key. Returns where it went: `"keychain"` or `"file"`.
    pub fn set(&self, backend: &str, key: &str) -> Result<&'static str, ToolError> {
        if key.trim().is_empty() {
            return Err(ToolError::invalid("The key is empty."));
        }
        if self.use_keychain && keychain::set(backend, key) {
            // Don't leave a stale copy in the fallback file (the keychain's copy is read first).
            if let Ok(mut t) = self.read_file_to_change()
                && t.remove(backend).is_some()
            {
                self.write_file(&t)?;
            }
            return Ok("keychain");
        }
        let mut t = self.read_file_to_change()?;
        t.insert(backend.to_string(), toml::Value::String(key.to_string()));
        self.write_file(&t).map_err(|e| ToolError::new(ErrorCode::NoPermission, format!("Couldn't save the key: {}", e.message)))?;
        Ok("file")
    }

    pub fn delete(&self, backend: &str) -> Result<(), ToolError> {
        if self.use_keychain {
            keychain::delete(backend);
        }
        let mut t = self.read_file_to_change()?;
        if t.remove(backend).is_some() {
            self.write_file(&t)?;
        }
        Ok(())
    }
}

/// Run a keychain operation on a helper thread with a deadline.
fn bounded<T: Send + 'static>(f: impl FnOnce() -> Option<T> + Send + 'static) -> Option<T> {
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::Builder::new()
        .name("keychain".into())
        .spawn(move || {
            let _ = tx.send(f());
        })
        .ok()?;
    rx.recv_timeout(KEYCHAIN_TIMEOUT).ok().flatten()
}

#[cfg(any(target_os = "linux", target_os = "macos", windows))]
mod keychain {
    use super::{SERVICE, bounded};

    pub fn get(backend: &str) -> Option<String> {
        let b = backend.to_string();
        bounded(move || keyring::Entry::new(SERVICE, &b).ok()?.get_password().ok())
    }

    pub fn set(backend: &str, key: &str) -> bool {
        let (b, k) = (backend.to_string(), key.to_string());
        bounded(move || keyring::Entry::new(SERVICE, &b).ok()?.set_password(&k).ok()).is_some()
    }

    pub fn delete(backend: &str) {
        let b = backend.to_string();
        let _ = bounded(move || keyring::Entry::new(SERVICE, &b).ok()?.delete_credential().ok());
    }
}

#[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
mod keychain {
    pub fn get(_: &str) -> Option<String> {
        let _ = super::bounded(|| None::<()>);
        None
    }
    pub fn set(_: &str, _: &str) -> bool {
        false
    }
    pub fn delete(_: &str) {}
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A second provider with no environment variable, so nothing here reads the real one.
    struct Other;

    impl AssetProvider for Other {
        fn id(&self) -> &'static str {
            "other"
        }
        fn name(&self) -> &'static str {
            "Other"
        }
        fn generate(&self, _key: &str, _req: &craft_anything_engines::assets::AssetRequest) -> Result<craft_anything_engines::assets::Generated, ToolError> {
            Err(ToolError::invalid("not here"))
        }
    }

    #[test]
    fn each_asset_provider_has_its_own_key() {
        let d = tempfile::tempdir().unwrap();
        let s = KeyStore::file_only(d.path().join("keys.toml"));
        let mut providers = AssetProviders::built_in();
        providers.register(std::sync::Arc::new(Other));
        s.set(&asset_key_name("other"), "o-1").unwrap();
        let keys = asset_keys(&s, &providers);
        assert_eq!(keys.get("other"), Some("o-1"));
        // fal's is stored where it always was, apart from the other provider's.
        assert_eq!(asset_key_name("fal"), FAL_KEY);
        s.set(FAL_KEY, "f-1").unwrap();
        let keys = asset_keys(&s, &providers);
        assert_eq!((keys.get("fal"), keys.get("other")), (Some("f-1"), Some("o-1")));
        s.delete(&asset_key_name("other")).unwrap();
        assert_eq!(asset_keys(&s, &providers).get("other"), None);
        assert_eq!(fal_key(&s).as_deref(), Some("f-1"));
    }

    /// #262: a key file that can't be read is left as it is, with every other key in it.
    #[test]
    fn an_unreadable_key_file_is_never_replaced() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("ai-keys.toml");
        let s = KeyStore::file_only(file.clone());
        let valid = b"FakeBackend = \"sk-test-backend\"\n\"assets:fal\" = \"sk-test-old\"\n".to_vec();
        let broken_toml = b"FakeBackend = \"sk-test-backend\"\n\"assets:fal\" = \"sk-test-old\n".to_vec();
        let broken_utf8 = [valid.clone(), b"\xff".to_vec()].concat();
        for bad in [broken_toml, broken_utf8] {
            std::fs::write(&file, &bad).unwrap();
            let e = s.set(FAL_KEY, "sk-test-new").unwrap_err();
            assert!(e.message.contains("Couldn't read the key file"), "{e:?}");
            assert!(s.delete("FakeBackend").is_err());
            assert_eq!(std::fs::read(&file).unwrap(), bad, "the file was changed");
        }
        std::fs::write(&file, &valid).unwrap();
        assert_eq!(s.set(FAL_KEY, "sk-test-new").unwrap(), "file");
        assert_eq!((s.get("FakeBackend").as_deref(), s.get(FAL_KEY).as_deref()), (Some("sk-test-backend"), Some("sk-test-new")));
    }

    #[test]
    fn file_fallback_is_labelled_and_private() {
        let dir = tempfile::tempdir().unwrap();
        let s = KeyStore::file_only(dir.path().join("ai-keys.toml"));
        assert_eq!(s.set("Claude", "sk-test").unwrap(), "file");
        assert_eq!(s.get("Claude").as_deref(), Some("sk-test"));
        let text = std::fs::read_to_string(dir.path().join("ai-keys.toml")).unwrap();
        assert!(text.starts_with("# Craft Anything AI keys: FALLBACK STORE."));
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt as _;
            assert_eq!(std::fs::metadata(dir.path().join("ai-keys.toml")).unwrap().permissions().mode() & 0o777, 0o600);
        }
        s.delete("Claude").unwrap();
        assert!(s.get("Claude").is_none());
        assert!(s.set("x", " ").is_err());
        assert_eq!(env_var(BackendKind::Openrouter), Some("OPENROUTER_API_KEY"));
    }
}
