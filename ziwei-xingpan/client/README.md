# 星命盘小程序端（一期）

Taro 4 + React 18 + TypeScript，目标 weapp。排盘在本地完成，不调后端、不走服务器。

## 怎么跑

```bash
# 包管理器用绝对路径 pnpm，源先试 npmmirror
/home/hatch/.npm-global/bin/pnpm install --registry https://registry.npmmirror.com
/home/hatch/.npm-global/bin/pnpm build:weapp   # 产物在 dist/
/home/hatch/.npm-global/bin/pnpm engine:smoke  # 引擎冒烟测试（不依赖小程序环境）
/home/hatch/.npm-global/bin/pnpm typecheck
```

用微信开发者工具导入本目录即可预览；AppID 见下。

## 页面清单（一期已存在）

- pages/index/index：首页。姓名（可选）、性别、公历生日、出生钟表时间、出生地（省市经度库）。
  时间校正区：真太阳时校正、夏令时减 1 小时均为用户亲手点的按钮，可撤销，绝不自动改。
- pages/chart/index：命盘图。传统 4x4 十二宫格 + 中央信息区；每宫含宫名、干支、主星 + 亮度、
  辅星/吉星/煞星、四化标记、将前/岁前/博士十二神、大限年龄段；下方有大运、流年/流月基础展示。
- pages/interpret/index：解读。13 维（命宫、财帛、事业、感情、健康、子女、手足、迁移、田宅、福德、父母、交友、身宫）
  + 格局判断；每处下方固定免责声明。
- pages/knowledge/index：知识。星曜、宫位、四化、格局科普短条目，全部自写。
- pages/mine/index：一期静态壳。头像区与会员/积分/邀请/订单/设置/反馈/关于入口行，
  点击提示“即将上线”，二期再接；未建不存在的页面。

TabBar：首页 / 解读 / 知识 / 我的。app.config 只列一期已存在的 5 个页面。

## 引擎移植清单与剔除清单

见 src/engine/SOURCE.md。移植 15 个纯计算模块（algorithm、cities、clock-adjust、constants、dst-cn、
patterns、school-config、school-data、school-tables.generated、shier-shen、sihua、true-solar-time、
types、yunxian-context、lunar-solar）+ lunar-javascript 类型声明；引擎目录内保留原项目 MIT LICENSE 复印件。
依赖 iztro@2.5.8 + lunar-javascript@1.7.3（纯 JS）。

剔除：history.ts（React hooks + BirthForm 依赖）、share.ts（BirthForm 依赖）、db-analysis.ts、
famous.ts，以及许可红线内容 lib/nihai/*、docs/tianji-ziwei、lib/heming-knowledge、lib/seo/knowledge 原文
（一律未移植、未抄录；解读与知识文本全部自写）。

## 配置占位（用户侧待办，绝不写真实值）

- project.config.json 的 appid 目前为 "touristappid" 占位。JSON 本身不支持注释，故 TODO 记在这里：
  TODO（用户侧）：拿到真实小程序 AppID 后替换 appid；云开发 envId、微信支付商户号、广告位 ID
  一律走二期配置下发，绝不硬编码进仓库。
- 无任何真实 AppID、密钥、商户号写进代码。

## UI 基底

UIDesign app/medley 设计系统（只读来源）：tokens 转为 src/styles/variables.scss（深色主题为主：
底 #111518、卡 #1e1f23、胶囊按钮 26px、药丸标签 20px、品牌三色点、宝石蓝光标 #6ea9dd、
暖/绿/蓝三处环境光；对照与残留见 MEDLEY-COMPARISON.md）；卡片、胶囊按钮、药丸标签、底部 TabBar
按 Medley 规格手写，未引入重型 UI 库。TabBar 图标为矢量重绘几何形（房子/对话/书本/头像），
81x81 PNG 在 src/assets/tabbar/，app.config.ts 已配 iconPath/selectedIconPath。

## 已知缺口（二期及以后）

- 账号（微信登录）、会员、微信支付、积分、邀请：我的页仅静态壳，未接。
- AI 解盘/问答、广告位、分享海报、命盘历史/合盘：三期内容，一期无。
- 出生地区县级选择：源项目区县表不在 lib/ziwei 目录内，一期只到地级市/直辖市区一级。
- 命盘图中央区用 CSS grid 实现（2x2 跨格），需在真机/开发者工具复核低版本基础库的 grid 表现；
  若遇不支持，改回“中央信息卡片置于宫格上方”的布局即可，数据层不受影响。
- 免责声明文案（每处解读下方固定）：
  “内容源自传统紫微斗数文化，仅供学习与娱乐参考，不构成人生决策建议。”

## 构建结果（2026-11-01 实测）

- `pnpm typecheck`：通过。
- `pnpm engine:smoke`：通过。768 个采样盘 0 失败（12 宫齐全、地支全覆盖、命宫逆时针排布、
  紫府对称、本命四化齐全）；已知案例 1995-06-15 午时男北京盘：农历 1995-5-18、火六局、
  命宫子、身宫子，12 宫主星 + 亮度 + 四化均有输出。
- `pnpm build:weapp`：成功，Compiled successfully in 18.54s（Taro 4.3.1，webpack5）。
- dist 体积：1.4M，共 34 个文件；最大单文件 vendors.js 832 KiB（仅触发 webpack 体积警告，不影响构建）。
- 页面清单（dist/app.json 与源码一致）：pages/index/index、pages/chart/index、pages/interpret/index、
  pages/knowledge/index、pages/mine/index；TabBar：首页 / 解读 / 知识 / 我的。
- 装包：npmmirror 源可用；中途遇到两处 pnpm 隔离问题已修复（webpack 5.91.0 按 runner peer 精确指定、
  补 @tarojs/shared 与 @babel/preset-react/@babel/preset-typescript 为直接依赖，见 package.json）。
