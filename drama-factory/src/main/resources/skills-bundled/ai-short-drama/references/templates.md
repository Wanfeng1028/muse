# AI 短劇工作模板

## 目錄

1. Opportunity Map
2. Greenlight Sheet
3. Premise Contract
4. Series Bible
5. 三集 Pilot
6. 單集可拍劇本
7. Production Pack JSON
8. Audit／實驗日誌

只填能影響故事或生產的欄位。未知寫 `TBD` 並標記驗證方式，不用空泛形容詞填滿版面。

## 1. Opportunity Map

```markdown
# Opportunity Map — [市場／平台／日期]

## 一句話結論
[唯一建議方向 + 為什麼是現在]

## 已驗證需求
- 引擎：
- 觀眾情感承諾：
- 來源與日期：

## 飽和與缺口
- 已飽和同構：
- 未滿足人群／情感／形式：
- 反例：

## 原創組合
- 主引擎：
- 輔引擎（0–2）：
- 新鮮變量：
- AI 原生優勢：
- 一句話 premise：

## 最小驗證
- 3–5 集 pilot：
- 單一測試變量：
- 通過訊號：
- 停止／改版條件：
```
## 2. Greenlight Sheet

```markdown
# Greenlight — [概念名]

| 維度 | 0–5 | 證據／問題 |
|---|---:|---|
| Instant legibility | | |
| Emotional voltage | | |
| Escalation runway | | |
| Reveal runway | | |
| Freshness | | |
| AI-native spectacle | | |
| Production repeatability | | |
| Compliance / IP | | |
| **總分** | **/40** | |

決策：GO PILOT／REVISE／STOP
最大風險：
最便宜的驗證方式：
```

## 3. Premise Contract

```yaml
title: 暫名
market: 市場
surface: 平台或發行表面
format: ai_live_action | 2d_motion_comic | 3d | anthropomorphic
episode_duration_seconds: 60
planned_episodes: 30

protagonist:
  public_identity: 大家以為他是誰
  hidden_truth: 他真正是誰／能做什麼
  desire: 他主動要得到什麼
  wound_or_fear: 什麼讓他不願直接亮牌
  constraint_or_cost: 為何不能立刻全力解決

engine: 主爽感引擎
core_injustice: 第一筆必須償還的不公
audience_promise: 觀眾每個 micro-arc 可期待什麼
season_question: 觀眾追完整季想知道的問題
fresh_twist: 具體的新規則／代價／關係／視角
ai_advantage: AI 能帶來什麼非裝飾性的優勢
ending_contract: 結局至少需要兌現什麼
```

## 4. Series Bible

```markdown
# Series Bible — [標題／版本／日期]

## Premise Contract
[貼上已核准版本]

## 世界與系統規則
| 規則 ID | 能做什麼 | 不能做什麼 | 成本 | 漏洞／反例 |
|---|---|---|---|---|

## 角色卡
| ID | 公開身份 | 隱藏真相 | 欲望 | 恐懼／錯誤信念 | 資源／能力 | 表演／聲音錨 |
|---|---|---|---|---|---|---|

## Reveal Ladder
| 層級 | 揭露內容 | 誰知道 | 證據 | 改變的權力 | 目標集 |
|---:|---|---|---|---|---:|

## Antagonist Ladder
| 層級 | 對手 | 控制的資源 | 會如何學習 | 主角付出的代價 | 收束集 |
|---:|---|---|---|---|---:|

## Payoff Debt Ledger
| Debt ID | 開債事件 | 情緒 | 最晚償還 | 償還方式 | 升級出的新問題 |
|---|---|---|---:|---|---|

## Entity Registry
[依 production-pipeline.md 建立角色、地點、道具、服裝、聲音 ID]

## 結局護欄
- 必須兌現：
- 不可背叛的角色選擇：
- 不可用巧合解決：
```

## 5. 三集 Pilot

```markdown
| 集 | Cold open | Pressure／選擇 | Dominant turn | Payoff／Progress | Cliffhanger | State delta | 驗證假設 |
|---:|---|---|---|---|---|---|---|
| 1 | | | | | | | premise 可讀性 |
| 2 | | | | 第一個小回報 | | | 世界／表演接受度 |
| 3 | | | 第一次公開反轉 | | 更高階對手／代價 | | 追更能力 |
```

每列不得只寫情緒。`State delta` 要能回答「本集播完後，什麼永久不同？」

## 6. 單集可拍劇本

