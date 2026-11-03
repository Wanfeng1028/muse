//! The builder's prompts: the first brief, per-stack and per-kind steps, follow-ups and
//! refinements.

use super::*;
use craft_anything_engines::assets::{Catalogue, Shape, about_usd};

pub(super) const RULES: &str = "\
Rules:
- Their request comes first. When it says how to build (a language, framework, engine, library or platform), build with exactly that, even where these instructions name something else: the stack given here is only the default for what the request leaves open. Don't switch away from what they asked for to get past a failing build or check; fix the build instead.
- Change files only inside app/. Everything else in the workspace is read-only evidence.
- Rebuild the layout, styling and behaviour yourself from the evidence. Don't copy logos, photos, brand names or long passages of text unless the person confirms they own the original or have permission (ask once with core_person_ask if it matters); otherwise use neutral placeholders: simple shapes or gradients for images, short sample copy for text.
- Use the core_person_ask tool (craft-anything MCP server) only for choices that really change the result. Give 2-4 short choices. Never ask about technical details you can decide yourself.
- Build what the person asked for. If part of it won't fit this version (for example online co-op, a whole game mode or another platform), ask with core_person_ask before leaving it out, with the smaller version as one of the choices; never drop it silently.
- Never start dev servers, watchers or anything that doesn't exit (npm run dev, npm start, vite, cargo watch). Craft Anything serves and checks the build itself.
- Finish with 3-5 plain sentences for the person: what you built, what differs from the original or is still unknown, and one idea for what to ask next. No code and no file paths in that summary.";

/// How the builder works, for every kind: it leads, the tools answer with evidence, it tests its
/// build against the original itself, and nothing unknown is passed off as known.
/// How to work. The follow-up questions the tools may answer depend on the mode: in Clean room
/// nothing inside the original is looked at.
pub(super) fn steps(deep: bool) -> String {
    let follow_up = if deep {
        "capture another width or an opened state into a new folder under checks/, inspect a page or a bundle, look up a program's strings or functions by their exact names, read a game's settings or files."
    } else {
        "capture another width or an opened state of a website into a new folder under checks/, or ask the person with core_person_ask. Clean room: nothing inside the original is looked at, so never open, read, list, fetch, run or decompile its files, its folder, its pages' code or its program, with any tool."
    };
    format!(
        "How to work: you lead the investigation and the craft-anything tools answer your questions with evidence.
1) Study the evidence, overview first (the README and summaries before the details). Where it leaves a gap that matters to the result, ask a focused follow-up with the craft-anything tools instead of guessing: {follow_up} Don't repeat a call that already answered. Record each question the evidence doesn't answer yet with core_unknown_add (the question, what would settle it as probes, and how much it matters as severity), and when a later look answers it, close it with core_unknown_edit (status resolved, the resolution and the evidence ids that settle it); until then say in it what you did instead (an estimate, a placeholder or a question for the person). Missing evidence is never proof, so mark what you estimated.
2) Make a short checklist with TodoWrite: 3-7 steps in plain words the person can follow (no file names or jargon), each with a short activeForm such as \"Drawing the map\"; the person watches it live, so keep it updated as you go.
3) Build it in app/ and fix errors until the build succeeds.
4) Test it against the original with rebuild_check: it runs the same checks Craft Anything runs after your turn and lists what differs and what couldn't be compared. Fix those, build and check again until it says it would pass.
5) Before you reply, go through your checklist and core_unknowns_show once more: settle what one more look can settle, and say what's left in your summary."
    )
}

/// What the builder is told for the stack (from `stacks.toml`).
pub(super) fn stack_steps(stack: &str, editor: Option<&Path>) -> String {
    stacks::steps(stack, editor)
}

/// The stack's steps, then those of each library the request asks for that works with it
/// ("use nextjs and shadcn" adds shadcn/ui's).
fn stack_and_library_steps(request: &str, stack: &str, editor: Option<&Path>) -> String {
    let mut s = stack_steps(stack, editor);
    for l in stacks::libraries_for(request, stack) {
        s.push(' ');
        s.push_str(&l.steps);
    }
    s
}

