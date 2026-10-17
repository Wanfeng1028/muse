use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::sync::RwLock;
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};

use PluginError::*;
pub const MAX_TOTAL_UNCOMPRESSED: u64 = 10 * 1024 * 1024;
pub const MAX_FILE_COUNT: usize = 200;
pub const MANIFEST_NAME: &str = "plugin.json";
/// 允许的权限白名单。
pub const ALLOWED_PERMISSIONS: [&str; 3] = ["fs.read", "fs.write", "settings.read"];

/// 入口路径前缀。
pub const ENTRY_PREFIX: &str = "/static/plugins/";


#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PluginManifest {
    pub id: String,
    pub name: String,
    pub version: String,
    pub entry: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub icon: String,
    #[serde(default)]
    pub permissions: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PluginError {
    EmptyArchive,
    TooManyFiles(usize),
    UncompressedTooLarge(u64),
    PathTraversal(String),
    AbsolutePath(String),
    InvalidEntryName(String),
    ManifestMissing,
    ManifestInvalid(String),
    IdMismatch { manifest_id: String, dir_name: String },
    AlreadyInstalled(String),
    Io(String),
}

impl std::fmt::Display for PluginError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EmptyArchive => write!(f, "压缩包为空"),
            TooManyFiles(n) => write!(f, "压缩包文件数超过上限 200（实际 {}）", n),
            UncompressedTooLarge(n) => {
                write!(f, "解压后总大小超过 10MB 上限（实际 {} 字节）", n)
            }
            PathTraversal(p) => write!(f, "检测到路径穿越：{}", p),
            AbsolutePath(p) => write!(f, "禁止绝对路径：{}", p),
            InvalidEntryName(p) => write!(f, "非法条目名：{}", p),
            ManifestMissing => write!(f, "缺少 plugin.json"),
            ManifestInvalid(msg) => write!(f, "plugin.json 解析失败：{}", msg),
            IdMismatch { manifest_id, dir_name } => write!(
                f,
                "manifest id ({}) 与目录名 ({}) 不一致",
                manifest_id, dir_name
            ),
            AlreadyInstalled(id) => write!(f, "插件 {} 已安装", id),
            Io(msg) => write!(f, "IO 错误：{}", msg),
        }
    }
}

impl std::error::Error for PluginError {}

fn validate_entry_name(raw: &str) -> Result<(), PluginError> {
    if raw.is_empty() {
        return Err(InvalidEntryName(raw.to_string()));
    }
    if raw.contains('\0') {
        return Err(InvalidEntryName(raw.to_string()));
    }
    if raw.starts_with('/') || raw.starts_with('\\') {
        return Err(AbsolutePath(raw.to_string()));
    }
    // Windows 盘符形如 C:\ 或 C:/
    let bytes = raw.as_bytes();
    if bytes.len() >= 2 && bytes[1] == b':' && bytes[0].is_ascii_alphabetic() {
        return Err(AbsolutePath(raw.to_string()));
    }
    for comp in Path::new(raw).components() {
        match comp {
            Component::ParentDir => return Err(PathTraversal(raw.to_string())),
            Component::RootDir | Component::Prefix(_) => {
                return Err(AbsolutePath(raw.to_string()))
            }
            Component::Normal(_) | Component::CurDir => {}
        }
    }
    Ok(())
}

fn safe_join(base: &Path, entry_name: &str) -> Result<PathBuf, PluginError> {
    validate_entry_name(entry_name)?;
    let mut out = base.to_path_buf();
    for comp in Path::new(entry_name).components() {
        if let Component::Normal(seg) = comp {
            out.push(seg);
        }
    }
    // 二次确认：结果必须仍在 base 之下
    let canon_base = base
        .canonicalize()
        .map_err(|e| Io(format!("canonicalize base: {}", e)))?;
    // 目标可能还不存在，用父目录规范化后再拼接
    let mut probe = canon_base.clone();
    for comp in Path::new(entry_name).components() {
        if let Component::Normal(seg) = comp {
            probe.push(seg);
        }
    }
    if !probe.starts_with(&canon_base) {
        return Err(PathTraversal(entry_name.to_string()));
    }
    Ok(probe)
}

