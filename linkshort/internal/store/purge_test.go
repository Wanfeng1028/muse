package store

import (
	"errors"
	"testing"
)

func TestPurgeLink_彻底删除并级联清访问日志(t *testing.T) {
	st := newTestStore(t)

	id, err := st.CreateLinkEx("t-pg-1", "https://example.com/x", "", nil, nil, true)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}

	if err := st.RecordVisit(id, "h", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit #1 失败: %v", err)
	}
	if err := st.RecordVisit(id, "h", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit #2 失败: %v", err)
	}

	if err := st.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned 失败: %v", err)
	}

	if err := st.PurgeLink(id); err != nil {
		t.Fatalf("PurgeLink 失败: %v", err)
	}

	if _, err := st.GetLink(id); !errors.Is(err, ErrNotFound) {
		t.Fatalf("PurgeLink 后 GetLink 期望 ErrNotFound, 实际: %v", err)
	}

	daily, err := st.LinkDailyClicks(id, 1)
	if err != nil {
		t.Fatalf("LinkDailyClicks 失败: %v", err)
	}
	for _, d := range daily {
		if d.Clicks != 0 {
			t.Fatalf("访问日志未级联删除, day=%s n=%d", d.Date, d.Clicks)
		}
	}

	if err := st.PurgeLink(id); !errors.Is(err, ErrNotFound) {
		t.Fatalf("重复 PurgeLink 期望 ErrNotFound, 实际: %v", err)
	}
}

func TestPurgeLink_不存在返回NotFound(t *testing.T) {
	st := newTestStore(t)

	if err := st.PurgeLink(999999); !errors.Is(err, ErrNotFound) {
		t.Fatalf("PurgeLink 不存在期望 ErrNotFound, 实际: %v", err)
	}
}