```markdown
# EP [N] — [集名]

時長目標：
本集 dominant turn：
本集償還／新開爽債：
State before：
State after：

## Scene 1 — [地點 ID／日夜]
目的：
角色：

[畫面可見的行為，不寫角色內心]

角色名（表演方向）：台詞

Turn：
End state：

## Scene 2...

## 集尾 Cliffhanger
- 最後可見動作／資訊：
- 觀眾上一秒的預測：
- 新預測：
- 為何必須看下一集：

## Continuation Capsule
- 知情人：
- 道具持有人：
- 傷勢／外觀：
- 關係：
- 系統狀態：
- 未償爽債：
```

## 7. Production Pack JSON

此 schema 可交給 `scripts/drama_lint.py` 驗證：

```json
{
  "project": {
    "title": "私印",
    "market": "zh-TW social",
    "format": "ai_live_action",
    "episode_duration_seconds": 60,
    "planned_episodes": 3
  },
  "premise_contract": {
    "public_identity": "被集團開除的實習生",
    "hidden_truth": "創辦人指定的危機接班人",
    "engine": "隱藏大佬／職場逆襲",
    "season_question": "她能否在不成為舊權力的情況下救回集團？",
    "fresh_twist": "每次動用接班權都必須公開一項自己的錯誤"
  },
  "characters": [
    {
      "id": "char_lin_ya",
      "name": "林雅",
      "public_identity": "失勢實習生",
      "hidden_truth": "危機接班人",
      "visual_anchor": "locked character sheet v3",
      "voice_anchor": "中低音、收斂、偏慢"
    }
  ],
  "locations": [
    {
      "id": "loc_boardroom_01",
      "name": "舊總部董事會議室",
      "visual_anchor": "locked location sheet v1"
    }
  ],
  "episodes": [
    {
      "id": "ep_001",
      "hook": "林被迫交出門禁卡時，董事長的私印從她包中落出。",
      "turn": "羞辱她的主管第一次懷疑她有董事會權限。",
      "payoff": "她用原始檔證明企劃未抄襲。",
      "progress": "觀眾知道她持有私印，但同事不知道原因。",
      "cliffhanger": "保全收到董事長親簽命令：任何人不得碰林雅。",
      "characters": ["char_lin_ya"],
      "locations": ["loc_boardroom_01"],
      "state_delta": ["主管開始懷疑林雅身份", "私印已被觀眾看見"],
      "debts_opened": [
        {"id": "debt_public_firing", "due_episode": 3}
      ],
      "debts_paid": []
    },
    {
      "id": "ep_002",
      "hook": "主管撕掉命令，聲稱它是偽造的。",
      "turn": "林選擇暫不亮明身份，改查命令外洩者。",
      "progress": "她找到偽造稽核的時間戳。",
      "cliffhanger": "時間戳的登入者竟是已故創辦人帳號。",
      "characters": ["char_lin_ya"],
      "locations": ["loc_boardroom_01"],
      "state_delta": ["林知道內部有人能使用創辦人帳號"],
      "debts_opened": [],
      "debts_paid": []
    },
    {
      "id": "ep_003",
      "hook": "主管在全員會議公開指控林偽造遺命。",
      "turn": "林公開原始稽核紀錄與私印驗證。",
      "payoff": "開除決定被撤銷，主管遭停職。",
      "cliffhanger": "董事會要求林立刻接任，但她拒絕。",
      "characters": ["char_lin_ya"],
      "locations": ["loc_boardroom_01"],
      "state_delta": ["林的權限對全員公開", "主管失去職位"],
      "debts_opened": [],
      "debts_paid": ["debt_public_firing"]
    }
  ]
}
```

`payoff` 與 `progress` 至少填一個。`--production-ready` 模式會要求角色／地點錨、角色與地點引用及非空 `state_delta`。

## 8. Audit／實驗日誌

```markdown
# Audit — [作品／集數／日期]

## 觀察
- 概念／包裝：
- 首段／turn／結尾：
- 集間留存：
- 觀眾原話的共同問題（摘要，不搬運個資）：
- 角色／聲音／畫面／剪輯錯誤：

## 診斷
- 問題層：Concept／Episode／Series／Production／Packaging
- 最可能原因：
- 競爭解釋：
- 現有證據強度：A／B／C／Q

## 下一個單變量實驗
- 只改：
- 保持不變：
- 成功訊號：
- 停止條件：
- 結果：
- 是否升格 pattern：否／候選／是（至少跨 3 個作品）
```
