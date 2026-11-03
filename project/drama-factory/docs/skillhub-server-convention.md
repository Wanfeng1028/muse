# 官网 SkillHub 服务端约定

> 面向：项目官网（剧坊/Playhouse）侧实现 skillhub 服务的同学。
> 客户端实现：`drama-factory/src/main/java/com/dramafactory/service/skill/SkillHubClient.java`
> 配置项：`drama.skillhub.base-url`（环境变量 `DRAMA_SKILLHUB_BASE_URL`），为空则客户端禁用远端。

## 1. 目标

用户在软件内的"官方 Skill 库"点击安装 skill 时，若该 skill 非内置，则客户端直接从官网
skillhub 下载 skill 包并安装到本地 `data/skills/<id>/`。本约定定义服务端需要暴露的
HTTP 接口、数据格式与安全要求。

## 2. 接口

基地址：`{baseUrl}`，如 `https://www.playhouse.example.com/skillhub`。

### 2.1 GET {baseUrl}/manifest.json —— skill 清单

返回所有上架 skill 的元数据。客户端每次打开官方列表 / 安装时拉取（建议服务端加
`Cache-Control: max-age=300`，客户端不做强缓存）。

```jsonc
{
  "hub": "playhouse-skillhub",   // 固定标识，客户端可校验
  "version": 1,                  // manifest 格式版本（整数）
  "updatedAt": "2026-10-19T00:00:00Z", // ISO-8601，展示用
  "skills": [
    {
      "id": "video-shots",              // 必填，^[a-z0-9][a-z0-9._-]*$，全局唯一且不可变
      "name": "video-shots",            // 展示名，可与 id 相同
      "version": "1.0.0",               // 必填，语义化版本，客户端按此比对升级
      "description": "拉片：把成片拆成逐镜头分析表……", // 一句话描述
      "author": "eternityspring",        // 作者
      "license": "Apache-2.0",          // SPDX；只上架 MIT / Apache-2.0 的 skill
      "packageUrl": "skills/video-shots/1.0.0.zip", // 必填；相对路径按 baseUrl 解析，也可写绝对 URL
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", // 推荐必填，见 §4
      "minAppVersion": "3.0.0"          // 可选；客户端版本低于此值时提示升级软件（客户端 v1 暂只展示）
    }
  ]
}
```

字段缺失策略（客户端行为）：`id` 缺失的条目直接跳过；其余缺失转空串；
`packageUrl` 缺失的 skill 在安装时报"缺少 packageUrl"。

### 2.2 GET {packageUrl} —— skill 包下载

- 内容：zip 压缩包，**解压后根目录即 skill 内容**（必须含 `SKILL.md`）。
- 要求：`Content-Length` 正确；支持断点续传（`Accept-Ranges`）为加分项，非强制。
- 同一 skill 的多版本：建议按 `skills/<id>/<version>.zip` 组织，URL 永久有效（客户端可能安装旧版本）。

### 2.3 skill 包（zip）格式

```
<zip 根>/
  SKILL.md            # 必填，frontmatter：name/version/description/author（见 §3）
  scripts/            # 可选
  references/         # 可选
  assets/             # 可选
```

- zip 内不许含 `..` 或绝对路径条目（客户端做 zip-slip 校验，非法直接拒绝安装）。
- 建议 zip < 20MB；超大 skill 考虑拆分或走对象存储直链。

### 2.4 SKILL.md frontmatter（服务端打包时可校验）

```yaml
---
name: video-shots        # 必填
version: 1.0.0           # 必填，应与 manifest 中的 version 一致
description: |           # 一句话，多行用 |
  拉片：把成片拆成逐镜头分析表。
author: eternityspring    # 可选
metadata:
  license: Apache-2.0    # 建议
---
```

## 3. 版本比对（客户端规则，服务端只需保证 version 规范）

- 语义化版本 `MAJOR.MINOR.PATCH`，可带 `-`/`​.` 后缀（如 `1.0.0-beta.1`）。
- 比较：按 `[.-]` 切分逐段比，全数字段按数值比，否则按字符串比；缺段视作 `0`。
- 安装幂等：已安装版本 == 目标版本时客户端直接返回"已安装"，不重复下载。

## 4. 校验与签名（安全要求）

1. **sha256（强推荐）**：manifest 中每个 skill 给出包文件的 SHA-256（小写 hex）。
   客户端下载后必校验，不一致则删除文件并报错，**不安装**。
2. **签名（可选增强）**：如需防篡改，可在 manifest 根加：
   ```jsonc
   { "signature": { "alg": "ed25519", "keyId": "2026-01", "value": "<base64>" } }
   ```
   签名覆盖对象为**按 key 排序后的 skills 数组的规范 JSON**（canonical JSON：无空白、key 排序、
   UTF-8）。客户端 v1 暂不验签，服务端可先预留字段。
3. **传输安全**：生产环境必须 HTTPS；manifest 与 zip 建议同源（同 baseUrl 下）。
4. **版权**：只上架 MIT / Apache-2.0（或经书面授权）的 skill；manifest 的 `license` 字段
   必须与 skill 包内声明一致；建议在官网 skillhub 页面公示每个 skill 的来源仓库与许可证。

## 5. 最小可用服务端（示例）

静态文件服务即可满足 v1：

```
skillhub/
  manifest.json
  skills/
    video-shots/
      1.0.0.zip
      1.1.0.zip
```

Nginx/COS/OSS 托管 + 正确 Content-Type（manifest `application/json`，zip `application/zip`）即达标。
后续需要审核流、灰度、统计时再做动态服务。

## 6. 变更记录

- v1（2026-10-19）：首版约定，随官方 Skill 库客户端一起落地。
