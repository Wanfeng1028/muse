//! Game assets from fal.ai over plain HTTPS: pictures (textures, skies, concept art)
//! and game-ready 3D models with Tripo P1 (a picture in, a low-poly GLB model out, its face count
//! capped). One key (`Authorization: Key …`), paid per generation; every call reports what it cost.
//! Which models and what they cost come from the asset table (`assets.toml`).

use super::{AssetProvider, AssetRequest, Generated, Shape, SizeBy};
use craft_anything_evidence::{ErrorCode, ToolError};
use serde_json::{Value, json};
use std::io::Read;
use std::time::Duration;

/// The provider id the asset table names.
pub const ID: &str = "fal";
const BASE: &str = "https://fal.run";
/// Largest download we keep (a textured GLB is a few MB).
const MAX_BYTES: u64 = 200 << 20;

/// How fal is told a picture's shape: the field and its value for the model.
fn fal_size(by: SizeBy, shape: Shape) -> (&'static str, &'static str) {
    match (by, shape) {
        (SizeBy::ImageSize, Shape::Square) => ("image_size", "square_hd"),
        (SizeBy::ImageSize, Shape::Wide) => ("image_size", "landscape_16_9"),
        (SizeBy::ImageSize, Shape::Tall) => ("image_size", "portrait_16_9"),
        (SizeBy::AspectRatio, Shape::Square) => ("aspect_ratio", "1:1"),
        (SizeBy::AspectRatio, Shape::Wide) => ("aspect_ratio", "16:9"),
        (SizeBy::AspectRatio, Shape::Tall) => ("aspect_ratio", "9:16"),
    }
}

/// fal.ai, as an [`AssetProvider`].
pub struct Fal {
    base: String,
}

impl Default for Fal {
    fn default() -> Fal {
        Fal { base: BASE.to_string() }
    }
}

impl AssetProvider for Fal {
    fn id(&self) -> &'static str {
        ID
    }

    fn name(&self) -> &'static str {
        "fal.ai"
    }

    fn keys_page(&self) -> Option<&'static str> {
        Some("https://fal.ai/dashboard/keys")
    }

    fn key_env(&self) -> Option<&'static str> {
        Some("FAL_KEY")
    }

    fn generate(&self, key: &str, req: &AssetRequest) -> Result<Generated, ToolError> {
        let key = key.trim();
        match *req {
            AssetRequest::Image { model, prompt, shape } => {
                let (field, size) = fal_size(model.size_by, shape);
                let body = json!({"prompt": prompt, field: size, "num_images": 1, "output_format": "png"});
                let v = self.post(key, &model.endpoint, &body)?;
                if v.pointer("/has_nsfw_concepts/0").and_then(Value::as_bool) == Some(true) {
                    return Err(
                        ToolError::new(ErrorCode::ProgramFailed, "fal.ai's safety check blocked that picture.").with_remediation("Describe it differently.")
                    );
                }
                let url = image_url(&v).ok_or_else(|| unexpected("picture", &v))?;
                Ok(Generated { bytes: download(&url)?, url, cost_usd: req.listed_cost() })
            }
            AssetRequest::Model3d { model, image_url, textured, faces } => {
                let range = model.faces();
                let faces = faces.clamp(*range.start(), *range.end());
                let v = self.post(key, &model.endpoint, &json!({"image_url": image_url, "texture": textured, "face_limit": faces}))?;
                let url = model_url(&v).ok_or_else(|| unexpected("3D model", &v))?;
                Ok(Generated { bytes: download(&url)?, url, cost_usd: req.listed_cost() })
            }
        }
    }
}

impl Fal {
    fn post(&self, key: &str, model: &str, body: &Value) -> Result<Value, ToolError> {
        let url = format!("{}/{model}", self.base);
        // A 3D model takes a minute or two; fal answers once it's done.
        let resp = agent(Duration::from_secs(10 * 60))
            .post(&url)
            .header("Authorization", &format!("Key {key}"))
            .header("Content-Type", "application/json")
            .send(body.to_string())
            .map_err(|e| {
                ToolError::new(ErrorCode::EngineMissing, format!("Couldn't reach fal.ai: {e}"))
                    .with_remediation("Check your internet connection and try again.")
            })?;
        let status = resp.status().as_u16();
        let text = resp.into_body().read_to_string().unwrap_or_default();
        match status {
            200..=299 => serde_json::from_str(&text).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("fal.ai sent an unreadable answer: {e}"))),
            401 | 403 => Err(ToolError::new(ErrorCode::BadSettings, "fal.ai didn't accept the key.")
                .with_remediation("Check the fal.ai key in Settings → AI → Game assets.")),
            402 => Err(ToolError::new(ErrorCode::OverLimit, "The fal.ai account is out of credit.").with_remediation("Add credit at fal.ai, then try again.")),
            _ => Err(ToolError::new(ErrorCode::EngineMissing, format!("fal.ai answered {status}: {}", text.chars().take(300).collect::<String>()))),
        }
    }
}

