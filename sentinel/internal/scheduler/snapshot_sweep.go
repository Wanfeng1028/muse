package scheduler

import (
	"os"
	"strconv"
	"time"

	"sentinel/internal/log"
)

// SetSnapshotGenerator 设置快照定时生成回调，nil 表示禁用。
func (s *Scheduler) SetSnapshotGenerator(fn func(pageID int64) error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.snapshotGen = fn
}

// maybeSweepSnapshots 节流：snapshotGen 为 nil 直接返回；距离上次扫描不足 5 分钟直接返回；
// 否则更新 lastSnapshotSweep 并调用 s.sweepSnapshot()。锁只保护字段读写，不包裹扫描本体。
func (s *Scheduler) maybeSweepSnapshots() {
	s.mu.Lock()
	if s.snapshotGen == nil {
		s.mu.Unlock()
		return
	}
	if time.Since(s.lastSnapshotSweep) < 5*time.Minute {
		s.mu.Unlock()
		return
	}
	s.lastSnapshotSweep = time.Now()
	s.mu.Unlock()

	s.sweepSnapshot()
}

// sweepSnapshot 遍历所有状态页，根据快照计划决定是否生成快照并裁剪历史。
func (s *Scheduler) sweepSnapshot() {
	s.mu.Lock()
	fn := s.snapshotGen
	s.mu.Unlock()
	if fn == nil {
		return
	}

	pages, err := s.store.ListStatusPages(1)
	if err != nil {
		log.Logger().Warn("获取状态页列表失败", "err", err)
		return
	}

	var generated, failed int

	for _, page := range pages {
		schedule := page.SnapshotSchedule
		var interval time.Duration
		switch schedule {
		case "off":
			continue
		case "daily":
			interval = 24 * time.Hour
		case "hourly":
			interval = 1 * time.Hour
		default:
			// 非法值跳过
			continue
		}

		last, found, err := s.store.LatestStatusSnapshotAt(page.ID)
		if err == nil && found {
			t, parseErr := time.Parse(time.RFC3339, last)
			if parseErr == nil && time.Since(t) < interval {
				continue
			}
		}

		if genErr := fn(page.ID); genErr != nil {
			log.Logger().Warn("快照生成失败", "pageID", page.ID, "err", genErr)
			failed++
			continue
		}
		generated++

		if _, pruneErr := s.store.PruneStatusSnapshots(page.ID, snapshotRetain()); pruneErr != nil {
			log.Logger().Warn("快照裁剪失败", "pageID", page.ID, "err", pruneErr)
		}
	}

	log.Logger().Info("快照扫描完成", "generated", generated, "failed", failed)
}

// snapshotRetain 读环境变量 SENTINEL_SNAPSHOT_RETAIN，解析失败或 <=0 返回 30。
func snapshotRetain() int {
	v := os.Getenv("SENTINEL_SNAPSHOT_RETAIN")
	if v == "" {
		return 30
	}
	n, err := strconv.Atoi(v)
	if err != nil || n <= 0 {
		return 30
	}
	return n
}
