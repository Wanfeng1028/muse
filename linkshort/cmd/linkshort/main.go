package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/handler"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func main() {
	if err := run(); err != nil {
		log.Fatalf("linkshort: %v", err)
	}
}

// run 负责装配依赖、启动 HTTP 服务并处理优雅退出。
func run() error {
	cfg := config.FromEnv()

	// 确保数据库所在目录存在。
	if dir := filepath.Dir(cfg.DBPath); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
	}

	database, err := db.Open(cfg.DBPath)
	if err != nil {
		return err
	}
	defer func() {
		if cerr := database.Close(); cerr != nil {
			log.Printf("[shutdown] close db: %v", cerr)
		}
	}()

	st := store.New(database)
	router := handler.NewRouter(st, cfg)

	srv := &http.Server{
		Addr:              cfg.Addr,
		Handler:           router,
		ReadHeaderTimeout: 10 * time.Second,
	}

	// 后台启动 HTTP 服务。
	serverErr := make(chan error, 1)
	go func() {
		log.Printf("[start] linkshort 监听于 %s，数据库 %s", cfg.Addr, cfg.DBPath)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			serverErr <- err
			return
		}
		serverErr <- nil
	}()

	// 等待退出信号或服务器错误。
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	select {
	case err := <-serverErr:
		if err != nil {
			return err
		}
		return nil
	case sig := <-sigCh:
		log.Printf("[shutdown] 收到信号 %s，开始优雅退出", sig)
	}

	// 优雅退出：最多等待 10 秒。
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		return err
	}
	// 等后台 goroutine 收尾。
	if err := <-serverErr; err != nil {
		return err
	}
	log.Printf("[shutdown] 已退出")
	return nil
}
