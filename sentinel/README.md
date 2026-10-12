sentinel/
├── main.go                     # 程序入口，装配配置、数据库、调度器与 HTTP 服务
├── go.mod                      # module: sentinel
├── internal/
│   ├── config/                 # 环境变量读取与默认值
│   ├── db/                     # SQLite 连接、建表与迁移
│   ├── store/                  # 数据访问层（monitors / checks / incidents）
│   ├── checker/                # HTTP(S) 与 TCP 检查实现
│   ├── scheduler/              # 调度循环、翻转检测与事件生成
│   ├── notify/                 # Webhook 通知发送
│   ├── handlers/               # /api 路由与业务处理
│   └── web/                    # 内嵌静态页面与资源
└── data/                       # 默认数据库目录（运行时生成）
