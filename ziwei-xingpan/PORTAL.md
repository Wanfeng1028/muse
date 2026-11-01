# 紫微星盘 · 门户重构（2026-11-01）

参照某占星小程序实拍（用户 2026-11-01 亲发 7 张）借结构与功能，
把小程序从“表单演示品”升级为门户型产品。只借结构与功能，不抄
对方美术、文案与头像；紫微仍为核心，不做西洋轮盘；一切分数与
百分比必须由本站排盘引擎实算（公式见下），绝不编“% 的人觉得准”
类营销数字；无真实数据的模块用诚实态（未配置 / 待开通），不硬造。

证据：`~/workspace/ziwei-h5-preview/shots-portal/`（H5 预览，390 宽校准）。

## 门户首页（pages/index/index）

顶部日期行（公历 + 星期 + 农历，lunar-javascript 实测方法）→
用户行（昵称或“紫微星盘用户”+ 命盘状态）→ 我的命盘卡 →
今日运势卡（圆环 + 四项竖条 + 一句话 + 更多）→ 热门功能
（星座骰子 / 塔罗牌 / 六爻卜卦 / AI 解梦，HOT 角标为功能标记，
非数据）→ 八字运势 / 紫微斗数 / 星象日历三张卡 →
许愿 / 祈福 / 万年历 / 老黄历 / 星宿 / MBTI 卡片阵 →
为你推荐报告列（综合 / 爱情 / 财富 / 事业 / 学业 / 婚姻 / 合盘，
矢量渐变封面 + 本站新写一句话，无百分比）→ AI 占星师入口。

出生表单已从首页移出，独立为非 Tab 页 pages/birth/index
（首页“开始排盘”/“重新排盘”进入；“查看上次命盘”直达命盘图）。

## 今日运势公式（lib/fortune.ts，确定性、引擎唯一来源）

宫分 palaceScore(p) = 主星亮度分（庙 +8 / 旺 +6 / 得 +4 /
利 +2 / 平 0 / 不 −2 / 闲 −1 / 陷 −6 / 地 −4，仅主星）
+ 吉星每颗 +2（上限 +6）+ 煞星每颗 −3（下限 −9）
+ 生年四化落在本宫星曜（化禄 +5 / 化权 +3 / 化科 +3 / 化忌 −8；四化可落在主星也可落在文昌等辅星，代码按实际带四化的星曜计）。
维分 dimScore = clamp(60 + palaceScore, 35, 95)。
爱情 = 夫妻宫维分，财富 = 财帛宫维分，事业 = 官禄宫维分，
学习 = 父母宫维分（学业取父母宫，取文昌文曲所在之宫的传统
对应；页内已注明）。日支宫 = 当日农历日支（getDayShengXiao
映射子丑寅卯辰巳午未申酉戌亥）对应的宫；日修正 dayAdj：
该宫有吉星无煞星 +4，有煞星无吉星 −4，其余 0。
综合 = clamp(round((爱情 + 财富 + 事业 + 学习) / 4 + dayAdj), 35, 95)。
一句话按分段新写（≥80 顺 / 65–79 稳 / <65 缓），不抄参照文案。
无命盘时运势卡为诚实空态（“排盘后查看”），不编分数。
运势页（pages/fortune/index）页内展示完整公式与宫分明细。

## 新增页一览（功能 → 数据来源 / 公式 → 截图）

