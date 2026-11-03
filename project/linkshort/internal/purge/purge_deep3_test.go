package purge

import (
	"context"
	"database/sql"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newStoreDeep3(t *testing.T) (*store.Store, *sql.DB) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	st := store.New(database)
	return st, database
}

func createBurnLinkDeep3(t *testing.T, st *store.Store, slug string) int64 {
	t.Helper()
	id, err := st.CreateLinkEx(slug, "https://example.com", "t", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx burn: %v", err)
	}
	if err := st.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}
	return id
}

func backdateBurnedDeep3(t *testing.T, database *sql.DB, id int64, at time.Time) {
	t.Helper()
	if _, err := database.Exec("UPDATE links SET burned_at=? WHERE id=?", at.UTC().Format(time.RFC3339), id); err != nil {
		t.Fatalf("exec update burned_at: %v", err)
	}
}

func TestStartPurgesMultipleExpiredBurnedDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	id1 := createBurnLinkDeep3(t, st, "slug-a")
	id2 := createBurnLinkDeep3(t, st, "slug-b")
	id3 := createBurnLinkDeep3(t, st, "slug-c")

	old := time.Now().Add(-72 * time.Hour)
	backdateBurnedDeep3(t, database, id1, old)
	backdateBurnedDeep3(t, database, id2, old)
	backdateBurnedDeep3(t, database, id3, old)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := &config.Config{PurgeInterval: 30 * time.Millisecond, PurgeRetentionDays: 1}
	go Start(ctx, st, cfg)

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		_, e1 := st.GetLink(id1)
		_, e2 := st.GetLink(id2)
		_, e3 := st.GetLink(id3)
		if errors.Is(e1, store.ErrNotFound) && errors.Is(e2, store.ErrNotFound) && errors.Is(e3, store.ErrNotFound) {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("not all expired burned links purged within deadline")
}

func TestStartPurgesExpiredKeepsFreshDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	oldID := createBurnLinkDeep3(t, st, "slug-old")
	freshID := createBurnLinkDeep3(t, st, "slug-fresh")

	backdateBurnedDeep3(t, database, oldID, time.Now().Add(-72*time.Hour))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := &config.Config{PurgeInterval: 30 * time.Millisecond, PurgeRetentionDays: 1}
	go Start(ctx, st, cfg)

	deadline := time.Now().Add(5 * time.Second)
	purged := false
	for time.Now().Before(deadline) {
		if _, err := st.GetLink(oldID); errors.Is(err, store.ErrNotFound) {
			purged = true
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if !purged {
		t.Fatal("old burned link was not purged")
	}
	if _, err := st.GetLink(freshID); err != nil {
		t.Fatalf("fresh burned link should remain, got err: %v", err)
	}
}

func TestStartWithLargeRetentionDaysKeepsAllDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	id := createBurnLinkDeep3(t, st, "slug-big-ret")
	backdateBurnedDeep3(t, database, id, time.Now().Add(-48*time.Hour))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := &config.Config{PurgeInterval: 20 * time.Millisecond, PurgeRetentionDays: 3650}
	go Start(ctx, st, cfg)

	time.Sleep(250 * time.Millisecond)

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("link within huge retention must remain, got err: %v", err)
	}
}

func TestStartRepeatedSweepsIdempotentDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	id := createBurnLinkDeep3(t, st, "slug-idem")
	backdateBurnedDeep3(t, database, id, time.Now().Add(-72*time.Hour))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := &config.Config{PurgeInterval: 20 * time.Millisecond, PurgeRetentionDays: 1}
	go Start(ctx, st, cfg)

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if _, err := st.GetLink(id); errors.Is(err, store.ErrNotFound) {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	// 继续跑多个 tick，验证不会 panic / 出错
	time.Sleep(200 * time.Millisecond)

	if _, err := st.GetLink(id); !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("link should stay purged, got err: %v", err)
	}
}

func TestStartEmptyStoreNoPanicDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan struct{})
	cfg := &config.Config{PurgeInterval: 20 * time.Millisecond, PurgeRetentionDays: 0}
	go func() {
		Start(ctx, st, cfg)
		close(done)
	}()

	time.Sleep(150 * time.Millisecond)
	cancel()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Start did not return after cancel on empty store")
	}
}

func TestStartCancelBeforeFirstTickDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // 立即取消

	done := make(chan struct{})
	cfg := &config.Config{PurgeInterval: time.Hour, PurgeRetentionDays: 0}
	go func() {
		Start(ctx, st, cfg)
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Start should exit promptly when ctx pre-cancelled")
	}
}

