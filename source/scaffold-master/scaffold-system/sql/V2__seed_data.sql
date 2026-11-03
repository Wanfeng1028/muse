-- 本地开发示例数据；组织与用户仅供演示，电话留空，邮箱使用 example.com。
INSERT IGNORE INTO sys_dept (id, parent_id, ancestors, dept_name, leader, phone, email, sort, status, create_by, update_by)
VALUES
    (1, 0, '0', '云原科技集团', '周明远', '', 'hq@example.com', 1, 1, 'system', 'system'),
    (2, 1, '0,1', '研发中心', '陈思远', '', 'rd@example.com', 1, 1, 'system', 'system'),
    (3, 1, '0,1', '产品中心', '赵晴', '', 'pm@example.com', 2, 1, 'system', 'system'),
    (4, 1, '0,1', '职能中心', '钱伟', '', 'hr@example.com', 3, 1, 'system', 'system'),
    (5, 2, '0,1,2', '平台架构部', '李维', '', 'arch@example.com', 1, 1, 'system', 'system'),
    (6, 2, '0,1,2', '应用开发部', '吴敏', '', 'app@example.com', 2, 1, 'system', 'system'),
    (7, 2, '0,1,2', '测试质量部', '韩雪', '', 'qa@example.com', 3, 1, 'system', 'system'),
    (8, 3, '0,1,3', '产品设计部', '孙浩', '', 'design@example.com', 1, 1, 'system', 'system'),
    (9, 3, '0,1,3', '用户研究部', '马玲', '', 'ux@example.com', 2, 0, 'system', 'system'),
    (10, 4, '0,1,4', '人力资源部', '冯婷', '', 'people@example.com', 1, 1, 'system', 'system'),
    (11, 4, '0,1,4', '财务部', '蒋文', '', 'finance@example.com', 2, 1, 'system', 'system');

INSERT IGNORE INTO sys_post (id, post_code, post_name, sort, status, remark, create_by, update_by)
VALUES
    (1, 'ceo', '董事长', 1, 1, '集团最高管理岗位', 'system', 'system'),
    (2, 'gm', '总经理', 2, 1, '分管业务线总经理', 'system', 'system'),
    (3, 'tech_dir', '技术总监', 3, 1, '研发中心负责人', 'system', 'system'),
    (4, 'pm', '产品经理', 4, 1, '负责产品规划与设计', 'system', 'system'),
    (5, 'arch', '架构师', 5, 1, '平台架构设计岗位', 'system', 'system'),
    (6, 'dev', '研发工程师', 6, 1, '前后端研发岗位', 'system', 'system'),
    (7, 'qa', '测试工程师', 7, 1, '质量保障岗位', 'system', 'system'),
    (8, 'hr', '人事专员', 8, 1, '人力资源岗位', 'system', 'system'),
    (9, 'finance', '财务专员', 9, 0, '财务核算岗位', 'system', 'system');

INSERT IGNORE INTO sys_role (id, role_name, role_code, data_scope, sort, status, builtin, remark, create_by, update_by)
VALUES
    (1, '超级管理员', 'super_admin', 'ALL', 1, 1, 1, '系统最高权限，不可删除', 'system', 'system'),
    (2, '系统管理员', 'sys_admin', 'DEPT_AND_CHILD', 2, 1, 0, '负责系统日常配置与维护', 'system', 'system'),
    (3, '业务管理员', 'biz_admin', 'DEPT', 3, 1, 0, '维护本部门业务数据', 'system', 'system'),
    (4, '研发工程师', 'developer', 'SELF', 4, 1, 0, '使用代码生成与开发模块', 'system', 'system'),
    (5, '审计专员', 'auditor', 'CUSTOM', 5, 1, 0, '查看操作日志与登录日志', 'system', 'system'),
    (6, '只读访客', 'guest', 'SELF', 6, 0, 0, '仅可查看授权报表', 'system', 'system');

