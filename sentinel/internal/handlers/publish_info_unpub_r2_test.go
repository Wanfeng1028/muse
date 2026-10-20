package handlers

import (
	"encoding/json"
	"net/http/httptest"
	"strconv"
	"testing"
)

func TestR2_PublishInfoUnpublished(t *testing.T) {
	srv, st := newTestServer(t)
	srv.SetPublishDir(t.TempDir())

	pageID, err := st.CreateStatusPage(1, "slug-r2", "标题")
	if err != nil {
		t.Fatalf("CreateStatusPage returned error: %v", err)
	}
	if pageID <= 0 {
		t.Fatalf("CreateStatusPage returned invalid id: %d", pageID)
	}

	req := httptest.NewRequest("GET", "/api/status-pages/"+strconv.FormatInt(pageID, 10)+"/publish-info", nil)
	req.SetPathValue("id", strconv.FormatInt(pageID, 10))

	rec := httptest.NewRecorder()
	srv.handlePublishInfo(rec, req)

	if rec.Code != 200 {
		t.Fatalf("status code = %d, want 200", rec.Code)
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("failed to decode response body %q: %v", rec.Body.String(), err)
	}

	published, ok := body["published"].(bool)
	if !ok {
		t.Fatalf("published field missing or not bool: %#v", body["published"])
	}
	if published {
		t.Fatalf("published = true, want false")
	}

	slug, ok := body["slug"].(string)
	if !ok {
		t.Fatalf("slug field missing or not string: %#v", body["slug"])
	}
	if slug != "slug-r2" {
		t.Fatalf("slug = %q, want %q", slug, "slug-r2")
	}
}