fn validate_manifest(m: &PluginManifest) -> Result<(), PluginError> {
    if m.id.trim().is_empty() {
        return Err(ManifestInvalid("id 不能为空".into()));
    }
    if m.id.contains('/') || m.id.contains('\\') || m.id.contains("..") {
        return Err(ManifestInvalid("id 含有非法字符".into()));
    }
    if m.name.trim().is_empty() {
        return Err(ManifestInvalid("name 不能为空".into()));
    }
    if m.version.trim().is_empty() {
        return Err(ManifestInvalid("version 不能为空".into()));
    }
    if m.entry.trim().is_empty() {
        return Err(ManifestInvalid("entry 不能为空".into()));
    }
    validate_entry_name(&m.entry)
        .map_err(|e| ManifestInvalid(format!("entry 非法：{}", e)))?;
    if !m.entry.ends_with(".js") {
        return Err(ManifestInvalid("entry 必须以 .js 结尾".into()));
    }
    Ok(())
}

/// 从 zip 字节安装插件到 data_dir/plugins/<id>/
///
/// 校验规则：
/// - 拒绝空压缩包
/// - 解压后总大小 <= 10MB
/// - 文件数 <= 200
/// - 拒绝路径穿越（..、绝对路径、盘符）
/// - 必须包含 plugin.json，且 id 与安装目录名一致
/// - 若目标目录已存在，返回 AlreadyInstalled
pub fn install_from_zip(zip_bytes: &[u8], data_dir: &Path) -> Result<PluginManifest, String> {
    install_from_zip_inner(zip_bytes, data_dir).map_err(|e| e.to_string())
}

fn install_from_zip_inner(
    zip_bytes: &[u8],
    data_dir: &Path,
) -> Result<PluginManifest, PluginError> {
    if zip_bytes.is_empty() {
        return Err(EmptyArchive);
    }
    let cursor = std::io::Cursor::new(zip_bytes);
    let mut archive = zip::ZipArchive::new(cursor)
        .map_err(|e| ManifestInvalid(format!("zip 打不开：{}", e)))?;

    let file_count = archive.len();
    if file_count == 0 {
        return Err(EmptyArchive);
    }
    if file_count > MAX_FILE_COUNT {
        return Err(TooManyFiles(file_count));
    }

    // 先扫描一遍：大小、路径、manifest 存在性
    let mut total_size: u64 = 0;
    let mut manifest_raw: Option<Vec<u8>> = None;
    for i in 0..file_count {
        let entry = archive
            .by_index(i)
            .map_err(|e| ManifestInvalid(format!("读 zip 条目失败：{}", e)))?;
        let name = entry.name().to_string();
        if entry.is_dir() {
            continue;
        }
        validate_entry_name(&name)?;
        total_size = total_size
            .checked_add(entry.size())
            .ok_or(UncompressedTooLarge(u64::MAX))?;
        if total_size > MAX_TOTAL_UNCOMPRESSED {
            return Err(UncompressedTooLarge(total_size));
        }
        if name == MANIFEST_NAME {
            let mut buf = Vec::with_capacity(entry.size() as usize);
            // 单独再取一次 reader（by_index 已持有 entry 借用，这里在循环外处理）
            drop(entry);
            let mut e2 = archive
                .by_index(i)
                .map_err(|e| ManifestInvalid(format!("读 zip 条目失败：{}", e)))?;
            e2.read_to_end(&mut buf)
                .map_err(|e| Io(format!("读 plugin.json 失败：{}", e)))?;
            manifest_raw = Some(buf);
        }
    }

    let manifest_raw = manifest_raw.ok_or(ManifestMissing)?;
    let manifest: PluginManifest = serde_json::from_slice(&manifest_raw)
        .map_err(|e| ManifestInvalid(e.to_string()))?;
    validate_manifest(&manifest)?;

    // 解压目录名必须与 manifest id 一致
    let plugins_root = data_dir.join("plugins");
    fs::create_dir_all(&plugins_root).map_err(|e| Io(format!("建 plugins 目录失败：{}", e)))?;

    let target_dir = plugins_root.join(&manifest.id);
    let dir_name = manifest.id.clone();

    if target_dir.exists() {
        return Err(AlreadyInstalled(manifest.id.clone()));
    }

    // 建临时目录，全部成功后再 rename，失败则清理
    let tmp_dir = plugins_root.join(format!(".tmp-{}-{}", manifest.id, std::process::id()));
    if tmp_dir.exists() {
        fs::remove_dir_all(&tmp_dir).map_err(|e| Io(format!("清理临时目录失败：{}", e)))?;
    }
    fs::create_dir_all(&tmp_dir).map_err(|e| Io(format!("建临时目录失败：{}", e)))?;

    let result = (|| -> Result<(), PluginError> {
        for i in 0..file_count {
            let mut entry = archive
                .by_index(i)
                .map_err(|e| ManifestInvalid(format!("读 zip 条目失败：{}", e)))?;
            let name = entry.name().to_string();
            if entry.is_dir() {
                continue;
            }
            let out_path = safe_join(&tmp_dir, &name)?;
            if let Some(parent) = out_path.parent() {
                fs::create_dir_all(parent)
                    .map_err(|e| Io(format!("建目录失败 {}: {}", parent.display(), e)))?;
            }
            let mut buf = Vec::with_capacity(entry.size() as usize);
            entry
                .read_to_end(&mut buf)
                .map_err(|e| Io(format!("读条目 {} 失败：{}", name, e)))?;
            if buf.len() as u64 > MAX_TOTAL_UNCOMPRESSED {
                return Err(UncompressedTooLarge(buf.len() as u64));
            }
            fs::write(&out_path, &buf)
                .map_err(|e| Io(format!("写文件失败 {}: {}", out_path.display(), e)))?;
        }
        Ok(())
    })();

    if let Err(e) = result {
        let _ = fs::remove_dir_all(&tmp_dir);
        return Err(e);
    }

    // 再次确认 id 与最终目录名一致
    if dir_name != manifest.id {
        let _ = fs::remove_dir_all(&tmp_dir);
        return Err(IdMismatch {
            manifest_id: manifest.id.clone(),
            dir_name,
        });
    }

    if let Err(e) = fs::rename(&tmp_dir, &target_dir) {
        let _ = fs::remove_dir_all(&tmp_dir);
        return Err(Io(format!("移动插件目录失败：{}", e)));
    }

    Ok(manifest)
}

