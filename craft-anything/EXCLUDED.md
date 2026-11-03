# EXCLUDED 清单（归档员注：非上游文件）

归档来源：https://github.com/storytold/craft-anything（2026-11-03 快照）
归档方法：`git clone --depth 1`（浅克隆，仅 main 分支当前快照，不含完整历史），
再原样拷入本文件夹。

## 被排除的内容

- `.git/` 目录：仅克隆元数据，不属于源码快照，已排除。
- 单个大于 50MB 的文件：**无**。已用 find 全量核查，最大单文件为
  `packaging/macos/dmg/background.tiff`（936K），其余均小于 1MB。

## 原文保留的许可文件

- `LICENSE-MIT`、`LICENSE-APACHE`（双许可 MIT OR Apache-2.0，全文未动）
- `NOTICE`、`ATTRIBUTION.md`（第三方归属说明，全文未动）

## 归档员添加的文件（非上游）

- 本文件 `EXCLUDED.md`
- `EVALUATION.md`（识别与集成评估）

除上述两文件外，本文件夹其余 621 个文件均为上游原文，未做任何修改。
