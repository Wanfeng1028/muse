package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestMeta_包含Purge配置(t *testing.T) {
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
	cfg := &config.Config{AdminKey: testKey, PurgeInterval: 24 * time.Hour, PurgeRetentionDays: 7}

	srv := httptest.NewServer(NewRouter(st, cfg))
	defer srv.Close()

	resp, body := doJSON(t, "GET", srv.URL+"/api/meta", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200, body = %s", resp.StatusCode, body)
	}

	var meta map[string]any
	if err := json.Unmarshal(body, &meta); err != nil {
		t.Fatalf("unmarshal meta: %v", err)
	}
	if got := meta["purge_interval"]; got != "24h0m0s" {
		t.Fatalf("purge_interval = %v, want 24h0m0s", got)
	}
	if got := meta["purge_retention_days"]; got != float64(7) {
		t.Fatalf("purge_retention_days = %v, want 7", got)
	}
}
