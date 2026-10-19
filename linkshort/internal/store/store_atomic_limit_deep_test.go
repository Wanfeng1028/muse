package store

import (
	"sync"
	"sync/atomic"
	"testing"

)

// mkLimitLink 建一条 max_visits 可空的链，返回 id。
func mkLimitLink(t *testing.T, st *Store, slug string, maxVisits *int64, burn bool) int64 {
	t.Helper()
	id, err := st.CreateLinkEx(slug, "https://example.com/"+slug, "", nil, maxVisits, burn, false)
	if err != nil {
		t.Fatalf("CreateLinkEx(%s): %v", slug, err)
	}
	return id
}

func i64ptr(v int64) *int64 { return &v }

// TestTryConsumeVisit_精确N次 max_visits=5：串行 7 次 → 前 5 次 true 后 2 次 false，clicks==5。
func TestTryConsumeVisit_精确N次(t *testing.T) {
	st := newTestStore(t)
	id := mkLimitLink(t, st, "limit5", i64ptr(5), false)

	for i := 0; i < 5; i++ {
		ok, err := st.TryConsumeVisit(id)
		if err != nil {
			t.Fatalf("第 %d 次 TryConsumeVisit err=%v", i+1, err)
		}
		if !ok {
			t.Fatalf("第 %d 次 TryConsumeVisit 应 true", i+1)
		}
	}
	for i := 0; i < 2; i++ {
		ok, err := st.TryConsumeVisit(id)
		if err != nil {
			t.Fatalf("超额第 %d 次 TryConsumeVisit err=%v", i+1, err)
		}
		if ok {
			t.Fatalf("超额第 %d 次 TryConsumeVisit 应 false", i+1)
		}
	}
	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.Clicks != 5 {
		t.Fatalf("Clicks = %d，期望 5", link.Clicks)
	}
}

// TestTryConsumeVisit_不限次 max_visits=nil：10 次全 true。
func TestTryConsumeVisit_不限次(t *testing.T) {
	st := newTestStore(t)
	id := mkLimitLink(t, st, "unlimited", nil, false)

	for i := 0; i < 10; i++ {
		ok, err := st.TryConsumeVisit(id)
		if err != nil {
			t.Fatalf("第 %d 次 TryConsumeVisit err=%v", i+1, err)
		}
		if !ok {
			t.Fatalf("第 %d 次 TryConsumeVisit 应 true（不限次）", i+1)
		}
	}
	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.Clicks != 10 {
		t.Fatalf("Clicks = %d，期望 10", link.Clicks)
	}
}

// TestTryConsumeVisit_不存在id 返回 false, nil 不报错。
func TestTryConsumeVisit_不存在id(t *testing.T) {
	st := newTestStore(t)
	ok, err := st.TryConsumeVisit(999999)
	if err != nil {
		t.Fatalf("不存在 id 应返回 nil err，got %v", err)
	}
	if ok {
		t.Fatalf("不存在 id 应返回 false")
	}
}

// TestTryBurn_串行两次 第一次 true，第二次 false。
func TestTryBurn_串行两次(t *testing.T) {
	st := newTestStore(t)
	id := mkLimitLink(t, st, "burn2", nil, true)

	ok, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("第一次 TryBurn err=%v", err)
	}
	if !ok {
		t.Fatalf("第一次 TryBurn 应 true")
	}
	ok, err = st.TryBurn(id)
	if err != nil {
		t.Fatalf("第二次 TryBurn err=%v", err)
	}
	if ok {
		t.Fatalf("第二次 TryBurn 应 false")
	}
}

// TestTryBurn_非burn链 返回 false。
func TestTryBurn_非burn链(t *testing.T) {
	st := newTestStore(t)
	id := mkLimitLink(t, st, "notburn2", nil, false)

	ok, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn err=%v", err)
	}
	if ok {
		t.Fatalf("非 burn 链 TryBurn 应 false")
	}
}

// TestAtomic_并发32协程TryConsumeVisit_max5 恰 5 个 true。
func TestAtomic_并发32协程TryConsumeVisit_max5(t *testing.T) {
	st := newTestStore(t)
	id := mkLimitLink(t, st, "conclimit5", i64ptr(5), false)

	const n = 32
	var trueCount int32
	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func() {
			defer wg.Done()
			<-start
			ok, err := st.TryConsumeVisit(id)
			if err != nil {
				t.Errorf("TryConsumeVisit err=%v", err)
				return
			}
			if ok {
				atomic.AddInt32(&trueCount, 1)
			}
		}()
	}
	close(start)
	wg.Wait()

	if trueCount != 5 {
		t.Fatalf("并发 TryConsumeVisit true 数 = %d，期望 5", trueCount)
	}
	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.Clicks != 5 {
		t.Fatalf("Clicks = %d，期望 5", link.Clicks)
	}
}

// TestAtomic_并发32协程TryBurn 恰 1 个 true。
func TestAtomic_并发32协程TryBurn(t *testing.T) {
	st := newTestStore(t)
	id := mkLimitLink(t, st, "concburn", nil, true)

	const n = 32
	var trueCount int32
	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func() {
			defer wg.Done()
			<-start
			ok, err := st.TryBurn(id)
			if err != nil {
				t.Errorf("TryBurn err=%v", err)
				return
			}
			if ok {
				atomic.AddInt32(&trueCount, 1)
			}
		}()
	}
	close(start)
	wg.Wait()

	if trueCount != 1 {
		t.Fatalf("并发 TryBurn true 数 = %d，期望 1", trueCount)
	}
}

// TestRecordVisitNoCount_不计clicks 调一次后 clicks 不变，visits 行 +1。
func TestRecordVisitNoCount_不计clicks(t *testing.T) {
	st := newTestStore(t)
	id := mkLimitLink(t, st, "nocount", nil, false)

	if err := st.RecordVisitNoCount(id, "iphash", "ua", "ref", "US", "United States", "CA", "SF"); err != nil {
		t.Fatalf("RecordVisitNoCount: %v", err)
	}

	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.Clicks != 0 {
		t.Fatalf("Clicks = %d，期望 0（RecordVisitNoCount 不计 clicks）", link.Clicks)
	}

	stats, err := st.GeoStats(id, 0, "", 8)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if stats.TotalClicks != 1 {
		t.Fatalf("visits 行数 = %d，期望 1", stats.TotalClicks)
	}
}
