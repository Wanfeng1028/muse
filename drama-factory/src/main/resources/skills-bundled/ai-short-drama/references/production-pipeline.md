# AI 短劇生產管線

## 目錄

1. 生產原則
2. 形態路由
3. 完整管線
4. Entity Registry
5. Episode State Ledger
6. Scene／Shot Card
7. 跨 Skill 交接
8. 修復矩陣

## 1. 生產原則

短劇不是一支 30 分鐘影片，而是一組需要共享人物、世界、狀態與懸念的短單元。預設採多階段管線：

```text
Premise → Bible → Pilot → Entity Registry → Style Probe
→ Episode Script → Scene Cards → Still Anchors → I2V
→ Voice / Audio → Story Cut → Polish → QA → State Handoff → Publish
```

硬規則：

- 劇情不清楚時回劇本層修，不用更多特效掩蓋。
- 人物長相錯誤時回 still／reference 層修，不反覆抽影片碰運氣。
- 動作、運鏡或口型錯誤時只重做該 shot。
- 每個鏡頭必須對應一個可觀察事件，不能只有形容詞。
- 先做一個最難場景與一個高頻場景的 style／cost probe，再估整季成本。
- 所有生成提示詞都引用固定 entity ID；描述更新只改 registry，不在各集散落改字。

## 2. 形態路由

### AI 仿真人

適合：都市逆襲、隱藏身份、豪門、復仇、懸疑。

優點：情感直覺、真人戲劇語法成熟。風險：臉、手、口型、多人互動、服裝延續。優先鎖定人物正／側／全身與關鍵表情 still。

### 2D 漫劇

適合：系統、修仙、末世、規則怪談、長季連載。

優點：資產化容易、可承受高概念場景。風險：只做靜態圖推拉、缺乏表演與空間關係。每場至少安排姿態、視線、道具或構圖變化。

### 3D／半 3D 動畫

適合：固定世界、高重用角色、戰鬥或奇觀型長季。

優點：角色與場景可重用。風險：前期資產成本高、表演僵硬。先確認回本集數再做完整 rig。

### 擬人動物／物件荒誕劇

適合：社群原生短篇、喜劇、反差寓言。

優點：AI 原生感強、跨語言。風險：角色雖可愛但沒有慾望與事件，只剩梗圖。仍需 Premise Contract 與 state delta。

## 3. 完整管線

### Gate A — Story Lock

輸入：Premise Contract、三集 pilot、Reveal／Antagonist／Payoff ladders。

通過條件：

- 第 1 集在最短時間內證明主角的表面身份與隱藏真相有差距。
- 三集內至少償還一筆爽債並打開更大問題。
- 每集有不同 dominant turn，不重複同一輪羞辱。
- 可用一句話說清每集 `state_before → event → state_after`。

### Gate B — Asset Lock

建立角色、場景、道具、服裝、傷勢與聲音的 registry。為主角色至少保存：

- 正面、3/4 側面、側面、全身比例
- 中性、壓抑、警覺、勝利後克制等核心表情
- 固定髮型、服裝組、配件與特殊標記
- 說話速度、音域、口音、能量與禁用表演

### Gate C — Style／Cost Probe

只生成：

1. 一個高頻對話／衝突場景；
2. 一個最難的能力、戰鬥、群像或奇觀場景。

記錄成功率、每個可用 shot 的時間／成本、返工原因、資產可重用率。若最難場景不可穩定生成，先改劇本或形態，不把風險推到量產期。

### Gate D — Episode Compile

把可拍劇本拆成 scene cards，再拆成 shots。先產 still anchors，再做 I2V。對白與旁白最後才進行精確時長配合，避免畫面被臨時音訊綁死。

### Gate E — Story Cut

只用必要畫面、暫時聲音與基本字幕檢查：

- 不讀簡介是否看懂誰想要什麼？
- 一次觀看是否看懂權力／資訊在何處翻轉？
- 拿掉音樂後事件是否仍成立？
- cliffhanger 是否造成一個明確未完成動作或新預測？

故事通過才做配樂、音效、調色、轉場與字幕精修。

### Gate F — Continuity QA

逐項核對：registry、狀態帳本、知情人、物品持有人、服裝、傷勢、時間、場所、系統資源、未償爽債。通過後才輸出下一集 continuation capsule。

## 4. Entity Registry

所有 ID 使用穩定、簡短、語義清楚的 ASCII：

