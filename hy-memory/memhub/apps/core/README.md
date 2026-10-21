# One Memory Core

Python / FastAPI 数据面。
它是 Evidence、导入任务、Hy Memory、检索和 Graph 的唯一 owner。

Core 可以作为 Runtime 的 Kernel 独立运行：

```bash
one-memory-core
```

Python 包中的旧 `one-memory` 命令暂时保持兼容，仍可使用 `serve/status/doctor`；未来
公开的用户命令由 `apps/cli` 提供，避免把 Kernel 进程和完整 Runtime 混为一层。

macOS App 与未来跨平台 CLI 共用同一 Runtime 的分层、安装边界和验收合同见
`docs/contracts/runtime-unification.md`。
