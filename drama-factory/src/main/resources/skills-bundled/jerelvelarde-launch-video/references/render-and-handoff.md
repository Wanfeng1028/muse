# Render, verify, and hand off

## Render strategy

Pin the render dependencies and ship a lockfile. Keep a separate render workspace; do not copy its dependencies into the product app. Bundle approved imagery/fonts locally where licensing allows so rendering does not depend on network asset loading.

For Remotion, set the design composition size once. Render 1920×1080 at scale 2 for 3840×2160 vector/HTML detail; don't scale a finished 1080p movie and call it a new native render. For Canvas, resize the actual bitmap and transform the drawing context; enlarging the CSS element alone adds no detail.

Render to a temporary file and promote it only after a successful process exit and media checks. Preserve previous exports. Use a versioned output name rather than silently overwriting an editor's changes.

Typical delivery: H.264 MP4, yuv420p, 30 or 60 fps chosen for the project; optional ProRes 422 master for an editor. A source recording cannot gain new detail through ProRes or upscaling. Label those copies accurately. Check the requested platform's current requirements when publishing; do not assume a particular social network always needs a square or vertical crop.

## Check the actual result

1. Render settled and boundary frames for each scene. Inspect headers, CTA, long URLs, logo edges, phone extents, and connectors at full size and at a feed-size preview.
2. Play the cut. Look for flashes between themes, stale recorded frames, abrupt scroll jumps, jitter, awkward pauses, confusing cursor paths, and unreadably fast receipts.
3. Probe dimensions, duration, frame rate, codecs, audio presence, and frame count. Fully decode final files to detect truncated or corrupted media. Use `gtm-os/tools/media-report.py --decode`.
4. Listen when audio is present. Confirm the last beat and fade finish inside the picture duration. A successful decoder does not confirm mix quality.
5. Verify CTA spelling, URL destination, and repository visibility. Make any verification limitations explicit.

## Editor folder

```text
project/
  01_Final_Video/           review MP4 and requested master
  02_Demo_Assets/Originals/ untouched recordings
  02_Demo_Assets/Edits/     clips with documented cuts/speeds
  03_Audio/                music/VO/SFX stems and rights notes
  04_Brand_Assets/          approved logos, mascots, fonts with licenses
  05_Code/                 source, lockfile, render commands
  06_Editor_Notes/          timeline, media inventory, stills, verification
```

Use the templates in `gtm-os/templates`. Keep source frame rate separate from delivery frame rate. Include asset provenance and the coordinates/timing of intentional editorial pans. The source should rebuild from the files in the handoff without app credentials. A live capture helper may require the separately running app; say so.

Copy only the needed source, assets, and lockfiles. Exclude node_modules, caches, browser profiles, `.env`, app databases, and reference media without redistribution rights. Test the rebuild after relocation when the user requests a self-contained handoff. If delivering a ZIP, verify its contents and CRC, and keep the uncompressed directory available.
