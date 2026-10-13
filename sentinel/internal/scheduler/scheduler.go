package scheduler

import (
	"context"
	"sync"
	"time"

	"sentinel/internal/checker"
	"sentinel/internal/log"
	"sentinel/internal/metrics"
	"sentinel/internal/store"
)

// Scheduler 周期性扫描到期监控并执行检查。
type Scheduler struct {
	store      *store.Store
	notify     func(webhookURL, event, name, target, at, errMsg string)
	sem        chan struct{}
	tickSec    int
	maxRetries int
	inflight   map[int64]bool
	mu         sync.Mutex
}

// New 创建调度器。concurrency<=0 则 10；tickSec<=0 则 5。
func New(st *store.Store, notifyFn func(webhookURL, event, name, target, at, errMsg string), concurrency, tickSec, maxRetries int) *Scheduler {
	if concurrency <= 0 {
		concurrency = 10
	}
	if tickSec <= 0 {
		tickSec = 5
	}
	if maxRetries < 0 {
		maxRetries = 0
	}
	return &Scheduler{
		store:      st,
		notify:     notifyFn,
		sem:        make(chan struct{}, concurrency),
		tickSec:    tickSec,
		maxRetries: maxRetries,
		inflight:   make(map[int64]bool),
	}
}

// Start 启动调度循环，立即执行一次 tick，随后每 tickSec 秒一次。
func (s *Scheduler) Start(ctx context.Context) {
	log.Logger().Info("调度器启动", "tickSec", s.tickSec)

	s.tick(ctx)

	ticker := time.NewTicker(time.Duration(s.tickSec) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Logger().Info("调度器退出")
			return
		case <-ticker.C:
			s.tick(ctx)
		}
	}
}

// tick 遍历所有监控，找出到期任务并异步执行。
func (s *Scheduler) tick(ctx context.Context) {
	monitors, err := s.store.ListMonitors()
	if err != nil {
		log.Logger().Error("调度器列出监控失败", "err", err)
		return
	}

	now := time.Now()
	for _, m := range monitors {
		if m.Enabled != 1 {
			continue
		}

		interval := m.IntervalSec
		if interval <= 0 {
			interval = 60
		}

		last, err := s.store.LastCheck(m.ID)
		if err != nil {
			log.Logger().Warn("调度器读取上次检查失败", "monitorID", m.ID, "err", err)
			continue
		}
		hasLast := last != nil

		due := !hasLast
		if hasLast {
			if t, perr := time.Parse(time.RFC3339, last.CheckedAt); perr != nil {
				due = true
			} else if !t.Add(time.Duration(interval) * time.Second).After(now) {
				due = true
			}
		}
		if !due {
			continue
		}

		s.mu.Lock()
		if s.inflight[m.ID] {
			s.mu.Unlock()
			continue
		}
		s.inflight[m.ID] = true
		s.mu.Unlock()

		prevOk := false
		if hasLast {
			prevOk = last.Ok == 1
		}

		go func(m store.Monitor, prevOk, hasPrev bool) {
			defer func() {
				s.mu.Lock()
				delete(s.inflight, m.ID)
				s.mu.Unlock()
			}()
			s.runOne(ctx, m, prevOk, hasPrev)
		}(m, prevOk, hasLast)
	}
}

// runOne 执行单次检查，带并发限流。
func (s *Scheduler) runOne(ctx context.Context, m store.Monitor, prevOk, hasPrev bool) {
	select {
	case s.sem <- struct{}{}:
		defer func() { <-s.sem }()
	case <-ctx.Done():
		return
	}

	c, retries := checker.CheckWithRetry(m, s.maxRetries)
	metrics.Default.RecordCheck(c.Ok == 1, c.LatencyMs, retries > 0)

	if _, err := s.store.InsertCheck(c); err != nil {
		log.Logger().Error("写入检查结果失败", "monitorID", m.ID, "err", err)
	}

	s.record(m, c, prevOk, hasPrev)
}

// CheckNow 同步执行一次检查（供 API 手动触发）。
func (s *Scheduler) CheckNow(id int64, maxRetries int) (store.Check, error) {
	m, err := s.store.GetMonitor(id)
	if err != nil {
		return store.Check{}, err
	}

	last, err := s.store.LastCheck(m.ID)
	if err != nil {
		log.Logger().Warn("读取上次检查失败", "monitorID", m.ID, "err", err)
	}
	hasLast := err == nil && last != nil
	prevOk := false
	if hasLast {
		prevOk = last.Ok == 1
	}

	c, retries := checker.CheckWithRetry(m, maxRetries)
	metrics.Default.RecordCheck(c.Ok == 1, c.LatencyMs, retries > 0)

	if _, err := s.store.InsertCheck(c); err != nil {
		log.Logger().Error("写入检查结果失败", "monitorID", m.ID, "err", err)
	}

	s.record(m, c, prevOk, hasLast)
	return c, nil
}

// record 根据状态翻转触发事件（down / recovered）。
func (s *Scheduler) record(m store.Monitor, c store.Check, prevOk, hasPrev bool) {
	nowOk := c.Ok == 1
	at := c.CheckedAt

	if !nowOk {
		// 无上次记录视为首次失败，也开事件。
		if !hasPrev || prevOk {
			if _, err := s.store.OpenIncident(m.ID, at, c.Error); err != nil {
				log.Logger().Error("开启事件失败", "monitorID", m.ID, "err", err)
			}
			if s.notify != nil {
				s.notify(m.WebhookURL, "down", m.Name, m.Target, at, c.Error)
			}
		}
		return
	}

	// 本次成功，且上次存在且失败 → 恢复。
	if hasPrev && !prevOk {
		var secs int64
		if startedAt, serr := s.store.OpenIncidentStartedAt(m.ID); serr == nil {
			if st, pe1 := time.Parse(time.RFC3339, startedAt); pe1 == nil {
				if et, pe2 := time.Parse(time.RFC3339, at); pe2 == nil {
					secs = int64(et.Sub(st).Seconds())
					if secs < 0 {
						secs = 0
					}
				}
			}
		}
		if err := s.store.CloseOpenIncident(m.ID, at, secs); err != nil {
			log.Logger().Error("关闭事件失败", "monitorID", m.ID, "err", err)
		}
		if s.notify != nil {
			s.notify(m.WebhookURL, "recovered", m.Name, m.Target, at, "")
		}
	}
}
