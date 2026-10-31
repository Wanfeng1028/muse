# docseek CLI --max-mb 非正数返回错误 发版对照报告

## 改动概述
src/main.cpp 的 --max-mb 分支（index/serve 两路）在 pos 整串校验之后、赋值之前加非正数校验：val <= 0 时打印“错误：--max-mb 参数无效”并 return 1；正数行为、尾随字符校验、缺参报错、catch 分支文案、两路赋值一字不动。

## checklist 对照表
| 模块 | 分类 | 结果 |
| --- | --- | --- |
| 可靠性 | 非法输入 fail-fast、既有错误文案复用 | 通过 |
| 可观测性 | stderr 明确报错、退出码 1 | 通过 |
| 数据 | 无 schema、无迁移 | 不适用 |
| 部署运维 | 无配置、无部署变更 | 不适用 |
| 安全 | 静默忽略消除 | 通过 |
| 可维护 | 改动面 1 个文件 1 处、文档同步 | 通过 |

## 测试与验收
cmake --build build --target docseek 成功；全新 1 文档库上 7 项真实二进制检查全部通过：index --max-mb 0、index --max-mb -5、serve --max-mb 0（--port 0）均退出码 1 且 stderr 为“错误：--max-mb 参数无效”；index --max-mb 10x 与 --max-mb abc 仍退出码 1 同文案；index --max-mb 10 退出码 0（扫描 1 文件、新增 1）；随后 search 退款退出码 0 并命中该文档。

## 已知限制
本轮未运行全量 ctest；未新增 gtest 用例（此前 CLI 参数收紧轮次同样以真实二进制检查验收）；无 UI 改动，视觉验收不适用；无 schema 变更、无版本号升级。