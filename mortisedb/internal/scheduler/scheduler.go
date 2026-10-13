// Package scheduler 提供基于间隔的定时同步调度能力。
package scheduler

import (
	"context"
	"sync"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
	syncpkg "github.com/Wanfeng1028/muse/mortisedb/internal/sync"
)

// Scheduler 负责按配置的作业间隔周期性地触发同步。
type Scheduler struct {
	cfg    *config.Config
	st     *store.Store
	logger *log.Logger
	wg     sync.WaitGroup
	cancel context.CancelFunc
}

// New 创建一个调度器实例。
func New(cfg *config.Config, st *store.Store, logger *log.Logger) *Scheduler {
	return &Scheduler{
		cfg:    cfg,
		st:     st,
		logger: logger,
	}
}

// Start 为每个作业启动一个 goroutine，按 Interval 周期性地执行同步。
// Interval 非法时记录错误并跳过该作业。
func (s *Scheduler) Start(ctx context.Context) {
	ctx, cancel := context.WithCancel(ctx)
	s.cancel = cancel

	for _, job := range s.cfg.Jobs {
		interval, err := time.ParseDuration(job.Interval)
		if err != nil {
			s.logger.Error("解析作业间隔失败，跳过该作业", map[string]any{
				"job":      job.Name,
				"interval": job.Interval,
				"error":    err.Error(),
			})
			continue
		}
		if interval <= 0 {
			s.logger.Error("作业间隔必须大于 0，跳过该作业", map[string]any{
				"job":      job.Name,
				"interval": job.Interval,
			})
			continue
		}

		s.wg.Add(1)
		go s.runJob(ctx, job, interval)
	}
}

// runJob 单个作业的循环执行体。
func (s *Scheduler) runJob(ctx context.Context, job config.JobConfig, interval time.Duration) {
	defer s.wg.Done()

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	s.logger.Info("作业已启动", map[string]any{
		"job":      job.Name,
		"interval": job.Interval,
	})

	for {
		select {
		case <-ctx.Done():
			s.logger.Info("作业已停止", map[string]any{"job": job.Name})
			return
		case <-ticker.C:
			stats, err := syncpkg.Sync(s.cfg, s.st, job.Sources, job.Name)
			if err != nil {
				// 错误仅记录日志，不退出循环。
				s.logger.Error("作业同步失败", map[string]any{
					"job":   job.Name,
					"error": err.Error(),
				})
				continue
			}
			s.logger.Info("作业同步完成", map[string]any{
				"job":   job.Name,
				"stats": stats,
			})
		}
	}
}

// Stop 取消所有作业并等待其退出。
func (s *Scheduler) Stop() {
	if s.cancel != nil {
		s.cancel()
	}
	s.wg.Wait()
}
