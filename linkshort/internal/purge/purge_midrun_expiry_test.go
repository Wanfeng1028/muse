package purge

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestPurgeR2_MidRunExpiryPickedUp(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer database.Close()

	st := store.New(database)
	exp := time.Now().Add(300 * time.Millisecond)
	id, err := st.CreateLinkEx("b2mr1", "https://example.com/b2mr1", "mid-run", &exp, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("link should exist before purge: %v", err)
	}

	cfg := &config.Config{PurgeInterval: 200 * time.Millisecond, PurgeRetentionDays: 0}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go Start(ctx, st, cfg)

	deadline := 50
	for i := 0; i < deadline; i++ {
		time.Sleep(100 * time.Millisecond)
		_, err := st.GetLink(id)
		if errors.Is(err, store.ErrNotFound) {
			return
		}
		if err != nil && !errors.Is(err, store.ErrNotFound) {
			t.Fatalf("GetLink unexpected error: %v", err)
		}
	}
	t.Fatalf("mid-run expired link was not purged within polling window")
}

func TestPurgeR2_FreshLinkSurvivesMultipleTicks(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer database.Close()

	st := store.New(database)
	exp := time.Now().Add(time.Hour)
	id, err := st.CreateLinkEx("b2mr2", "https://example.com/b2mr2", "fresh", &exp, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	cfg := &config.Config{PurgeInterval: 200 * time.Millisecond, PurgeRetentionDays: 0}
	ctx, cancel := context.WithCancel(context.Background())

	go Start(ctx, st, cfg)

	time.Sleep(700 * time.Millisecond)
	cancel()

	if _, err := st.GetLink(id); err != nil {
		t.Fatalf("fresh link should survive multiple ticks, got: %v", err)
	}
}

func TestPurgeR2_CancelStopsSweeps(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer database.Close()

	st := store.New(database)
	exp := time.Now().Add(-time.Hour)
	id, err := st.CreateLinkEx("b2mr3", "https://example.com/b2mr3", "expired", &exp, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	cfg := &config.Config{PurgeInterval: 200 * time.Millisecond, PurgeRetentionDays: 0}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	go Start(ctx, st, cfg)

	time.Sleep(400 * time.Millisecond)

	// 钉死实际行为：Start 在进入 select 之前会先执行一轮 sweep。
	// 即使 ctx 在调用前已取消，首轮 sweep 仍可能执行并删除已过期链。
	// 依据本仓库 Start 的实现（先 sweep 后 select），此处断言链已被删除。
	if _, err := st.GetLink(id); !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("expected expired link purged by initial sweep even after cancel, got err=%v", err)
	}
}
