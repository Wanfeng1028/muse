//! models 模块深度测试：JSON 字段命名、缺省值、错误传播、边界。
//! 本文件为集成测试，只能通过 crate 公开路径引用类型。

use mini_os::models::{
    AppInfo, CreateNodeRequest, CreateShareRequest, LoginRequest, Node, RegisterRequest,
    SetRoleRequest, SettingRequest, SetupNeededResponse, ShareAdminItem, ShareCreated,
    ShareDirEntry, ShareDirListing, ShareInfo, Stats, UpdateNodeRequest, UserInfo, UserWithRole,
};
use serde_json::{json, Value};

fn sample_node() -> Node {
    Node {
        id: 7,
        parent_id: Some(3),
        name: "报告.docx".to_string(),
        kind: "file".to_string(),
        content: "hello".to_string(),
        created_at: "2024-05-01T10:00:00Z".to_string(),
        updated_at: "2024-05-02T11:30:00Z".to_string(),
        size: 5,
        mime_type: Some("application/msword".to_string()),
    }
}

#[test]
fn node_serializes_with_camel_case_keys_and_roundtrips() {
    let node = sample_node();
    let value: Value = serde_json::to_value(&node).expect("Node 序列化失败");

    assert_eq!(value["id"], json!(7));
    assert_eq!(value["parentId"], json!(3));
    assert_eq!(value["name"], json!("报告.docx"));
    assert_eq!(value["kind"], json!("file"));
    assert_eq!(value["createdAt"], json!("2024-05-01T10:00:00Z"));
    assert_eq!(value["updatedAt"], json!("2024-05-02T11:30:00Z"));
    assert_eq!(value["mimeType"], json!("application/msword"));
    assert_eq!(value.get("parent_id"), None);
    assert_eq!(value.get("created_at"), None);
    assert_eq!(value.get("mime_type"), None);

    let back: Node = serde_json::from_value(value).expect("Node 反序列化失败");
    assert_eq!(back.id, node.id);
    assert_eq!(back.parent_id, node.parent_id);
    assert_eq!(back.name, node.name);
    assert_eq!(back.size, node.size);
    assert_eq!(back.mime_type, node.mime_type);
}

#[test]
fn node_root_and_missing_mime_type_roundtrip() {
    let raw = json!({
        "id": 1,
        "parentId": null,
        "name": "root-folder",
        "kind": "folder",
        "content": "",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
        "size": 0,
        "mimeType": null
    });

    let node: Node = serde_json::from_value(raw).expect("根节点反序列化失败");
    assert_eq!(node.parent_id, None);
    assert_eq!(node.mime_type, None);
    assert_eq!(node.size, 0);
    assert_eq!(node.content, "");

    let value = serde_json::to_value(&node).expect("根节点序列化失败");
    assert_eq!(value["parentId"], Value::Null);
    assert_eq!(value["mimeType"], Value::Null);
}

#[test]
fn node_rejects_missing_required_field() {
    let raw = json!({
        "id": 2,
        "parentId": null,
        "kind": "file",
        "content": "x",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
        "size": 1,
        "mimeType": null
    });

    let err = serde_json::from_value::<Node>(raw).expect_err("缺少 name 应当反序列化失败");
    let msg = err.to_string();
    assert!(msg.contains("name"), "错误信息应提到缺失字段 name，实际: {msg}");
}

#[test]
fn create_node_request_defaults_parent_and_content() {
    let raw = json!({ "name": "新建目录", "kind": "folder" });
    let req: CreateNodeRequest =
        serde_json::from_value(raw).expect("CreateNodeRequest 反序列化失败");

    assert_eq!(req.parent_id, None);
    assert_eq!(req.name, "新建目录");
    assert_eq!(req.kind, "folder");
    assert_eq!(req.content, None);
}

#[test]
fn update_node_request_partial_fields_roundtrip() {
    let raw = json!({ "name": "改名后.txt" });
    let req: UpdateNodeRequest =
        serde_json::from_value(raw).expect("UpdateNodeRequest 反序列化失败");
    assert_eq!(req.name.as_deref(), Some("改名后.txt"));
    assert_eq!(req.content, None);

    let value = serde_json::to_value(&req).expect("UpdateNodeRequest 序列化失败");
    assert_eq!(value["name"], json!("改名后.txt"));
    assert_eq!(value["content"], Value::Null);
    assert_eq!(value.get("name"), Some(&json!("改名后.txt")));
}

