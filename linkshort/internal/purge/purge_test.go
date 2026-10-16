package purge

import (
	"context"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestStart_短间隔真实触发清理(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer func() {
		if cerr := database.Close(); cerr != nil {
			t.Logf("close db: %v", cerr)
		}
	}()

	st := store.New(database)
	cfg := &config.Config{PurgeInterval: 50 * time.Millisecond, PurgeRetentionDays: 0}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go Start(ctx, st, cfg)

	id, err := st.CreateLinkEx("pg-timer", "https://example.com/timer", "timer", nil, nil, true)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := st.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}
	if _, err := database.Exec("UPDATE links SET burned_at = ? WHERE id = ?", time.Now().Add(-5*time.Second).UTC().Format(time.RFC3339), id); err != nil {
		t.Fatalf("backdate burned_at: %v", err)
	}

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if _, err := st.GetLink(id); err == store.ErrNotFound {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("link %d still exists after timeout", id)
}
