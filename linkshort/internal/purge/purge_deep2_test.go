package purge

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newStoreDeep2(t *testing.T) (*store.Store, *sql.DB) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	st := store.New(database)
	return st, database
}

func createBurnLinkDeep2(t *testing.T, st *store.Store) int64 {
	t.Helper()
	id, err := st.CreateLinkEx("slug-burn", "https://example.com", "t", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx burn: %v", err)
	}
	if err := st.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}
	return id
}

func createPlainLinkDeep2(t *testing.T, st *store.Store) int64 {
	t.Helper()
	id, err := st.CreateLinkEx("slug-plain", "https://example.com", "t", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx plain: %v", err)
	}
	return id
}

func TestStartPurgesBurnedImmediatelyDeep2(t *testing.T) {
	st, database := newStoreDeep2(t)
	defer database.Close()

	id := createBurnLinkDeep2(t, st)

	past := time.Now().Add(-5 * time.Second).UTC().Format(time.RFC3339)
	if _, err := database.Exec("UPDATE links SET burned_at=? WHERE id=?", past, id); err != nil {
		t.Fatalf("exec update burned_at: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := &config.Config{PurgeInterval: 50 * time.Millisecond, PurgeRetentionDays: 0}
	go Start(ctx, st, cfg)

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		_, err := st.GetLink(id)
		if errors.Is(err, store.ErrNotFound) {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("link %d still present after purge window", id)
}

func TestStartKeepsFreshBurnedDeep2(t *testing.T) {
	st, database := newStoreDeep2(t)
	defer database.Close()

	id := createBurnLinkDeep2(t, st)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// retention=1 天：cutoff 为昨天，新销毁的链接（burned_at=now）必定保留，避免秒级边界竞态
	cfg := &config.Config{PurgeInterval: 50 * time.Millisecond, PurgeRetentionDays: 1}
	go Start(ctx, st, cfg)

	time.Sleep(300 * time.Millisecond)

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("fresh burned link should remain, got err: %v", err)
	}
}

func TestMarkBurnedNonBurnLinkDeep2(t *testing.T) {
	st, database := newStoreDeep2(t)
	defer database.Close()

	id := createPlainLinkDeep2(t, st)

	if err := st.MarkBurned(id); !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("MarkBurned on non-burn link: want ErrNotFound, got %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := &config.Config{PurgeInterval: 50 * time.Millisecond, PurgeRetentionDays: 0}
	go Start(ctx, st, cfg)

	time.Sleep(300 * time.Millisecond)

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("non-burn link should remain, got err: %v", err)
	}
}

func TestStartExitsOnContextCancelDeep2(t *testing.T) {
	st, database := newStoreDeep2(t)
	defer database.Close()

	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan struct{})
	cfg := &config.Config{PurgeInterval: 50 * time.Millisecond, PurgeRetentionDays: 0}
	go func() {
		Start(ctx, st, cfg)
		close(done)
	}()

	time.Sleep(150 * time.Millisecond)
	cancel()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Start did not return within 2s after cancel")
	}
}

func TestPurgeExpiredBurnedSkipsNullBurnedAtDeep2(t *testing.T) {
	st, database := newStoreDeep2(t)
	defer database.Close()

	id, err := st.CreateLinkEx("slug-null", "https://example.com", "t", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	n, err := st.PurgeExpiredBurned(time.Now().Add(time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 0 {
		t.Fatalf("expected 0 rows deleted (burned_at NULL), got %d", n)
	}

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("link with NULL burned_at should remain, got err: %v", err)
	}
}

func TestRetentionZeroCutoffSemanticsDeep2(t *testing.T) {
	st, database := newStoreDeep2(t)
	defer database.Close()

	id := createBurnLinkDeep2(t, st)

	n, err := st.PurgeExpiredBurned(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 0 {
		t.Fatalf("expected 0 rows deleted with cutoff=now, got %d", n)
	}

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("freshly burned link should remain under cutoff=now, got err: %v", err)
	}
}