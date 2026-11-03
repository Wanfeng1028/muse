# Releasing Craft Anything

The recipe is shared by every Crafting App: `release/playbook.md` in
[craftrules](https://github.com/storytold/craftrules) (`../craftrules`), and the runbook for cutting
one is `release/cut-a-release.md` there. That repo is private; you don't need it to follow this
page. In short: a release is whatever is on the `release` branch. Pushing to it makes
`.github/workflows/release.yml` build, sign and package every platform and attach the files to a
draft GitHub Release, which a maintainer publishes once every job is green. Signing needs the
maintainers' certificates (secrets of the `release` environment, which only the `release` branch can read), so a fork's run produces unsigned packages.

`ci.yml` checks every pull request and every push to `main` once the repository is public; while
it's private its jobs are skipped (they would cost Actions minutes), so run it by hand before a
release: `gh workflow run ci.yml --ref main`. The other workflows (`freebsd.yml`,
`windows-arm64.yml`, `packaging-lint.yml`) run by hand (`gh workflow run <file>`).

## Cutting a release

1. Bump the version on `main`: `cargo xtask version set X.Y.Z` (the workspace version in the root
   `Cargo.toml` is the single source; `cargo xtask version` prints it).
2. Fast-forward `release` to `main`. The push runs `.github/workflows/release.yml`, which builds every
   platform and creates or updates the draft GitHub Release **Craft Anything vX.Y.Z**.
3. When every job is green, publish the draft.

A dry run of the unsigned platforms from any branch: `gh workflow run release.yml --ref <branch>`.

## What it ships

| Platform | Files |
|---|---|
| macOS | `craft-anything-<v>-macos-universal.dmg` (`Craft Anything.app`), `craft-anything-cli-<v>-macos-universal.zip` |
| Windows | `craft-anything-<v>-windows-{x64,x86,arm64}.msi` and `-portable.zip` |
| Linux | `craft-anything-<v>-linux-{x86_64,aarch64}.{AppImage,AppImage.zsync,deb,rpm,tar.gz,flatpak}`, `craft-anything-<v>-linux-riscv64.tar.gz` |
| FreeBSD | `craft-anything-<v>-freebsd-x86_64.tar.gz` |
| Web | `craft-anything-web-<v>.zip` (the browser viewer, `apps/craft-anything-web`) |

Plus `SHA256SUMS.txt`.

## App-specific choices

- **No file associations.** Craft Anything opens any file, so it claims no file type and no URL
  scheme on any platform. It appears in Windows' "Open with" list and accepts paths on the
  command line. Projects (`*.cany`) are folders.
- **The macOS executable** is `Craft Anything.app/Contents/MacOS/craft-anything`. Only the bundle
  carries the display name. `craft-anything-cli` sits beside it, as it does in the Windows zip: the
  app starts it as the coding agents' MCP server, so an app without it can't build (#91).
- **Windows portable mode:** the portable zip ships `portable.txt`. While it sits next to the exe,
  settings live in `CraftAnythingData\` (`crates/engine/src/settings.rs`).
- **Flatpak** grants `--share=network` (AI backends, engine downloads) and `--filesystem=home:ro`
  (files to inspect, passed by path).
- **Fonts** are committed in `assets/fonts` (OFL-1.1). Release and CI builds also embed craft-fonts
  at the commit pinned in `release.yml` and `ci.yml` (`CRAFT_FONTS_DIR`, `CRAFT_FONTS_REQUIRED=1`),
  the fallbacks for Korean, Chinese, Japanese, Thai, Arabic, Hebrew, Devanagari and symbols; a
  build without them shows those as boxes (#19). Every package ships all their licences
  (`OFL-*.txt`, craft-fonts' as `OFL-<font>.txt`).
- **The WiX UpgradeCode** `8F69A8B5-4384-479B-B3FF-93C5374BCA51` belongs to Craft Anything for good.