fn agent(timeout: Duration) -> ureq::Agent {
    ureq::Agent::config_builder()
        .http_status_as_error(false)
        .user_agent("CraftAnything")
        .timeout_connect(Some(Duration::from_secs(20)))
        .timeout_recv_response(Some(timeout))
        .timeout_recv_body(Some(Duration::from_secs(10 * 60)))
        .build()
        .new_agent()
}

/// Fetch a generated file (fal answers with its address, or a `data:` URI in sync mode).
fn download(url: &str) -> Result<Vec<u8>, ToolError> {
    if let Some(data) = url.strip_prefix("data:") {
        let b64 =
            data.split_once(";base64,").map(|(_, b)| b).ok_or_else(|| ToolError::new(ErrorCode::GarbledOutput, "fal.ai sent a file in an unknown form."))?;
        return base64_decode(b64);
    }
    let resp =
        agent(Duration::from_secs(120)).get(url).call().map_err(|e| ToolError::new(ErrorCode::EngineMissing, format!("Couldn't download the file: {e}")))?;
    if !resp.status().is_success() {
        return Err(ToolError::new(ErrorCode::EngineMissing, format!("Downloading the file failed ({}).", resp.status().as_u16())));
    }
    let mut bytes = Vec::new();
    resp.into_body()
        .into_reader()
        .take(MAX_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| ToolError::new(ErrorCode::EngineMissing, format!("The download broke off: {e}")))?;
    if bytes.len() as u64 > MAX_BYTES {
        return Err(ToolError::new(ErrorCode::OverLimit, "The generated file is too large."));
    }
    Ok(bytes)
}

fn image_url(v: &Value) -> Option<String> {
    v.pointer("/images/0/url").and_then(Value::as_str).map(str::to_string)
}

/// The GLB: Tripo lists it under `model_urls`; its main `model_mesh` can be an FBX instead.
fn model_url(v: &Value) -> Option<String> {
    let glb = v.pointer("/model_urls/glb/url").and_then(Value::as_str);
    let mesh = v.get("model_mesh").filter(|m| {
        let named = |k: &str| m.get(k).and_then(Value::as_str).unwrap_or_default().to_ascii_lowercase();
        named("file_name").ends_with(".glb") || named("content_type") == "model/gltf-binary"
    });
    glb.or_else(|| mesh.and_then(|m| m.get("url")?.as_str())).filter(|u| !u.is_empty()).map(str::to_string)
}

fn unexpected(what: &str, v: &Value) -> ToolError {
    ToolError::new(ErrorCode::GarbledOutput, format!("fal.ai didn't return a {what}."))
        .with_details(json!({"answer": v.to_string().chars().take(500).collect::<String>()}))
}

/// A `data:` URI for a local picture (fal accepts these for some models; links always work).
pub fn data_uri(bytes: &[u8], media_type: &str) -> String {
    format!("data:{media_type};base64,{}", base64_encode(bytes))
}

fn base64_encode(bytes: &[u8]) -> String {
    use base64::Engine as _;
    base64::engine::general_purpose::STANDARD.encode(bytes)
}

