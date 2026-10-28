# X / 链接归档：yichen 微信生态 skill（2026-10-29）

## 来源之一：用户给的 README 链接

- https://github.com/mcncarl/yichen-skills/blob/main/yichen-wechat-local-vault/README.md
- 指向 skill：yichen-wechat-local-vault（微信本地数字资产库，macOS / Windows 本地全量解析）

## 来源之二：@gengdaJ X 帖子（2026-09-10，同一作者）

- 帖子把微信生态列成 4 个 skill，全部都在 yichen-skills 仓内，本次全仓入库已覆盖，
  无需另开归档：
  1. 微信数据 Skill → yichen-wechat-local-vault（聊天记录、联系人、朋友圈、收藏夹可被
     Codex 读取，支持增量；作者原话：只有首次重签名有一定风险，后续基本无风险）
  2. 微信公众号文章下载 Skill → yichen-wechat-mp-batch-exporter（给链接下载 Markdown；
     作者原话：按公众号名批量导出上千篇的上游仓库已关闭，他自己维护的批量版只对
     TradeWinds 社群成员开放——公开仓版本以给链接下载为准，不要写成批量版）
  3. 微信双开 Skill → yichen-mac-wechat-dual-open（作者原话：有一定风险，自己经常
     被弹出登录，现在没用了）
  4. 企微微信数据 Skill → yichen-wecom-local-vault（同微信 Skill）
- 上述风险提示已如实写进 yichen-skills/ARCHIVE-NOTE.md，未淡化风险，
  未把 TradeWinds 专属批量版写成公开版功能。

## 仓库

- mcncarl/yichen-skills，4,912★ / 2,817 forks，commit ed6200f81ff1fddd1482ad6cae7f4a75de5ffc75
- 全仓归档：muse-repo/yichen-skills/（240 文件，约 4.9MB，无排除项）
- 许可证：自定义 Personal Learning and Non-Commercial Use License（非开源许可，
  仅个人学习/研究/非商业使用；商业使用与公开打包再发布须书面许可）。详见 ARCHIVE-NOTE。

## 技能入库（17 个，原文，sha256 校验，LICENSE 已附）

- yichen-agent-memory、yichen-asr、yichen-bookmarks-export、yichen-chatgpt-web-research、
  yichen-codex-chatgpt、yichen-content-archive、yichen-mac-wechat-dual-open、
  yichen-unified-search、yichen-volc-asr、yichen-web-research、yichen-wechat-local-vault、
  yichen-wechat-mp-batch-exporter、yichen-wecom-local-vault、yichen-wecom-operations、
  yichen-x-article-draft-uploader、yichen-x-slicer、yichen-grok-consult
- 主索引 1417 → 1434，镜像 1405 → 1422（均以索引文件内 skills 数为准）
- 技能测试：41/41 全绿，BUILD SUCCESS
- 未往 _index.openmontage.json（OpenMontage 专属索引）里加非 OpenMontage 条目

## 云盘

- yichen-skills-source-20261029.tar.gz → Drive「02项目/Muse」（id: 1chW-eXAVqkR57JxqzWEWqOJKV1GP_Cb9），
  上传后经 Drive API 核实文件名/父文件夹/大小

## 提交

- 见本批 git log（作者 晚风）；push 后经 git branch -r --contains 核实 origin/main 含本批 commit
