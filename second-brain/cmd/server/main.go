// cmd/server/main.go
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/api"
	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/push"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func main() {
	// 加载配置
	cfg := config.Load()

	// 打开数据库
	st, err := store.Open(cfg.DBPath)
	if err != nil {
		log.Fatalf("打开数据库失败: %v", err)
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
		log.Printf("推送调度器已启动，每日 %s（%s）", cfg.Push.Time, cfg.Push.Timezone)
	}

	log.Printf("second-brain 正在监听 %s，数据库路径 %s", cfg.Addr, cfg.DBPath)

	// 启动服务
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP 服务异常: %v", err)
		}
	}()

	// 等待中断信号
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	log.Println("收到退出信号，正在优雅关闭...")

	// 停止推送调度器
	if sched != nil {
		sched.Stop()
	}

	// 优雅关闭 HTTP 服务
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("HTTP 关闭出错: %v", err)
	}

	// 关闭数据库
	if err := st.Close(); err != nil {
		log.Printf("数据库关闭出错: %v", err)
	}

	log.Println("已退出")
}
