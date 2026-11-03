//! The browser shell: the eframe web runner and the file picker.

use crate::viewer::{Inbox, Viewer};
use wasm_bindgen::JsCast as _;

const CANVAS_ID: &str = "craft_anything_canvas";
const LOADING_ID: &str = "craft_anything_loading";

pub fn start() {
    eframe::WebLogger::init(log::LevelFilter::Info).ok();
    wasm_bindgen_futures::spawn_local(async {
        let Some(document) = web_sys::window().and_then(|w| w.document()) else {
            log::error!("no document");
            return;
        };
        let Some(canvas) = document.get_element_by_id(CANVAS_ID).and_then(|e| e.dyn_into::<web_sys::HtmlCanvasElement>().ok()) else {
            log::error!("missing <canvas id=\"{CANVAS_ID}\">");
            return;
        };
        let mut options = eframe::WebOptions::default();
        // `?webgl`: force the WebGL2 backend (troubleshooting, and headless browsers whose WebGPU
        // adapter request returns nothing).
        if query().contains("webgl")
            && let eframe::egui_wgpu::WgpuSetup::CreateNew(create) = &mut options.wgpu_options.wgpu_setup
        {
            create.instance_descriptor.backends = eframe::wgpu::Backends::GL;
        }
        let result = eframe::WebRunner::new()
            .start(
                canvas,
                options,
                Box::new(|cc| {
                    if let Some(rs) = &cc.wgpu_render_state {
                        log::info!("craft-anything-web: wgpu backend {:?}", rs.adapter.get_info().backend);
                    }
                    Viewer::setup(&cc.egui_ctx);
                    let inbox = Inbox::default();
                    let open = open_picker(inbox.clone(), cc.egui_ctx.clone());
                    let read_drop = read_dropped(inbox.clone(), cc.egui_ctx.clone());
                    Ok(Box::new(Shell { viewer: Viewer::new(inbox, open, read_drop) }))
                }),
            )
            .await;
        if let Some(el) = document.get_element_by_id(LOADING_ID) {
            match result {
                Ok(()) => el.remove(),
                Err(e) => el.set_inner_html(&format!("<p>Craft Anything failed to start: {e:?}</p><p>A browser with WebGPU or WebGL2 is required.</p>")),
            }
        }
    });
}

/// The Open button: the browser's file picker, read into memory, then handed to the next frame.
fn open_picker(inbox: Inbox, ctx: egui::Context) -> Box<dyn Fn()> {
    Box::new(move || {
        let inbox = inbox.clone();
        let ctx = ctx.clone();
        wasm_bindgen_futures::spawn_local(async move {
            let Some(file) = rfd::AsyncFileDialog::new().pick_file().await else { return };
            let bytes = file.read().await;
            deliver(&inbox, &ctx, Ok((file.file_name(), bytes)));
        });
    })
}

/// A dropped file: browsers only read file contents asynchronously.
fn read_dropped(inbox: Inbox, ctx: egui::Context) -> Box<dyn Fn(egui::DroppedFileHandle)> {
    Box::new(move |file| {
        let inbox = inbox.clone();
        let ctx = ctx.clone();
        wasm_bindgen_futures::spawn_local(async move {
            let name = file.path().file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "the file".to_string());
            let got = file.bytes_async().await.map(|b| (name.clone(), b)).map_err(|e| format!("The browser couldn't read {name}: {e}"));
            deliver(&inbox, &ctx, got);
        });
    })
}

fn deliver(inbox: &Inbox, ctx: &egui::Context, got: Result<(String, Vec<u8>), String>) {
    if let Ok(mut slot) = inbox.lock() {
        *slot = Some(got);
    }
    ctx.request_repaint();
}

fn query() -> String {
    web_sys::window().and_then(|w| w.location().search().ok()).unwrap_or_default()
}

struct Shell {
    viewer: Viewer,
}

impl eframe::App for Shell {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        self.viewer.ui(ui);
    }
}
