package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRefreshViewAPI(t *testing.T) {
	st, srv := newTestServer(t)
	if err := st.SaveView("v_adult", "SELECT \"id\",\"name\" FROM \"users\" WHERE \"age\" > 26", ""); err != nil {
		t.Fatalf("SaveView: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/views/v_adult/refresh", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("refresh status = %d, body = %s", rec.Code, rec.Body.String())
	}

	var body struct {
		Name       string `json:"name"`
		Rows       int64  `json:"rows"`
		DurationMs int64  `json:"duration_ms"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if body.Name != "v_adult" {
		t.Fatalf("name = %q, want v_adult", body.Name)
	}
	if body.Rows != 1 {
		t.Fatalf("rows = %d, want 1", body.Rows)
	}

	reqList := httptest.NewRequest(http.MethodGet, "/api/views", nil)
	recList := httptest.NewRecorder()
	srv.ServeHTTP(recList, reqList)
	if recList.Code != http.StatusOK {
		t.Fatalf("list status = %d, body = %s", recList.Code, recList.Body.String())
	}

	var listResp []struct {
		Name            string `json:"name"`
		LastRefreshAt   string `json:"last_refresh_at"`
		LastRefreshRows *int64 `json:"last_refresh_rows"`
	}
	if err := json.Unmarshal(recList.Body.Bytes(), &listResp); err != nil {
		t.Fatalf("decode list: %v", err)
	}

	var found bool
	for _, v := range listResp {
		if v.Name != "v_adult" {
			continue
		}
		found = true
		if v.LastRefreshRows == nil {
			t.Fatalf("last_refresh_rows = nil, want 1")
		}
		if *v.LastRefreshRows != 1 {
			t.Fatalf("last_refresh_rows = %d, want 1", *v.LastRefreshRows)
		}
		if v.LastRefreshAt == "" {
			t.Fatalf("last_refresh_at is empty, want non-empty")
		}
	}
	if !found {
		t.Fatalf("v_adult not found in list")
	}
}

func TestRefreshViewNotFound(t *testing.T) {
	_, srv := newTestServer(t)
	req := httptest.NewRequest(http.MethodPost, "/api/views/nope/refresh", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404, body = %s", rec.Code, rec.Body.String())
	}
}
