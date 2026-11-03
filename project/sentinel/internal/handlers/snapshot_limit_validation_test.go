package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSnapshotListLimitValidation(t *testing.T) {
	srv, st := newTestServer(t)

	pageID, err := st.CreateStatusPage(1, "snap-limit-val-page", "限制校验页")
	if err != nil {
		t.Fatalf("create status page: %v", err)
	}

	for i := 0; i < 2; i++ {
		req := newReq(http.MethodPost, fmt.Sprintf("/api/status-pages/%d/snapshots", pageID), nil)
		rec := httptest.NewRecorder()
		srv.Routes().ServeHTTP(rec, req)
		if rec.Code != http.StatusCreated {
			t.Fatalf("create snapshot %d: expected 201, got %d", i, rec.Code)
		}
	}

	cases := []struct {
		name      string
		query     string
		wantCode  int
		wantItems int
	}{
		{"limit=abc", "?limit=abc", http.StatusBadRequest, 0},
		{"limit=0", "?limit=0", http.StatusBadRequest, 0},
		{"limit=-1", "?limit=-1", http.StatusBadRequest, 0},
		{"limit=2", "?limit=2", http.StatusOK, 2},
		{"no limit", "", http.StatusOK, 2},
	}

	for _, tc := range cases {
		req := newReq(http.MethodGet, fmt.Sprintf("/api/status-pages/%d/snapshots%s", pageID, tc.query), nil)
		rec := httptest.NewRecorder()
		srv.Routes().ServeHTTP(rec, req)
		if rec.Code != tc.wantCode {
			t.Fatalf("%s: expected %d, got %d", tc.name, tc.wantCode, rec.Code)
		}
		if tc.wantCode != http.StatusOK {
			continue
		}
		var body map[string]any
		if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
			t.Fatalf("%s: decode body: %v", tc.name, err)
		}
		items, ok := body["items"].([]any)
		if !ok {
			t.Fatalf("%s: items missing or not an array", tc.name)
		}
		if len(items) != tc.wantItems {
			t.Fatalf("%s: expected %d items, got %d", tc.name, tc.wantItems, len(items))
		}
	}
}