/// The first message to the builder: the request, the evidence, the kind's goal and stack steps,
/// the shared rules, then the kind's own sections. `extra`: what the person also said.
/// Clean room: what the builder has of a website, all of it what a visitor sees.
const WEBSITE_FROM_OUTSIDE: &str = "capture/ holds what a visitor of the live site sees, recorded in Clean room: README.md (start here: its colours, fonts, spacing and the layout at each width), capture.json (design tokens with colours in hex, spacing and content widths, the layout measured at each width (`layouts`: page width, heading and text sizes, each section's padding, gap, content column and items per row), a layout outline with positions in CSS pixels, headings, links, form outlines, picture sizes and the visible text), screenshot-<width>.png for each width (desktop, tablet and phone; open them all with the Read tool and look closely), and noise-<width>.png where parts of the page change by themselves (white squares: carousels, videos, animations; they aren't compared, so match how they look, not the exact frame). Clean room: the page's HTML, CSS and scripts weren't read and must not be: don't open or fetch the original site or its files, and don't look at its code (the tools that would are off, and fetching it is refused). Work from these pictures and measurements.\n\n\
     Match it exactly, not roughly: take colours, fonts, text sizes, padding, gaps, corner radii and content widths from capture.json as exact values (make them the project's theme tokens rather than a library's defaults), use the same font families (or the closest free ones), change the layout where the screenshots at each width show it changing (sections stack, columns per row and the navigation switch), and never let the page scroll sideways on a phone. Craft Anything measures your build the same way at every width and tells you each difference.";

/// Clean room: what the builder has of an app or a game. Nothing inside it was read.
const PROGRAM_FROM_OUTSIDE: &str = "capture/README.md says what we could see from outside. Clean room: nothing inside the program, its files or its folder was read, and you must not open, list, read, run or decompile anything there either (the tools that look inside are off, and reading its files is refused). Build from the person's request and description, the pictures in reference/ and, when capture/ has one, the picture of it running; ask the person with core_person_ask about anything you can't see.";

pub(super) fn brief(kind: &dyn TargetKind, cx: &BriefCx, extra: Option<&str>) -> String {
    let ws = cx.ws;
    let m = &ws.manifest;
    let target = match &m.target {
        TargetRef::Website { url } => format!("the website {url}"),
        TargetRef::Local { path } => format!("the program at {}", path.display()),
        TargetRef::None => "nothing specific (build from the request)".into(),
    };
    let capture = match &m.target {
        TargetRef::Website { .. } if !cx.deep => WEBSITE_FROM_OUTSIDE,
        TargetRef::Local { .. } if !cx.deep => PROGRAM_FROM_OUTSIDE,
        TargetRef::Website { .. } => {
            "capture/ holds what we recorded from the live site: README.md (start here: its colours, fonts, spacing, breakpoints and the layout at each width), capture.json (design tokens with colours in hex, spacing and content widths, the widths its CSS switches layout at (`breakpoints`), the layout measured at each width (`layouts`: page width, heading and text sizes, each section's padding, gap, content column and items per row), a layout outline with positions in CSS pixels, headings, links, form shapes, asset lists with its font files, and the visible text), screenshot-<width>.png for each width (desktop, tablet and phone; open them all with the Read tool and look closely), noise-<width>.png where parts of the page change by themselves (white squares: carousels, videos, animations; they aren't compared, so match how they look, not the exact frame), and page.html (the rendered HTML).\n\n\
             Match it exactly, not roughly: take colours, fonts, text sizes, padding, gaps, corner radii and content widths from capture.json as exact values (make them the project's theme tokens rather than a library's defaults), load the same font families, change the layout at the same breakpoints so each width matches its screenshot and `layouts` entry (sections stack, columns per row and the navigation switch where the original's do), and never let the page scroll sideways on a phone. Craft Anything measures your build the same way at every width and tells you each difference.

             Deep mode: every craft-anything tool is yours, so learn how it works, not only how it looks, before you build. capture/how-it-works.md already has what its JavaScript is made of (modules, routes, the requests it makes, the libraries it uses) and ten seconds of what the start page did (requests, console, WebSocket messages). The original is open in Craft Anything's private browser (web_site_open opens another page of it); ask web_page_show (its structure, scripts, network requests and console), web_listeners_list on a control (what clicking it runs, and where that code is), web_coverage_measure while you use it (which code runs and which requests it makes) and web_walkthrough_record to click or type through a flow and record every step; web_scripts_save, js_app_map and js_sources_restore read its code as an app. Rebuild the behaviour you learn in your own code; never paste the original's code into app/."
        }
        TargetRef::Local { .. } => {
            "capture/README.md holds a first static look at the program (nothing was run) and, for a game, a list of its own files: maps, textures, models, sounds and settings. Read its settings and scripts for the real numbers (speeds, health, weapons, modes, controls) and open a few of its pictures with the Read tool to learn the style; never change anything in that folder. Deep mode: every craft-anything tool is yours, so learn how the parts the person cares about work before you build: core_target_open and core_target_triage first, then native_functions_list, native_strings_find and native_function_pseudocode for a program's code, managed_assembly_show and managed_members_list for .NET, java_* and android_* for Java and Android apps, js_app_map, js_sources_restore and js_electron_* for an Electron app, and game_archives_list and the other game_* tools for a game's files."
        }
        TargetRef::None => "There is no target to study.",
    };
    let mut s = format!(
        "You are the builder inside Craft Anything, rebuilding software for a person who doesn't code.\n\n\
         Their request: \"{}\"\nTarget: {target}\nYour working folder is the project workspace ({}).\n\n{capture}\n\n\
         What to build: {}.\n\nHow to build it, unless their request says otherwise: {}\n\n{}\n\n{RULES}",
        m.request,
        ws.root.display(),
        kind.goal(),
        stack_and_library_steps(&m.request, &m.stack, cx.editor),
        steps(cx.deep),
    );
    for section in kind.brief_sections(cx) {
        s.push_str(&format!("\n\n{section}"));
    }
    if let Some(note) = pictures_note(ws, kind) {
        s.push_str(&format!("\n\n{note}"));
    }
    if let Some(note) = start_files_note(m) {
        s.push_str(&format!("\n\n{note}"));
    }
    if let Some(e) = extra.filter(|e| e.trim() != m.request.trim()) {
        s.push_str(&format!("\n\nThe person also said: \"{e}\""));
    }
    s
}