| 页 | 功能 | 数据来源 / 公式 | 截图 |
|---|---|---|---|
| birth | 出生表单（原首页表单原样迁移） | 本地引擎即时排盘；真太阳时 / 夏令时为手动可逆修正 | birth.png |
| fortune | 今日运势明细 | 上述公式；宫分明细 + 主星列示 | fortune.png |
| bazi | 八字运势 | 引擎 lunarInfo.fourPillars（四柱）；五行分布 = 四柱天干地支五行计数 /8；日主 = 日柱天干 | bazi.png |
| calendar | 万年历 / 老黄历 / 星宿 | lunar-javascript 1.7.3 实测方法：月历格、初一标月份、节气 getJieQi、节日 getFestivals、宜 getDayYi、忌 getDayJi、冲 getDayChong、煞 getDaySha、星宿 getXiu、干支日 getDayGan+getDayZhi 分开取；日五行该库无方法，故不展示 | calendar.png / calendar-huangli.png / calendar-xingsu.png |
| wish | 许愿 / 祈福 | 许愿：本机存储（上限 50 条，仅自己的愿望）；祈福：每日一次本机打卡 + 连续天数（仅自己的天数），祝福语 8 条按年积日轮换、本站新写；无任何“% 的人”社会证明数字 | wish.png / wish-prayer.png / wish-prayed.png（真实点一次祈福后的状态） |
| dice | 星座骰子 | 随机：12 星座 × 10 行星 × 12 宫位，组合句本站新写；页内注明纯随机娱乐 | dice.png |
| tarot | 塔罗牌 | 22 张大阿卡纳（本站新写牌意），随机抽 1 / 3 张、不放回 | tarot.png |
| liuyao | 六爻卜卦 | 三枚铜钱掷六次（3 正老阳动 / 2 正少阳 / 1 正少阴 / 0 正老阴动），自下而上成卦；卦名按文王卦序上下卦查表（64 卦组合唯一性已自检）；页内注明不附传统断语、不作吉凶断言 | liuyao.png |
| dream | AI 解梦 | 梦境日记只存本机（上限 50 条）；AI 解读走云端通道，未配置时诚实告知、不伪造解读；已配置时引导到解读页 AI 问答 | dream.png |
| mbti | MBTI 趣味测试 | 16 题全部本站自编（每维 4 题）；计分：每维选 B 过半取 B 侧，否则取 A 侧，平局取 A 侧；结果描述本站新写；页内注明非官方 MBTI、仅供娱乐 | mbti.png |
| astrologers | AI 占星师 | 4 位本站原创人格（星衡 / 月棠 / 云舟 / 灯下，名、介绍、擅长均为新写），头像为 Lucide 字形渐变圆；不展示聊过人数（无该数据）；私聊打开解读页（本地 13 维解读；AI 生成待云配置） | astrologers.png |
| compare | 合盘报告 | 与“我的 → 合盘对照”共用 CompareView；宫名已修正为引擎原名（命宫 / 财帛 / 官禄 / 夫妻 / 疾厄 / 福德），修复了旧版“财帛宫”等带后缀宫名匹配不上、5/6 宫显示“—”的 bug；数据来自云端已保存命盘，未配置时诚实空态 | compare.png |

## 星盘页分段（pages/chart/index）

西洋分段只借结构，不借内容：本命（当前盘面）/ 大运（滚动到
大运卡）/ 流年 / 流月（滚动到流年流月卡）/ 合盘（跳合盘页）。
不做三限 / 次限（西洋主限 / 次限推运），不做天象轮盘；
天象入口对应首页星象日历卡（节气 + 月相信息页），页内已注明。
新增“AI 解读星盘”Gemini 蓝大 CTA（跳解读页）。
滚动落点已用 viewport 截图实证：chart-dayun-view.png（大运卡
置顶）、interpret-dim-view.png（?dim=ganqing 落点感情卡置顶）。

## 我的页重组（pages/mine/index）

新增星币卡（余额与积分同源；充值走诚实未配置态，待微信支付
商户配置；签到 / 分享领星币跳积分中心）。服务行重组为参照
分组：会员中心、积分中心、邀请中心、档案管理（原命盘历史）、
合盘对照、报告记录（新增：仅记录用户自己打开过的解读，按日
去重，不编造浏览数据）、分享海报、我的订单、设置、联系客服
（原意见反馈）、关于（含数据来源）。其余行（组件演示等）保留，
只重组、不删除。无命盘时各入口文案指向排盘页（birth）。

## 解读页联动（pages/interpret/index）

报告行按维度直达：综合 → 解读页顶；爱情 / 婚姻 → ?dim=ganqing
（夫妻宫）；财富 → ?dim=cai；事业 → ?dim=shiye；学业 → ?dim=fumu
（父母宫）。解读页加载后 500ms 滚动到对应维度卡（Taro
createSelectorQuery + pageScrollTo，失败时静默留在顶部，不伪造
定位）。报告记录仅在有命盘打开解读页时记一条（标题“命盘解读”，
按日去重）。无命盘时文案指向排盘页。

## 登录屏修正（2026-11-01 用户纠正，本轮已落地）

