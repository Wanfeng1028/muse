# 软件安装常见问题

## Q1：支持哪些系统？

Windows 10 及以上 64 位，macOS 12 及以上，Ubuntu 20.04 及以上。暂不支持 32 位系统和 Windows 7。

## Q2：安装包多大，装完占多少空间？

安装包约 180 MB，安装后占用约 650 MB。建议预留 2 GB 空间给缓存和日志。

## Q3：安装步骤？

1. 到官网下载对应系统的安装包，核对 SHA256 校验值。
2. Windows 双击 exe，macOS 拖入 Applications，Linux 用 dpkg -i 或解压后运行。
3. 首次启动选择安装目录，默认 C:\Program Files\AppName。
4. 登录账号，同步配置。

## Q4：安装失败怎么办？

先看错误码。错误 2503/2502 是权限问题，用管理员身份运行。错误 1603 是旧版本残留，用官方卸载工具清理后重装。磁盘空间不足也会报错。

## Q5：怎么静默安装？

Windows：AppName-setup.exe /S /D=C:\AppName。macOS：命令行 install -pkg。Linux：apt install -y appname。企业部署可导出配置模板批量下发。

## Q6：如何卸载干净？

Windows 控制面板卸载，再删除 %AppData%\AppName 和安装目录。macOS 拖到废纸篓，再清 ~/Library/Application Support/AppName。

## Q7：安装后打不开？

检查是否被杀毒软件拦截，把安装目录加白名单。显卡驱动太旧也可能导致启动黑屏，更新到最新版。
