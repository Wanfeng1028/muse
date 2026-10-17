# 深测轮 r3 验收报告（2026-10-18）

## 范围：41 个 *DeepTest 文件，652 个用例

本轮覆盖 41 个 *DeepTest 文件，共 652 个用例，跑的是 surefire 全量。

## 全量结果（以 surefire 实测为准）

上一轮 full2：30 失败 + 43 错误 = 73。
本轮修复后 full3：19 失败 + 42 错误 = 61。

算一下：652 个用例里，本轮之后还有 61 个没过。绿了 591 个，绿的比例约 90.6%。没到全绿，下面摊开说。

## 本轮修复的真产品 bug 清单（每个：现象/根因/修复/验证）

### 1. PromptRecipeService.apply 并发丢更新

- 现象：两个线程同时写同一条 recipe 的 usageCount，只加了一次，丢了一次 +1。
- 根因：read-modify-write，没有锁。两个线程都先读到旧值，各自 +1 再写回，后写的覆盖前写的。
- 修复：改成 @Modifying 原子自增 JPQL，方法上加 @Transactional。
- 验证：并发用例跑过，两次 +1 都落到库里。

### 2. UsageService.summary / provider-model-days 时间过滤查不到数据

- 现象：走"不限时间"这条过滤路径时，查询永远返回空。
- 根因：代码拿 LocalDateTime.MIN 去查 H2。LocalDateTime.MIN 是 -999999999 年，H2 对这种年份的时间比较直接返回空结果，所以永远查不到。
- 修复：加 TIME_BEGIN 常量（1970-01-01），替掉三处 LocalDateTime.MIN。
- 验证：不限时间过滤的用例跑过，能查到数据。

### 3. POST /api/projects 超长 synopsis 报 500

- 现象：synopsis 超过 VARCHAR 2000，接口返回 500。
- 根因：GlobalExceptionHandler 没映射 DataIntegrityViolationException，异常直接冒到 500。
- 修复：新增 DataIntegrityViolationException 到 400 的映射。
- 验证：超长 synopsis 用例跑过，返回 400。

### 4. MvController compose 的测试 stub 笔误

- 现象：compose 用例里 mock 返回 null，接口 500。
- 根因：这是测试自己写错了，不是产品 bug。stub 写的是 eq("m2")，但实际解析出来是 "99"，匹配不上，mock 返回 null。
- 修复：改测试 stub。
- 验证：compose 用例跑过。

## 测试 bug 清单（每个：哪个测试的期望与产品真实语义矛盾、怎么改的）

1. CharacterResponse.role 断言：测试拿 String "LEAD" 去断言，产品里 role 是 CharacterRole 枚举。改成按枚举断言。
2. CharacterService.delete / listByProject 未知 id：测试期望 204 / 空列表，产品真实语义是抛 ResourceNotFoundException。改成断言抛异常。
3. FinalCut.qc：测试断言 status 变 APPROVED，产品写的是 qcStatus 字段，status 保持 READY。改成断言 qcStatus 变、status 保持 READY。
4. SkillService.install 未知版本：测试期望 404，产品真实语义是抛 IllegalArgumentException。改成断言抛这个异常。
5. SkillService.rate 重复评分：测试期望重复评分被拒绝，产品里 rate 没有去重。改成按无去重的真实语义断言。
6. findById(null)：测试期望 ResourceNotFoundException，产品真实抛的是 InvalidDataAccessApiUsageException。改成断言抛后者。
7. 跨类 H2 数据污染：setUp 没按外键顺序清 characters 等子表，导致数据串。改成按外键顺序清。
8. ScriptSplitterService 反射构造：测试传的是 Function lambda，产品要的是 HttpExchange 接口实现。改成传接口实现。
9. SettingsService 并发测试 flake：读线程可能在写线程首次落盘前就跑完。加 firstWrite 门闩。

## 已知遗留与技术债

- SkillService.install 并发同版本安装会撞唯一约束：find-then-insert 没有锁。本轮测试改成串行幂等验证，竞态没修，记入技术债，产品修复待排期。
- full3 还剩 19 失败 + 42 错误 = 61 个用例没过，上面测试 bug 清单里改的那些是否已把对应失败全部消掉，本报告没拿到逐条对照数据，不下结论。
- MvController compose 那条是测试 stub 笔误，算测试侧问题，不计入产品 bug。

## 诚实结论（绿了多少、还剩多少、下一轮做什么）

- 绿了 591 / 652，约 90.6%。
- 还剩 61 个没过：19 失败 + 42 错误。
- 本轮确认并修掉 4 个真产品 bug，其中 3 个是产品问题（PromptRecipeService 并发丢更新、UsageService 时间过滤、超长 synopsis 500），1 个是测试 stub 笔误。
- 测试侧对齐了 9 类期望与产品语义矛盾的地方。
- 没有"全部通过"。61 个没过的用例，下一轮要逐条过一遍，分清哪些是产品还没修、哪些是测试还没对齐。
- 下一轮具体做：SkillService.install 并发竞态排期修；把剩下 61 个用例按失败/错误分类，逐个定位。