#[test]
fn setting_request_uses_key_value_field_names() {
    let req = SettingRequest {
        key: "theme".to_string(),
        value: "dark".to_string(),
    };
    let value = serde_json::to_value(&req).expect("SettingRequest 序列化失败");
    assert_eq!(value["key"], json!("theme"));
    assert_eq!(value["value"], json!("dark"));

    let back: SettingRequest = serde_json::from_value(value).expect("SettingRequest 反序列化失败");
    assert_eq!(back.key, "theme");
    assert_eq!(back.value, "dark");
}

#[test]
fn create_share_request_renames_type_field_and_defaults_path() {
    let raw = json!({ "nodeId": 42, "type": "dir", "path": "/docs" });
    let req: CreateShareRequest =
        serde_json::from_value(raw).expect("CreateShareRequest 反序列化失败");

    assert_eq!(req.node_id, Some(42));
    assert_eq!(req.share_type.as_deref(), Some("dir"));
    assert_eq!(req.path.as_deref(), Some("/docs"));

    let value = serde_json::to_value(&req).expect("CreateShareRequest 序列化失败");
    assert_eq!(value["type"], json!("dir"));
    assert_eq!(value["nodeId"], json!(42));
    assert_eq!(value["path"], json!("/docs"));
    assert_eq!(value.get("share_type"), None);
    assert_eq!(value.get("shareType"), None);

    let minimal: CreateShareRequest =
        serde_json::from_value(json!({ "nodeId": 1 })).expect("缺省字段反序列化失败");
    assert_eq!(minimal.node_id, Some(1));
    assert_eq!(minimal.share_type, None);
    assert_eq!(minimal.path, None);
}

#[test]
fn share_info_and_dir_listing_carry_kind_and_size() {
    let info_raw = json!({
        "token": "abc123",
        "name": "docs",
        "kind": "folder",
        "size": 1024,
        "mimeType": null,
        "shareType": "dir"
    });
    let info: ShareInfo = serde_json::from_value(info_raw).expect("ShareInfo 反序列化失败");
    assert_eq!(info.token, "abc123");
    assert_eq!(info.kind, "folder");
    assert_eq!(info.size, 1024);
    assert_eq!(info.mime_type, None);
    assert_eq!(info.share_type, "dir");

    let entry = ShareDirEntry {
        name: "子目录".to_string(),
        kind: "folder".to_string(),
        size: 0,
        mtime: "2024-06-01T08:00:00Z".to_string(),
    };
    let listing = ShareDirListing {
        path: "".to_string(),
        entries: vec![entry.clone()],
    };
    let value = serde_json::to_value(&listing).expect("ShareDirListing 序列化失败");
    assert_eq!(value["path"], json!(""));
    assert_eq!(value["entries"][0]["name"], json!("子目录"));
    assert_eq!(value["entries"][0]["kind"], json!("folder"));
    assert_eq!(value["entries"][0]["size"], json!(0));
    assert_eq!(value["entries"][0]["mtime"], json!("2024-06-01T08:00:00Z"));

    let back: ShareDirListing =
        serde_json::from_value(value).expect("ShareDirListing 反序列化失败");
    assert_eq!(back.entries.len(), 1);
    assert_eq!(back.entries[0].name, "子目录");
}

#[test]
fn user_info_never_contains_password_field() {
    let user = UserInfo {
        id: 9,
        username: "晚风".to_string(),
        is_admin: true,
        role: "admin".to_string(),
    };
    let value = serde_json::to_value(&user).expect("UserInfo 序列化失败");
    let object = value.as_object().expect("UserInfo 应为 JSON 对象");

    assert_eq!(value["id"], json!(9));
    assert_eq!(value["username"], json!("晚风"));
    assert_eq!(value["isAdmin"], json!(true));
    assert_eq!(value["role"], json!("admin"));
    assert_eq!(object.get("passwordHash"), None);
    assert_eq!(object.get("password_hash"), None);
    assert_eq!(object.get("password"), None);
}

