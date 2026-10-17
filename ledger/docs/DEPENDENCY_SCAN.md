# 依赖定期扫描

## 做什么

扫描 `pyproject.toml` 中 `[project].dependencies` 列出的**直接依赖**，输出：

1. 每个依赖的**已安装版本**（`importlib.metadata`）。
2. 每个依赖的**最新版本**（`python -m pip list --outdated --format=json`）。
3. 每个依赖在 **OSV 漏洞库**（https://api.osv.dev/v1/querybatch）中的已知漏洞。

依赖清单完全从 `pyproject.toml` 读取，脚本中没有任何硬编码包名。

## 多久跑一次

- **自动**：`.github/workflows/deps-scan.yml`，每周一 03:00 UTC 触发；也支持 `workflow_dispatch` 手动触发。
- **手动**：`make deps-scan`。

## 怎么跑

