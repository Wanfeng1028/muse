# v09-t006-q11 不可修复记录

## 1. 现象

评测对（eval/eval_pairs_v09.json）：

- id: v09-t006-q11
- query: 弹力带用久了出现什么情况就该换新的了？
- expected: v09_t006_05.md
- type: locate

期望文档 v09_t006_05.md 的 "使用注意" 段原文是：

> 弹力带怕晒怕油，用完挂在门后阴凉处。检查有没有小裂口，尤其是和门扣接触的位置。如果发现发白或者变硬，就该换了。

用户问的 "出现什么情况就该换新的了"，对应的答案文本是 "发现发白或者变硬，就该换了"。期望文档里**没有 "出现"、没有 "情况"、没有 "新的"** 这几个字面词。

locate 路径实际执行结果：期望文档不在前 4。

### 链路逐跳

**a) parseNaturalQuery**（src/query_parser.cpp）

- extractPhrases：query 无引号定界符，phrases 空，rest 为原文。
- 2a token 边界删除：`jieba->Cut(rest, toks)` 后，`fillerWords()` 里能整段命中的有 "什么"（单 token）、"该"（单 token）。换成空格后 rest ≈ `弹力带用久了出现 情况 就  换新的了？`。
- 2b eraseAll：`fillerWords()` 里能删的残余，剩下的 rest 尾部是 "？"。
- stripTrailingPredicates：`trailingPredicates()` = {写在哪, 写在, 说明, 介绍, 申请, 开具, 重置, 阐述, 写}，与 "？" 不匹配，不动。
- 步骤 3 CutForSearch + 过滤：对 "弹力带用久了" 段，jieba 的 CutForSearch 产出重叠子词，其中 "弹力"（起于字节 0）与 "带用"（起于字节 6，"带""用" 由 HMM 聚成新词）是事实三记录的切分结果。"弹力带" 这个词典长词在这段上下文里没有被切出，或切出后被 HMM 词图压制。keywords 里因此出现 "弹力"、"带用"。
- "出现"、"情况" 不在 `singleCharStopwords()`，不在 `isQuestionGlueWord()`，不在 `fillerWords()`，因此被保留进 keywords。
- "就"、"的"、"了" 由 `singleCharStopwords()` 过滤（"了" 在多字 token "新的了" 里时不被过滤，这里 "了" 是否单独切出取决于 CutForSearch）。
- keywords 大致为：弹力、带用、久、出现、情况、换、新（及可能的 "新的"）。

**b) Locator::locate**（src/locator.cpp）

- recallQuery = keywords 与 phrases 去重后空格拼接，例如 `弹力 带用 久 出现 情况 换 新`。
- `hasQuestionTail(rawQuery)` 因末尾 "？" 返回 true → 走 `searchQuestion(recallQuery, opts.recallDocs)`。

**c) searchQuestion 展开**（src/searcher.cpp 节选三）

- extractPhrases：无引号，phrases 空，rest = recallQuery。
- stripFillerWords(rest)：`fillerWords()` 表里能命中 recallQuery 的项为 0（"出现"、"情况"、"久"、"换"、"新"、"弹力"、"带用" 都不在表里），rest 不变。
- splitTokens：tokens = [弹力, 带用, 久, 出现, 情况, 换, 新]。
- isSingleCharStopword 过滤：以上都不是单字停用词，全保留。
- 走主路径 `buildMatchQuery(rest)`，对每个 token 调 `expandTokenWithJoiner(token, " AND ")`（src/searcher.cpp 节选二）：
  - "弹力"：CutForSearch 得 [弹力]，claimTokenPositions 认领字节 0，groups = {0: [弹力]}，单成员单组，返回 `"弹力"`。
  - "带用"：CutForSearch 得 [带用]（或 [带][用]）。若为 [带用]，claimTokenPositions 认领字节 0，返回 `"带用"`；若为 [带][用]，两组，返回 `"带"* AND "用"*`。两种情形下，作为整体双字 token 的 `"带用"` 在索引里不存在，或前缀 `"带"*`/`"用"*` 命中的是 "弹力带" 里单独的 "带" 和 "用久" 里单独的 "用"，语义完全错位。
  - "久"：单字 CJK 非停用词，`wordExpr` 返回 `"久"*`。
  - "出现"：`"出现"`。
  - "情况"：`"情况"`。
  - "换"：单字 CJK 非停用词，`"换"*`。
  - "新"：单字 CJK 非停用词，`"新"*`。
