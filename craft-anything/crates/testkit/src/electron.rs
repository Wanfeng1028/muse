//! A tiny synthetic Electron app ("Notes") and archive builders for JavaScript tests.
//!
//! The feature under test: the renderer's Export button calls `window.api.exportNotes(notes)`,
//! the preload bridges that to `ipcRenderer.invoke('export-notes')`, and the main process
//! handles `export-notes` by asking for a path and writing a CSV file.

use std::path::{Path, PathBuf};

pub const PACKAGE_JSON: &str = r#"{
  "name": "notes",
  "productName": "Notes",
  "version": "1.0.0",
  "main": "main.js",
  "dependencies": { "electron-log": "5.0.0" },
  "devDependencies": { "electron": "31.0.0" }
}
"#;

pub const MAIN_JS: &str = r#"const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

function toCsv(notes) {
  const rows = notes.map((n) => [n.title, n.body].map((v) => '"' + String(v).replace(/"/g, '""') + '"').join(','));
  return ['title,body', ...rows].join('\n');
}

ipcMain.handle('export-notes', async (_event, notes) => {
  const { filePath, canceled } = await dialog.showSaveDialog(mainWindow, { defaultPath: 'notes.csv' });
  if (canceled || !filePath) return { ok: false };
  fs.writeFileSync(filePath, toCsv(notes), 'utf8');
  return { ok: true, path: filePath };
});

ipcMain.on('log', (_event, message) => console.log(message));

app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
"#;

pub const PRELOAD_JS: &str = r#"const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  exportNotes: (notes) => ipcRenderer.invoke('export-notes', notes),
  log: (message) => ipcRenderer.send('log', message),
});
"#;

pub const INDEX_HTML: &str = r#"<!doctype html>
<html>
<head>
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'">
  <title>Notes</title>
</head>
<body>
  <p><span id="count">0</span> notes</p>
  <button id="export">Export CSV</button>
  <script src="app.js"></script>
</body>
</html>
"#;

pub const RENDERER_JS: &str = r#"const notes = [];

function addNote(title, body) {
  notes.push({ title, body });
  render();
}

function render() {
  document.getElementById('count').textContent = String(notes.length);
}

async function exportNotes() {
  const result = await window.api.exportNotes(notes);
  if (result.ok) window.api.log('exported to ' + result.path);
}

document.getElementById('export').addEventListener('click', exportNotes);
fetch('https://api.notes.example/v1/sync', { method: 'POST', body: JSON.stringify(notes) });
localStorage.setItem('draft', '');
addNote('First', 'Hello');
"#;

/// Version 2 of the same app: a new `import-notes` channel and a changed CSV header.
pub const MAIN_JS_V2_EXTRA: &str = r#"
ipcMain.handle('import-notes', async () => {
  const { filePaths } = await dialog.showOpenDialog(mainWindow, {});
  return fs.readFileSync(filePaths[0], 'utf8');
});
"#;

/// (path, contents) for every file of the Notes app.
pub fn notes_app_files() -> Vec<(&'static str, String)> {
    vec![
        ("package.json", PACKAGE_JSON.to_string()),
        ("main.js", MAIN_JS.to_string()),
        ("preload.js", PRELOAD_JS.to_string()),
        ("renderer/index.html", INDEX_HTML.to_string()),
        ("renderer/app.js", RENDERER_JS.to_string()),
    ]
}

/// The Notes app, version 2.
pub fn notes_app_v2_files() -> Vec<(&'static str, String)> {
    let mut v = notes_app_files();
    for (p, c) in &mut v {
        if *p == "main.js" {
            c.push_str(MAIN_JS_V2_EXTRA);
        }
        if *p == "package.json" {
            *c = c.replace("1.0.0\",\n  \"main", "2.0.0\",\n  \"main");
        }
    }
    v
}

/// Write files under `root` (created) and return it.
pub fn write_files(root: &Path, files: &[(&str, String)]) -> std::io::Result<PathBuf> {
    for (p, c) in files {
        let path = root.join(p);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(path, c)?;
    }
    Ok(root.to_path_buf())
}

/// Write the Notes app as an unpacked folder at `dir/notes`.
pub fn write_notes_app(dir: &Path) -> std::io::Result<PathBuf> {
    write_files(&dir.join("notes"), &notes_app_files())
}

/// Build an ASAR archive from (path, bytes).
pub fn asar(files: &[(&str, &[u8])]) -> Vec<u8> {
    use serde_json::{Map, Value, json};
    fn insert(map: &mut Map<String, Value>, parts: &[&str], leaf: Value) {
        match parts {
            [] => {}
            [last] => {
                map.insert((*last).to_string(), leaf);
            }
            [dir, rest @ ..] => {
                let e = map.entry((*dir).to_string()).or_insert_with(|| json!({"files": {}}));
                insert(e["files"].as_object_mut().unwrap(), rest, leaf);
            }
        }
    }
    let mut root = Map::new();
    let mut data = Vec::new();
    for (p, b) in files {
        let parts: Vec<&str> = p.split('/').collect();
        insert(&mut root, &parts, json!({"size": b.len(), "offset": data.len().to_string()}));
        data.extend_from_slice(b);
    }
    let json = serde_json::to_vec(&json!({"files": root})).unwrap();
    let pad = (4 - json.len() % 4) % 4;
    let payload = json.len() + 4 + pad;
    let mut out = Vec::new();
    out.extend_from_slice(&4u32.to_le_bytes());
    out.extend_from_slice(&((payload + 4) as u32).to_le_bytes());
    out.extend_from_slice(&(payload as u32).to_le_bytes());
    out.extend_from_slice(&(json.len() as u32).to_le_bytes());
    out.extend_from_slice(&json);
    out.extend(std::iter::repeat_n(0u8, pad));
    out.extend_from_slice(&data);
    out
}

/// The Notes app packed as `app.asar` bytes.
pub fn notes_app_asar() -> Vec<u8> {
    let files = notes_app_files();
    let refs: Vec<(&str, &[u8])> = files.iter().map(|(p, c)| (*p, c.as_bytes())).collect();
    asar(&refs)
}

fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for &b in data {
        crc ^= u32::from(b);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb8_8320 & (crc & 1).wrapping_neg());
        }
    }
    !crc
}