fn base64_decode(s: &str) -> Result<Vec<u8>, ToolError> {
    use base64::Engine as _;
    base64::engine::general_purpose::STANDARD.decode(s.trim()).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("invalid base64: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::assets::Catalogue;
    use craft_anything_platform::sync::Mutex;
    use std::io::{BufRead, BufReader, Write};
    use std::net::TcpListener;
    use std::sync::Arc;

    /// A tiny local server that answers each request in turn and records what it was sent.
    fn serve(answers: Vec<(u16, String)>) -> (String, Arc<Mutex<Vec<String>>>) {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", l.local_addr().unwrap());
        let seen = Arc::new(Mutex::new(Vec::new()));
        let s2 = seen.clone();
        std::thread::spawn(move || {
            for (status, body) in answers {
                let (mut stream, _) = l.accept().unwrap();
                let mut r = BufReader::new(stream.try_clone().unwrap());
                let mut head = String::new();
                let mut len = 0usize;
                loop {
                    let mut line = String::new();
                    r.read_line(&mut line).unwrap();
                    if let Some(v) = line.to_ascii_lowercase().strip_prefix("content-length:") {
                        len = v.trim().parse().unwrap();
                    }
                    head.push_str(&line);
                    if line == "\r\n" {
                        break;
                    }
                }
                let mut req_body = vec![0; len];
                r.read_exact(&mut req_body).unwrap();
                s2.lock().unwrap().push(format!("{head}{}", String::from_utf8_lossy(&req_body)));
                write!(stream, "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len())
                    .unwrap();
            }
        });
        (base, seen)
    }

    /// A picture with FLUX.1 [dev].
    fn image(fal: &Fal, key: &str, prompt: &str, shape: Shape) -> Result<Generated, ToolError> {
        let c = Catalogue::built_in();
        fal.generate(key, &AssetRequest::Image { model: c.image_model(Some("flux-dev"))?, prompt, shape })
    }

    fn model_3d(fal: &Fal, key: &str, image_url: &str, textured: bool, faces: u32) -> Result<Generated, ToolError> {
        let c = Catalogue::fallback();
        fal.generate(key, &AssetRequest::Model3d { model: c.model_3d(None)?, image_url, textured, faces })
    }

    #[test]
    fn a_picture_then_a_model_from_its_address() {
        let png = base64_encode(b"\x89PNG fake");
        let glb = base64_encode(b"glTF fake");
        let (base, seen) = serve(vec![
            (200, json!({"images": [{"url": format!("data:image/png;base64,{png}"), "content_type": "image/png"}], "has_nsfw_concepts": [false]}).to_string()),
            (200, json!({"model_mesh": {"url": "https://x/m.fbx", "file_name": "m.fbx"}, "model_urls": {"glb": {"url": format!("data:model/gltf-binary;base64,{glb}")}}}).to_string()),
        ]);
        let fal = Fal { base };
        let pic = image(&fal, " k-123 ", "a wooden crate, game asset", Shape::Square).unwrap();
        assert_eq!(pic.bytes, b"\x89PNG fake");
        assert!((pic.cost_usd - 0.0262144).abs() < 1e-9, "1024×1024 at $0.025 per megapixel");
        let model = model_3d(&fal, "k-123", "https://v3.fal.media/files/crate.png", true, 2000).unwrap();
        assert_eq!(model.bytes, b"glTF fake", "the GLB, not the FBX");
        assert!((model.cost_usd - 0.50).abs() < 1e-9, "a textured Tripo P1 model");
        let seen = seen.lock().unwrap();
        assert!(seen[0].starts_with("POST /fal-ai/flux/dev "), "{}", seen[0]);
        // Header names aren't case-sensitive; the key goes in fal's "Key …" form.
        assert!(seen[0].to_ascii_lowercase().contains("authorization: key k-123"), "{}", seen[0]);
        assert!(seen[0].contains("\"image_size\":\"square_hd\"") && seen[0].contains("\"output_format\":\"png\""));
        assert!(
            seen[1].starts_with("POST /tripo3d/p1/image-to-3d ") && seen[1].contains("\"texture\":true") && seen[1].contains("\"face_limit\":2000"),
            "{}",
            seen[1]
        );
        assert!(seen[1].contains("\"image_url\":\"https://v3.fal.media/files/crate.png\""));
    }

    #[test]
    fn nano_banana_pro_is_asked_for_an_aspect_ratio() {
        let png = base64_encode(b"PNG fake");
        let (base, seen) = serve(vec![(200, json!({"images": [{"url": format!("data:image/png;base64,{png}")}], "description": ""}).to_string())]);
        let c = Catalogue::built_in();
        let req = AssetRequest::Image { model: c.image_model(None).unwrap(), prompt: "a night sky", shape: Shape::Wide };
        let pic = Fal { base }.generate("k", &req).unwrap();
        assert_eq!((pic.bytes.as_slice(), pic.cost_usd), (&b"PNG fake"[..], 0.15));
        let seen = seen.lock().unwrap();
        assert!(seen[0].starts_with("POST /fal-ai/nano-banana-pro "), "{}", seen[0]);
        assert!(seen[0].contains("\"aspect_ratio\":\"16:9\"") && !seen[0].contains("image_size"), "{}", seen[0]);
    }

    #[test]
    fn only_a_glb_is_taken_as_the_model() {
        let fbx_only = json!({"model_mesh": {"url": "https://x/m.fbx", "file_name": "m.fbx"}, "model_urls": {}});
        assert_eq!(model_url(&fbx_only), None);
        let glb_mesh = json!({"model_mesh": {"url": "https://x/m.glb", "file_name": "m.glb"}});
        assert_eq!(model_url(&glb_mesh).as_deref(), Some("https://x/m.glb"));
    }

    #[test]
    fn refusals_say_what_to_do() {
        let (base, _) = serve(vec![
            (401, "{}".into()),
            (402, "{}".into()),
            (200, json!({"images": [{"url": "data:image/png;base64,AA=="}], "has_nsfw_concepts": [true]}).to_string()),
        ]);
        let fal = Fal { base };
        assert_eq!(image(&fal, "bad", "x", Shape::Wide).unwrap_err().code, ErrorCode::BadSettings);
        assert_eq!(image(&fal, "bad", "x", Shape::Wide).unwrap_err().code, ErrorCode::OverLimit);
        assert!(image(&fal, "bad", "x", Shape::Wide).unwrap_err().message.contains("safety check"));
    }

    #[test]
    fn shapes_and_data_uris() {
        assert_eq!(Shape::parse("wide"), Some(Shape::Wide));
        assert!(Shape::parse("huge").is_none());
        let uri = data_uri(b"hi", "image/png");
        assert_eq!(uri, "data:image/png;base64,aGk=");
        assert_eq!(download(&uri).unwrap(), b"hi");
    }
}