- 最终 AND 查询：`"弹力" AND "带用" AND "久"* AND "出现" AND "情况" AND "换"* AND "新"*`（或 "带用" 被拆成 `"带"* AND "用"*` 的变体）。

**d) 索引侧 jiebaXTokenize**（src/jieba_tokenizer.cpp）

- 期望文档里 CutForSearch 对 "弹力带怕晒" 产出 `<弹力>`、`<弹力带>`、`<带>`、`<怕晒>`、`<怕>`、`<晒>`，claimTokenPositions 逐个认领并 emitToken。对 "用完" 产出 `<用>`、`<用完>`、`<完>`。对 "就该换了" 产出 `<就>`、`<该>`、`<换>`、`<了>`、`<该换>`、`<该换了>` 等。
- 索引里存在 `<弹力>`、`<弹力带>`、`<带>`、`<用>`、`<久>` 这些 token，但**不存在 `<带用>` 这个双字 token**——文档里没有 "带""用" 相邻出现的地方。
- 索引里**不存在 `<出现>`、`<情况>`、`<新的>`**——这三个词在期望文档里一个字都没有。

**e) 失配精确位置**

失配发生在 `searchQuestion` 阶段 1 的精确 AND（`src/searcher.cpp` 节选三：`const std::string matchQuery = buildMatchQuery(rest);`，再 `db_.searchFts(matchQuery, limit * 2)`）。

AND 链中 `"带用"`（或拆出的 `"带"* AND "用"*`）、`"出现"`、`"情况"` 三项在期望文档的 FTS 索引里任一不命中，整个 AND 恒为 0 结果。后续 OR 并集、substringRecallPass、tryCharDecomposedSingle 回退都基于 `tokens`（含 "带用"、"出现"、"情况"），精滤时要求 hay 包含 token 的全部非停用字，`弹力带怕晒...` 这段文本里既没有 "出现"、"情况"，也没有相邻的 "带""用" 二字，"带用" 或拆分后的字符组合无法通过 `substringRecallPass`。

失败在 **searchQuestion 的 AND 召回 + 精滤链路**，不在 rankPassages。

## 2. 已尝试的思路

### F-T006A（v0.18.0 Wave4）

逐字记录：

> 查询 "弹力带..." 切出 [弹力][带用]，索引侧为 [弹力带]。F-T006A 曾尝试同起点前缀吸收，但与 v0.14 刻意保留重叠 token 的行为冲突（导致 ContactLookupQueryDropsXiangAndPunct 回归），已回滚。

F-T006A 的做法是在查询侧对同一起始字节位置的重叠词做前缀吸收：把 `<弹力>`（起于字节 0）与 `<弹力带>`（若被切出）合并成一组，用 `弹力` 覆盖 `弹力带`，让查询侧 `"弹力"` 或 `"弹力"*` 能够命中索引侧 `<弹力带>` 这个长 token。

**回滚原因**：v0.14 起 `jiebaXTokenize` 刻意保留重叠 token，源码注释逐字：

> 不同词允许同一位置重叠（如 "计算" 和 "计算机" 都在字节 0），因此 key 必须包含词本身。

索引侧同时存 `<弹力>` 与 `<弹力带>` 是设计选择，不是缺陷。查询侧若对同一起始位置的词做前缀吸收（`弹力` → `弹力*` 或直接把 `弹力带` 也并入 OR 组），会改变 `expandTokenWithJoiner` 的 groups 结构，进而改变 `parseNaturalQuery("想找客服，联系方式在哪啊")` 的 keywords 结果——测试断言 keywords 必须含 "客服"/"联系"/"联系方式"，且不含 "想"/"，"/"在哪"/"啊"。前缀吸收引入了原本不存在的关键词，或改变了词条顺序，该断言红。

