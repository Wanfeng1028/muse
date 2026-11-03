# AI 短劇自動製作執行契約

這份契約把 `ai-short-drama` 的敘事決策、`ai-media-generator` 的媒體生成，以及選配的 `video-autopilot` 成片交付串成可續跑狀態機。只有使用者明確要求製作 AI 短劇時才走這條路；不要改變 `video-autopilot` 對一般 YouTube／Shorts／Reels 任務的預設路由。

## Dependency gate

本 Skill 可獨立完成故事設計、production pack、schema／lint 驗證、生成佇列與剪輯 handoff。要自動產生本地成片，還需要：

1. 已安裝並可呼叫 `ai-media-generator`，或有相容的圖片／影片／聲音 provider。
2. 已安裝 `video-autopilot/drama_autopilot.py`，或有能讀取 production pack 的相容剪輯執行器。
3. 目標 provider 的登入、額度與模型能力可用；需要時具備 FFmpeg。

缺少成片執行器時，把專案標成 `waiting_for_executor`，交付已驗證的 production pack 與 handoff；不可假造生成紀錄，也不可聲稱已有 `current.mp4`。

## 一句話入口

```powershell
$dramaRunner = Join-Path $env:USERPROFILE '.codex\skills\video-autopilot\drama_autopilot.py'
if (-not (Test-Path -LiteralPath $dramaRunner)) { throw 'Optional video-autopilot runtime is not installed.' }
python $dramaRunner run `
  --topic "一個被當成廢物的臨時工，其實每次打響指都能讓世界倒轉五秒" `
  --episodes 3 --duration 60 --provider browser
```

輸出專案位於 `videos/_AUTOPILOT/ai-short-drama/<project-id>/`。`state.json`、`generation_queue.json` 與 `events.jsonl` 是唯一執行真相；任何中斷都用同一個 project id 續跑，不重做已通過 QA 的任務。

## 自動狀態機

```text
題目
  → 結構化 production pack
  → schema + drama_lint 雙重驗證
  → 角色／場景／道具 anchor 任務
  → Seedance 逐鏡任務
  → 視聽 QA；失敗則依原因重試
  → FFmpeg 正規化、字幕與逐集組裝
  → duration / resolution / audio / contact-sheet QA
  → current.mp4 + publish package
  → 等待公開發布確認
```

## Browser executor 迴圈

當 `run` 回傳 `waiting_for_browser_executor` 時，主 Agent 必須自行循環，不把工作丟回使用者：

1. 執行 `next <project>` 取得唯一可執行任務。
2. 執行 `claim <project> <task-id>`。
3. 依任務 `payload.provider`、`payload.model`、`payload.prompt` 與 `reference_task_ids` 使用 `ai-media-generator`。
4. 實際檢查人物一致性、可觀察動作、液體／肢體／口型、聲音、片尾 end state；不能只看檔案存在。
5. 通過時執行 `complete ... --qc-passed`；失敗時執行 `fail ... --reason "具體原因"`。
6. 重複到佇列完成，然後執行 `build <project>`。

## 安全停點

以下狀況必須把 stage 設為 waiting 或 failed，留下明確原因：

- 登入、驗證碼、模型不可用或區域限制。
- 點數不足、付費牆或將新增不可預期費用。
- 平台實際顯示的模型能力與 prompt 的 capability gate 不符。
- 任務達到最大重試次數，或一致性／權利／合規無法確認。
- 對外公開發布。成片、標題、說明與揭露可以自動準備；最後上架必須取得使用者明確確認。

## 常用恢復命令

```powershell
python $dramaRunner status <project>
python $dramaRunner next <project>
python $dramaRunner build <project>
python $dramaRunner approve <project> --confirm
```

`approve` 只記錄可交給外部發布 adapter 的批准，不自行上傳。每集正式成片固定為 `episodes/<ep-id>/_out/current.mp4`，不累積 `final_v2_v3` 類檔名。
