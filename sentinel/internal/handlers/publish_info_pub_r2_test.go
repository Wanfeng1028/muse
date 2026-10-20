package handlers

import (
	"encoding/json"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"testing"
)

func TestR2_PublishThenInfo(t *testing.T) {
	srv, st := newTestServer(t)
	dir := t.TempDir()
	srv.SetPublishDir(dir)

	pageID, err := st.CreateStatusPage(1, "slug-r2b", "标题")
	if err != nil {
		t.Fatalf("CreateStatusPage failed: %v", err)
	}

	version, err := srv.PublishStatusPage(pageID)
	if err != nil {
		t.Fatalf("PublishStatusPage failed: %v", err)
	}
	if version == "" {
		t.Fatal("expected non-empty version")
	}

	req := httptest.NewRequest("GET", "/x", nil)
	req.SetPathValue("id", strconv.FormatInt(pageID, 10))
	rec := httptest.NewRecorder()
	srv.handlePublishInfo(rec, req)

	if rec.Code != 200 {
		t.Fatalf("expected status code 200, got %d", rec.Code)
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("failed to unmarshal response body: %v", err)
	}

	if published, ok := body["published"].(bool); !ok || !published {
		t.Fatalf("expected published to be true, got %v", body["published"])
	}
	if mc, ok := body["monitor_count"].(float64); !ok || mc != 0 {
		t.Fatalf("expected monitor_count to be 0, got %v", body["monitor_count"])
	}

	manifestPath := filepath.Join(dir, "slug-r2b", "manifest.json")
	if _, err := os.Stat(manifestPath); err != nil {
		t.Fatalf("manifest.json does not exist: %v", err)
	}
}
