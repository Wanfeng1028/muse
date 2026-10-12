package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"sentinel/internal/config"
	"sentinel/internal/db"
	"sentinel/internal/handlers"
	"sentinel/internal/notify"
	"sentinel/internal/scheduler"
	"sentinel/internal/seed"
	"sentinel/internal/store"
)

func main() {
	// 加载配置
	cfg := config.Load()

	// 打开数据库连接
	dbConn, err := db.Open(cfg.DBPath)
	if err != nil {
		log.Fatal(err)
	}

	// 初始化存储层
	st := store.New(dbConn)

	// 初始化通知器
	ntf := notify.Notifier{WebhookURL: cfg.WebhookURL}

	// 初始化调度器
	sc := scheduler.New(st, ntf.Send)

	// 创建可被信号取消的上下文，用于优雅退出
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// 启动调度器
	go sc.Start(ctx)

	// 初始化 HTTP 处理器
	srv := handlers.New(st, sc)

	// 执行种子数据初始化（包级函数，不返回 error）
	seed.EnsureSeed(st)

	// 启动 HTTP 服务
	if err := http.ListenAndServe(cfg.Addr(), srv.Routes()); err != nil {
		log.Fatal(err)
	}
}
