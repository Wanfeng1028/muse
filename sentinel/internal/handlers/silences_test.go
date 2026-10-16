package handlers

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestCreateSilenceHandlerOK(t *testing.T) {
	srv, _ := newTestServer(t)
	body := map[string]any{
		"monitor_id": 0,
		"name_match": "api",
		"starts_at":  time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		"ends_at":    time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
		"reason":     "维护",
	}
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/silences", bytes.NewReader(raw))
	req.Header.Set("Authorization", "Bearer test-token")
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("期望 201，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	if id, ok := out["id"].(float64); !ok || id <= 0 {
		t.Fatalf("期望返回正 id，得到 %v", out["id"])
	}
}

func TestCreateSilenceHandlerBadWindow(t *testing.T) {
	srv, _ := newTestServer(t)
	body := map[string]any{
		"starts_at": time.Now().UTC().Add(time.Hour).Format(time.RFC3339),
		"ends_at":   time.Now().UTC().Format(time.RFC3339),
		"reason":    "x",
	}
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/silences", bytes.NewReader(raw))
	req.Header.Set("Authorization", "Bearer test-token")
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestCreateSilenceHandlerMissingMonitor(t *testing.T) {
	srv, _ := newTestServer(t)
	body := map[string]any{
		"monitor_id": 999999,
		"starts_at":  time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		"ends_at":    time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
		"reason":     "x",
	}
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/silences", bytes.NewReader(raw))
	req.Header.Set("Authorization", "Bearer test-token")
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestListSilencesHandlerContainsCreated(t *testing.T) {
	srv, _ := newTestServer(t)
	body := map[string]any{
		"name_match": "list",
		"starts_at":  time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		"ends_at":    time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
		"reason":     "r",
	}
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/silences", bytes.NewReader(raw))
	req.Header.Set("Authorization", "Bearer test-token")
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建失败: %d %s", rec.Code, rec.Body.String())
	}
	req2 := httptest.NewRequest(http.MethodGet, "/api/silences", nil)
	req2.Header.Set("Authorization", "Bearer test-token")
	rec2 := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d", rec2.Code)
	}
	var out struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec2.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析列表失败: %v", err)
	}
	if len(out.Items) != 1 {
		t.Fatalf("期望 1 条，得到 %d", len(out.Items))
	}
	if out.Items[0]["name_match"] != "list" {
		t.Fatalf("内容不符: %v", out.Items[0])
	}
}

func TestDeleteSilenceHandlerThenEmpty(t *testing.T) {
	srv, _ := newTestServer(t)
	body := map[string]any{
		"starts_at": time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		"ends_at":   time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
		"reason":    "del",
	}
	raw, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/silences", bytes.NewReader(raw))
	req.Header.Set("Authorization", "Bearer test-token")
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建失败: %d %s", rec.Code, rec.Body.String())
	}
	var created map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &created); err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	id := int64(created["id"].(float64))

	reqDel := httptest.NewRequest(http.MethodDelete, "/api/silences/"+itoa(id), nil)
	reqDel.Header.Set("Authorization", "Bearer test-token")
	recDel := httptest.NewRecorder()
	srv.Routes().ServeHTTP(recDel, reqDel)
	if recDel.Code != http.StatusOK {
		t.Fatalf("删除期望 200，得到 %d body=%s", recDel.Code, recDel.Body.String())
	}

	req2 := httptest.NewRequest(http.MethodGet, "/api/silences", nil)
	req2.Header.Set("Authorization", "Bearer test-token")
	rec2 := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d", rec2.Code)
	}
	var out struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec2.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if len(out.Items) != 0 {
		t.Fatalf("期望空列表，得到 %d", len(out.Items))
	}
}