/// 列出已安装插件（读取每个目录的 plugin.json）
pub fn list_installed(data_dir: &Path) -> Result<Vec<PluginManifest>, String> {
    let plugins_root = data_dir.join("plugins");
    if !plugins_root.exists() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    let rd = fs::read_dir(&plugins_root).map_err(|e| format!("读 plugins 目录失败：{}", e))?;
    for entry in rd {
        let entry = entry.map_err(|e| format!("读目录项失败：{}", e))?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with(".tmp-") {
            continue;
        }
        let manifest_path = path.join(MANIFEST_NAME);
        if !manifest_path.exists() {
            continue;
        }
        let raw = fs::read(&manifest_path)
            .map_err(|e| format!("读 {} 失败：{}", manifest_path.display(), e))?;
        let m: PluginManifest =
            serde_json::from_slice(&raw).map_err(|e| format!("解析 {} 失败：{}", manifest_path.display(), e))?;
        out.push(m);
    }
    Ok(out)
}

/// 卸载插件：删除 data_dir/plugins/<id>/
pub fn uninstall(id: &str, data_dir: &Path) -> Result<(), String> {
    if id.trim().is_empty() || id.contains('/') || id.contains('\\') || id.contains("..") {
        return Err(format!("非法插件 id：{}", id));
    }
    let target = data_dir.join("plugins").join(id);
    if !target.exists() {
        return Err(format!("插件 {} 未安装", id));
    }
    fs::remove_dir_all(&target).map_err(|e| format!("删除插件目录失败：{}", e))
}

#[cfg(test)]
mod unit_tests {
    use super::*;

    #[test]
    fn rejects_dotdot() {
        let r = validate_entry_name("../evil.js");
        assert!(matches!(r, Err(PathTraversal(_))));
        assert!(r.is_err());
    }

    #[test]
    fn rejects_absolute() {
        assert!(matches!(
            validate_entry_name("/etc/passwd"),
            Err(AbsolutePath(_))
        ));
        assert!(validate_entry_name("/etc/passwd").is_err());
    }

    #[test]
    fn rejects_windows_drive() {
        let r = validate_entry_name("C:\\evil.js");
        assert!(matches!(r, Err(AbsolutePath(_))));
        assert!(r.is_err());
    }

    #[test]
    fn accepts_normal_path() {
        assert!(validate_entry_name("js/main.js").is_ok());
        assert!(validate_entry_name("plugin.json").is_ok());
    }

    #[test]
    fn manifest_validation_rejects_empty_id() {
        let m = PluginManifest {
            id: String::new(),
            name: "n".into(),
            version: "1.0.0".into(),
            entry: "main.js".into(),
            description: String::new(),
            icon: String::new(),
            permissions: vec![],
        };
        assert!(validate_manifest(&m).is_err());
        assert!(matches!(
            validate_manifest(&m),
            Err(ManifestInvalid(_))
        ));
    }

