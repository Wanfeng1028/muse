# 用户自定义正则规则「慢正则」防护设计

版本：v2.12 设计稿
对应发版报告遗留项：v2.11「未通过：正则执行风险」

## 1. 威胁模型

### 1.1 背景

用户在创建/更新匹配规则时可指定 `pattern_type = "regex"`，其 `keyword` 字段作为正则表达式由
`matching.compile_rule_pattern(pattern)` 编译，编译结果在匹配调度阶段被
`match_best` 对每条规则调用 `compiled.search(haystack)`。

`compile_rule_pattern` 仅捕获 `re.error`，对「合法但病态」的模式不做任何拦截：

```python
def compile_rule_pattern(pattern: str):
    """编译用户正则，失败返回 None（调用方跳过该规则，绝不抛异常）。"""
    try:
        return re.compile(pattern)
    except re.error:
        return None
```

### 1.2 风险

Python 标准库 `re` 使用回溯引擎（backtracking），**没有超时或步数上限机制**。某些合法
模式在特定输入上会产生指数级回溯（catastrophic backtracking），例如：

- 嵌套量词：`(a+)+$`、`(.*)*`、`(\w+)*$`
- 交替嵌套量词：`(a|a)*$`、`(a|b|ab)*c`

对输入 `"aaaa...aaab"`（约 30 个 a 加一个不匹配字符），`(a+)+$` 的匹配时间随 a 的数量
指数增长，单次 `search` 即可耗尽 CPU。

### 1.3 攻击/事故面

- **恶意规则**：任意可创建规则的用户（或经由导入/同步写库的路径）注入一条病态正则，
  即可在后续每次账单匹配调度时拖慢整个进程。
- **手误规则**：普通用户写 `(\d+)+` 这类模式本意是「一段数字」，实际落入嵌套量词陷阱。
- **放大效应**：`match_best` 对**每条** regex 规则、对**每条**待匹配交易描述执行
  `compiled.search(haystack)`。一批 N 条交易 × M 条规则 = N×M 次潜在病态回溯，
  单条坏规则即可让整批匹配从毫秒级退化到分钟级乃至挂起。
- **无超时可依赖**：不能用 signal/alarm 做超时（异步事件循环内不安全、跨平台不可靠），
  不能中断正在执行的回溯。

结论：必须在**规则写入时**拦截病态模式，并在**匹配执行时**限制输入规模，把风险面
压到可控范围。

## 2. 防护方案

零第三方依赖，全部基于标准库与既有代码路径。

### 2.a 写入时静态复杂度检查

在创建/更新规则的路由处，对 `pattern_type == "regex"` 的 `keyword` 先做安全检查，
再走既有编译校验。安全不通过时返回 `400`，`detail` 为具体原因。

实现入口：新增 `matching.check_pattern_safety(pattern: str) -> str | None`，
返回 `None` 表示安全，返回字符串表示拒绝原因。调用方（`statements` 路由）在
现有编译校验之前调用：

```
reason = matching.check_pattern_safety(payload.keyword)
if reason is not None:
    raise HTTPException(status_code=400, detail=reason)
if payload.pattern_type == "regex" and matching.compile_rule_pattern(payload.keyword) is None:
    raise HTTPException(status_code=400, detail="正则表达式非法")
```

判定规则见第 4 节。

### 2.b 匹配时长度熔断

在匹配调度执行正则 `search` 前，对 `haystack` 长度做检查：

- `haystack` 长度 > `REGEX_HAYSTACK_MAX_LEN`（常量 = 500）时，**跳过该条 regex 规则**，
  记一条 warning 日志（含规则 id、haystack 长度），继续处理后续规则。
- 该熔断只作用于 `pattern_type == "regex"` 的规则；普通子串/关键字规则不受影响。
- 阈值选 500：真实账单摘要/商户名远短于此，超长输入极可能是异常数据，跳过代价可忽略。

伪代码（写在匹配调度内、每次 `compiled.search` 之前）：

```
if len(haystack) > REGEX_HAYSTACK_MAX_LEN:
    logger.warning(
        "regex rule %s skipped: haystack length %d exceeds %d",
        rule.id, len(haystack), REGEX_HAYSTACK_MAX_LEN,
    )
    continue
```

常量 `REGEX_HAYSTACK_MAX_LEN = 500` 定义在 `matching` 模块，便于集中调整与测试引用。

### 2.c 文档化限制

在 `docs/OPERATIONS.md` 的「已知限制」小节追加：

- 用户自定义正则规则不支持嵌套量词（如 `(a+)+`）、回溯引用滥用与超长模式
  （> 200 字符），创建/更新时会返回 400 并说明原因。
- 正则匹配仅在输入（haystack）长度 ≤ 500 字符时执行，超长输入会被跳过并记录日志。
- 平台不提供正则执行超时中断（Python 标准库 `re` 无此能力），防护依赖上述
  写入期静态检查与执行期长度熔断两道闸。

## 3. 明确不做什么

- **不引入第三方 `regex` 库**：`regex` 支持超时，但会打破本项目「零第三方依赖」约定，
  并改变现有正则语义/行为，本期不做。如未来确需，另行立项评估。
