## 审查范围

本次 QA 审查对象为 Toonflow 二阶段 4 个媒体 provider 描述符文件：

- `data/providers/toonflow-apimart.json`
- `data/providers/toonflow-compshare.json`
- `data/providers/toonflow-metaso.json`
- `data/providers/toonflow-tfrouter.json`

审查方式为纯静态审查：以 4 份 JSON 全文为唯一事实来源，逐字核对 schema 结构、模板变量、路径映射与 doc 描述的自洽性。不发起任何外部请求，不做真实接口联调。本次仅审查，不修改任何 JSON 文件。

审查维度：
1. 顶层 schema 一致性（八键：id/label/version/models/auth/submit/poll/doc）
2. 模板变量完备性（{{model}}/{{prompt}}/{{seconds}}/{{taskId}}）
3. taskIdPath 与 submit 响应结构的自洽性
4. statusMap 的 COMPLETED/FAILED 映射完备性与 statusPath 自洽性
5. auth.keyRef 的 env: 前缀与全大写命名规范
6. models 的 id 命名风格一致性
7. doc 字段对鉴权、任务跟踪、限制的说明完备性

## 逐项结论

### toonflow-apimart.json

**通过项**
- 顶层八键齐全：id、label、version、models、auth、submit、poll、doc 均存在。
- 模板变量齐全：submit.body 含 `{{model}}`、`{{prompt}}`、`{{seconds}}`；poll.url 含 `{{taskId}}`。
- taskIdPath 为 `data.data.0.task_id`，与 doc 描述"任务 id 位于 data.data[0].task_id"一致，自洽。
- statusPath 为顶层 `status`，statusMap 覆盖 completed/success/Completed/Success → COMPLETED，failed/failure/Failed/Failure → FAILED，映射完备。
- auth.keyRef 为 `env:APIMART_API_KEY`，env: 前缀 + 全大写，规范。
- doc 明确写出鉴权方式（Bearer + 环境变量 APIMART_API_KEY）、任务跟踪方式（data.data[0].task_id → 轮询取最终视频地址）、海外节点替换说明，并注明限制"仅覆盖文本生视频，参考图等高级模式不支持"，说明完备。

**问题项**
- 无。

**建议项**
- models 的 id 风格为 `seedance-2.5`、`seedance-2.0`、`wan3.0-video`，与 tfrouter 的 `Seedance 2.5`、`wan-3.0` 风格不一致（详见跨文件共性问题）。
- statusMap 键中同时存在 completed/success/Completed/Success 四类大小写变体，属防御性写法，可接受；若上游状态取值可枚举，建议在 doc 中标注实际取值以减少冗余。

### toonflow-compshare.json

**通过项**
- 顶层八键齐全。
- 模板变量齐全：submit.body 含 `{{model}}`、`{{prompt}}`、`{{seconds}}`；poll.url 含 `{{taskId}}`。
- taskIdPath 为 `output.task_id`，与 doc 描述"提交后由 output.task_id 跟踪任务"一致，自洽。
- statusPath 为 `output.task_status`，statusMap 覆盖 Success → COMPLETED，Failure/Expired/Cancelled/Canceled → FAILED，COMPLETED/FAILED 两侧均有映射。
- auth.keyRef 为 `env:MODELVERSE_API_KEY`，规范。
- doc 明确写出鉴权（Bearer + MODELVERSE_API_KEY）、任务跟踪（output.task_id → output.task_status 映射）、限制（"仅收录公开分支；H3 分支使用另一套地址与密钥，此处不含，MiniMax H3 请使用独立 provider"），说明完备。

**问题项**
- 无。

**建议项**
- statusMap 未包含成功侧的 `Completed`/`completed` 或失败侧其他大小写变体，若上游存在大小写差异可能漏映射；建议在 doc 中标注上游实际状态取值以确认覆盖度。
- models 仅收录 1 个模型（doubao-seedance-2-0），与 doc"仅收录公开分支"一致，无需改动。

### toonflow-metaso.json

**通过项**
- 顶层八键齐全（键顺序与 tfrouter 不同，不影响完备性）。
- 模板变量齐全：submit.body 含 `{{model}}`、`{{prompt}}`、`{{seconds}}`；poll.url 含 `{{taskId}}`。
- taskIdPath 为 `task_id`，与 doc 描述"提交任务后返回 task_id"一致，自洽。
- statusPath 为 `task.status`，statusMap 覆盖 succeeded/Succeeded → COMPLETED，failed/Failed → FAILED，两侧均有映射。
- auth.keyRef 为 `env:METASO_API_KEY`，规范。
- doc 明确写出鉴权（METASO_API_KEY）、任务跟踪（task_id → task.status → task.content.url / task.error），说明完备。

**问题项**
- 无。

**建议项**
- submit 未声明 headers（无 Content-Type），与其他三个文件（apimart/compshare 显式声明 Content-Type，tfrouter 亦未声明）风格不一致；本项属风格观察，不判定为问题。
- statusMap 成功侧仅覆盖 succeeded/Succeeded，失败侧仅覆盖 failed/Failed，未包含 completed 等其他可能取值；建议在 doc 中标注上游状态枚举以确认覆盖度。