/// The person's own files, when the project started in a folder that had them: the app to edit
/// in place, or material to start from.
pub(super) fn start_files_note(m: &craft_anything_engine::workspace::Manifest) -> Option<String> {
    if m.start_files.is_empty() && !m.app_in_root {
        return None;
    }
    let names = m.start_files.join(", ");
    let own = craft_anything_engine::workspace::OWN_NAMES.join(", ");
    Some(if m.app_in_root {
        format!(
            "This project's app is the person's own folder, the project workspace itself, and it already has their files ({names}). Wherever these instructions say app/, use the workspace folder itself (./): work on their files in place, keep what works and change only what the request needs; never start over, delete or replace their work, and don't create an app/ folder. Craft Anything keeps its own records beside their files ({own}): leave those alone."
        )
    } else {
        format!(
            "The person started this project in a folder of their own, which already had these files: {names}. They're material to start from: read them first (code, notes, pictures, designs), build on what they show and bring into app/ whatever the app uses. Leave the originals where they are, unchanged."
        )
    })
}

/// Realistic assets with fal.ai: what each tool makes and costs (prices from the asset table,
/// for the picture model `image_model` names), the budget, where the engine loads them from, and
/// that every design is original.
pub(super) fn assets_note(ws: &Workspace, image_model: Option<&str>) -> String {
    let folder = match game::Builder::from_stack(&ws.manifest.stack) {
        Some(game::Builder::Unity) => "Unity loads them from Assets/, e.g. Assets/Generated/",
        Some(game::Builder::Godot) => "Godot loads them from the project, e.g. assets/generated/",
        Some(game::Builder::Unreal) => "save them under Content/Generated/ and import them with an editor Python script run through UnrealEditor-Cmd",
        _ => "e.g. assets/generated/",
    };
    let budget = ws.manifest.asset_budget_usd;
    let spent = ws.assets_spent();
    let table = Catalogue::built_in();
    // An unknown picture model is reported by the tool itself; the note quotes the default's price.
    let picture = table.image_model(image_model).or_else(|_| table.image_model(None)).map(|m| m.cost(Shape::Square));
    let (model_cost, picture_cost) = match (table.model_3d(None).map(|m| m.cost(true)), picture) {
        (Ok(model), Ok(picture)) => (format!(" ({} each)", about_usd(model + picture)), format!(" ({})", about_usd(picture))),
        _ => (String::new(), String::new()),
    };
    format!(
        "Realistic assets: you can make them with fal.ai. assets_model_generate makes a textured, game-ready low-poly 3D model (GLB) of one object from a description{model_cost}; set faces to the fewest that still look right (about 500-1500 for small props, 2000-5000 for weapons and vehicles, 6000-15000 for main characters) so the game stays fast; assets_image_generate makes a picture{picture_cost} for textures, skies, backgrounds and menu art. This project's asset budget is ${budget:.2} (${spent:.2} used), so spend it on what the player sees most (the main characters, weapons, vehicles and the level's key props) and use simple shapes for the rest. Save each one inside app/ where the engine loads it ({folder}). Every asset is an original design in the original's style: describe what it is, its shape, materials and colours, never a recognisable character, logo or brand artwork. List each generated file in app/CREDITS.md as made with fal.ai."
    )
}