INSERT IGNORE INTO sys_user (id, username, password, nickname, phone, email, dept_id, status, create_by, update_by)
VALUES
    (1, 'admin', '$2b$10$L7q28dpKkcfrrUzfvZebqe7pvxcKpaSgh7EUenf9Q5z2LiYKxDpIu', '周明远', '', 'zhoumy@example.com', 5, 1, 'system', 'system'),
    (2, 'chensy', '$2b$10$L7q28dpKkcfrrUzfvZebqe7pvxcKpaSgh7EUenf9Q5z2LiYKxDpIu', '陈思远', '', 'chensy@example.com', 5, 1, 'system', 'system'),
    (3, 'wumin', '$2b$10$L7q28dpKkcfrrUzfvZebqe7pvxcKpaSgh7EUenf9Q5z2LiYKxDpIu', '吴敏', '', 'wumin@example.com', 6, 1, 'system', 'system');

INSERT IGNORE INTO sys_user_role (user_id, role_id) VALUES (1, 1), (2, 2), (3, 3);
INSERT IGNORE INTO sys_user_post (user_id, post_id) VALUES (1, 3), (2, 5), (3, 6);

INSERT IGNORE INTO sys_menu (id, parent_id, menu_name, menu_type, icon, path, component, permission, sort, visible, status, create_by, update_by)
VALUES
    (1, 0, '工作台', 'menu', 'dashboard', '/dashboard', 'dashboard/index', '', 1, 1, 1, 'system', 'system'),
    (100, 0, '系统管理', 'dir', 'gear', '/system', '', '', 2, 1, 1, 'system', 'system'),
    (101, 100, '用户管理', 'menu', 'users', '/system/user', 'system/user/index', 'system:user:list', 1, 1, 1, 'system', 'system'),
    (1011, 101, '新增用户', 'btn', '', '', '', 'system:user:add', 1, 1, 1, 'system', 'system'),
    (1012, 101, '编辑用户', 'btn', '', '', '', 'system:user:edit', 2, 1, 1, 'system', 'system'),
    (1013, 101, '删除用户', 'btn', '', '', '', 'system:user:remove', 3, 1, 1, 'system', 'system'),
    (1014, 101, '重置密码', 'btn', '', '', '', 'system:user:resetPwd', 4, 1, 1, 'system', 'system'),
    (102, 100, '角色管理', 'menu', 'role', '/system/role', 'system/role/index', 'system:role:list', 2, 1, 1, 'system', 'system'),
    (1021, 102, '新增角色', 'btn', '', '', '', 'system:role:add', 1, 1, 1, 'system', 'system'),
    (1022, 102, '编辑角色', 'btn', '', '', '', 'system:role:edit', 2, 1, 1, 'system', 'system'),
    (1023, 102, '删除角色', 'btn', '', '', '', 'system:role:remove', 3, 1, 1, 'system', 'system'),
    (103, 100, '菜单管理', 'menu', 'menu', '/system/menu', 'system/menu/index', 'system:menu:list', 3, 1, 1, 'system', 'system'),
    (1031, 103, '新增菜单', 'btn', '', '', '', 'system:menu:add', 1, 1, 1, 'system', 'system'),
    (1032, 103, '编辑菜单', 'btn', '', '', '', 'system:menu:edit', 2, 1, 1, 'system', 'system'),
    (1033, 103, '删除菜单', 'btn', '', '', '', 'system:menu:remove', 3, 1, 1, 'system', 'system'),
    (104, 100, '部门管理', 'menu', 'dept', '/system/dept', 'system/dept/index', 'system:dept:list', 4, 1, 1, 'system', 'system'),
    (1041, 104, '新增部门', 'btn', '', '', '', 'system:dept:add', 1, 1, 1, 'system', 'system'),
    (1042, 104, '编辑部门', 'btn', '', '', '', 'system:dept:edit', 2, 1, 1, 'system', 'system'),
    (1043, 104, '删除部门', 'btn', '', '', '', 'system:dept:remove', 3, 1, 1, 'system', 'system'),
    (105, 100, '岗位管理', 'menu', 'post', '/system/post', 'system/post/index', 'system:post:list', 5, 1, 1, 'system', 'system'),
    (1051, 105, '新增岗位', 'btn', '', '', '', 'system:post:add', 1, 1, 1, 'system', 'system'),
    (1052, 105, '编辑岗位', 'btn', '', '', '', 'system:post:edit', 2, 1, 1, 'system', 'system'),
    (1053, 105, '删除岗位', 'btn', '', '', '', 'system:post:remove', 3, 1, 1, 'system', 'system'),
    (106, 100, '字典管理', 'menu', 'dict', '/system/dict', 'system/dict/index', 'system:dict:list', 6, 1, 1, 'system', 'system'),
    (1061, 106, '新增字典', 'btn', '', '', '', 'system:dict:add', 1, 1, 1, 'system', 'system'),
    (1062, 106, '编辑字典', 'btn', '', '', '', 'system:dict:edit', 2, 1, 1, 'system', 'system'),
    (1063, 106, '删除字典', 'btn', '', '', '', 'system:dict:remove', 3, 1, 1, 'system', 'system'),
    (107, 100, '参数配置', 'menu', 'gear', '/system/config', 'system/config/index', 'system:config:list', 7, 1, 1, 'system', 'system'),
    (1071, 107, '新增参数', 'btn', '', '', '', 'system:config:add', 1, 1, 1, 'system', 'system'),
    (1072, 107, '编辑参数', 'btn', '', '', '', 'system:config:edit', 2, 1, 1, 'system', 'system'),
    (1073, 107, '删除参数', 'btn', '', '', '', 'system:config:remove', 3, 1, 1, 'system', 'system'),
    (200, 0, '系统监控', 'dir', 'log', '/monitor', '', '', 3, 1, 1, 'system', 'system'),
    (201, 200, '操作日志', 'menu', 'file', '/monitor/oper-log', 'monitor/operlog/index', 'monitor:operlog:list', 1, 1, 1, 'system', 'system'),
    (2011, 201, '清理操作日志', 'btn', '', '', '', 'monitor:operlog:remove', 1, 1, 1, 'system', 'system'),
    (202, 200, '登录日志', 'menu', 'lock', '/monitor/login-log', 'monitor/loginlog/index', 'monitor:loginlog:list', 2, 1, 1, 'system', 'system'),
    (2021, 202, '清理登录日志', 'btn', '', '', '', 'monitor:loginlog:remove', 1, 1, 1, 'system', 'system'),
    (300, 0, '系统工具', 'dir', 'tool', '/tool', '', '', 4, 1, 1, 'system', 'system'),
    (301, 300, '代码生成', 'menu', 'command', '/tool/generator', 'tool/gen/index', 'tool:gen:list', 1, 1, 1, 'system', 'system');

