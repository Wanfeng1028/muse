package handlers

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_PublishTwiceArchivesHistory(t *testing.T) {
	srv, st := newTestServer(t)
	dir := t.TempDir()
	srv.SetPublishDir(dir)

	pageID, err := st.CreateStatusPage(1, "slug-r2c", "标题")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}
	mid, err := st.CreateMonitor(store.Monitor{
		Name:        "m1",
		Kind:        "http",
		Target:      "http://x/",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	if err := st.AddMonitorToPage(pageID, mid); err != nil {
		t.Fatalf("AddMonitorToPage: %v", err)
	}

	if _, err := srv.PublishStatusPage(pageID); err != nil {
		t.Fatalf("first PublishStatusPage: %v", err)
	}

	time.Sleep(1100 * time.Millisecond)

	if _, err := srv.PublishStatusPage(pageID); err != nil {
		t.Fatalf("second PublishStatusPage: %v", err)
	}

	histDir := filepath.Join(dir, "slug-r2c", "history")
	entries, err := os.ReadDir(histDir)
	if err != nil {
		t.Fatalf("ReadDir history: %v", err)
	}
	count := 0
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if strings.HasPrefix(name, "index-") && strings.HasSuffix(name, ".html") {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("history archived html count = %d, want 1", count)
	}
}
