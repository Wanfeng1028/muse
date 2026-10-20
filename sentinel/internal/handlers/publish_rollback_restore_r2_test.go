package handlers

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_RollbackRestoresContent(t *testing.T) {
	srv, st := newTestServer(t)

	publishDir := t.TempDir()
	srv.SetPublishDir(publishDir)

	pageID, err := st.CreateStatusPage(1, "rb2-r2", "t")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	mid, err := st.CreateMonitor(store.Monitor{
		Name:        "first-name",
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

	v1, err := srv.PublishStatusPage(pageID)
	if err != nil {
		t.Fatalf("first PublishStatusPage: %v", err)
	}
	if v1 == "" {
		t.Fatal("first publish returned empty version")
	}

	pageDir := filepath.Join(publishDir, "rb2-r2")
	indexPath := filepath.Join(pageDir, "index.html")
	firstContent, err := os.ReadFile(indexPath)
	if err != nil {
		t.Fatalf("read first index: %v", err)
	}
	if !strings.Contains(string(firstContent), "first-name") {
		t.Fatalf("first snapshot does not contain first-name: %s", string(firstContent))
	}

	time.Sleep(1100 * time.Millisecond)

	if err := st.RemoveMonitorFromPage(pageID, mid); err != nil {
		t.Fatalf("RemoveMonitorFromPage: %v", err)
	}

	mid2, err := st.CreateMonitor(store.Monitor{
		Name:        "second-name",
		Kind:        "http",
		Target:      "http://x/",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor second: %v", err)
	}
	if err := st.AddMonitorToPage(pageID, mid2); err != nil {
		t.Fatalf("AddMonitorToPage second: %v", err)
	}

	v2, err := srv.PublishStatusPage(pageID)
	if err != nil {
		t.Fatalf("second PublishStatusPage: %v", err)
	}
	if v2 == "" {
		t.Fatal("second publish returned empty version")
	}
	if v2 == v1 {
		t.Fatalf("expected distinct publish versions, got %q twice", v1)
	}

	historyPath := filepath.Join(pageDir, "history", "index-"+v1+".html")
	historyContent, err := os.ReadFile(historyPath)
	if err != nil {
		t.Fatalf("read history %q: %v", v1, err)
	}
	if string(historyContent) != string(firstContent) {
		t.Fatal("history archive does not match first published index")
	}

	secondContent, err := os.ReadFile(indexPath)
	if err != nil {
		t.Fatalf("read second index: %v", err)
	}
	if !strings.Contains(string(secondContent), "second-name") {
		t.Fatalf("second snapshot does not contain second-name: %s", string(secondContent))
	}
	if strings.Contains(string(secondContent), "first-name") {
		t.Fatalf("second snapshot unexpectedly contains first-name: %s", string(secondContent))
	}

	restored, err := srv.RollbackStatusPage(pageID)
	if err != nil {
		t.Fatalf("RollbackStatusPage: %v", err)
	}
	if restored != v1 {
		t.Fatalf("rollback restored %q, want %q", restored, v1)
	}

	rolledContent, err := os.ReadFile(indexPath)
	if err != nil {
		t.Fatalf("read rolled index: %v", err)
	}
	if string(rolledContent) != string(firstContent) {
		t.Fatal("rolled index does not match first published index")
	}
	if !strings.Contains(string(rolledContent), "first-name") {
		t.Fatalf("rolled snapshot does not contain first-name: %s", string(rolledContent))
	}
	if strings.Contains(string(rolledContent), "second-name") {
		t.Fatalf("rolled snapshot unexpectedly contains second-name: %s", string(rolledContent))
	}

	manifestBytes, err := os.ReadFile(filepath.Join(pageDir, "manifest.json"))
	if err != nil {
		t.Fatalf("read manifest: %v", err)
	}
	var manifest publishManifest
	if err := json.Unmarshal(manifestBytes, &manifest); err != nil {
		t.Fatalf("unmarshal manifest: %v", err)
	}
	if !strings.HasSuffix(manifest.Version, "-rollback") {
		t.Fatalf("manifest version %q does not end with -rollback", manifest.Version)
	}
	if want := restored + "-rollback"; manifest.Version != want {
		t.Fatalf("manifest version = %q, want %q", manifest.Version, want)
	}
	if manifest.Slug != "rb2-r2" {
		t.Fatalf("manifest slug = %q, want %q", manifest.Slug, "rb2-r2")
	}
}
