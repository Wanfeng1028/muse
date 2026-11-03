<p align="center">
  <a href="https://getartcraft.com/">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/brand/artcraft-logo-white.svg">
      <img alt="ArtCraft" src="docs/brand/artcraft-logo.svg" width="200">
    </picture>
  </a>
</p>

<p align="center">
  <img src="assets/app-icon/hicolor/256x256/apps/ai.storyteller.craft-anything.png" width="128" height="128" alt="Craft Anything のアイコン: 青いタイルに刻まれたワタリガラス">
</p>

<h1 align="center">Craft Anything</h1>

<p align="center">
  <a href="README.md">English</a> · <b>日本語</b> · <a href="README.zh.md">简体中文</a> · <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <b>あらゆる Web サイト、アプリ、ゲームがどう動いているかを見て、あなた自身の版を AI に作らせる。純粋な Rust で書かれた、オープンソースのクリーンルームエンジン。</b><br>
  対象を指定して、欲しいものを伝えるだけ。実際の調査ツールで元のソフトを調べ、<br>
  コーディングエージェントに新しいプロジェクトを作らせ、結果を元のソフトと比較して磨き上げます。
</p>

<p align="center">
  <img alt="100% Rust" src="https://img.shields.io/badge/100%25-Rust-b7410e?style=flat-square&logo=rust">
  <img alt="macOS · Windows · Linux · FreeBSD · Web" src="https://img.shields.io/badge/macOS%20%C2%B7%20Windows%20%C2%B7%20Linux%20%C2%B7%20FreeBSD%20%C2%B7%20Web-native-2d81ff?style=flat-square">
  <img alt="ライセンス: MIT OR Apache-2.0" src="https://img.shields.io/badge/license-MIT%20%2F%20Apache--2.0-3a3a3a?style=flat-square">
  <img alt="ステータス: アルファ版の初期段階" src="https://img.shields.io/badge/status-early%20alpha-d69e2e?style=flat-square">
</p>

<p align="center">
  <a href="https://discord.gg/artcraft"><img alt="ArtCraft コミュニティの Discord に参加する" src="https://img.shields.io/badge/Join%20us%20on%20Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" height="40"></a>
</p>

<p align="center">
  <a href="#downloads"><b>Craft Anything をダウンロード</b></a> ·
  <a href="https://getartcraft.com/">ArtCraft</a> ·
  <a href="https://getartcraft.com/apps">すべての Crafting Apps</a>
</p>

<br>

<p align="center">
  <img src="docs/images/project-website.png" alt="Craft Anything の Web サイトプロジェクト: チェックがまだ一致していない点と各ページの類似度を示し、ビルダーはビルドした版の準備ができたと告げ、承認カードはコマンド実行の前に確認を求め、プランは 4 ステップのうち 2 つが完了していることを示している" width="100%">
  <br>
  <sub>Web サイトプロジェクト: 各チェックは、ビルドが元のソフトにどれくらい似ているかを示し、ルールから外れるものはあなたが承認し、プランは残りの作業を示します。</sub>
</p>