```yaml
characters:
  - id: char_lin_ya
    name: 林雅
    public_identity: 失勢實習生
    hidden_truth: 集團創辦人指定的危機接班人
    visual_anchor: 正／側／全身參考與不可變特徵
    performance_anchor: 收斂、觀察先於反應、勝利時不張揚
    voice_anchor: 中低音、偏慢、句尾不揚
    wardrobe_sets: [ward_lin_office_01]

locations:
  - id: loc_boardroom_01
    name: 舊總部董事會議室
    visual_anchor: 深木牆、狹長窗、午後逆光、無現代霓虹

props:
  - id: prop_seal_01
    name: 創辦人私印
    holder: char_lin_ya
    reveal_level: 2

voices:
  - id: voice_lin_ya_zh
    actor_or_model: licensed_voice_reference
    consent_status: verified
```

不要建立 `beautiful_woman_2`、`same_room_but_darker` 這類會漂移的 ID。別名只在 registry 保存，不在 prompt 中輪流使用。

## 5. Episode State Ledger

每集結束保存：

```yaml
episode_id: ep_003
knowledge:
  char_lin_ya: [knows_audit_was_forged]
  char_rival_chen: [suspects_lin_has_board_access]
possessions:
  prop_seal_01: char_lin_ya
wounds_or_appearance:
  char_lin_ya: left_wrist_bandage
relationships:
  lin_to_chen: open_hostility
payoff_debts_open: [debt_public_firing]
payoff_debts_paid: [debt_stolen_credit]
reveal_levels:
  audience: 2
  char_rival_chen: 1
system_state:
  credits: 12
  cooldown: 8h
continuation_capsule: 陳已看見私印盒但未看見印章；林左腕仍包紮。
```

`audience` 與角色的知情程度必須分開。懸念常來自觀眾知道、角色不知道，或角色知道、觀眾只看見後果。

## 6. Scene／Shot Card

### Scene Card

```yaml
scene_id: ep003_sc02
purpose: 公開償還被偷功勞的爽債
location_id: loc_boardroom_01
characters: [char_lin_ya, char_rival_chen]
state_before: 陳控制會議，林被要求道歉
event: 林讓投影顯示帶時間戳的原始稽核紀錄
state_after: 陳失去可信度，董事開始詢問林的權限來源
turn: 資訊權力由陳轉到林
end_hook: 董事長認出林手中的私印盒
```

### Shot Card

```yaml
shot_id: ep003_sc02_sh04
duration_target: 2.4s
frame_intent: 先看見時間戳，再看見陳的反應
entities: [char_rival_chen, prop_audit_screen]
observable_action: 陳的手停在遙控器上，目光從日期移向林
camera: 50mm medium close-up, slow 10cm push-in
audio: 投影機風扇聲停頓後，會議室低語升起
continuity: 陳右手持遙控器；領帶仍略鬆
end_state: 陳第一次失去發言節奏
negative: 不開口說話，不看鏡頭，不新增文件
```

描述「緊張、史詩、電影感」不能替代 observable action。

## 7. 跨 Skill 交接

### 交給 `ai-media-generator`

傳入：

- 鎖定的 entity registry
- 形態與平台比例
- style／cost probe 結果
- scene／shot cards
- 每鏡 reference IDs、可觀察動作、鏡頭、音訊意圖、end state、negative constraints

要求它回傳：模型／平台路由、逐資產 prompt、reference 使用方式、生成順序、失敗重試策略；不要讓它改寫季弧。

### 交給 `video-autopilot`

傳入：

- 已核准的 story cut 順序
- shot 素材與音訊
- 字幕規則、節奏點、音樂／音效意圖
- continuity QA 與發行表面

要求它負責組裝、剪輯 QA、輸出、發布包與結果日誌；不要讓剪輯任意刪除 turn 或 cliffhanger。

### 交給 `video-craft-playbook`

只交付平台包裝：首幀、標題、caption、預告切片與 repurpose。故事真相揭露不可被包裝提前洩漏。

## 8. 修復矩陣

| 症狀 | 回到哪一層 | 優先修法 |
|---|---|---|
| 變臉、年齡漂移、服裝改變 | Asset Lock | 強化 still anchors、固定 ID、減少同鏡角色數 |
| 動作不自然、物理錯 | Shot／I2V | 簡化為單一可觀察動作、縮短 shot、重做影片 |
| 聲音無情緒、口型差 | Voice／edit | 改 performance direction、分句、用反應鏡頭遮接 |
| 漂亮但看不懂 | Script／Scene | 重寫 state change 與畫面因果 |
| 集與集狀態重置 | State Ledger | 補 knowledge／possession／appearance／relationship |
| 每集像同一輪打臉 | Season | 升級 Antagonist Ladder，改變權力與代價 |
| PPT 感 | Scene／Shot | 增加角色互動、空間變化、具體動作；刪全文旁白 |
| 後段品質崩壞 | Probe／batch | 降低批次、鎖版本與資產、逐 micro-arc 驗收 |