/// Sent once when a Deep-mode build turn ended without decompiling anything.
pub(super) const DECOMPILE_FIRST: &str = "You haven't decompiled anything yet, and Deep mode requires it. Do it now: open the original's main program with core_target_open, find the functions behind what you built (native_strings_find for names, settings and messages, then follow the references), and read each with native_function_pseudocode, waiting for every result. Put the real values, formulas and rules into app/MECHANICS.md with their function addresses, change the build to use them, and build it again.";

/// Deep mode: decompiling the target is required, not optional, before anything is estimated.
/// `game`: point at a game's mechanics rather than the requested features.
pub(super) fn decompile_note(game: bool, ghidra: bool) -> String {
    let what = if game {
        "the code behind movement, aiming and firing, damage and health, and how enemies behave (native_strings_find for weapon names, settings or console variables, then follow the references to the functions)"
    } else {
        "the code behind the features the person asked for (native_strings_find for their words, messages and settings, then follow the references to the functions)"
    };
    let mut s = format!(
        "\n- Deep mode is on: decompile the program before you estimate anything. Open its main program with core_target_open, find {what}, and read each with native_function_pseudocode. Write the constants, formulas and rules you find into app/MECHANICS.md with their function addresses, and mark a value \"estimated\" only after you looked for it in the code. Then write your own code from that sheet: never paste decompiled code into app/."
    );
    s.push_str(if ghidra {
        " native_function_pseudocode reads the code with Ghidra, which has already analysed the program, so it answers in moments (the first call takes a minute or two while Ghidra opens it). If a call takes long, wait for it: never skip decompiling because it's slow."
    } else {
        " Ghidra isn't installed, so native_function_pseudocode uses the built-in decompiler, which is rougher: check each value against a second function or the program's files before you trust it."
    });
    s
}

/// Where the extractor lists what it took out (under app/).
pub(super) const ORIGINALS_MANIFEST: &str = "Original/MANIFEST.md";
/// The extractor's own conversation, kept in the project.
pub(super) const EXTRACT_TRANSCRIPT: &str = "extract-transcript.json";

/// What the extractor is asked: take the game's own files out of `folder` into app/Original/.
pub(super) fn extract_brief(folder: &Path) -> String {
    format!(
        "You are the asset extractor inside Craft Anything. The person owns this game and has its developer's permission to use its files in a private rebuild on this computer. Take the game's own files out of its folder ({}) into app/Original/ so the builder can use them. You don't build the game.\n\
         - Call enable_toolset with \"formats\". game_archives_list finds the game's archives; game_pak_list, game_iostore_list, game_unity_list and game_unity_bundle_list show what's inside.\n\
         - game_pak_extract takes files out of an Unreal .pak and makes their folders: a `file` ending in `/` (for example Game/Content/UI/) takes that whole folder in one call into the folder `output`, keeping its layout; when it says files are left, call it again the same way to carry on.\n\
         - Pictures: game_unreal_texture_export (with permission: true) or game_unity_asset_export, saved as PNG. Sounds and models: take them out with game_pak_extract as they are; convert them only with a converter you set up inside app/Original/tools/.\n\
         - Read the archives only with these tools; never write your own archive reader or parser. When a tool fails, read its error, fix the call and try again; if a tool can't do something, say so in your summary.\n\
         - Keep the game's folder layout under app/Original/ (for example app/Original/Content/UI/Logo.png). Take what a rebuild needs first: the player's view (arms and weapons), the main enemies, the level's materials and props, the interface and its fonts, and the sounds and music.\n\
         - Never decrypt, crack or bypass protection: an encrypted archive stays closed; say so and move on.\n\
         - When you're done, write app/{ORIGINALS_MANIFEST}: one line per file with its path under app/Original/, its source path in the game and what it is. Then say in 2-3 plain sentences what you took out and what you couldn't.",
        folder.display()
    )
}

