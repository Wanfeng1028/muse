# mini-os 发版对照报告：v1.19.9

## 改动摘要
WS 层 term_open/term_resize 尺寸解析收紧；新增 term_size_from helper；非法尺寸以 Err(TermError::InvalidSize) 走已有 term_error 通路；manager 2–500 范围与文案未动；字段缺失仍默认 80/24。

## 验收范围
- 靶向测试：tests/ws_term_size_invalid_test.rs 4/4 通过（超大 open、字符串 open、缺省建会话、超大 resize）。
- 关联回归：term_size_validation_test 8/8、ws_term_open_r2 3/3；cargo fmt 干净；cargo check 通过（qrcode vendor 4 警告为既存，与本轮无关）。
- 真实服务冒烟：18429 端口隔离库二进制实测，注册 201、WS 握手 101，超大 open、字符串 open、超大 resize 均 term_error“终端尺寸非法（列 2–500、行 2–500）”，合法 open term_ready 且 session_id 32 位，冒烟后服务已停、端口复查已关。

## 对照表
- 可靠性：通过。理由：靶向测试4/4通过且非法尺寸统一走已有term_error通路。
- 可观测性：通过。理由：真实服务冒烟验证非法尺寸返回明确错误文案。
- 数据：通过。理由：字段缺失仍默认80/24。
- 部署：通过。理由：真实服务冒烟使用隔离库实测且冒烟后端口已关闭。
- 安全：通过。理由：非法尺寸以Err(TermError::InvalidSize)走已有term_error通路。
- 可维护性：通过。理由：cargo fmt干净且cargo check通过（qrcode vendor警告为既存）。

## 已知限制
权限失败与尺寸非法同时出现时仍按原分支顺序先报权限（本轮未改分支顺序）；全量测试套件本轮未跑（只跑靶向与关联组）。