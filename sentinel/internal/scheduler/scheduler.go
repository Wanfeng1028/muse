// Package scheduler 实现监控目标的后台调度与翻转检测。
package scheduler

import (
	"context"
	"database/sql"
	"log"
	"time"

	"sentinel/internal/checker"
	"sentinel/internal/store"
)

// Scheduler 周期性挑选到期的监控目标并并发执行检查。
type Scheduler struct {
	store  *store.Store
	notify func(webhookURL, event, name, target, at, errMsg string)
	sem    chan struct{}
}

// New 创建一个调度器，并发上限为 10。
func New(st *store.Store, notifyFn func(string, string, string, string, string, string)) *Scheduler {
	return &Scheduler{
		store:  st,
		notify: notifyFn,
		sem:    make(chan struct{}, 10),
	}
}

// Start 立即执行一轮 tick，随后每 5 秒一轮，直到 ctx 取消。
func (sc *Scheduler) Start(ctx context.Context) {
	sc.tick()
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			sc.tick()
		}
	}
}

// tick 挑选 enabled=1 且已到期的监控目标并发执行。
func (sc *Scheduler) tick() {
	monitors, err := sc.store.ListMonitors()
	if err != nil {
		log.Printf("scheduler: 列出监控失败: %v", err)
		return
	}
	now := time.Now().UTC()
	for _, m := range monitors {
		if m.Enabled != 1 {
			continue
		}
		last, err := sc.store.LastCheck(m.ID)
		if err != nil {
			log.Printf("scheduler: 读取上次检查失败 monitor=%d: %v", m.ID, err)
			continue
		}
		due := false
		var prevOk bool
		hasPrev := false
		if last == nil {
			due = true
		} else {
			prevOk = last.Ok == 1
			hasPrev = true
			t, perr := time.Parse(time.RFC3339, last.CheckedAt)
			if perr != nil {
				// 时间解析失败视为到期，避免永久卡死。
				due = true
			} else if !t.Add(time.Duration(m.IntervalSec) * time.Second).After(now) {
				due = true
			}
		}
		if !due {
			continue
		}
		mon := m
		po := prevOk
		hp := hasPrev
		go sc.runOne(mon, po, hp)
	}
}

// runOne 执行一次检查并处理翻转。
func (sc *Scheduler) runOne(m store.Monitor, prevOk bool, hasPrev bool) {
	sc.sem <- struct{}{}
	defer func() { <-sc.sem }()

	c := checker.Check(m)
	id, err := sc.store.InsertCheck(c)
	if err != nil {
		log.Printf("scheduler: 写入检查记录失败 monitor=%d: %v", m.ID, err)
	} else {
		c.ID = id
	}
	if _, rerr := sc.record(m, c, prevOk, hasPrev); rerr != nil {
		log.Printf("scheduler: 翻转处理失败 monitor=%d: %v", m.ID, rerr)
	}
}

// record 记录翻转：down 时开 incident 并通知，recovered 时关 incident 并通知。
func (sc *Scheduler) record(m store.Monitor, c store.Check, prevOk bool, hasPrev bool) (store.Check, error) {
	if hasPrev && prevOk && c.Ok == 0 {
		if _, err := sc.store.OpenIncident(m.ID, c.CheckedAt, c.Error); err != nil {
			return c, err
		}
		if sc.notify != nil {
			sc.notify(m.WebhookURL, "down", m.Name, m.Target, c.CheckedAt, c.Error)
		}
	}
	if hasPrev && !prevOk && c.Ok == 1 {
		startedAt, err := sc.store.OpenIncidentStartedAt(m.ID)
		if err != nil {
			if err == sql.ErrNoRows {
				// 没有未关闭的 incident，跳过关闭与通知。
				return c, nil
			}
			return c, err
		}
		startT, perr := time.Parse(time.RFC3339, startedAt)
		endT, perr2 := time.Parse(time.RFC3339, c.CheckedAt)
		var secs int64
		if perr == nil && perr2 == nil {
			secs = int64(endT.Sub(startT).Seconds())
			if secs < 0 {
				secs = 0
			}
		}
		if err := sc.store.CloseOpenIncident(m.ID, c.CheckedAt, secs); err != nil {
			return c, err
		}
		if sc.notify != nil {
			sc.notify(m.WebhookURL, "recovered", m.Name, m.Target, c.CheckedAt, "")
		}
	}
	return c, nil
}

// CheckNow 立即对指定监控执行一次检查并返回结果。
func (sc *Scheduler) CheckNow(id int64) (store.Check, error) {
	m, err := sc.store.GetMonitor(id)
	if err != nil {
		return store.Check{}, err
	}
	last, err := sc.store.LastCheck(id)
	if err != nil {
		return store.Check{}, err
	}
	prevOk := false
	hasPrev := false
	if last != nil {
		prevOk = last.Ok == 1
		hasPrev = true
	}
	sc.sem <- struct{}{}
	defer func() { <-sc.sem }()

	c := checker.Check(m)
	cid, ierr := sc.store.InsertCheck(c)
	if ierr != nil {
		return c, ierr
	}
	c.ID = cid
	out, rerr := sc.record(m, c, prevOk, hasPrev)
	if rerr != nil {
		return out, rerr
	}
	return out, nil
}
