# docseek v09 评测失败分类报告

## 1. 概述

本次分析基于 `doctests_full.log` 中记录的可复现失败样本。需要特别说明的是，v09 评测日志存在不完整问题：`eval_v09_new.log` 仅 33 字节，无法提供有效信息；`PROJECTS.md` 中记录的 134 项失败数缺乏对应的详细日志支撑。因此，本报告仅针对 `doctests_full.log` 中明确出现的 `TokenizerPunctTest` 系列失败进行实证分析。

## 2. 失败分类

根据失败性质，可将评测失败划分为以下三类：

- **回归（Regression）**：指此前版本通过、当前版本失败的用例，通常由近期代码变更引入。
- **环境（Environment）**：指因机器配置、依赖版本或外部服务差异导致的失败，与代码逻辑无关。
- **真问题（Real Bug）**：指代码逻辑与预期行为不一致，属于需要修复的实质缺陷。

## 3. 基于样本的失败分析

从 `doctests_full.log` 中提取的失败样本如下：

```
Expected: (hitCount(searcher, "，")) >= (1u), actual: 0 vs 1
[  FAILED  ] TokenizerPunctTest.FullWidthPunctuationDoesNotPollute
[  FAILED  ] TokenizerPunctTest.HalfWidthPunctuationDoesNotPollute
[  FAILED  ] TokenizerPunctTest.SpecialSymbolsDoNotPollute
[  FAILED  ] TokenizerPunctTest.OnlyPunctuationYieldsNoHits
[  FAILED  ] TokenizerPunctTest.MixedWidthPunctuationKeepsBothScripts
```

**失败模式**：中文/英文标点符号（如 `，`、`。`、`！`、`；`、`.`、`#`）被分词器过滤，未产生有效 token，导致 `hitCount` 为 0。

**分类判定**：`TokenizerPunctTest` 系列失败属于**真问题**。该系列失败并非环境差异或回归所致，而是分词器的标点处理逻辑与测试期望存在直接冲突。测试期望标点符号不应污染检索结果（即不应产生命中），但当前分词器在遇到标点时未能正确跳过或将其视为无意义 token，导致 `hitCount` 异常为 0，与预期行为不一致。

## 4. 修复建议方向

针对上述真问题，建议从以下方向进行排查与修复（不涉及具体代码实现）：

1. **分词器标点过滤策略审查**：检查分词器在预处理阶段对标点符号的处理逻辑，确认其是否将标点视为独立 token 或直接丢弃。需确保标点不会进入倒排索引，也不会影响有效词的切分。
2. **Unicode 标点分类完善**：验证分词器是否覆盖了全角（FullWidth）与半角（HalfWidth）标点，以及特殊符号（如 `#`、`@` 等）的 Unicode 分类。当前失败样本显示中英文标点均未被正确处理，说明标点识别范围存在遗漏。
3. **空查询与纯标点查询的边界处理**：针对 `OnlyPunctuationYieldsNoHits` 用例，需明确分词器对纯标点输入的处理策略。预期行为应为不产生任何 token，从而返回 0 命中；若当前实现将标点作为有效 token 处理，则会导致逻辑错误。
4. **混合宽度标点的脚本隔离**：在 `MixedWidthPunctuationKeepsBothScripts` 失败中，需确保分词器在处理中英文混合文本时，标点不会干扰相邻脚本（中文/英文）的 token 边界识别。
5. **回归测试补充**：修复后应扩充标点相关的测试用例，覆盖更多 Unicode 标点类别，防止类似问题再次发生。

## 5. 结论

v09 评测中，`TokenizerPunctTest` 系列失败属于**真问题**，核心原因在于分词器标点处理逻辑与测试期望不一致。由于 `eval_v09_new.log` 日志不完整（仅 33 字节），且 134 项失败总数缺乏详细日志佐证，本报告仅能基于 `doctests_full.log` 中的 Tokenizer 相关失败进行确定性分析。建议优先修复分词器标点过滤逻辑，并完善评测日志的完整性以支持更全面的失败归因。