-- 超级管理员拥有全部菜单；其余角色由管理员在「角色管理」中按需授权
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT 1, id FROM sys_menu;

INSERT IGNORE INTO sys_dict_type (id, dict_name, dict_type, status, remark, create_by, update_by)
VALUES
    (1, '用户性别', 'sys_user_sex', 1, '用户性别列表', 'system', 'system'),
    (2, '系统开关', 'sys_normal_disable', 1, '系统正常 / 停用状态', 'system', 'system'),
    (3, '是否', 'sys_yes_no', 1, '通用是 / 否选项', 'system', 'system');

INSERT IGNORE INTO sys_dict_data (id, dict_type, dict_label, dict_value, sort, status, tone, is_default, create_by, update_by)
VALUES
    (1, 'sys_user_sex', '男', '0', 1, 1, 'info', 1, 'system', 'system'),
    (2, 'sys_user_sex', '女', '1', 2, 1, 'purple', 0, 'system', 'system'),
    (3, 'sys_user_sex', '未知', '2', 3, 1, 'neutral', 0, 'system', 'system'),
    (4, 'sys_normal_disable', '正常', '1', 1, 1, 'ok', 1, 'system', 'system'),
    (5, 'sys_normal_disable', '停用', '0', 2, 1, 'danger', 0, 'system', 'system'),
    (6, 'sys_yes_no', '是', 'Y', 1, 1, 'ok', 1, 'system', 'system'),
    (7, 'sys_yes_no', '否', 'N', 2, 1, 'neutral', 0, 'system', 'system');

INSERT IGNORE INTO sys_config (id, config_name, config_key, config_value, config_type, builtin, remark, create_by, update_by)
VALUES
    (1, '用户管理-账号初始密码', 'sys.user.initPassword', 'Yy@123456', 'Y', 1, '初始化密码', 'system', 'system'),
    (2, '账号自助-验证码开关', 'sys.account.captchaEnabled', 'true', 'Y', 1, '是否开启登录验证码', 'system', 'system'),
    (3, '主框架-默认外观', 'sys.index.appearance', 'light', 'N', 0, '可选 light / dark / auto', 'system', 'system');

-- 代码生成配置初始为空，按需导入当前数据库的真实表。
