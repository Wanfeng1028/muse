# 怎么用风格包(`styles/`)

风格是一个独立于代码的令牌包(`styles/*.json`):颜色、字体角色、动效节奏参数、后期强度全部在令牌里,组件代码只通过 `@accent`、`type.keyword` 这类角色名取值,换风格只换令牌文件,不改任何组件代码。写法:

- `styles/base.json` 是模板,列出所有组件会用到的键,取中性黑白值,不直接使用。
- 新风格用 `"extends": "base"`(或继承另一个已有风格)只覆盖要改的键,`render/common.py` 的 `load_style()` 会按继承链深合并。
- 现有风格包:`coldlight`(冷光,取自创意短片《在我开口之前》前半段)、`paperwhite`(纸白)、`scrapbook`(拼贴手账,取自 vlog 演示)、`kepu-explainer`(科普讲解,取自 kepu 演示)、`paper-handdrawn`(纸本手绘,取自 faceless 演示)——分镜里 `"style": "scrapbook"` 这样直接引用文件名(不带 `.json`)。
- 字体默认用可分发的开源字体(思源黑/宋、霞鹜文楷等,见 `fonts/SOURCES.md`),本机没装时退回系统字体,并在渲染报告里标记为"不可分发"——发布前确认最终用的字体角色都跑过 `scripts/get_fonts.sh` 或系统里确实装了对应字体,不要带着"不可分发"标记的成片去交付。
