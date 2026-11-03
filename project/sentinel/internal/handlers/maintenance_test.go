package handlers

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestCreateMaintenanceWindowHandlerOK(t *testing.T) {
	srv, _ := newTestServer(t)
	start := time.Now().UTC().Add(-time.Minute).Format(time.RFC3339)
	end := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	body := fmt.Sprintf(`{"monitor_id":0,"title":"割接","starts_at":%q,"ends_at":%q}`, start, end)
	rec, out := doJSON(t, srv.Routes(), http.MethodPost, "/api/maintenance", body)
	if rec.Code != http.StatusCreated {
		t.Fatalf("期望 201，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	if id, ok := out["id"].(float64); !ok || id <= 0 {
		t.Fatalf("期望返回正 id，得到 %v", out["id"])
	}
}

func TestCreateMaintenanceWindowHandlerBadWindow(t *testing.T) {
	srv, _ := newTestServer(t)
	start := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	end := time.Now().UTC().Format(time.RFC3339)
	body := fmt.Sprintf(`{"monitor_id":0,"title":"x","starts_at":%q,"ends_at":%q}`, start, end)
	rec, _ := doJSON(t, srv.Routes(), http.MethodPost, "/api/maintenance", body)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestCreateMaintenanceWindowHandlerMissingMonitor(t *testing.T) {
	srv, _ := newTestServer(t)
	start := time.Now().UTC().Add(-time.Minute).Format(time.RFC3339)
	end := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	body := fmt.Sprintf(`{"monitor_id":999999,"title":"x","starts_at":%q,"ends_at":%q}`, start, end)
	rec, _ := doJSON(t, srv.Routes(), http.MethodPost, "/api/maintenance", body)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestMaintenanceWindowHandlerListAndDelete(t *testing.T) {
	srv, _ := newTestServer(t)
	start := time.Now().UTC().Add(-time.Minute).Format(time.RFC3339)
	end := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	body := fmt.Sprintf(`{"monitor_id":0,"title":"删我","starts_at":%q,"ends_at":%q}`, start, end)
	rec, out := doJSON(t, srv.Routes(), http.MethodPost, "/api/maintenance", body)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建期望 201，得到 %d", rec.Code)
	}
	id := int64(out["id"].(float64))
	rec, out = doJSON(t, srv.Routes(), http.MethodGet, "/api/maintenance", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("列表期望 200，得到 %d", rec.Code)
	}
	items, ok := out["items"].([]any)
	if !ok || len(items) != 1 {
		t.Fatalf("期望列表 1 条，得到 %v", out["items"])
	}
	req := newReq(http.MethodDelete, fmt.Sprintf("/api/maintenance/%d", id), nil)
	delRec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(delRec, req)
	if delRec.Code != http.StatusOK {
		t.Fatalf("删除期望 200，得到 %d body=%s", delRec.Code, delRec.Body.String())
	}
	rec, out = doJSON(t, srv.Routes(), http.MethodGet, "/api/maintenance", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("删除后列表期望 200，得到 %d", rec.Code)
	}
	items, ok = out["items"].([]any)
	if !ok || len(items) != 0 {
		t.Fatalf("期望删除后列表 0 条，得到 %v", out["items"])
	}
}
