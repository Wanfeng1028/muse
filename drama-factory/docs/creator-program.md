# 创作者计划 v1 功能文档

## 1. 功能

- **创作者列表**：支持按关键词搜索，支持排序
- **创作者详情页**：展示创作者统计数据与技能列表
- **个人资料**：用户可创建/编辑自己的创作者主页
- **关注体系**：支持关注/取消关注创作者

## 2. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/creators` | 创作者列表(支持搜索与排序) |
| GET | `/api/creators/{handle}` | 创作者详情(含统计与技能列表) |
| POST | `/api/creators` | 创建自己的创作者资料 |
| PUT | `/api/creators/{handle}` | 编辑自己的创作者资料 |
| POST | `/api/creators/{handle}/follow` | 关注该创作者 |
| DELETE | `/api/creators/{handle}/follow` | 取消关注该创作者 |
| GET | `/api/creators/feed?limit=20` | 关注动态：当前用户关注的创作者新发布的 Skill，按发布时间倒序 |
| GET | `/api/creators/following` | 我的关注列表：当前用户已关注的创作者，按关注时间倒序 |

## 3. 统计口径

- **技能统计**：以 `Skill.author` 字段匹配创作者，handle 或 displayName 命中均计入
- **粉丝数**：取真实关注关系(follow 表)的行数，不做去重估算
- **收益数据**：v1 不提供任何收益、分成数字，商业化激励规则仍在评审中，待定后再补充

## 5. 关注动态（v2）

- **接口**：`GET /api/creators/feed?limit=20`，limit 取值 1–50，超出抛 400（`limit 参数非法`）。
- **口径**：只含当前用户已关注的创作者名下 Skill；匹配规则与详情统计一致（Skill.author 等于 handle 或 displayName，同一 Skill 按 id 去重）；按 Skill 发布时间倒序，发布时间为空排最后；关注关系指向的档案已删除时跳过该关系。
- **前端**：创作者页「关注动态」卡片展示动态列表（创作者 + Skill 名 + 安装数 + 评分 + 描述 + 发布时间），无动态时显示诚实空态（未关注，或关注的创作者暂未发布新 Skill）；页面加载与关注/取消关注成功后自动刷新，另有刷新按钮可手动刷新。
- **收益数据**：v2 同样不提供任何收益、分成数字。

## 6. 我的关注列表（v3）

- **接口**：`GET /api/creators/following`，无分页参数；当前用户已关注的创作者按关注时间倒序（关注时间为空排最后）；关注关系指向的档案已删除时跳过该关系。
- **条目**：handle/displayName/bio + 技能数（与详情统计一致：Skill.author 等于 handle 或 displayName，按 id 去重）+ 粉丝数（真实 follow 行数）+ 最新 Skill 名称与发布时间（名下 Skill 中发布时间最晚的一条，无发布时间的 Skill 不计入最新；名下无 Skill 时两项均为 null）+ 关注时间 followedAt。
- **前端**：创作者页「我的关注」卡片（`#creatorFollowing` 列表 + `#creatorFollowingEmpty` 诚实空态 + `#creatorFollowingRefresh` 刷新按钮）；每条含取消关注按钮（调 `DELETE /api/creators/{handle}/follow`，成功后同时刷新关注列表、关注动态与创作者列表）；页面加载与详情卡关注/取消关注成功后自动刷新。
- **收益数据**：v3 同样不提供任何收益、分成数字。

## 7. 为你推荐（v4）

- **接口**：`GET /api/creators/recommended?limit=10`，limit 取值 1–50，超出抛 400（`limit 参数非法`）。
- **口径**：排除当前用户已关注的创作者与 ownerId 为当前用户的本人主页；其余创作者按粉丝数倒序、技能数倒序、创建时间倒序排列并截断至 limit；技能数与最新 Skill 口径与第 6 节一致（handle 与 displayName 匹配、按 id 去重；最新取发布时间最晚且发布时间非空的一条）。
- **前端**：创作者页「为你推荐」卡片（`#creatorRecommended` 列表 + `#creatorRecommendedEmpty` 诚实空态 + `#creatorRecommendedRefresh` 刷新按钮）；每条含关注按钮（调 `POST /api/creators/{handle}/follow`，成功后同时刷新推荐列表、我的关注、关注动态与创作者列表）；页面加载与详情卡关注/取消关注、关注卡取消关注后自动刷新推荐。
- **收益数据**：v4 同样不提供任何收益、分成数字。

## 4. 校验规则

- **handle**:3–50 个字符，仅允许小写字母、数字和连字符；重复 handle 创建时将被拒绝
- **displayName**:1–100 个字符
- **bio / website**:最长 500 个字符
