package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSnapshotListLimitUpper(t *testing.T) {
	srv, st := newTestServer(t)
	pageID, err := st.CreateStatusPage(1, "snap-limit-upper-page", "上限校验页")
	if err != nil {
		t.Fatalf("CreateStatusPage failed: %v", err)
	}

	for i := 0; i < 2; i++ {
		req := newReq(http.MethodPost, fmt.Sprintf("/api/status-pages/%d/snapshots", pageID), nil)
		rec := httptest.NewRecorder()
		srv.Routes().ServeHTTP(rec, req)
		if rec.Code != http.StatusCreated {
			t.Fatalf("expected status 201, got %d", rec.Code)
		}
	}

	tests := []struct {
		name     string
		query    string
		wantCode int
		wantLen  int
	}{
		{"limit=201", "?limit=201", http.StatusBadRequest, -1},
		{"limit=1000", "?limit=1000", http.StatusBadRequest, -1},
		{"limit=200", "?limit=200", http.StatusOK, 2},
		{"limit=50", "?limit=50", http.StatusOK, 2},
		{"limit=abc", "?limit=abc", http.StatusBadRequest, -1},
		{"limit=0", "?limit=0", http.StatusBadRequest, -1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := newReq(http.MethodGet, fmt.Sprintf("/api/status-pages/%d/snapshots%s", pageID, tt.query), nil)
			rec := httptest.NewRecorder()
			srv.Routes().ServeHTTP(rec, req)

			if rec.Code != tt.wantCode {
				t.Fatalf("expected status %d, got %d, body: %s", tt.wantCode, rec.Code, rec.Body.String())
			}

			if tt.wantLen >= 0 {
				var body map[string]json.RawMessage
				if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
					t.Fatalf("failed to unmarshal body: %v", err)
				}
				var items []any
				if err := json.Unmarshal(body["items"], &items); err != nil {
					t.Fatalf("failed to unmarshal items: %v", err)
				}
				if len(items) != tt.wantLen {
					t.Fatalf("expected items length %d, got %d", tt.wantLen, len(items))
				}
			}
		})
	}
}