**精确冲突点**：`expandTokenWithJoiner` 中 `std::map<size_t, std::vector<std::string>> groups` 是按起始字节偏移分组的。索引侧同一字节位置存在多个词（`弹力` 和 `弹力带`），查询侧若对同一起始位置的词做前缀吸收，会扩大 groups 的成员集合，进而影响 `groupExpr` 的输出串。ContactLookupQueryDropsXiangAndPunct 断言的是 keywords 列表内容，不是查询串，但 keywords 与查询串共用 `pushUnique` 去重逻辑，前缀吸收会通过展开路径反向污染 keywords 内容（或至少让关键词表随展开路径变化）。这是 v0.14 保留重叠 token 行为的直接后果。

### EVAL 建议方向："多字 token 尾字停用词剥离 + jieba 切分错误后处理"

**为什么没走通**：

- "多字 token 尾字停用词剥离"：本 query 里 `单字停用词` 是 "的"、"了"，两者若被切为单独 token 已由 `singleCharStopwords()` 过滤；若被切为多字 token 的尾字（如 "新的了"），剥离尾字 "了" 会产出 "新的"，但 "新的" 在期望文档里也不存在，且**剥离无法解决 "带用"、"出现"、"情况" 三个真正的杀点**。剥离后 keywords 仍带 "带用"、"出现"、"情况"，AND 仍恒空。

- "jieba 切分错误后处理"：需要判断哪些多字 token 是错误切分。索引侧切分依据的是**文档原文**，查询侧只有 query 文本，**没有文档可对照**，无法判断 "带用" 是否错切。若退化为 "所有多字 token 都拆单字前缀 OR"，会与 `expandTokenWithJoiner` 的单字前缀规则重叠，产生大量噪音命中，rankPassages 阶段无法在 recallDocs 限内把期望文档拉回前 4；同时 `ContactLookupQueryDropsXiangAndPunct` 会因为查询侧单字拆分引入的额外关键词而红。

- 该方向本质上是 F-T006A 的变体：F-T006A 在**头部**做前缀吸收，本方向在**尾部**做单字拆分，两者都动 `expandTokenWithJoiner` 的 groups 结构，都与 v0.14 索引侧重叠保留行为冲突。

- 加词表（往 `fillerWords()` 或 `isQuestionGlueWord` 加 "出现"、"情况"）是**写死字面量**，违反 v0.18.1 红线 "不许写死字面量"。

## 3. 为什么不可修

三条约束锁死：

**约束一：查询侧与索引侧切分错位的对称性。**

`jiebaXTokenize` 在索引侧对文档原文切分，`expandTokenWithJoiner` 在查询侧对 query 切分。两者都调用同一个 `CutForSearch`，但输入不同——文档原文和 query 是不同文本。`CutForSearch` 在 "弹力带怕晒"（文档）上切出 `弹力带`，在 "弹力带用久了"（query）上切出 `弹力`+`带用`。这种错位不是 bug，是 jieba 词图在不同上下文下的正常输出差异。查询侧无法知道文档侧切出了什么，除非把文档原文拉过来——但 locate 路径的设计是"先召回、后过滤"，召回阶段没有文档原文可用。

**约束二：重叠保留行为的约束。**

`jiebaXTokenize` 明确保留同一起始字节位置的重叠 token（`<弹力>` 与 `<弹力带>` 并存），`expandTokenWithJoiner` 的 `groups` 也按起始字节偏移分组、允许组内多成员 OR。查询侧任何试图"对齐"或"吸收"重叠词的改动，都会改变 groups 的成员集合，进而改变展开串，影响所有走 `searchQuestion`/`expandTokenWithJoiner` 的用例。F-T006A 就是在这一点上撞墙。

**约束三：红线约束。**

v0.18.1 独立复核红线逐字：

> 不许模糊同义词、不许写死字面量、不许为凑分调权重。