/// A stored (uncompressed) ZIP from (name, bytes). Names are written as given, so tests can
/// build hostile archives (`../evil`, absolute paths).
pub fn zip_stored(files: &[(&str, &[u8])]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut cd = Vec::new();
    for (name, body) in files {
        let off = out.len() as u32;
        let crc = crc32(body);
        let len = body.len() as u32;
        out.extend_from_slice(b"PK\x03\x04\x14\0\0\0\0\0\0\0\0\0");
        out.extend_from_slice(&crc.to_le_bytes());
        out.extend_from_slice(&len.to_le_bytes());
        out.extend_from_slice(&len.to_le_bytes());
        out.extend_from_slice(&(name.len() as u16).to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes());
        out.extend_from_slice(name.as_bytes());
        out.extend_from_slice(body);
        cd.extend_from_slice(b"PK\x01\x02\x14\0\x14\0\0\0\0\0\0\0\0\0");
        cd.extend_from_slice(&crc.to_le_bytes());
        cd.extend_from_slice(&len.to_le_bytes());
        cd.extend_from_slice(&len.to_le_bytes());
        cd.extend_from_slice(&(name.len() as u16).to_le_bytes());
        cd.extend_from_slice(&[0; 12]);
        cd.extend_from_slice(&off.to_le_bytes());
        cd.extend_from_slice(name.as_bytes());
    }
    let cd_off = out.len() as u32;
    out.extend_from_slice(&cd);
    out.extend_from_slice(b"PK\x05\x06\0\0\0\0");
    out.extend_from_slice(&(files.len() as u16).to_le_bytes());
    out.extend_from_slice(&(files.len() as u16).to_le_bytes());
    out.extend_from_slice(&(cd.len() as u32).to_le_bytes());
    out.extend_from_slice(&cd_off.to_le_bytes());
    out.extend_from_slice(&0u16.to_le_bytes());
    out
}

/// A small webpack 5 style bundle with three modules (`./src/index.js` requires the other two).
pub const WEBPACK_BUNDLE: &str = r#"(()=>{var __webpack_modules__={"./src/api.js":(module,exports,__webpack_require__)=>{const base="https://api.example.test";module.exports={list:()=>fetch(base+"/items")}},"./src/util.js":(module,exports)=>{exports.sum=(a,b)=>a+b},"./src/index.js":(module,exports,__webpack_require__)=>{const api=__webpack_require__("./src/api.js");const u=__webpack_require__("./src/util.js");console.log(u.sum(1,2),!0,void 0);api.list()}};var __webpack_module_cache__={};function __webpack_require__(id){var c=__webpack_module_cache__[id];if(c!==undefined)return c.exports;var m=__webpack_module_cache__[id]={exports:{}};__webpack_modules__[id](m,m.exports,__webpack_require__);return m.exports}__webpack_require__("./src/index.js")})();
//# sourceMappingURL=main.js.map
"#;

/// A minified webpack chunk file pushing two numbered modules.
pub const WEBPACK_CHUNK: &str = r#"(self.webpackChunknotes=self.webpackChunknotes||[]).push([[179],{512:function(e,t,n){"use strict";var r=n(87);e.exports=function(){return r.a+1}},87:function(e,t){t.a=41}}]);"#;

/// An esbuild bundle with two CommonJS modules.
pub const ESBUILD_BUNDLE: &str = r#"var __getOwnPropNames=Object.getOwnPropertyNames;var __commonJS=(cb,mod)=>function __require(){return mod||(0,cb[__getOwnPropNames(cb)[0]])((mod={exports:{}}).exports,mod),mod.exports};
var require_util=__commonJS({"src/util.js"(exports,module){module.exports={twice:x=>x*2}}});
var require_main=__commonJS({"src/main.js"(exports,module){var u=require_util();console.log(u.twice(21))}});
require_main();
"#;