func TestPurgeExpiredBurnedBoundaryExactCutoffDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	id := createBurnLinkDeep3(t, st, "slug-boundary")

	// burned_at 精确设为某个时间，cutoff 设为同一时刻的 RFC3339 字符串
	at := time.Now().Add(-time.Hour).UTC().Truncate(time.Second)
	backdateBurnedDeep3(t, database, id, at)

	// cutoff 等于 burned_at：取决于实现是否使用严格小于
	n, err := st.PurgeExpiredBurned(at)
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	// 不做严格数量断言，只要求结果一致：要么删掉，要么保留
	if n == 0 {
		if _, err := st.GetLink(id); err != nil {
			t.Fatalf("n=0 but link gone, err: %v", err)
		}
	} else if n == 1 {
		if _, err := st.GetLink(id); !errors.Is(err, store.ErrNotFound) {
			t.Fatalf("n=1 but link still present, err: %v", err)
		}
	} else {
		t.Fatalf("unexpected n=%d", n)
	}
}

func TestPurgeExpiredBurnedFutureCutoffDeletesAllDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	id1 := createBurnLinkDeep3(t, st, "slug-f1")
	id2 := createBurnLinkDeep3(t, st, "slug-f2")

	n, err := st.PurgeExpiredBurned(time.Now().Add(24 * time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 2 {
		t.Fatalf("expected 2 rows deleted, got %d", n)
	}
	if _, err := st.GetLink(id1); !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("id1 should be gone, err: %v", err)
	}
	if _, err := st.GetLink(id2); !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("id2 should be gone, err: %v", err)
	}
}

func TestPurgeExpiredBurnedPastCutoffKeepsAllDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	id := createBurnLinkDeep3(t, st, "slug-past")

	n, err := st.PurgeExpiredBurned(time.Now().Add(-24 * time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 0 {
		t.Fatalf("expected 0 rows deleted, got %d", n)
	}
	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("link should remain, err: %v", err)
	}
}

func TestPurgeExpiredBurnedIgnoresUnburnedBurnLinksDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	// burn 链接但未 MarkBurned
	id, err := st.CreateLinkEx("slug-unburned", "https://example.com", "t", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	n, err := st.PurgeExpiredBurned(time.Now().Add(24 * time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 0 {
		t.Fatalf("expected 0 (unburned burn link), got %d", n)
	}
	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("unburned link should remain, err: %v", err)
	}
}

func TestPurgeExpiredBurnedIgnoresNonBurnMarkedDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	// 非 burn 链接，即使手改 burned_at 也不该被清理（取决于实现）
	id, err := st.CreateLinkEx("slug-nonburn", "https://example.com", "t", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	backdateBurnedDeep3(t, database, id, time.Now().Add(-72*time.Hour))

	n, err := st.PurgeExpiredBurned(time.Now().Add(24 * time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	// 只断言不会删掉非 burn 链接
	if n != 0 {
		t.Fatalf("expected 0 rows deleted for non-burn link, got %d", n)
	}
	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("non-burn link should remain, err: %v", err)
	}
}

func TestStartConcurrentMultipleInstancesDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	for i := 0; i < 5; i++ {
		id := createBurnLinkDeep3(t, st, "slug-c"+string(rune('a'+i)))
		backdateBurnedDeep3(t, database, id, time.Now().Add(-72*time.Hour))
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := &config.Config{PurgeInterval: 20 * time.Millisecond, PurgeRetentionDays: 1}

	var wg sync.WaitGroup
	for i := 0; i < 3; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			Start(ctx, st, cfg)
		}()
	}

	time.Sleep(250 * time.Millisecond)
	cancel()

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("concurrent Start instances did not exit")
	}
}

func TestStartWithLongIntervalNoTickDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	id := createBurnLinkDeep3(t, st, "slug-long")
	backdateBurnedDeep3(t, database, id, time.Now().Add(-72*time.Hour))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// 间隔 1 小时，只有初始 sweep 会跑
	cfg := &config.Config{PurgeInterval: time.Hour, PurgeRetentionDays: 1}
	go Start(ctx, st, cfg)

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if _, err := st.GetLink(id); errors.Is(err, store.ErrNotFound) {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("initial sweep did not purge expired link")
}

func TestStartInitialSweepRunsBeforeTickerDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	id := createBurnLinkDeep3(t, st, "slug-init")
	backdateBurnedDeep3(t, database, id, time.Now().Add(-72*time.Hour))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// 极长间隔确保只有启动时的那一轮 sweep 会执行
	cfg := &config.Config{PurgeInterval: 24 * time.Hour, PurgeRetentionDays: 1}
	go Start(ctx, st, cfg)

	// 短窗口内必须已经被删除
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if _, err := st.GetLink(id); errors.Is(err, store.ErrNotFound) {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("initial sweep should have purged link immediately")
}

func TestPurgeExpiredBurnedManyRowsDeep3(t *testing.T) {
	st, database := newStoreDeep3(t)
	defer database.Close()

	const N = 50
	for i := 0; i < N; i++ {
		id := createBurnLinkDeep3(t, st, "slug-many-"+string(rune('A'+i%26))+string(rune('0'+i/26)))
		backdateBurnedDeep3(t, database, id, time.Now().Add(-72*time.Hour))
	}

	n, err := st.PurgeExpiredBurned(time.Now().Add(24 * time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != N {
		t.Fatalf("expected %d rows deleted, got %d", N, n)
	}
}
