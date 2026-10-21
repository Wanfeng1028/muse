# Contributing

感谢你参与 One Memory。

## 开发环境

- Node.js 24
- pnpm 11
- Python 3.12
- uv

安装依赖并运行检查：

```bash
pnpm install
uv sync --directory apps/core --all-groups --locked
pnpm check
```

## 提交流程

1. 从 `main` 创建短生命周期功能分支。
2. 修复缺陷或新增行为时，先补能证明问题和结果的测试。
3. 保持改动聚焦，不混入生成文件、真实用户数据或无关格式化。
4. 提交 Pull Request，说明用户影响、测试证据、隐私影响和回滚方式。
5. 等待 CI 和代码审查通过后再合并。

涉及外部源码时，必须记录项目、固定版本或 commit、许可证、采用文件和修改说明。不得提交
密钥、内部地址、真实对话、个人路径、模型权重或签名证书。
