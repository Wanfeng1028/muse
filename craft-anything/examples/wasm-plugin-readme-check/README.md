# Example check plugin: does the build say how to run it?

A Craft Anything check plugin written in Rust. Its one check, `readme_says_how_to_run`, passes when
the build has a `README.md` at its top that tells a person how to start it, and otherwise says what
to add. It implements `craft-anything:plugin/checks` from
[`crates/engines/wit/plugin.wit`](../../crates/engines/wit/plugin.wit), imports nothing, and asks
only for `.md` files' text (`"extensions": ["md"]`); every other file comes as path and size.

Checks run after the built-in checks of each round. A failed one is shown to the builder to fix,
like any other check.

## Build

```sh
rustup target add wasm32-unknown-unknown
cargo build --release --target wasm32-unknown-unknown
wasm-tools component new target/wasm32-unknown-unknown/release/wasm_plugin_readme_check.wasm -o readme-check.wasm
```

## Use

Craft Anything built with `--features wasm-plugins`, and in `config.toml` (or Settings → Plugins):

```toml
[[plugins.wasm]]
id = "readme"
path = "/full/path/to/readme-check.wasm"
```

Its check is then `readme_readme_says_how_to_run` in each build's check results.

## Check it

```sh
CRAFT_ANYTHING_TEST_WASM_CHECK=/full/path/to/readme-check.wasm \
  cargo test -p craft-anything-engines --features wasm-plugins the_example_check
```