小程序登录屏不再有 Google / Apple 按钮（小程序用不上谷歌，
旧 Web/App 规范生搬是错的）。主按钮 = 微信一键登录
（wx.login → login 云函数，openid 取自云函数调用上下文，
客户端不发明 JWT）；邮箱 + 密码登录 / 注册保留为次要方式
（同页分段切换、忘记密码入口保留）。云开发未配置时（envId
待用户提供）微信登录与邮箱提交均走诚实未配置态，绝不假登录。
主按钮仍为 Gemini 蓝渐变、999px 胶囊、亮色默认。
品牌标：微信一键登录按钮的绿色 WeChat 标取自中央库
`~/workspace/vendor-logos/svg/WeChat-color.svg`（Simple Icons
16.36.0 原文，#07C160），光栅化为 144px 透明 PNG
（src/assets/brand/wechat.png，源 SVG 同目录存档），置于白色
圆芯片内呈现在渐变按钮上（不改色、不手绘、不拿 Lucide 冒充）。
修复轮留下的 chrome / apple 死资产已清干净：icons.tsx 的
4 色 import、ICON_NAMES 条目、map 条目，png/chrome-*.png、
png/apple-*.png、svg/chrome.svg、apple.svg，以及两份脚本
（lucide-rasterize.cjs、gen-icons-map.cjs）ICONS 列表中的
chrome、apple；全库 grep 确认零引用（仅 Playwright 壳路径含
chrome 字样，与品牌无关）。

## 本轮修复（截图验出的问题，当轮修掉）

1. Tab 页数据过期（真 bug，不只截图问题）：Taro 的 Tab 页切走后
   不重挂载，首页 / 解读 / 我的三页若只在挂载时读本地命盘，
   用户排盘后切回 Tab 仍显示排盘前状态（门户首页重拍时亲眼
   见到：已排盘却仍显示“还没有命盘”）。修法：三页改用
   useDidShow 每次显示时重读本地命盘（与 lib/theme、custom-tab-bar
   的既有模式一致）；解读页的报告记录随显示重记（按日去重，
   同日不重复）；我的页云端刷新仍只在挂载 + 手动刷新按钮，
   显示时只重读本地命盘与本地报告记录（无云端调用）。
   命盘图页为非 Tab 页（每次 navigateTo 新实例），挂载读数即可，
   不动。
3. Tab 页跳转方式错误（真 bug，H5 截图验不出来）：首页报告列、
   命盘图 AI CTA、AI 占星师私聊、AI 解梦四处原用 navigateTo 去
   解读页，而解读页是 Tab 页，微信真机上 navigateTo 会直接报错
   “can not navigateTo a tabbar page”，等于四条主链路全断。
   修法：新增 lib/nav.ts 的 goInterpret(dim?)——switchTab 切解读
   页（Tab 页唯一合法方式），?dim= 深链经本地存储 zw_dim_target
   中转（switchTab 不带参数），解读页显示时取走并滚动落点；
   H5 直链的 router 参数路径保留。四处调用点全部改走 goInterpret。
4. OCR 审查修复（审查关发现，当轮修掉再推）：①祈福/愿望/梦境/
   报告记录的日期原用 UTC（toISOString），本地 0–8 点会差一天，
   改为本地日期函数 todayStr / yesterdayStr；②fortune.ts 末尾
   STEMS_EXPORT / BRANCHES_EXPORT 为零引用的死导出，连同 import
   一并删掉；③PORTAL.md 运势公式“四化落在本宫主星”措辞过窄
   （文昌化科等四化可落在辅星，代码按实际带四化的星曜计），
   改为“落在本宫星曜”；④六爻页注释“表见 lib/tools.ts”改为
   tools-data.ts（经 tools.ts 转出）。
2. H5 截图点击失效（仅截图 harness，不动产品代码）：
   Playwright 合成鼠标点击（含 force）在 Taro H5 的 View onClick
   上静默失效（骰子 / 塔罗 / 六爻 / MBTI 均为空态），而
   el.click() 立即生效；截图脚本的 tap 一律改为 evaluate-click。
   另：fullPage 截图无法证明 ?dim= 落点滚动，故解读维度落点
   另附一张 viewport 截图（interpret-dim-view.png）。

## 有意保留（不许擅自“修复”）

命盘选中金边（宫垣式选中特征）；黑色小 pill 中性次级样式；
知识页类色为内容色；logo（assets/logo、品牌行、头像）零改动；
Lucide 真字形；Gemini 蓝渐变；亮色默认（深色保留切换）；
v3 闭合 7 条；产品化功能（命盘连线与详情卡、表单预览卡、
悬浮底栏、6 交互组件 + 演示页）。

## 诚实残留（未配置 / 待用户项）

云开发未配置（envId 等 13 项见 docs/pending-user-items.md，
新增第 14 项：12 个新页的真机复核）→ 登录、会员、积分云端、
邀请、订单、合盘云端数据、AI 解梦、星币充值均诚实空态；
知识封面为矢量替代（无图库、外链不可上架）；TabBar 全局深色
（微信单全局配置，浅色页仍配深色栏）；weapp 真机复核未做
（H5 预览已全量验图；真机 TabBar 尺寸、低版本栅格、浅色导航栏、
环境光 fixed 行为待 envId + AppID 后复核）。
