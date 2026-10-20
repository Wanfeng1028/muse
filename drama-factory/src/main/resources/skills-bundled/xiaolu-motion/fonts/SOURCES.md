# fonts/ 来源与许可

**Last Updated:** 2026-09-26

本目录只放可随开源项目分发的 OFL 字体。文件名与 PostScript 名和 `styles/base.json` 的 `fonts.*.open.faces` 一致，渲染器可直接找到。本目录目前在仓库 `.gitignore` 里，是否把字体文件提交进仓库另行决定（OFL 允许随软件分发，需附带许可文本）。

## 已下载（`scripts/get_fonts.sh` 拉取的集合，共约 162 MB，9 个字体文件）

`scripts/get_fonts.sh` 拉 `styles/base.json` 三个中文角色实际声明的字重（sans Regular/Medium/Bold、serif Bold/Heavy、kai Regular），另外加了 sans Heavy(900)——`base.json` 本身不声明这一档，但 `library/card-number-impact`（数字冲击卡，直接用 `fonts/` 里的文件，不走 style 令牌）用得到。霞鹜文楷 Medium(500) 是本机额外留存，脚本不下载但校验和一并记在这里备查。

| 文件 | 字体 / 字重 | 版本 | 许可 | 大小 (bytes) | SHA-256 | get_fonts.sh |
|---|---|---|---|---|---|---|
| `SourceHanSansSC-Regular.otf` | 思源黑体 Source Han Sans SC Regular (400) | 2.005 | SIL OFL 1.1 | 16,529,832 | `f1d8611151880c6c336aabeac4640ef434fa13cbfbf1ffe82d0a71b2a5637256` | 是 |
| `SourceHanSansSC-Medium.otf` | 思源黑体 Source Han Sans SC Medium (500) | 2.005 | SIL OFL 1.1 | 16,546,328 | `1df61d31687d04fd2f928a3bb6ca6cd61f0e988cc267cf317f32406edbb49f70` | 是 |
| `SourceHanSansSC-Bold.otf` | 思源黑体 Source Han Sans SC Bold (700) | 2.005 | SIL OFL 1.1 | 16,963,428 | `df2b90f5bcc6d01dfc964cec5f6d535d6b6aebd26ed7fd79a9c1b3f2112fcb6b` | 是 |
| `SourceHanSansSC-Heavy.otf` | 思源黑体 Source Han Sans SC Heavy (900) | 2.005 | SIL OFL 1.1 | 17,614,484 | `6374b11bc4c2cd4bd7be1a1d64cf5047906c8a6a025c64e023c6792e50ba985e` | 是（`card-number-impact` 需要）|
| `SourceHanSerifSC-Bold.otf` | 思源宋体 Source Han Serif SC Bold (700) | 2.003 | SIL OFL 1.1 | 25,521,732 | `706b8c0de2deff6cbc0c87e2cdedfd33a78b7ffd76cebb4549012f197ba611fe` | 是 |
| `SourceHanSerifSC-Heavy.otf` | 思源宋体 Source Han Serif SC Heavy (900) | 2.003 | SIL OFL 1.1 | 24,063,280 | `d033af54f96530476faed924ab5d5e9e6ef0833495670fd57bab9a7758398048` | 是 |
| `LXGWWenKai-Regular.ttf` | 霞鹜文楷 LXGW WenKai Regular (400) | 1.522 | SIL OFL 1.1 | 25,575,676 | `39ad71264b588165b469e35e6afb162a378dacd1f95348160240ba9038ac3009` | 是 |
| `LXGWWenKai-Medium.ttf` | 霞鹜文楷 LXGW WenKai Medium (500) | 1.522 | SIL OFL 1.1 | 25,379,848 | `d4bdeb38a39151d74d084cba5090f8cb7d20bf83eedb78c35939ae70b9f4e3f6` | 否（手动，见上）|

许可文本：

| 文件 | 对应字体 | 来源 | SHA-256 |
|---|---|---|---|
| `LICENSE-SourceHanSans.txt` | 思源黑体（保留字体名 “Source”） | https://raw.githubusercontent.com/adobe-fonts/source-han-sans/2.005R/LICENSE.txt | `fcac737e761ec63dbfbdce11030a1780161920d80315edba9c8beff1c2bac5a2` |
| `LICENSE-SourceHanSerif.txt` | 思源宋体（保留字体名 “Source”） | https://raw.githubusercontent.com/adobe-fonts/source-han-serif/2.003R/LICENSE.txt | `9ff5bb567e1b92c801fc1069e5fbf992ff8efccacb9db94e5959a5b3ba9bb903` |
| `LICENSE-LXGWWenKai.txt` | 霞鹜文楷 | https://raw.githubusercontent.com/lxgw/LxgwWenKai/v1.522/OFL.txt | `c38b1994a5e48ac30ac7d1da7d0409fd8fd8127dfe28a13d6e787d5b1ef34a5e` |

