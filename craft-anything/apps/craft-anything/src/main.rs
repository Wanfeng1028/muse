//! The Craft Anything desktop app.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use craft_anything_ai::AiHub;
use craft_anything_engine::{Engine, Session, Settings};
use craft_anything_ui_egui::CraftApp;
use std::path::PathBuf;
use std::sync::Arc;

fn main() -> eframe::Result {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--version" || a == "-V") {
        println!("craft-anything {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    // A path on the command line (or from "Open with…") opens as the first target.
    let open: Option<PathBuf> = args.iter().find(|a| !a.starts_with('-')).map(PathBuf::from);
    // The window app has no console: what goes wrong before (or instead of) a window is kept in
    // desktop.log beside the settings, so a start that shows nothing leaves a trace.
    log_to_file();
    log::info!("starting {} (pid {})", env!("CARGO_PKG_VERSION"), std::process::id());

    let settings = Settings::load();
    let mut session = Session::new(settings);
    let plugins = craft_anything_engine::plugins::install(&mut session);
    let mut layer_tools = craft_anything_ai::tools();
    layer_tools.extend(craft_anything_setup::tools::specs());
    let engine = Engine::shared_with(session, layer_tools, plugins);
    let hub = Arc::new(AiHub::new(engine.clone()));
    log::info!("engine and AI ready; opening the window");

    let viewport = eframe::egui::ViewportBuilder::default()
        .with_title("Craft Anything")
        .with_app_id("ai.storyteller.craft-anything")
        .with_inner_size([1360.0, 860.0])
        .with_min_inner_size([760.0, 520.0])
        // Our own title bar draws the window controls, moves and resizes the window.
        .with_decorations(false)
        .with_resizable(true)
        .with_drag_and_drop(true);
    // On macOS a window icon replaces the Dock icon, and the bundle's own icon is the one padded to
    // Apple's icon grid (the full tile looked bigger than other apps', #102). An empty icon keeps
    // the bundle's; no icon at all would bring eframe's own.
    let icon = if cfg!(target_os = "macos") { None } else { eframe::icon_data::from_png_bytes(craft_anything_ui_egui::APP_ICON_PNG).ok() };
    let viewport = viewport.with_icon(Arc::new(icon.unwrap_or_default()));
    #[cfg_attr(not(windows), expect(unused_mut, reason = "only Windows picks its own graphics adapter"))]
    let mut options = eframe::NativeOptions { viewport, ..Default::default() };
    #[cfg(windows)]
    if let eframe::egui_wgpu::WgpuSetup::CreateNew(setup) = &mut options.wgpu_options.wgpu_setup {
        // Starting GL loads the system's OpenGL driver before any adapter is picked, and some
        // Intel drivers crash in it (ig9icd64.dll, #196), so the window never opens. Similarly,
        // starting Vulkan loads Intel's Vulkan driver (igvk64.dll, #394) and crashes before any
        // window. DX12 (with WARP) covers all Windows systems; `WGPU_BACKEND` still asks for others.
        setup.instance_descriptor.backends = windows_backends(eframe::wgpu::Backends::from_env());
        setup.native_adapter_selector = Some(Arc::new(pick_adapter));
    }
    let run = eframe::run_native(
        "Craft Anything",
        options,
        Box::new(move |cc| {
            log::info!("window open");
            CraftApp::setup_context(&cc.egui_ctx);
            let mut app = CraftApp::new(engine, hub);
            app.load_prefs(cc.storage);
            if let Some(p) = open {
                app.open_path(p);
            }
            Ok(Box::new(app))
        }),
    );
    match &run {
        Ok(()) => log::info!("closed"),
        Err(e) => {
            log::error!("the window couldn't start: {e}");
            // Without a window the app would just vanish (#166): say why, and where the log is.
            let log = craft_anything_engine::settings::config_dir().join("desktop.log");
            let _ = rfd::MessageDialog::new()
                .set_level(rfd::MessageLevel::Error)
                .set_title("Craft Anything couldn't open its window")
                .set_description(format!(
                    "{e}\n\nUpdating your graphics driver often fixes this. What happened is written to {}; please attach it if you report this.",
                    log.display()
                ))
                .set_buttons(rfd::MessageButtons::Ok)
                .show();
        }
    }
    run
}

/// Windows: the adapter that draws the window. GL is the last resort, Windows' own software
/// renderer (WARP) included: in a VMware VM, GL is the way to the virtual GPU and drew a black
/// window (#27). The fastest device wins, and between same-class devices DX12 comes before Vulkan
/// (#33). `WGPU_BACKEND` still narrows the choice.
#[cfg(windows)]
fn pick_adapter(adapters: &[eframe::wgpu::Adapter], surface: Option<&eframe::wgpu::Surface<'_>>) -> Result<eframe::wgpu::Adapter, String> {
    let picked = adapters.iter().filter(|a| surface.is_none_or(|s| a.is_surface_supported(s))).min_by_key(|a| {
        let info = a.get_info();
        adapter_rank(info.backend, info.device_type)
    });
    match picked {
        Some(a) => {
            log::info!("drawing with {:?}", a.get_info());
            Ok(a.clone())
        }
        None => Err(format!("None of the {} graphics adapters found can draw this window.", adapters.len())),
    }
}

/// Windows: the graphics backends to start. `WGPU_BACKEND` decides when set; otherwise DX12
/// only (#196, #394). Vulkan and GL load third-party driver DLLs (igvk64.dll, ig9icd64.dll) before
/// an adapter is chosen, which crash on some Intel systems. DX12 (with WARP) covers all Windows
/// installations; `WGPU_BACKEND=vulkan` or `gl` still asks for them explicitly.
#[cfg(windows)]
fn windows_backends(from_env: Option<eframe::wgpu::Backends>) -> eframe::wgpu::Backends {
    from_env.unwrap_or(eframe::wgpu::Backends::DX12)
}

/// Lower is better: GL last, fastest device first, DX12 before Vulkan only between same-class devices
/// (#33).
#[cfg(windows)]
fn adapter_rank(backend: eframe::wgpu::Backend, device: eframe::wgpu::DeviceType) -> (bool, u8, u8) {
    use eframe::wgpu::DeviceType;
    let is_gl = backend == eframe::wgpu::Backend::Gl;
    let speed = match device {
        DeviceType::DiscreteGpu => 0,
        DeviceType::IntegratedGpu => 1,
        DeviceType::VirtualGpu => 2,
        DeviceType::Cpu => 3,
        DeviceType::Other => 4,
    };
    let dx12_before_vulkan = match backend {
        eframe::wgpu::Backend::Dx12 => 0,
        eframe::wgpu::Backend::Vulkan => 1,
        _ => 2,
    };
    (is_gl, speed, dx12_before_vulkan)
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use eframe::wgpu::{Backend as B, DeviceType as T};

    /// #27: a VMware VM offers its virtual GPU over GL and WARP over DX12; GL drew a black window.
    /// #33: a start that shows nothing is looked at through `desktop.log`; between same-class
    /// devices DX12 comes before Vulkan, and GL stays the last resort.
    #[test]
    fn dx12_comes_before_vulkan_and_gl_is_the_last_resort() {
        let best = |c: &[(B, T)]| c.iter().enumerate().min_by_key(|(_, (b, t))| adapter_rank(*b, *t)).map(|(i, _)| i);
        assert_eq!(best(&[(B::Gl, T::Other), (B::Dx12, T::Cpu)]), Some(1), "VMware: WARP, not GL");
        assert_eq!(best(&[(B::Gl, T::IntegratedGpu), (B::Dx12, T::Cpu)]), Some(1));
        assert_eq!(best(&[(B::Vulkan, T::DiscreteGpu), (B::Dx12, T::IntegratedGpu)]), Some(0), "fastest GPU first");
        assert_eq!(best(&[(B::Dx12, T::IntegratedGpu), (B::Vulkan, T::IntegratedGpu)]), Some(0), "DX12 before Vulkan between same-class devices");
        assert_eq!(best(&[(B::Dx12, T::Cpu), (B::Vulkan, T::DiscreteGpu)]), Some(1), "WARP does not beat a real Vulkan device");
        assert_eq!(best(&[(B::Dx12, T::IntegratedGpu), (B::Vulkan, T::DiscreteGpu), (B::Dx12, T::Cpu)]), Some(1), "fastest GPU first");
        assert_eq!(best(&[(B::Gl, T::Other)]), Some(0), "GL when it's all there is");
    }

    /// #196: an Intel OpenGL driver crashed the app as wgpu started GL, before any window.
    /// #394: an Intel Vulkan driver (igvk64.dll) crashed the app as wgpu started Vulkan.
    #[test]
    fn gl_and_vulkan_are_only_started_when_asked_for() {
        use eframe::wgpu::Backends;
        let started = windows_backends(None);
        assert_eq!(started, Backends::DX12);
        assert_eq!(windows_backends(Some(Backends::GL)), Backends::GL, "WGPU_BACKEND=gl still works");
        assert_eq!(windows_backends(Some(Backends::VULKAN)), Backends::VULKAN, "WGPU_BACKEND=vulkan still works");
    }
}

/// Kept small: started afresh once it passes this size.
const LOG_MAX: u64 = 512 * 1024;

/// Warnings and errors from everything, plus our own progress, appended to `desktop.log`; and
/// panics, which would otherwise vanish with the window.
fn log_to_file() {
    use std::io::Write as _;
    struct FileLog(craft_anything_platform::sync::Mutex<Option<std::fs::File>>);
    impl log::Log for FileLog {
        fn enabled(&self, m: &log::Metadata<'_>) -> bool {
            m.level() <= log::Level::Warn || (m.level() <= log::Level::Info && m.target().starts_with("craft_anything"))
        }
        fn log(&self, r: &log::Record<'_>) {
            if !self.enabled(r.metadata()) {
                return;
            }
            let at = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
            if let Ok(mut f) = self.0.lock()
                && let Some(f) = f.as_mut()
            {
                let _ = writeln!(f, "{at} [{}] {}: {}", r.level(), r.target(), r.args());
            }
        }
        fn flush(&self) {}
    }
    let dir = craft_anything_engine::settings::config_dir();
    let path = dir.join("desktop.log");
    let _ = std::fs::create_dir_all(&dir);
    let fresh = std::fs::metadata(&path).is_ok_and(|m| m.len() > LOG_MAX);
    let file = std::fs::OpenOptions::new().create(true).append(!fresh).write(true).truncate(fresh).open(&path).ok();
    if log::set_logger(Box::leak(Box::new(FileLog(craft_anything_platform::sync::Mutex::new(file))))).is_ok() {
        log::set_max_level(log::LevelFilter::Info);
    }
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        log::error!("panic: {info}");
        default_hook(info);
    }));
    craft_anything_platform::sync::start_watchdog(craft_anything_engine::settings::config_dir().join("logs"));
}
