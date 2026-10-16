package store

import (
	"testing"
	"time"
)

func mustCreateSilence(t *testing.T, st *Store, sl Silence) int64 {
	t.Helper()
	id, err := st.CreateSilence(sl)
	if err != nil {
		t.Fatalf("CreateSilence: %v", err)
	}
	return id
}

func TestCreateSilenceAndList(t *testing.T) {
	st := newTestStore(t)
	start := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	end := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	id := mustCreateSilence(t, st, Silence{
		MonitorID: 0,
		NameMatch: "api",
		StartsAt:  start,
		EndsAt:    end,
		Reason:    "维护窗口",
	})
	if id <= 0 {
		t.Fatalf("期望正 id，得到 %d", id)
	}
	list, err := st.ListSilences()
	if err != nil {
		t.Fatalf("ListSilences: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("期望 1 条，得到 %d", len(list))
	}
	if list[0].ID != id || list[0].NameMatch != "api" || list[0].Reason != "维护窗口" {
		t.Fatalf("列表内容不符: %+v", list[0])
	}
}

func TestCreateSilenceRejectsBadWindow(t *testing.T) {
	st := newTestStore(t)
	start := time.Now().UTC().Format(time.RFC3339)
	end := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	if _, err := st.CreateSilence(Silence{
		StartsAt: start, EndsAt: end, Reason: "x",
	}); err == nil {
		t.Fatalf("期望 starts_at >= ends_at 被拒")
	}
	if _, err := st.CreateSilence(Silence{
		StartsAt: "not-a-time", EndsAt: end, Reason: "x",
	}); err == nil {
		t.Fatalf("期望非法时间被拒")
	}
}

func TestCreateSilenceRejectsEmptyReason(t *testing.T) {
	st := newTestStore(t)
	start := time.Now().UTC().Format(time.RFC3339)
	end := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	if _, err := st.CreateSilence(Silence{
		StartsAt: start, EndsAt: end, Reason: "   ",
	}); err == nil {
		t.Fatalf("期望空 reason 被拒")
	}
}

func TestFindActiveSilenceHitInsideWindow(t *testing.T) {
	st := newTestStore(t)
	now := time.Now().UTC()
	mustCreateSilence(t, st, Silence{
		MonitorID: 7,
		StartsAt:  now.Add(-time.Minute).Format(time.RFC3339),
		EndsAt:    now.Add(time.Minute).Format(time.RFC3339),
		Reason:    "in",
	})
	sil, ok, err := st.FindActiveSilence(7, "anything", now)
	if err != nil {
		t.Fatalf("FindActiveSilence: %v", err)
	}
	if !ok || sil == nil {
		t.Fatalf("期望命中，得到 ok=%v sil=%v", ok, sil)
	}
	if sil.Reason != "in" {
		t.Fatalf("reason 不符: %s", sil.Reason)
	}
}

func TestFindActiveSilenceMissOutsideWindow(t *testing.T) {
	st := newTestStore(t)
	now := time.Now().UTC()
	mustCreateSilence(t, st, Silence{
		MonitorID: 7,
		StartsAt:  now.Add(time.Hour).Format(time.RFC3339),
		EndsAt:    now.Add(2 * time.Hour).Format(time.RFC3339),
		Reason:    "future",
	})
	_, ok, err := st.FindActiveSilence(7, "anything", now)
	if err != nil {
		t.Fatalf("FindActiveSilence: %v", err)
	}
	if ok {
		t.Fatalf("期望不命中")
	}
}

func TestFindActiveSilenceOverlapPicksSmallestID(t *testing.T) {
	st := newTestStore(t)
	now := time.Now().UTC()
	first := mustCreateSilence(t, st, Silence{
		MonitorID: 0,
		StartsAt:  now.Add(-time.Minute).Format(time.RFC3339),
		EndsAt:    now.Add(time.Minute).Format(time.RFC3339),
		Reason:    "first",
	})
	_ = mustCreateSilence(t, st, Silence{
		MonitorID: 0,
		StartsAt:  now.Add(-time.Minute).Format(time.RFC3339),
		EndsAt:    now.Add(time.Minute).Format(time.RFC3339),
		Reason:    "second",
	})
	sil, ok, err := st.FindActiveSilence(1, "x", now)
	if err != nil || !ok {
		t.Fatalf("FindActiveSilence: err=%v ok=%v", err, ok)
	}
	if sil.ID != first {
		t.Fatalf("期望返回最小 id %d，得到 %d", first, sil.ID)
	}
}

func TestFindActiveSilenceGlobalMonitor(t *testing.T) {
	st := newTestStore(t)
	now := time.Now().UTC()
	mustCreateSilence(t, st, Silence{
		MonitorID: 0,
		StartsAt:  now.Add(-time.Minute).Format(time.RFC3339),
		EndsAt:    now.Add(time.Minute).Format(time.RFC3339),
		Reason:    "global",
	})
	_, ok, err := st.FindActiveSilence(999, "anything", now)
	if err != nil {
		t.Fatalf("FindActiveSilence: %v", err)
	}
	if !ok {
		t.Fatalf("期望全局静默命中")
	}
}

func TestFindActiveSilenceNameMatch(t *testing.T) {
	st := newTestStore(t)
	now := time.Now().UTC()
	mustCreateSilence(t, st, Silence{
		NameMatch: "api",
		StartsAt:  now.Add(-time.Minute).Format(time.RFC3339),
		EndsAt:    now.Add(time.Minute).Format(time.RFC3339),
		Reason:    "api-only",
	})
	if _, ok, err := st.FindActiveSilence(1, "prod-api-01", now); err != nil || !ok {
		t.Fatalf("期望子串命中: err=%v ok=%v", err, ok)
	}
	if _, ok, err := st.FindActiveSilence(1, "prod-web-01", now); err != nil || ok {
		t.Fatalf("期望不命中: err=%v ok=%v", err, ok)
	}
}

func TestDeleteSilenceThenMiss(t *testing.T) {
	st := newTestStore(t)
	now := time.Now().UTC()
	id := mustCreateSilence(t, st, Silence{
		StartsAt: now.Add(-time.Minute).Format(time.RFC3339),
		EndsAt:   now.Add(time.Minute).Format(time.RFC3339),
		Reason:   "del",
	})
	if _, ok, _ := st.FindActiveSilence(1, "x", now); !ok {
		t.Fatalf("删除前应命中")
	}
	if err := st.DeleteSilence(id); err != nil {
		t.Fatalf("DeleteSilence: %v", err)
	}
	if _, ok, _ := st.FindActiveSilence(1, "x", now); ok {
		t.Fatalf("删除后不应命中")
	}
}

func TestGetSilenceMissing(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.GetSilence(12345); err == nil {
		t.Fatalf("期望 GetSilence 对不存在 id 报错")
	}
}