`scripts/get_fonts.sh` 已验证跑通（2026-09-27）：全新下载与校验和缓存命中两条路径都测过，退出码 0。

## 来源 URL

### 思源黑体 SC 2.005R

- 官方发布页：https://github.com/adobe-fonts/source-han-sans/releases/tag/2.005R
- 发布页只提供打包 zip（SC 语言版 `09_SourceHanSansSC.zip` 95 MB，全包数百 MB），没有单独 OTF。四个单文件取自同一 tag（2.005R）下官方仓库的 `OTF/SimplifiedChinese/` 目录，`get_fonts.sh` 全部拉取（Regular/Medium/Bold/Heavy）：
  - https://raw.githubusercontent.com/adobe-fonts/source-han-sans/2.005R/OTF/SimplifiedChinese/SourceHanSansSC-Regular.otf
  - https://raw.githubusercontent.com/adobe-fonts/source-han-sans/2.005R/OTF/SimplifiedChinese/SourceHanSansSC-Medium.otf
  - https://raw.githubusercontent.com/adobe-fonts/source-han-sans/2.005R/OTF/SimplifiedChinese/SourceHanSansSC-Bold.otf
  - https://raw.githubusercontent.com/adobe-fonts/source-han-sans/2.005R/OTF/SimplifiedChinese/SourceHanSansSC-Heavy.otf
- 校验：本地 `git hash-object` 与 GitHub API 在 tag 2.005R 下给出的 blob SHA 一致（Medium `304b3e6c…`、Bold `3b33e77f…`、Heavy `149f6b80…`）；字体 name 表版本为 `Version 2.005`。SHA-256 见上表，`get_fonts.sh` 每次都校验。
- 许可提示：OFL 带保留字体名 “Source”。如果以后做子集化等修改再分发，修改版不能继续用 “Source” 命名。

### 思源宋体 SC 2.003R

- 官方发布页：https://github.com/adobe-fonts/source-han-serif/releases/tag/2.003R
- 同样取自 `OTF/SimplifiedChinese/` 目录（`get_fonts.sh` 只拉 `base.json` 声明的 Bold/Heavy；该目录另有 ExtraLight/Light/Regular/Medium/SemiBold，需要时按同一 URL 模式加）：
  - https://raw.githubusercontent.com/adobe-fonts/source-han-serif/2.003R/OTF/SimplifiedChinese/SourceHanSerifSC-Bold.otf
  - https://raw.githubusercontent.com/adobe-fonts/source-han-serif/2.003R/OTF/SimplifiedChinese/SourceHanSerifSC-Heavy.otf
- 许可提示：与思源黑体同一份 OFL，同样保留字体名 “Source”。

### 霞鹜文楷 v1.522

- 官方发布页：https://github.com/lxgw/LxgwWenKai/releases/tag/v1.522
  - https://github.com/lxgw/LxgwWenKai/releases/download/v1.522/LXGWWenKai-Regular.ttf
  - https://github.com/lxgw/LxgwWenKai/releases/download/v1.522/LXGWWenKai-Medium.ttf
- 霞鹜文楷只有 Light / Regular / Medium 三个字重，没有 Bold；Medium 是最粗的一档，用作”粗体”（`get_fonts.sh` 只拉 Regular，`base.json` 的 kai 角色只声明这一档）。

## get_fonts.sh 不下载的

- 霞鹜文楷 Medium (500)：本机已有、不在 `base.json` 的 `open.faces` 声明范围内，保留在上表备查；需要时用上面同一路径模式手动取。
- 得意黑 Smiley Sans（OFL 1.1）：本机只在剪映缓存里有 2022 版 `SmileySans-Oblique.ttf`，没有装进系统字体目录。要让 `display` 角色可分发，需要从官方发布页 https://github.com/atelier-anchor/smiley-sans/releases 另取。
- 非 OFL 的“免费商用”字体只做对比，不下载、不放进本目录：
  - 阿里巴巴普惠体：阿里自有字体法律声明。禁止修改、转换、拆分字库（子集化属于此类），禁止出售、出租或转授权；早期版本还禁止上传或转载字体文件。3.0 版是否放开转载，以官网最新声明为准。https://www.alibabafonts.com/
  - HarmonyOS Sans：HarmonyOS Sans Fonts License Agreement。不得修改；只能随软件捆绑分发原样文件，不能单独分发或出售，也不能随字体类软件分发；软件内要显著声明使用了该字体，并保留版权声明和协议；违约后许可自动终止。https://github.com/openharmony/global_system_resources/blob/master/LICENSE_Fonts
  - MiSans：小米《MiSans 字体知识产权许可协议》。不得改编或二次开发；不得单独出租、转许可、赠与、出借、进一步分发或出售字体文件；需在软件中注明使用了 MiSans；许可可撤销。https://hyperos.mi.com/font/download
  - 以上三款都可以在用户本机装好后用于自己的成片（成片可分发），但字体文件不能进开源仓库，也不能放在 OFL 许可下。
