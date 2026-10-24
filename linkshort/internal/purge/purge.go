// Package purge 提供 burn 短链的定时清理：后台 goroutine 按间隔删除已销毁且超过保留期的链接。
package purge

import (
	"context"
	"log"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/metrics"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

// Start 启动定时清理循环，直到 ctx 取消。启动时先执行一轮，随后按配置间隔执行。
func Start(ctx context.Context, st *store.Store, cfg *config.Config) {
	retention := time.Duration(cfg.PurgeRetentionDays) * 24 * time.Hour
	log.Printf("[purge] 定时清理已启动：interval=%s，retention=%dd，目标=已销毁的 burn 短链 + 过期的时间链", cfg.PurgeInterval, cfg.PurgeRetentionDays)

	sweep := func() {
		nb, err := st.BackfillBurnedAt()
		if err != nil {
			log.Printf("[purge] 回填失败：%v", err)
			return
		}
		if nb > 0 {
			log.Printf("[purge] 回填完成：为 %d 条已销毁 burn 短链补齐 burned_at", nb)
		}

		cutoff := time.Now().Add(-retention)
		n, err := st.PurgeExpiredBurned(cutoff)
		if err != nil {
			log.Printf("[purge] 清理失败：%v", err)
			return
		}
		if n > 0 {
			log.Printf("[purge] 清理完成：删除 %d 条已销毁 burn 短链", n)
			metrics.Default.IncLinksPurged(n)
		}

		cutoff2 := time.Now().Add(-retention)
		n2, err := st.PurgeExpiredLinks(cutoff2)
		if err != nil {
			log.Printf("[purge] 清理过期链接失败：%v", err)
			return
		}
		if n2 > 0 {
			log.Printf("[purge] 清理完成：删除 %d 条过期链接", n2)
			metrics.Default.IncExpiredLinksPurged(n2)
		}
	}
	sweep()

	ticker := time.NewTicker(cfg.PurgeInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			log.Printf("[purge] 定时清理已停止")
			return
		case <-ticker.C:
			sweep()
		}
	}
}
