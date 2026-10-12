// 程序入口：读取配置、初始化状态、构建路由并启动 HTTP 服务
use mini_os::{build_app, config::Config, init_state};

#[tokio::main]
async fn main() {
    // 从环境变量读取配置（缺省使用默认值）
    let config = Config::from_env();

    // 初始化全局状态（打开数据库、建表、写入种子数据）
    let state = init_state(&config.database_path, &config.static_dir);

    // 构建 axum 应用路由
    let app = build_app(state);

    // 绑定 0.0.0.0:port 并启动服务
    let addr = format!("0.0.0.0:{}", config.port);
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("无法绑定监听地址");

    println!("mini-os 已启动: http://{}", addr);
    println!("数据库路径: {}", config.database_path);

    axum::serve(listener, app).await.expect("服务运行失败");
}