#[test]
fn register_and_login_requests_use_camel_case_and_roundtrip() {
    let register = RegisterRequest {
        username: "alice".to_string(),
        password: "s3cr3t!".to_string(),
    };
    let reg_value = serde_json::to_value(&register).expect("RegisterRequest 序列化失败");
    assert_eq!(reg_value["username"], json!("alice"));
    assert_eq!(reg_value["password"], json!("s3cr3t!"));

    let login_raw = json!({ "username": "alice", "password": "s3cr3t!" });
    let login: LoginRequest = serde_json::from_value(login_raw).expect("LoginRequest 反序列化失败");
    assert_eq!(login.username, "alice");
    assert_eq!(login.password, "s3cr3t!");

    let setup: SetupNeededResponse =
        serde_json::from_value(json!({ "needed": false })).expect("SetupNeededResponse 反序列化失败");
    assert_eq!(setup.needed, false);
    let setup_value = serde_json::to_value(&setup).expect("SetupNeededResponse 序列化失败");
    assert_eq!(setup_value["needed"], json!(false));
}

#[test]
fn stats_and_app_info_and_role_models_roundtrip() {
    let stats = Stats {
        files: 12,
        folders: 3,
        total_bytes: 4096,
    };
    let stats_value = serde_json::to_value(&stats).expect("Stats 序列化失败");
    assert_eq!(stats_value["files"], json!(12));
    assert_eq!(stats_value["folders"], json!(3));
    assert_eq!(stats_value["totalBytes"], json!(4096));
    let stats_back: Stats = serde_json::from_value(stats_value).expect("Stats 反序列化失败");
    assert_eq!(stats_back.files, 12);
    assert_eq!(stats_back.total_bytes, 4096);

    let app = AppInfo {
        id: "files".to_string(),
        name: "文件管理器".to_string(),
        icon: "📁".to_string(),
        description: "浏览和编辑文件".to_string(),
    };
    let app_value = serde_json::to_value(&app).expect("AppInfo 序列化失败");
    assert_eq!(app_value["id"], json!("files"));
    assert_eq!(app_value["icon"], json!("📁"));
    assert_eq!(app_value["description"], json!("浏览和编辑文件"));

    let role_req: SetRoleRequest =
        serde_json::from_value(json!({ "role": "viewer" })).expect("SetRoleRequest 反序列化失败");
    assert_eq!(role_req.role, "viewer");

    let with_role = UserWithRole {
        id: 3,
        username: "bob".to_string(),
        is_admin: false,
        role: "editor".to_string(),
        created_at: "2024-03-03T03:03:03Z".to_string(),
    };
    let value = serde_json::to_value(&with_role).expect("UserWithRole 序列化失败");
    assert_eq!(value["createdAt"], json!("2024-03-03T03:03:03Z"));
    assert_eq!(value["isAdmin"], json!(false));
    assert_eq!(value["role"], json!("editor"));
}

#[test]
fn share_created_and_admin_item_keep_expected_field_names() {
    let created = ShareCreated {
        token: "tok-001".to_string(),
        url: "/api/s/tok-001".to_string(),
    };
    let value = serde_json::to_value(&created).expect("ShareCreated 序列化失败");
    assert_eq!(value["token"], json!("tok-001"));
    assert_eq!(value["url"], json!("/api/s/tok-001"));

    let item = ShareAdminItem {
        id: 5,
        token: "tok-001".to_string(),
        share_type: "file".to_string(),
        owner_id: 1,
        owner_username: "晚风".to_string(),
        node_name: "简历.pdf".to_string(),
        created_at: "2024-07-07T07:07:07Z".to_string(),
    };
    let item_value = serde_json::to_value(&item).expect("ShareAdminItem 序列化失败");
    assert_eq!(item_value["shareType"], json!("file"));
    assert_eq!(item_value["ownerId"], json!(1));
    assert_eq!(item_value["ownerUsername"], json!("晚风"));
    assert_eq!(item_value["nodeName"], json!("简历.pdf"));
    assert_eq!(item_value["createdAt"], json!("2024-07-07T07:07:07Z"));

    let back: ShareAdminItem =
        serde_json::from_value(item_value).expect("ShareAdminItem 反序列化失败");
    assert_eq!(back.token, "tok-001");
    assert_eq!(back.node_name, "简历.pdf");
}