    #[test]
    fn manifest_validation_rejects_non_js_entry() {
        let m = PluginManifest {
            id: "demo".into(),
            name: "n".into(),
            version: "1.0.0".into(),
            entry: "main.wasm".into(),
            description: String::new(),
            icon: String::new(),
            permissions: vec![],
        };
        assert!(validate_manifest(&m).is_err());
        assert!(matches!(validate_manifest(&m), Err(ManifestInvalid(_))));
    }
}

/// 插件注册表。用 RwLock 包住 HashMap，读多写少。
pub struct PluginRegistry {
    inner: RwLock<HashMap<String, PluginManifest>>,
}

impl PluginRegistry {
    /// 新建空注册表。
    pub fn new() -> Self {
        Self {
            inner: RwLock::new(HashMap::new()),
        }
    }

    /// 注册插件。校验失败或 id 重复时返回 Err，错误信息为中文。
    pub fn register(&self, manifest: PluginManifest) -> Result<(), String> {
        validate_id(&manifest.id)?;
        validate_version(&manifest.version)?;
        validate_entry(&manifest.entry)?;
        validate_permissions(&manifest.permissions)?;

        let mut map = self
            .inner
            .write()
            .map_err(|_| "插件注册表锁已中毒，无法写入".to_string())?;

        if map.contains_key(&manifest.id) {
            return Err(format!("插件 id 已存在：{}", manifest.id));
        }
        map.insert(manifest.id.clone(), manifest);
        Ok(())
    }

    /// 卸载插件。成功返回被移除的清单，不存在返回 None。
    pub fn unregister(&self, id: &str) -> Option<PluginManifest> {
        let mut map = self.inner.write().ok()?;
        map.remove(id)
    }

    /// 列出全部插件，按 id 升序，保证输出稳定。
    pub fn list(&self) -> Vec<PluginManifest> {
        let map = match self.inner.read() {
            Ok(m) => m,
            Err(_) => return Vec::new(),
        };
        let mut items: Vec<PluginManifest> = map.values().cloned().collect();
        items.sort_by(|a, b| a.id.cmp(&b.id));
        items
    }
}

impl Default for PluginRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// id：字母数字加连字符，长度 1-32。

fn validate_id(id: &str) -> Result<(), String> {
    let len = id.chars().count();
    if len < 1 || len > 32 {
        return Err(format!("插件 id 长度必须在 1-32 字符之间，当前为 {} 字符", len));
    }
    if !id
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-')
    {
        return Err(format!("插件 id 只允许字母、数字和连字符，当前为：{}", id));
    }
    Ok(())
}

/// version：semver 格式 MAJOR.MINOR.PATCH，三段都是数字，不允许前导零。
fn validate_version(version: &str) -> Result<(), String> {
    let parts: Vec<&str> = version.split('.').collect();
    if parts.len() != 3 {
        return Err(format!(
            "插件 version 必须是 semver 格式 MAJOR.MINOR.PATCH，当前为：{}",
            version
        ));
    }
    for part in &parts {
        if part.is_empty() {
            return Err(format!("插件 version 段不能为空，当前为：{}", version));
        }
        if !part.chars().all(|c| c.is_ascii_digit()) {
            return Err(format!(
                "插件 version 每段必须是数字，当前为：{}",
                version
            ));
        }
        if part.len() > 1 && part.starts_with('0') {
            return Err(format!(
                "插件 version 段不允许前导零，当前为：{}",
                version
            ));
        }
    }
    Ok(())
}

/// entry：必须以 /static/plugins/ 开头。
fn validate_entry(entry: &str) -> Result<(), String> {
    if !entry.starts_with(ENTRY_PREFIX) {
        return Err(format!(
            "插件 entry 必须以 {} 开头，当前为：{}",
            ENTRY_PREFIX, entry
        ));
    }
    Ok(())
}

/// permissions：只允许白名单内的三种，且不允许重复。
fn validate_permissions(permissions: &[String]) -> Result<(), String> {
    let mut seen: Vec<&str> = Vec::new();
    for p in permissions {
        if !ALLOWED_PERMISSIONS.contains(&p.as_str()) {
            return Err(format!("插件权限不合法：{}", p));
        }
        if seen.contains(&p.as_str()) {
            return Err(format!("插件权限重复：{}", p));
        }
        seen.push(p.as_str());
    }
    Ok(())
}
