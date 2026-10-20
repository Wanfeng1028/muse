# 字体说明

把用到的字体文件放进这个目录，并在 `src/theme.ts` 的 `fonts` 数组里登记（family 必须和文件里的字体名一致）。

**不要依赖系统字体。** 渲染环境不同，系统字体可能不存在，中文会回退成难看的字体甚至方块。控制台出现
`[code-film] 字体加载失败` 警告，就说明文件缺失或路径不对。

推荐的免费可商用字体（下载后放到这里）：

| 字体 | 用途 | 下载 |
|---|---|---|
| JetBrains Mono（已内置 woff2） | 等宽、代码、字符画 | 已在模板里（许可证见本目录 `LICENSE-JetBrainsMono.txt`） |
| 思源宋体 Noto Serif SC | 电影感标题、诗意正文 | fonts.google.com/noto |
| 思源黑体 Noto Sans SC | 通用正文、标题 | fonts.google.com/noto |
| 得意黑 Smiley Sans | 潮流 PV 标题 | github.com/atelier-anchor/smiley-sans |
| 霞鹜文楷 LXGW WenKai | 手写感、文艺 | github.com/lxgw/LxgwWenKai |

theme.ts 默认登记了三个字体文件。JetBrains Mono 已内置；两个 Noto 字体文件较大，需要自己下载放进来
（文件名对不上就改 theme.ts）。不放的话渲染仍能进行，但中文用的是回退字体，效果会差很多。
