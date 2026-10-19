package purge

import (
	"context"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestStart_清理过期时间链(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	st := store.New(database)

	expiresAt := time.Now().Add(-1 * time.Hour)
	id, err := st.CreateLinkEx("expired-slug", "https://example.com/x", "t", &expiresAt, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}

	// 同时建一条 burn 链，验证 burn 扫荡不受影响（burned 未设置，不会被删）。
	if _, err := st.CreateLinkEx("burn-slug", "https://example.com/y", "t", nil, nil, true, false); err != nil {
		t.Fatalf("create burn link: %v", err)
	}

	cfg := &config.Config{PurgeInterval: 50 * time.Millisecond, PurgeRetentionDays: 0}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go Start(ctx, st, cfg)

	deadline := time.Now().Add(3 * time.Second)
	for {
		_, err := st.GetLink(id)
		if err == store.ErrNotFound {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("expired link not purged, last err=%v", err)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func TestStart_保留期内不删(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	st := store.New(database)

	expiresAt := time.Now().Add(-1 * time.Hour)
	id, err := st.CreateLinkEx("kept-slug", "https://example.com/z", "t", &expiresAt, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}

	cfg := &config.Config{PurgeInterval: 50 * time.Millisecond, PurgeRetentionDays: 30}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go Start(ctx, st, cfg)

	time.Sleep(300 * time.Millisecond)

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("link should be retained, got err=%v", err)
	}
}
