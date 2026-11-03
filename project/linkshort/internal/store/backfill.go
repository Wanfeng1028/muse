package store

import (
	"fmt"
)

// BackfillBurnedAt 回填 v1.5 之前销毁的 burn 链的 burned_at 字段。
//
// 回填目的：v1.5 之前销毁的 burn 链没有 burned_at，导致定时清理永远跳过它们。
// 只认 enabled = 0 的依据：enabled = 0 的 burn 链表示已经销毁（MarkBurned 会把 enabled 置 0），
// 仍 enabled = 1 的 burn 链尚未被访问销毁，绝不能回填。
// 回填值选取规则：优先取该链最后一次访问时间（visits 表中同 link_id 的最大 ts），
// 若无访问记录则回退取该行自身的 updated_at。
// 回填后该行即进入正常保留期清理口径（不会被立即删除，删除仍由保留期 cutoff 决定）。
func (s *Store) BackfillBurnedAt() (int64, error) {
	res, err := s.db.Exec(`
UPDATE links
SET burned_at = COALESCE((SELECT MAX(ts) FROM visits WHERE visits.link_id = links.id), links.updated_at)
WHERE burn = 1 AND enabled = 0 AND burned_at IS NULL`)
	if err != nil {
		return 0, fmt.Errorf("backfill burned_at: %w", err)
	}

	n, err := res.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("backfill burned_at: %w", err)
	}

	return n, nil
}