### toonflow-tfrouter.json

**通过项**
- 顶层八键齐全（键顺序与 metaso 不同，不影响完备性）。
- 模板变量齐全：submit.body 含 `{{model}}`、`{{prompt}}`、`{{seconds}}`；poll.body 含 `{{taskId}}`（该文件以 POST body 传 taskId，符合其接口形态）。
- taskIdPath 为 `data`，与 doc 描述"从 data 字段取任务标识"一致，自洽。
- statusPath 为顶层 `status`，statusMap 覆盖 success/completed/Success/Completed → COMPLETED，failed/failure/error/rejected/Failed/Failure/Error/Rejected → FAILED，映射完备。
- auth.keyRef 为 `env:TOONFLOW_TF_ROUTER_KEY`，规范。
- doc 明确写出鉴权（官方 TF-Router Key + TOONFLOW_TF_ROUTER_KEY）、无 Key 时的行为（"抛清晰错误，不影响其他通道"）、任务跟踪（data → POST 轮询 → data.data / data.failReason），说明完备。

**问题项**
- 无。

**建议项**
- models 的 id 为 `Seedance 2.5`、`Seedance 2.0`、`wan-3.0`、`MiniMax-H3`，与 apimart/compshare 的 slug 风格不一致（详见跨文件共性问题）。
- poll.body 中键名为 `taskICode`（大写 I），与 taskIdPath 返回字段名 `data` 无直接对应关系；该键名疑为上游接口约定，本次静态审查无法判定对错，建议在 doc 中补一句说明该字段来源，以降低后续维护歧义。

## 跨文件共性问题

1. **models.id 命名风格不统一（建议项）**
   - apimart：`seedance-2.5`、`seedance-2.0`、`wan3.0-video`（小写 slug，点号连接，部分带后缀）
   - compshare：`doubao-seedance-2-0`（小写 slug，连字符）
   - metaso：`MiniMax-H3`（大小写混合，连字符）
   - tfrouter：`Seedance 2.5`、`Seedance 2.0`、`wan-3.0`、`MiniMax-H3`（含空格与点号，与 slug 风格混用）
   - 结论：4 文件内部各自自洽，但跨文件风格不统一，建议统一为小写 slug（如 `seedance-2.5`、`wan-3.0`、`minimax-h3`），并在 label 中保留展示名。

2. **statusMap 大小写覆盖策略不一致（建议项）**
   - apimart 与 tfrouter 覆盖了多组大小写变体，compshare 与 metaso 覆盖较少。
   - 结论：属防御性写法差异，不构成 schema 违规；建议以 doc 标注上游实际状态枚举，避免冗余或漏映射。

3. **submit.headers 声明不一致（建议项）**
   - apimart、compshare 显式声明 `Content-Type: application/json`；metaso、tfrouter 未声明。
   - 结论：若上游对 Content-Type 有要求，缺省可能导致提交失败；建议统一显式声明或在 doc 中说明默认行为。

4. **poll 方法差异（通过项，非问题）**
   - apimart/compshare/metaso 使用 GET + URL 传 taskId；tfrouter 使用 POST + body 传 taskId。
   - 结论：各文件与自身 doc 描述自洽，属接口形态差异，不判定为问题。

5. **taskIdPath 形态差异（通过项，非问题）**
   - 分别采用 `data.data.0.task_id`、`output.task_id`、`task_id`、`data` 四种形态，均与各自 doc 描述一致，自洽。

## DoD 小结

- **schema 完备性（八键齐全）**：通过。4 文件均含 id/label/version/models/auth/submit/poll/doc，键顺序差异不影响完备性。
- **模板变量完备性**：通过。4 文件 submit.body 均含 `{{model}}`/`{{prompt}}`/`{{seconds}}`；poll 均含 `{{taskId}}`（apimart/compshare/metaso 在 URL，tfrouter 在 body）。
- **taskIdPath 自洽性**：通过。各文件 taskIdPath 与自身 doc 描述一致。
- **statusMap COMPLETED/FAILED 映射完备性**：通过。4 文件均同时具备成功侧与失败侧映射。
- **auth.keyRef 规范（env: + 全大写）**：通过。4 文件均符合。
- **models.id 命名风格统一**：建议。跨文件风格不统一，记为建议项，不阻断交付。
- **doc 字段说明完备性**：通过。4 文件均说清鉴权、任务跟踪与限制；apimart"仅文本生视频"、compshare"H3 分支不含"为明确优点。
- **真实接口联调**：未验证。本次为纯静态审查，未发起任何外部请求，所有映射与路径结论均基于 JSON 文本与 doc 描述的内部自洽性判断。
- **JSON 原文改动**：不适用。本次仅审查，未修改任何描述符文件。

总体结论：4 个描述符在 schema 完备性、模板变量、taskIdPath 自洽性、statusMap 双侧映射、auth.keyRef 规范、doc 说明完备性上均判定通过；跨文件存在 models.id 命名风格、statusMap 大小写覆盖、submit.headers 声明三项一致性问题，均记为建议项，不阻断交付。真实接口联调结论待后续联调阶段补充。