/// Told to the builder when the extractor left the original's files in app/Original/.
pub(super) const ORIGINALS_READY: &str = "\n\nThe original game's own files are already taken out for you in app/Original/ (app/Original/MANIFEST.md lists each one with its source in the game), by the extraction step the person set up, under their permission. Import them into the project and use them, and list the ones you use in app/CREDITS.md. Take nothing more out of the game folder unless something you need is missing.";

/// The line a Deep-mode game that uses the original's files starts app/README.md with
/// (`CreditsCheck` looks for it as written).
pub(super) const PRIVATE_USE_NOTE: &str = "This build contains the original game's own files, for the private use of the person who owns the game, on their own computer. It must not be shared or published.";

/// How to rebuild a game faithfully: the real numbers first, and in Deep mode only, decompiling and
/// the original's own readable files used 1:1 for the person's private copy (never decrypted);
/// Clean room copies none of its files. `generated`: the person chose generated assets, so new
/// models and pictures replace the original's art (in Deep mode its sounds, music, fonts,
/// animations and maps are still used).
pub(super) fn game_steps(deep: bool, ghidra: bool, has_target: bool, generated: bool) -> String {
    let mut s = String::from(
        "Making it play like the original:\n\
         - Start app/MECHANICS.md: every number that shapes how it plays. Movement (walk and run speed, acceleration, friction, air control, jump height, gravity, crouch), camera (field of view, mouse sensitivity), each weapon (damage, fire rate, magazine, reload time, spread, recoil, range), health and armour, respawn, scoring, modes, timers, and how computer players behave. Next to each value say where it came from (a file in the game's folder, a function address or evidence id) or mark it \"estimated\". Build from that sheet and keep it up to date.\n\
         - Match the controls and key bindings, the on-screen information and where it sits, and the rules of each mode.",
    );
    s.push_str("\n- ");
    s.push_str(super::kinds::mechanics::MECHANICS_CONTRACT);
    if has_target {
        if deep {
            s.push_str(&decompile_note(true, ghidra));
        } else {
            s.push_str("\n- Clean room is on: don't open, read, list or decompile the game's files or code. Work from the person's description, the pictures and any documentation they give, and mark the numbers you estimate. If exact values matter, tell the person they can switch on Deep mode.");
        }
        s.push_str("\n- We can't watch the original running on this computer yet. For how it looks in play, use the pictures in reference/; when something about how it behaves isn't in the evidence, ask the person with core_person_ask.");
        if !deep {
            let make = if generated {
                "Make the models, textures and UI pictures with assets_model_generate and assets_image_generate, and your own sounds, music, fonts and maps"
            } else {
                "Make your own simple versions"
            };
            s.push_str(&format!(
                "\n- Art, sounds, models, animations, maps and UI: Clean room is on, so take nothing from the original game's files. {make} in the original's style: the same role, size, palette and feel, from the pictures and how it plays, without reproducing logos or trademarks. If the person wants the original's own art, tell them it needs Deep mode."
            ));
            return s;
        }
        let (lead, bring) = if generated {
            (
                "- Models, textures and UI pictures: the person chose to generate new ones, so make them with assets_model_generate and assets_image_generate in the original's style instead of copying the original's.\n- Sounds, music, fonts, animations and maps: the person wants them 1:1 from the original game's own files",
                "the sounds, music, fonts, animations and maps",
            )
        } else {
            (
                "- Art, sounds, models, animations, maps and UI: the person wants a 1:1 copy made with the original game's own files",
                "the models, animations, textures, sounds, music, fonts, UI images and maps",
            )
        };
        s.push_str(&format!(
            "\n{lead}, from their own installed copy. Use the originals wherever they can be read: bring {bring} from the game folder into the project (converting formats as the engine needs), for the person's own use on this computer. Craft Anything's own tools read game archives, so use them first: call enable_toolset with \"formats\", then game_archives_list finds the game's archives, game_pak_list, game_iostore_list, game_unity_list and game_unity_bundle_list show what's inside, game_pak_extract takes files out of an Unreal .pak, and game_unreal_texture_export (with permission: true, since the person asked for the originals) and game_unity_asset_export save pictures as PNG. Set up another converter only for what these can't convert yet (such as models and sounds), and keep it inside the project folder. Never decrypt, crack or bypass encryption or copy protection: files inside encrypted archives (for example encrypted .pak, .utoc or .ucas files) stay closed. Recreate those as closely as you can from the pictures, the game's readable data and how it plays, in the same role, size, palette and feel, without reproducing logos or trademarks. List every original file you used in app/CREDITS.md with its source path, and start app/README.md with this line, as written: \"{PRIVATE_USE_NOTE}\" Craft Anything checks both after each build.",
        ));
    }
    s
}

