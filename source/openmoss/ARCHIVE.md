# 收录说明（非上游原件，2026-11-03 归档时附加）

- 原项目：https://github.com/pwilkin/openmoss（上游 README 自称 openmoss-ggml）
- 归档 commit：bfb1f465e0a86fb5a52bbf93e67ceba4b7d0b4e1（简称 bfb1f46，release: prepare 0.3.0，2026-08-21）
- LICENSE：Apache-2.0，仓库根目录 LICENSE 原文在位，未改动。
- 归档方式：上游新鲜克隆的工作树内容，排除 .git 后归档。
- 子模块处理：third_party/llama.cpp 子模块已干净初始化成功（ggml-org/llama.cpp，检出 050ee92d04c2e1f639025786dea701c70e7d4204），本次归档含子模块内容；为便于收录仓直接查阅，子模块内容已展平为普通文件（不含 .git），上游 .gitmodules 文件原样保留作来源证明，muse 仓内不是活动子模块。
- 其他说明：weights 为上游原有的悬空符号链接（指向 /devel/models/models/openmoss），按上游原样保留，未补模型权重文件。