> [!NOTE]
> **ArtCraft は、あらゆる分野の作り手が集まるコミュニティです。** 画家、写真家、映像作家、
> イラストレーター、デザイナー、アニメーター、趣味で作っている人、先週ペンを持ったばかりの人。
> 何かを作っているなら、あなたも仲間です。**[Discord で気軽に声をかけてください](https://discord.gg/artcraft)。**

<p align="center">
  <a href="#how-it-works">仕組み</a> ·
  <a href="#two-ways-to-use-it">2 つの使い方</a> ·
  <a href="#ai">AI</a> ·
  <a href="#built-for-agents">エージェント向け</a> ·
  <a href="#under-the-hood">内部の仕組み</a> ·
  <a href="#get-started">はじめかた</a> ·
  <a href="#status">ステータス</a> ·
  <a href="#downloads">ダウンロード</a> ·
  <a href="https://discord.gg/artcraft">Discord</a>
</p>

<br>

<table>
  <tr>
    <td width="25%" valign="top">
      <h3>🔍 なんでも調べる</h3>
      Web サイト、デスクトップアプリ、スマホアプリ、ゲーム、ファイル。本物の調査ツールが、それらがどう作られ、何をするのかを突き止め、答えの裏付けとなるエビデンスも添えます。
    </td>
    <td width="25%" valign="top">
      <h3>🛠️ 自分の版を作る</h3>
      「この Web サイトを再現して」「このゲームのゲームプレイを Rust で再現して」と伝えれば、コーディングエージェントが指定した技術スタックで新しいプロジェクトを作ります。
    </td>
    <td width="25%" valign="top">
      <h3>✅ 推測ではなく検証</h3>
      すべてのビルドは元のソフトと比較され (3 つの画面幅で表示したページ、ゲーム自身のセルフテスト、アプリの実行結果)、十分近づくまで磨かれます。
    </td>
    <td width="25%" valign="top">
      <h3>🤖 エージェント対応</h3>
      314 個のツールは、それぞれが CLI コマンドであり、MCP ツールでもあります。どのエージェントでも、アプリが使うのと同じエンジンを動かせます。調査に AI は要りません。
    </td>
  </tr>
</table>

<br>

<a name="how-it-works"></a>

## 仕組み

Craft Anything で対象を指定し、欲しいものを伝えて「Start」を押すだけ。4 つのステップで進み、判断が必要なときは、わかりやすい言葉であなたに尋ねます:

1. **調べる (Study):** 元のソフトを調査します。あらゆる幅で表示したページ、コード、ファイル、動作のしかたを調べます。
2. **作る (Build):** コーディングエージェントが新しいプロジェクトを作ります。言語、フレームワーク、エンジンはリクエストで指定したもの (指定がなければ妥当な既定値)を使います。
3. **確認する (Check):** ビルドを元のソフトと比較し、まだ一致していない点を一覧にします。
4. **完成 (Ready):** 結果を開いたり、遊んだり、プレビューしたりできます。変更を頼めば磨き直します。

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/images/make.png" alt="Make 画面: 再現する Web サイト、アプリ、ゲームを選び、アドレスを入力し、「Clean room」か「Deep」かを選び、欲しいものを伝えて Start を押す" width="100%"><br>
      <sub><b>Make:</b> 何を再現するかを選び、欲しいものを伝え、Start を押します。</sub>
    </td>
    <td width="50%" valign="top">
      <img src="docs/images/project-game.png" alt="完成したスネークゲームのプロジェクト。すべてのステップが完了し、「Play the game」ボタンがある" width="100%"><br>
      <sub><b>Ready:</b> ゲームで遊ぶ。変更は下の欄から頼めます。</sub>
    </td>
  </tr>
</table>

<a name="two-ways-to-use-it"></a>

## 2 つの使い方

- **Simple** (既定): 「What do you want to make?」と表示されるので、Web サイト、アプリ、ゲームから選び、説明して Start を押します。プロジェクトページには 4 つのステップ (Study → Build → Check → Ready)、エージェントが今何をしているかの平易な説明、質問と承認のカード、結果がどれくらい似ているか、結果やそのフォルダを開くボタンが並びます。変更は下の入力欄から頼めます。「Just look inside」は、何も作らずに対象へ質問できます (ディープモード時)。
- **Advanced**: フル機能のワークベンチ。すべてのツール (Ctrl/Cmd+K)、関数、文字列、疑似 C、逆アセンブル、16 進数、コールグラフ、エビデンス、不明点、ジョブ、ログ、エージェントコンソール。

どちらのモードも同じエンジンを動かします。

## クリーンルーム(Clean room)かディープモード(Deep)

- **クリーンルーム(Clean room)** (既定): 元のソフトの中身は一切読みません。コードも、ファイルも、ページのソースも読みません。Craft Anything は、あなたに見えるものだけから作業します。追加した画像、訪問者から見た Web サイト (スクリーンショット、見えているテキスト、計測したレイアウト、色、フォント、余白、開いたメニュー)、そして許可した場合はアプリのウィンドウの画像です。中を覗こうとするツールは拒否され、ディープモードの有効化方法を案内します。
- **ディープモード(Deep)**: すべてのツールを使います。私的利用のためのモードです。プログラムのコードとファイルは内蔵エンジン (インストールされていれば Ghidra も)で読み、Web サイトの JavaScript を読み、そのスタートページを観察します。ビルダーもそれらすべてを使えます。

タイトルバーまたは Settings で切り替えられます。`settings_set deep_mode true` で設定するか、CLI の 1 回限りなら `--deep` (または `--clean-room`)を使ってください。

<p align="center">
  <img src="docs/images/workbench.png" alt="Advanced モードのワークベンチ: 関数一覧、選択した関数の疑似 C、ツール呼び出しで質問に答えるエージェント、エビデンスの台帳" width="100%">
  <br>
  <sub><b>Advanced:</b> 関数、疑似 C、エージェント、そしてあらゆる答えの裏にあるエビデンス。</sub>
</p>

<a name="ai"></a>

## AI

ビルドには、お使いのコンピュータ上のコーディングエージェントが必要です。まず **Claude Code** に対応しています。Craft Anything は、あなた自身の改変されていない `claude` プログラムを実行します。これはあなた自身のサインイン情報を使います。Craft Anything がアカウントを見たり扱ったりすることはありません。利用は Anthropic とのあなた自身の契約に従います。方法と理由は [docs/claude-code.md](docs/claude-code.md) を参照してください。Codex アダプターもありますが、実際のインストール環境ではまだ検証されていません。質問と分析には、Anthropic、OpenAI、OpenRouter、ローカルの OpenAI 互換サーバーが使えます (Settings → AI)。

<a name="built-for-agents"></a>

## エージェント向け

すべてのツールは CLI サブコマンドでも MCP ツールでもあるので、エージェントはアプリなしで対象を調べたり、再構築を丸ごと実行したりできます:

```sh
craft-anything-cli commands                                   # every tool, by toolset
craft-anything-cli mcp                                        # serve them to any MCP client
craft-anything-cli rebuild https://example.com "Recreate this website"
```

結果は、信頼度・カバレッジ・制限事項を備えたエビデンス記録です。大きな結果はまず要約として返り、`core_evidence_browse` でページ送りできます。`craft-anything-cli setup` は Craft Anything をコーディングエージェントのアプリにつなぎます。

<a name="under-the-hood"></a>

## 内部の仕組み

純粋な Rust で書かれたリバースエンジニアリングエンジンです。ネイティブプログラム、.NET、Java、Android、Apple、Electron/JavaScript、Web サイト、ファームウェア、パケットキャプチャ、データベース、ゲームファイル向けに 314 個のツール (うち 298 個がエンジン本体、残りは AI とセットアップの層)を備えています。独自のデコーダ、逆アセンブラ、逆コンパイラは外部プログラムなしで動きます。ディープモードではそれらすべてを使い、インストールされていれば Ghidra も使います。これがデスクトップアプリ (egui)、CLI、MCP サーバーを支え、一部は WebAssembly としてブラウザでも動きます。全リストは [docs/tools.md](docs/tools.md) にあります。

<a name="get-started"></a>

## はじめかた

Rust **1.97 以降**が必要です (依存関係が要求します。`rustup update`)。Debian か Ubuntu では、デスクトップアプリには次のものも必要です:

```sh
sudo apt-get install libxkbcommon-dev libwayland-dev libx11-dev libxrandr-dev libxi-dev libgl1-mesa-dev libgtk-3-dev
```

続いて:

```sh
git clone https://github.com/storytold/craft-anything && cd craft-anything
cargo run --release -p craft-anything                # the desktop app
cargo install --path apps/craft-anything-cli         # the CLI, as `craft-anything-cli`
craft-anything-cli doctor                            # checks the install, coding agents and engines
```

ビルドには、コンピュータ上でサインイン済みのコーディングエージェントが必要です ([AI](#ai) を参照)。足りないものは `doctor` が示します。コマンドラインからの再構築 (ターミナルで質問に答えます):

```sh
craft-anything-cli rebuild https://example.com "Recreate this website"
craft-anything-cli rebuild - "A snake game in Rust" --rounds 1
craft-anything-cli rebuild https://example.com "Make the header blue" --continue-in "<project folder>"
craft-anything-cli rebuild - "Add a contact form" --project-folder "<your folder>" --existing edit
```

新しいプロジェクトは `Documents/Craft Anything` に作られます (Settings → General で変更できます)。各プロジェクトフォルダには `craft.json` (リクエスト、対象、状態、履歴)、`capture/` (対象から記録したもの)、`app/` (生成されたプロジェクト)、`checks/` (元のソフトとの比較ごとの結果)、`investigation.cany/` (エビデンス)、`inbox/` (未回答の質問)が入ります。

プロジェクトは、選んだフォルダから始めることもできます (Start の下にある「Choose a folder…」、または `--project-folder`)。すでにファイルがある場合は、それが何なのかを答えます。アプリ本体 (ビルダーがその場で編集します)か、そこから始める素材 (アプリはその隣の `app/` に作られます)のどちらかです (Settings → General で答えを記憶できます)。Settings → General では、ほかのフォルダにあるプロジェクトも一覧できます。一覧から外すと、その一覧から消えるだけです。

<a name="status"></a>

## ステータス

> [!IMPORTANT]
> **ステータス:** Craft Anything はアルファ版の初期段階です。いま動くもの、一部だけのもの、この先の予定:
>
> - **いま動くもの:** デスクトップアプリ (Simple と Advanced)、CLI、MCP サーバー。Claude Code
> をビルダーとして、Web サイト・アプリ・ゲームを「調べる → 作る → 確認する → 磨く」の順に進める
> ワークフロー。3 つの画面幅での Web サイト確認。Unity、Unreal、Godot でのゲーム再構築。Ghidra を
> 使うディープモード。生成画像と 3D モデル (オプトイン、自分の fal.ai キー)。プラグイン (MCP
> サーバー、および `wasm-plugins` オプション付きビルドでの WASM コンポーネント)。
> - **一部だけ:** API キーや他のコーディングエージェントでのビルド (実装済み、実環境では未実行)、
> アプリとゲームの挙動チェック、実物ではなくダミーの対象でしかテストしていない一部のエンジンツール。
> - **次:** 最初の公開リリース (Windows、macOS、Linux、FreeBSD 向けインストーラとブラウザ
> ビューアは CI に用意済み)、その後マネージドプランを提供予定。
>
> [docs/STATUS.md](docs/STATUS.md) に詳細と、各部分をどう確かめたか、
> [docs/tool-status.md](docs/tool-status.md) にツールごとのチェックリスト、
> [docs/ROADMAP.md](docs/ROADMAP.md) に計画の項目別一覧があります。issue を立てるか、
> [Discord](https://discord.gg/artcraft) で壊れたところを教えてください。

**責任ある使い方。** Craft Anything は、所有しているか、調べる許可があるソフトにだけ使ってください。DRM、ログイン、
アンチチートを回避することは決してありません。再構築は、エビデンスに基づいてレイアウト・スタイル・挙動を再現します。エージェントには、ロゴ・写真・テキストを、あなたが権利を持つか使用許可があると確認できるまでコピーしないよう指示しています。

<a name="downloads"></a>

## ダウンロード

GitHub の [最新リリース](https://github.com/storytold/craft-anything/releases/latest) には以下に挙げるすべてのビルドがあり、[すべてのリリース](https://github.com/storytold/craft-anything/releases) には過去のバージョンとそのリリースノートがあります。ファイル名の `<ver>` はバージョン番号で、`SHA256SUMS.txt` に各ファイルのチェックサムが載っています。

### Windows

| ビルド | インストーラ | ポータブル |
|---|---|---|
| x64 (64 ビット Intel/AMD) | `craft-anything-<ver>-windows-x64.msi` | `craft-anything-<ver>-windows-x64-portable.zip` |
| arm64 (Snapdragon などの ARM PC) | `craft-anything-<ver>-windows-arm64.msi` | `craft-anything-<ver>-windows-arm64-portable.zip` |
| x86 (32 ビット) | `craft-anything-<ver>-windows-x86.msi` | `craft-anything-<ver>-windows-x86-portable.zip` |

インストーラと実行ファイルはコード署名済みです。ポータブルの zip は設定をアプリの隣に保存します。

### macOS

| ビルド | ファイル | 備考 |
|---|---|---|
| アプリ、ユニバーサル (Apple silicon + Intel) | `craft-anything-<ver>-macos-universal.dmg` | 署名・公証済み |
| コマンドラインツール、ユニバーサル | `craft-anything-cli-<ver>-macos-universal.zip` | 署名・公証済み。macOS がブロックする場合は下記を参照 |

0.2.0 以降のバージョンではコマンドラインツールがアプリに同梱されるため、ビルドに別の zip は
不要です。必要なのは、アプリなしでコマンドラインだけを使う場合です。

ブラウザから zip をダウンロードすると「Apple could not verify craft-anything-cli」で止まることが
あります(単体のプログラムは公証を自分に添付できないため、macOS がオンラインで確認します)。
ターミナルからのダウンロードはこの検査を受けないので、代わりに次を使ってください:

```sh
ver=0.2.0   # change this to the version you want
curl -fLO "https://github.com/storytold/craft-anything/releases/download/v$ver/craft-anything-cli-$ver-macos-universal.zip"
ditto -x -k "craft-anything-cli-$ver-macos-universal.zip" .
mkdir -p ~/.local/bin
mv "craft-anything-cli-$ver-macos-universal/craft-anything-cli" ~/.local/bin/
~/.local/bin/craft-anything-cli --version
```

`craft-anything-cli` だけで実行したい場合は、`~/.local/bin` を `PATH` に追加してください。

すでにブロックされたコピーがある場合は、Done(「ゴミ箱に入れる」ではなく)を押してから
`xattr -d com.apple.quarantine <craft-anything-cli のパス>` を実行するか、システム設定 →
プライバシーとセキュリティ → このまま開く で許可してください。

### Linux

| 形式 | x86_64 | aarch64 (ARM64) | 備考 |
|---|---|---|---|
| AppImage | `craft-anything-<ver>-linux-x86_64.AppImage` | `craft-anything-<ver>-linux-aarch64.AppImage` | どこでも動きます。[AppImageUpdate](https://github.com/AppImageCommunity/AppImageUpdate) で自己更新します (`.zsync` ファイル) |
| Flatpak | `craft-anything-<ver>-linux-x86_64.flatpak` | `craft-anything-<ver>-linux-aarch64.flatpak` | サンドボックス化。`flatpak install --user <file>` |
| Debian/Ubuntu | `craft-anything-<ver>-linux-x86_64.deb` | `craft-anything-<ver>-linux-aarch64.deb` | |
| Fedora/RHEL/openSUSE | `craft-anything-<ver>-linux-x86_64.rpm` | `craft-anything-<ver>-linux-aarch64.rpm` | |
| Tarball | `craft-anything-<ver>-linux-x86_64.tar.gz` | `craft-anything-<ver>-linux-aarch64.tar.gz` | どこにでも展開できます |

RISC-V (riscv64): `craft-anything-<ver>-linux-riscv64.tar.gz`、tarball のみです。

### FreeBSD

| ビルド | ファイル |
|---|---|
| x86_64 | `craft-anything-<ver>-freebsd-x86_64.tar.gz` |

### Web (WebAssembly)

| ビルド | ファイル | 備考 |
|---|---|---|
| ブラウザビューア | `craft-anything-web-<ver>.zip` | ファイルが何であるかをブラウザ上で示します (ファイルはブラウザから出ません)。フォルダはどんな静的 Web サーバーでも公開できます ([packaging/web/README.md](packaging/web/README.md)) |

<br>

<p align="center">
  <a href="https://discord.gg/artcraft"><img alt="ArtCraft コミュニティの Discord に参加する" src="https://img.shields.io/badge/Join%20us%20on%20Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" height="40"></a>
</p>

<h3 align="center">一緒にものづくりを</h3>

<p align="center">
  私たちの Discord は、あらゆる種類の作り手が集まる場所です。絵を描く人、写真を撮る人、
  デッサンする人、映像を編集する人、文字を組む人、そしてまだ自分が何を作りたいのか
  模索している人。いま取り組んでいることを共有したり、助けを求めたり、不具合を
  教えたり、これらのツールでこうだったらいいのにと思うことを話したりしてください。
  どんな表現手段を使っていても、経験の長さにかかわらず、ここでは誰でも歓迎します。
</p>

<p align="center">
  <a href="https://discord.gg/artcraft"><b>discord.gg/artcraft</b></a> ·
  <a href="https://getartcraft.com/">getartcraft.com</a> ·
  <a href="https://getartcraft.com/apps">すべての Crafting Apps</a> ·
  <a href="https://github.com/storytold/craft-anything">Craft Anything</a>
</p>

---

## The Craft App Suite

| | アプリ | 用途 | コード | 詳細 |
|:-:|---|---|---|---|
| <img src="https://raw.githubusercontent.com/storytold/photocraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.photocraft.png" alt="" width="32" height="32"> | **PhotoCraft** | 画像編集:レイヤー、マスク、文字、本物の PSD ファイル | [GitHub](https://github.com/storytold/photocraft) | [ウェブサイト](https://getartcraft.com/apps/photocraft) |
| <img src="https://raw.githubusercontent.com/storytold/vectorcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.vectorcraft.png" alt="" width="32" height="32"> | **VectorCraft** | ベクターイラスト | [GitHub](https://github.com/storytold/vectorcraft) | [ウェブサイト](https://getartcraft.com/apps/vectorcraft) |
| <img src="https://raw.githubusercontent.com/storytold/filmcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.filmcraft.png" alt="" width="32" height="32"> | **FilmCraft** | 動画編集、カラー、サウンド | [GitHub](https://github.com/storytold/filmcraft) | [ウェブサイト](https://getartcraft.com/apps/filmcraft) |
| <img src="https://raw.githubusercontent.com/storytold/lightcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.lightcraft.png" alt="" width="32" height="32"> | **LightCraft** | 写真ライブラリと RAW 現像 | [GitHub](https://github.com/storytold/lightcraft) | [ウェブサイト](https://getartcraft.com/apps/lightcraft) |
| <img src="https://raw.githubusercontent.com/storytold/pdfcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.pdfcraft.png" alt="" width="32" height="32"> | **PdfCraft** | PDF の閲覧、整理、保護 | [GitHub](https://github.com/storytold/pdfcraft) | [ウェブサイト](https://getartcraft.com/apps/pdfcraft) |
| <img src="https://raw.githubusercontent.com/storytold/effectcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.effectcraft.png" alt="" width="32" height="32"> | **EffectCraft** | モーショングラフィックスと視覚効果 | [GitHub](https://github.com/storytold/effectcraft) | [ウェブサイト](https://getartcraft.com/apps/effectcraft) |
| <img src="https://raw.githubusercontent.com/storytold/designcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.designcraft.png" alt="" width="32" height="32"> | **DesignCraft** | ページレイアウトと出版 | [GitHub](https://github.com/storytold/designcraft) | [ウェブサイト](https://getartcraft.com/apps/designcraft) |
| <img src="https://raw.githubusercontent.com/storytold/figcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.figcraft.png" alt="" width="32" height="32"> | **FigCraft** | インターフェースデザインとプロトタイピング | [GitHub](https://github.com/storytold/figcraft) | [ウェブサイト](https://getartcraft.com/apps/figcraft) |
| <img src="https://raw.githubusercontent.com/storytold/wordcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.wordcraft.png" alt="" width="32" height="32"> | **WordCraft** | ワープロと文書 | [GitHub](https://github.com/storytold/wordcraft) | [ウェブサイト](https://getartcraft.com/apps/wordcraft) |
| <img src="https://raw.githubusercontent.com/storytold/soundcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.soundcraft.png" alt="" width="32" height="32"> | **SoundCraft** | 音声の録音と編集 | [GitHub](https://github.com/storytold/soundcraft) | [ウェブサイト](https://getartcraft.com/apps/soundcraft) |
| <img src="https://raw.githubusercontent.com/storytold/deckcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.deckcraft.png" alt="" width="32" height="32"> | **DeckCraft** | プレゼンテーションとスライド | [GitHub](https://github.com/storytold/deckcraft) | [ウェブサイト](https://getartcraft.com/apps/deckcraft) |
| <img src="https://raw.githubusercontent.com/storytold/cadcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.cadcraft.png" alt="" width="32" height="32"> | **CADCraft** | コンピューター支援設計 | [GitHub](https://github.com/storytold/cadcraft) | [ウェブサイト](https://getartcraft.com/apps/cadcraft) |
| <img src="https://raw.githubusercontent.com/storytold/gridcraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.gridcraft.png" alt="" width="32" height="32"> | **GridCraft** | 表計算とデータ | [GitHub](https://github.com/storytold/gridcraft) | [ウェブサイト](https://getartcraft.com/apps/gridcraft) |
| <img src="https://raw.githubusercontent.com/storytold/texturecraft/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.texturecraft.png" alt="" width="32" height="32"> | **TextureCraft** | 3D テクスチャ描画 | [GitHub](https://github.com/storytold/texturecraft) | [ウェブサイト](https://getartcraft.com/apps/texturecraft) |
| <img src="https://raw.githubusercontent.com/storytold/craft-anything/main/assets/app-icon/hicolor/64x64/apps/ai.storyteller.craft-anything.png" alt="" width="32" height="32"> | **Craft Anything** | あらゆるソフトの仕組みを知り、自分の版を作る | [GitHub](https://github.com/storytold/craft-anything) | [ウェブサイト](https://getartcraft.com/apps/craft-anything) |
| <img src="https://raw.githubusercontent.com/tangency-labs/solidcraft/main/assets/icons/app/linux/exports/hicolor/64x64/apps/io.tangencylabs.solidcraft.png" alt="" width="32" height="32"> | **SolidCraft** | Tangency Labs によるパラメトリック 3D CAD(コミュニティ製アプリ) | [GitHub](https://github.com/tangency-labs/solidcraft) | |

## ライセンスとクレジット

Craft Anything は [MIT](LICENSE-MIT) または [Apache-2.0](LICENSE-APACHE) のデュアルライセンスです (どちらかお選びください)。Copyright (c) 2026 ArtCraft Team and the Craft Anything contributors. 必要な通知は [NOTICE](NOTICE) にあります。

同梱のフォント、アイコン、画像、その他のアセットは、それぞれ独自のオープンライセンスが適用されます。各アセットの作者、出典、ライセンスは [ATTRIBUTION.md](ATTRIBUTION.md) に記載しています。

スクリーンショットに写っているのは、そのために作られたサンプルプロジェクトです: example.com、スネークゲーム、小さな電卓プログラム。

[`docs/brand/`](docs/brand/) にある ArtCraft の名称、ワードマーク、ロゴは ArtCraft Team の商標で、このライセンスの対象外です。無改変のまま、このリポジトリと Craft Anything の一部としてのみ、[`docs/brand/LICENSE-brand.txt`](docs/brand/LICENSE-brand.txt) に従って使用できます。フォークや改変版では、これらを削除しなければなりません。

<p align="center">
  <a href="https://getartcraft.com/"><img alt="ArtCraft" src="docs/brand/artcraft-mark.svg" width="28"></a><br>
  <sub><a href="https://getartcraft.com/">ArtCraft</a> チームとコミュニティによる制作。</sub>
</p>

---

<sub>このページは [README.md](README.md) の日本語訳です。内容に食い違いがある場合は英語版が優先されます。</sub>