/// The pictures of the original the person added: the look to match, and (for programs, which
/// we can't photograph like a website) how the builder can see its own result to compare.
pub(super) fn pictures_note(ws: &Workspace, kind: &dyn TargetKind) -> Option<String> {
    let pics = ws.references();
    if pics.is_empty() {
        return None;
    }
    let names = pics.iter().filter_map(|p| p.file_name()).map(|n| format!("reference/{}", n.to_string_lossy())).collect::<Vec<_>>().join(", ");
    let mut s = format!(
        "The person added {} picture(s) of the original: {names}. They show the result they expect. Open every one with the Read tool before you plan, and match what they show: the camera or view, the on-screen layout (menus, HUD, panels) and where each part sits, the colours and lighting, the look of surfaces and characters, and the proportions and scale. Make your own artwork in that style; don't trace or copy logos, characters or other artwork from them.",
        pics.len()
    );
    if kind.self_screenshots() {
        s.push_str(" After each build, run the program with --screenshot to a file inside app/ (for example app/shots/now.png), open that picture with Read, compare it with each picture of the original, and fix the biggest differences first.");
    }
    Some(s)
}

/// A short reminder for later rounds, so pictures added after the first build count too.
pub(super) fn pictures_reminder(ws: &Workspace) -> String {
    let n = ws.references().len();
    if n == 0 {
        return String::new();
    }
    format!(
        "\n\nKeep matching the {n} picture(s) of the original in reference/ (open any you haven't looked at yet), and compare a fresh screenshot of your build with them before you reply."
    )
}

pub(super) fn added_prompt(notes: &[String]) -> String {
    let list = notes.iter().map(|n| format!("- {n}")).collect::<Vec<_>>().join("\n");
    format!(
        "While you were working, the person added:\n{list}\n\nTake this into account now: change app/ as needed, build again and fix any errors. Reply with 1-3 plain sentences on what you changed."
    )
}

/// For an agent continuing its own session after its last run stopped part-way (paused, the app
/// closed, or the computer stopped).
pub(super) fn continue_prompt(kind: &dyn TargetKind) -> String {
    let build = kind.rebuild_words();
    format!(
        "Your last run stopped before it finished (it was paused, or the app or the computer stopped). Everything you made so far is in app/. Pick up where you left off: see what's done and what's left (your checklist and core_unknowns_show), finish the task, then {build}, fix any errors and check it with rebuild_check. Reply with 1-3 plain sentences on what you did."
    )
}

/// For an agent whose saved session isn't on this computer (the project was copied from another
/// one, or moved): the whole brief, then what was made so far and where to find it, and the
/// earlier conversation as the project kept it (`handoff`), else its last summary, so it carries
/// on from the project rather than starting over.
pub(super) fn resumed_elsewhere(brief: &str, last_reply: &str, handoff: Option<&str>) -> String {
    let mut s = format!(
        "{brief}\n\nThis project is already under way: an earlier conversation built it, but that conversation isn't on this computer (the project was started on another computer or in another folder). Everything made so far is in app/. Before changing anything, look through app/ and the open questions (core_unknowns_show) to see what's done, then carry on from there instead of starting again."
    );
    if let Some(h) = handoff.map(str::trim).filter(|h| !h.is_empty()) {
        s.push_str(&format!(
            "\n\nThe earlier conversation, as the project kept it (oldest first; when it was long, the newest part is kept and long messages are cut short):\n\n{h}"
        ));
        return s;
    }
    let last = last_reply.trim();
    if !last.is_empty() {
        let last: String = last.chars().take(2000).collect();
        s.push_str(&format!("\n\nWhat the earlier conversation last told the person:\n\"{last}\""));
    }
    s
}

pub(super) fn follow_up(message: &str, kind: &dyn TargetKind) -> String {
    let build = kind.rebuild_words();
    format!(
        "The person asks: \"{message}\"\n\nMake the change in app/, then {build}, fix any errors and check it with rebuild_check. Reply with 1-3 plain sentences on what changed."
    )
}
