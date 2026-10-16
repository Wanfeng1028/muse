package store

import (
	"errors"
	"testing"
	"time"
)

func TestPurgeExpiredBurned_只删超期已销毁(t *testing.T) {
	st := newTestStore(t)

	// ① 超期已销毁 burn：MarkBurned 后把 burned_at 回拨 10 天。
	idOld, err := st.CreateLinkEx("pg-old", "https://example.com/old", "old", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx old: %v", err)
	}
	if err := st.MarkBurned(idOld); err != nil {
		t.Fatalf("MarkBurned old: %v", err)
	}
	if _, err := st.db.Exec("UPDATE links SET burned_at = ? WHERE id = ?", formatTime(nowUTC().Add(-240*time.Hour)), idOld); err != nil {
		t.Fatalf("backdate burned_at: %v", err)
	}

	// ② 刚销毁 burn：不回拨。
	idNew, err := st.CreateLinkEx("pg-new", "https://example.com/new", "new", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx new: %v", err)
	}
	if err := st.MarkBurned(idNew); err != nil {
		t.Fatalf("MarkBurned new: %v", err)
	}

	// ③ 未销毁 burn。
	idNotBurned, err := st.CreateLinkEx("pg-notburned", "https://example.com/nb", "nb", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx notburned: %v", err)
	}

	// ④ 普通链。
	idPlain, err := st.CreateLinkEx("pg-plain", "https://example.com/plain", "plain", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx plain: %v", err)
	}

	// ⑤ burned_at=NULL 的历史行。
	idNull, err := st.CreateLinkEx("pg-null", "https://example.com/null", "null", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx null: %v", err)
	}
	if err := st.MarkBurned(idNull); err != nil {
		t.Fatalf("MarkBurned null: %v", err)
	}
	if _, err := st.db.Exec("UPDATE links SET burned_at = NULL WHERE id = ?", idNull); err != nil {
		t.Fatalf("null burned_at: %v", err)
	}

	n, err := st.PurgeExpiredBurned(nowUTC().Add(-7 * 24 * time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 1 {
		t.Fatalf("purged = %d, want 1", n)
	}

	if _, err := st.GetLink(idOld); !errors.Is(err, ErrNotFound) {
		t.Fatalf("old link err = %v, want ErrNotFound", err)
	}
	for _, id := range []int64{idNew, idNotBurned, idPlain, idNull} {
		if _, err := st.GetLink(id); err != nil {
			t.Fatalf("link %d should exist, err = %v", id, err)
		}
	}
}

func TestPurgeExpiredBurned_无超期返回0(t *testing.T) {
	st := newTestStore(t)

	id, err := st.CreateLinkEx("pg-fresh", "https://example.com/fresh", "fresh", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := st.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}

	n, err := st.PurgeExpiredBurned(nowUTC().Add(-30 * 24 * time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 0 {
		t.Fatalf("purged = %d, want 0", n)
	}
	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("link should exist, err = %v", err)
	}
}

func TestMarkBurned_设置BurnedAt(t *testing.T) {
	st := newTestStore(t)

	id, err := st.CreateLinkEx("pg-mark", "https://example.com/mark", "mark", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	before, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink before: %v", err)
	}
	if before.BurnedAt != nil {
		t.Fatalf("BurnedAt before = %v, want nil", before.BurnedAt)
	}

	if err := st.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}

	after, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink after: %v", err)
	}
	if after.BurnedAt == nil {
		t.Fatalf("BurnedAt after = nil, want non-nil")
	}
	if after.Enabled {
		t.Fatalf("Enabled after = true, want false")
	}
}
