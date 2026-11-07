# Sherlock

来源：`https://github.com/sherlock-project/sherlock`

性质：第三方开源项目源码归档（只存档，不改动）。

## 项目简介

Sherlock 是一个开源命令行工具：给它一个用户名，它去 400+ 个社交网站和平台上逐个检查该用户名是否注册过，帮你找到一个人在全网的账号归属。属于 OSINT（公开情报）工具，只查公开信息，不用登录、不绕过隐私设置。

- 语言：Python（要求 3.9+），命令行工具
- 许可证：MIT
- 作者：Siddharth Dushantha（挪威）；200+ 贡献者
- 官网：https://sherlockproject.xyz
- 支持站点列表：https://sherlockproject.xyz/sites

## 归档信息

- 归档日期：2026-11-07
- 上游 commit：`c588d7c8b476df9f9c84912a05d1430fb8cdcdae`（2026-11-01，`update banner layout`）
- 上游版本：0.16.2（2026 年 9 月发布）
- 包：`sherlock-20261107-c588d7c8.tar.gz`（源码 56 个文件，`.git` 已去除）
- 解包：`tar -xzf sherlock-20261107-c588d7c8.tar.gz`

## 安装与使用

```sh
pipx install sherlock-project
# 或
pip install --user sherlock-project

sherlock <用户名>          # 查全部支持站点
sherlock <用户名> --csv    # 结果存 CSV
sherlock <用户名> --site github,twitter  # 只查指定站点
```

更多用法见上游文档：https://sherlockproject.xyz/usage
