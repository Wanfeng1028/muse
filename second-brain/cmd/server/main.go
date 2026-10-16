// cmd/server/main.go
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/api"
	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	logpkg "github.com/Wanfeng1028/muse/second-brain/internal/log"
	"github.com/Wanfeng1028/muse/second-brain/internal/push"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func main() {
	// 加载配置
	cfg := config.Load()

	// 初始化结构化日志（SB_LOG_LEVEL，默认 info，JSON 输出）
	logpkg.Init()

	// 打开数据库
	st, err := store.Open(cfg.DBPath)
	if err != nil {
		slog.Error("server.db_open_failed", "db", cfg.DBPath, "error", err)
		os.Exit(1)
	}

	// 构建 HTTP 服务
	handler := api.NewServer(st, cfg)
	srv := &http.Server{
		Addr:    cfg.Addr,
		Handler: handler,
	}

	// 推送调度器（启用时）
	var sched *push.Scheduler
	if cfg.Push.Enabled {
		senders := push.BuildSenders(cfg.Push)
		sched = push.NewScheduler(st, senders, cfg.Push)
		sched.Start()
		slog.Info("server.push_scheduler_started", "time", cfg.Push.Time, "timezone", cfg.Push.Timezone)
	}

	slog.Info("server.listening", "addr", cfg.Addr, "db", cfg.DBPath)
	// v0.12 启动日志：暴露指标与限流配置，便于运维核对实际生效值。
	slog.Info("server.metrics", "enabled", cfg.Metrics.Enabled, "token_protected", cfg.Metrics.Token != "")
	slog.Info("server.ratelimit", "enabled", cfg.RateLimit.Enabled, "rps", cfg.RateLimit.RPS, "burst", cfg.RateLimit.Burst, "write_rps", cfg.RateLimit.WriteRPS, "write_burst", cfg.RateLimit.WriteBurst)

	// 启动服务
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server.http_failed", "error", err)
			os.Exit(1)
		}
	}()

	// 等待中断信号
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	slog.Info("server.shutting_down")

	// 停止推送调度器
	if sched != nil {
		sched.Stop()
	}

	// 优雅关闭 HTTP 服务
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		slog.Warn("server.http_close_error", "error", err)
	}

	// 关闭数据库
	if err := st.Close(); err != nil {
		slog.Warn("server.db_close_error", "error", err)
	}

	slog.Info("server.exited")
}
