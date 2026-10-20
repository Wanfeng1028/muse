# Fish Audio 角色声音母版合同

本页在使用 Fish Audio 筛选声音、生成试听、克隆已授权声音、制作声音母版或把声音资产交给 H3 时读取。Fish Audio 是外部服务；执行查询、生成或上传前都要获得当次授权。

## 1. 生产定位

Fish Audio 不默认承担全剧逐句配音。它优先承担：

- 从公开声音库筛选 1–4 个评估候选。
- 用同一句非剧情试音文本生成可盲听的 WAV。
- 把自有或已获授权的录音建立为私有声音 ID。
- 为主要角色生成 6–12 秒稳定声音母版。
- 为金额、人名、咒语和付费点台词生成必须逐字准确的整句。

普通对白仍优先走 H3 `h3-native-reference`，把批准后的母版作为 `reference_audio`；这样兼顾口型、表演和成本。

## 2. 本适配器的能力边界

本 skill 只使用 Fish 公开 OpenAPI 中以下端点：

- 公开声音检索：`GET https://api.fish.audio/model`。
- 获取声音详情：`GET https://api.fish.audio/model/{id}`。
- 创建声音克隆：`POST https://api.fish.audio/model`。
- 语音生成：`POST https://api.fish.audio/v1/tts`。
- 密钥：`FISH_API_KEY`、`FISH_API_KEY_FILE` 或 `~/.codex/secrets/fish.key`。

其他 Fish 能力不属于当前适配器；即使官方 OpenAPI 已提供，也不能在没有对应脚本、确认门和测试时临时拼接调用。需要原创音色时先在 Fish 官方界面或其他已授权流程中得到 `reference_id`，再交给本脚本；也可直接使用自有/已授权录音建立私有模型。

权威资料：

- <https://api.fish.audio/openapi.json>
- <https://docs.fish.audio/features/voice-cloning>
- <https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech>
- <https://docs.fish.audio/developer-guide/models-pricing/pricing-and-rate-limits>
- <https://fish.audio/terms/>

模型、免费期、价格、留存和商用条款会变化；每次投产前重新核对。

## 3. 免费到付费的可升级路径

`s2.1-pro-free` 资产统一登记为 `licenseScope=evaluation-only`，可以用于内部试听、角色定音和 H3 样片，不得进入商业交付。公共声音接口返回 `licensed=false` 时，即使换成付费 TTS 也不能自动视为拥有该音色的商用权。

进入商业投产时：

1. 选用 Fish 明确许可的声音，或用自有/已授权录音建立私有模型。
2. 使用具有商业许可的付费模型重制同一 `voiceAssetId`。
3. 记录模型、声音 ID、生成时间、权利凭证和新 SHA-256。
4. 重新执行 `voice-approve`；旧哈希自动失效。
5. 刷新所有引用该声音的 H3 任务并重新审批。

不能只改 JSON 标记而复用免费文件，必须重制实际音频。

## 4. 内置命令

所有命令默认只做无网络 dry-run；只有同时给 `--execute --confirm <id>` 才连接 Fish。脚本使用系统 `curl`，以兼容 Windows 系统代理；密钥只作为请求头传给 Fish，不写入日志或产物。

筛选公开声音：

```bash
node scripts/fish-voice.mjs discover \
  --id C01-search \
  --title "御姐" --language zh --count 20 \
  --out <C01-public-voices.json>
```

用 1–4 个 `reference_id` 生成同文试听候选：

```bash
node scripts/fish-voice.mjs audition \
  --id C01-audition \
  --reference-ids <id1,id2,id3> \
  --text "请把方案放在桌上。我们只讨论事实、时间和责任。" \
  --out <candidate-dir> \
  --model s2.1-pro-free
```

`audition` 会获取每个来源声音的标题、可见性和 `licensed` 标记，生成标准 44.1 kHz PCM WAV，修正流式 WAV 长度头，并写候选 JSON。候选始终登记为 `evaluation-only`、`humanApproval=pending`、`productionExportAllowed=false`。

将自有或已获授权录音建立为私有声音 ID：

```bash
node scripts/fish-voice.mjs clone \
  --id C01-private \
  --sample <authorized-sample.wav> \
  --title "C01 private voice" \
  --visibility private \
  --out <C01-fish-voice.json>
```

生成母版并自动登记到 `production.json`：

```bash
node scripts/fish-voice.mjs master \
  --production <production.json> \
  --id V-C01-MASTER \
  --character C01 \
  --reference-id <fish-reference-id> \
  --text "我知道事情没有这么简单，但我们仍然要把真相说清楚。" \
  --out <voices/C01-master.wav> \
  --model s2.1-pro-free \
  --rights unknown
```

确认 dry-run、发送文本、输出位置、范围和外部动作后，再追加：

```text
--execute --confirm <本命令的 id>
```

不得自动批量生成、自动重试或把项目剧本原文作为外部试音文本；优先使用能测试角色特征的通用句。

## 5. 候选评审

每个角色至少比较：

- 年龄与身份可信度。
- 共鸣位置、音高、气息和口音。
- 正常语速下的自然度与吐字。
- 克制、愤怒、悲伤和低声表达的可塑性。
- 与其他主要角色的可区分度。
- 多次生成的音色稳定性。

最终母版保持单人、干声、无音乐、无混响，建议 6–12 秒；输出 WAV 后人工试听，再执行 `voice-approve`。候选 WAV、Fish ID、来源许可、请求文本、模型、SHA-256 和授权范围都要留档。

## 6. 禁止事项

- 调用未出现在官方 OpenAPI 的猜测端点。
- 免费资产或 `licensed=false` 的公共声音标记成 `commercial`。
- 未经同意克隆真人、演员、主播或公众人物。
- 将私有角色声音发布为 `public`。
- 未试听就批准为角色母版。
- 免费结束后只改模型字段而不重新生成文件。
- 同一句台词同时保留 H3 原声和 Fish 后期 TTS。