- **不做真正的超时中断**：Python 标准库 `re` 不支持在回溯中途打断。基于
  `signal.alarm` 的方案在异步事件循环中不安全且非跨平台；线程池 + 强制终止无法
  安全回收 GIL 占用。因此不实现「真超时」，只做静态拒绝 + 输入长度熔断。
- **不做模式改写/自动修正**：不尝试把用户病态模式自动改写成等价安全模式（语义风险高），
  一律拒绝并给出原因。
- **不改动非 regex 规则的既有行为**：子串/关键字匹配路径保持原样。

## 4. `check_pattern_safety(pattern: str) -> str | None` 判定规则表

返回值约定：`None` = 安全；非空字符串 = 拒绝原因（同时作为 400 的 `detail`）。

判定按下列顺序执行，**首个命中的规则决定返回原因**：

| 序号 | 规则 | 判定方式 | 命中时返回的原因字符串 |
| --- | --- | --- | --- |
| 1 | 空 pattern | `pattern == ""`（空字符串） | `"正则表达式不能为空"` |
| 2 | 超长 pattern | `len(pattern) > 200` | `"正则表达式过长（最多 200 字符）"` |
| 3 | 嵌套量词 | 见下方「嵌套量词检测」 | `"正则表达式包含嵌套量词，可能导致指数级回溯"` |
| 4 | 回溯引用滥用 | 见下方「回溯引用滥用检测」 | `"正则表达式回溯引用过多，可能影响匹配性能"` |
| 5 | 其它 | 以上均未命中 | 返回 `None`（安全） |

补充说明：

- 规则 1 与规则 2 是纯长度/空值检查，先于任何结构分析。
- 规则 3、4 只做「语法级」启发式检测，目标是拦住常见病态模式，不追求完备。
- 本函数**不负责**语法合法性校验；语法非法由既有 `compile_rule_pattern` 返回 `None`
  后由路由抛 400 `"正则表达式非法"` 处理。

### 4.1 嵌套量词检测

定义：一个**量词作用域内**又出现量词，且内层作用域本身可被外层量词重复，即视为嵌套量词。

判定启发式（对 pattern 做一次线性扫描，跟踪括号深度与「分组内是否含量词」）：

- 维护栈，记录每个 `(` 分组内是否出现过量词 `* + ? {m,n}`。
- 当遇到作用于分组的量词（分组闭合 `)` 后紧跟 `* + ? {m,n}`），且该分组内
  曾出现过量词，则命中嵌套量词。
- 同时覆盖交替型嵌套：分组内包含 `|` 且分组内曾出现量词，闭合后又跟量词
  （即 `(a|b)*` 这类其中一支可被外层重复的形态，若分组内还叠加了内层量词则命中）。
- 转义字符 `\` 及其后一字符不计入量词识别；字符类 `[...]` 内的 `* + ? {` 视为普通字符，
  不参与量词统计。

命中示例：`(a+)+$`、`(.*)*`、`(\w+)*`、`([a-z]+){2,}`、`(a|ab)+c` 中若分组内含量词者。
不命中示例：`a+b*`、`\d{3}-\d{4}`、`(abc)+`（分组内无量词）、`[+*]{2}`（字符类内符号不算量词）。

### 4.2 回溯引用滥用检测

定义：模式中回溯引用（`\1` … `\9` 及其它数字反向引用）数量过多时，回溯成本显著上升。

判定启发式：

- 统计 pattern 中反向引用出现次数（形如 `\1`~`\9`，且该 `\` 未被转义）。
- 出现次数 ≥ 3 时命中。
- 出现次数 ≤ 2 时视为可接受，不单独拒绝（真正的病态组合通常也会被规则 3 捕获）。

命中示例：`(\w)\1\2\3`（含 3 个反向引用）。
不命中示例：`(\w)\1`（1 个）、`(\d{2})-\1`（1 个）。

### 4.3 与现有代码的衔接

- `matching` 模块新增 `check_pattern_safety` 与常量 `REGEX_HAYSTACK_MAX_LEN = 500`。
- `statements` 路由在 `create_match_rule`（及对应的更新路径）中，对 regex 类型
  在调用 `compile_rule_pattern` 之前先调用 `check_pattern_safety`，命中即 400。
- 匹配调度在每次 regex `search` 前做 `len(haystack) > REGEX_HAYSTACK_MAX_LEN`
  判断，超限则跳过并 warning 日志。

## 5. 测试要点（供后续实现参考）

- `check_pattern_safety`：对 `""`、长度 201 的 pattern、`(a+)+$`、`(.*)*`、`(\w+)*`、
  `(a|ab)+`（分组内含量词）、`(\w)\1\2\3` 断言返回对应原因字符串；对 `\d{3}-\d{4}`、
  `(abc)+`、`(\w)\1`、`a+b*` 断言返回 `None`。
- 路由：POST 创建 regex 规则携带 `(a+)+$` → 400 且 detail 为嵌套量词原因；
  携带非法正则（如 `(`）→ 400 且 detail 为 `"正则表达式非法"`。
- 匹配：构造长度 > 500 的 haystack，验证 regex 规则被跳过且不影响其它规则匹配结果。
</｜DSML｜ parameter>
</｜DSML｜ invoke>
</｜DSML｜ calls>