- 不许模糊同义词：不能把 "出现"、"情况" 换成与 "发白"、"变硬" 同义的模糊词。
- 不许写死字面量：不能往 `fillerWords()`、`isQuestionGlueWord`、`singleCharStopwords()` 加 "出现"、"情况"、"新的" 等 query 专属词。
- 不许为凑分调权重：不能通过调 `SearchWeights` 让期望文档挤进前 4。

三条约束下，唯一能真正修的方向是"查询侧切分与索引侧对齐"，而这需要在查询侧拿到文档原文——这与 locate 路径"先召回后过滤"的架构前提矛盾。任何在查询侧做切分对齐的改动，都会重蹈 F-T006A 覆辙，或触发红线。

结论：v09-t006-q11 在当前架构下不可修复。v0.18.1 判定 "架构级不可修复" 成立。

## 4. 建议的后续方向

### 方向一：查询理解升级（query understanding）

把 `parseNaturalQuery` 从 "停用词表 + 规则剥离" 升级为 "句式识别 + 主题词抽取"：识别 "X 用久了出现什么情况就该换新的了" 是 "条件 + 疑问 + 结果" 句式，抽取出主题词 "弹力带" 和动作词 "换新"，把 "出现"、"情况"、"新的" 这类句式骨架词整体丢弃。

- **代价**：需要引入句式模板或轻量意图分类器，`parseNaturalQuery` 复杂度显著上升，且要重新跑 v07 56 对、v08 83 对、v09s 200 对全部回归。
- **风险**：句式模板容易过拟合当前 query，泛化到其他长问句时可能引入新的错误抽取；与 "不许写死字面量" 红线的边界模糊（句式模板算不算字面量？需要与复核者确认）。

### 方向二：索引侧 n-gram 兜底

在 FTS 索引里额外存一份 CJK n-gram（bigram/trigram）token，查询侧对多字 token 也走 n-gram 匹配，绕开 jieba 词图错位。

- **代价**：索引体积膨胀数倍，`jiebaXTokenize` 要产出两套 token（词 + n-gram），FTS5 查询串构造要相应改造，`expandTokenWithJoiner` 的分组逻辑要重写。
- **风险**：n-gram 召回噪音大，rankPassages 阶段压力大；`ContactLookupQueryDropsXiangAndPunct` 等断言 keywords 精确内容的测试需要重新评估（n-gram 是否进入 keywords？若进入则红，若不进入则召回路径与 keywords 分离，改动面更大）。

### 方向三：locate 路径改为"先取候选文档、再在文档侧做 query 对齐"

放弃 "查询侧切分对齐"，改为 "召回阶段用宽松的 OR 粗筛，取回候选文档后在文档侧用 `claimTokenPositions` 把 query 切分对齐到文档切分"。

- **代价**：召回阶段用 OR 粗筛会把大量文档拉进候选池，`LocateOptions::recallDocs` 要放大；文档侧对齐逻辑与 `jiebaXTokenize` 共享 `claimTokenPositions`，需要重新设计过滤语义。
- **风险**：性能退化；`rerankHits` 与 `rankPassages` 的接口要调整；`ContactLookupQueryDropsXiangAndPunct` 断言 keywords 内容不变，本方向不动 keywords，理论上不冲突，但召回路径改动面大，需要重新跑全部回归。

### 方向四：接受为已知限制

在 `docs/eval.md` 的已知问题清单里登记 v09-t006-q11 为已知限制，标记为 "长问句 locate + jieba 切分错位" 类型，不再尝试修复，把精力放在其他用例上。

- **代价**：v09s 维持在 197/200，不达 200/200。
- **风险**：无。这是当前架构下最诚实的选择。

---

## 回归影响面总结

本次交付为诚实记录文档，**未改动任何源码**。因此：

- v07：预期 56/56 不变。
- v08：预期 81/83 不变（与 v0.18.1 基线一致）。
- v09s：预期 197/200 不变，v09-t006-q11 仍为失败。
- `ContactLookupQueryDropsXiangAndPunct`：保持绿（未触碰 `parseNaturalQuery`、`expandTokenWithJoiner`、`jiebaXTokenize` 任何一行）。
