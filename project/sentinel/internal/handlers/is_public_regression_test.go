package handlers

import (
	"net/http"
	"testing"

	"sentinel/internal/store"
)

func TestCreateMonitor_IsPublicTrue(t *testing.T) {
	srv, st := newTestServer(t)
	rec, body := doJSON(t, srv.Routes(), http.MethodPost, "/api/monitors",
		`{"name":"pub-true","kind":"http","target":"http://127.0.0.1:1/health","is_public":1}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("期望状态码 201，实际为 %d，响应：%v", rec.Code, body)
	}
	if got := body["is_public"].(float64); got != 1 {
		t.Fatalf("期望响应 is_public 为 1，实际为 %v", body["is_public"])
	}
	id := int64(body["id"].(float64))
	m, err := st.GetMonitor(id)
	if err != nil {
		t.Fatalf("回查失败：%v", err)
	}
	if m.IsPublic != 1 {
		t.Fatalf("期望数据库 IsPublic 为 1，实际为 %d", m.IsPublic)
	}
}

func TestCreateMonitor_IsPublicFalse(t *testing.T) {
	srv, st := newTestServer(t)
	rec, body := doJSON(t, srv.Routes(), http.MethodPost, "/api/monitors",
		`{"name":"pub-false","kind":"http","target":"http://127.0.0.1:1/health","is_public":0}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("期望状态码 201，实际为 %d，响应：%v", rec.Code, body)
	}
	if got := body["is_public"].(float64); got != 0 {
		t.Fatalf("期望响应 is_public 为 0，实际为 %v", body["is_public"])
	}
	id := int64(body["id"].(float64))
	m, err := st.GetMonitor(id)
	if err != nil {
		t.Fatalf("回查失败：%v", err)
	}
	if m.IsPublic != 0 {
		t.Fatalf("期望数据库 IsPublic 为 0，实际为 %d", m.IsPublic)
	}
}

func TestCreateMonitor_IsPublicDefault(t *testing.T) {
	srv, st := newTestServer(t)
	rec, body := doJSON(t, srv.Routes(), http.MethodPost, "/api/monitors",
		`{"name":"pub-default","kind":"http","target":"http://127.0.0.1:1/health"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("期望状态码 201，实际为 %d，响应：%v", rec.Code, body)
	}
	if got := body["is_public"].(float64); got != 0 {
		t.Fatalf("期望响应 is_public 为 0，实际为 %v", body["is_public"])
	}
	id := int64(body["id"].(float64))
	m, err := st.GetMonitor(id)
	if err != nil {
		t.Fatalf("回查失败：%v", err)
	}
	if m.IsPublic != 0 {
		t.Fatalf("期望数据库 IsPublic 为 0，实际为 %d", m.IsPublic)
	}
}

func TestCreateMonitor_IsPublicInvalid(t *testing.T) {
	srv, _ := newTestServer(t)
	rec, body := doJSON(t, srv.Routes(), http.MethodPost, "/api/monitors",
		`{"name":"pub-invalid","kind":"http","target":"http://127.0.0.1:1/health","is_public":2}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望状态码 400，实际为 %d，响应：%v", rec.Code, body)
	}
}

func TestUpdateMonitor_IsPublicPreserved(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{Name: "pub", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1, IsPublic: 1})
	if err != nil {
		t.Fatalf("造数据失败：%v", err)
	}
	rec, _ := doJSON(t, srv.Routes(), http.MethodPut, "/api/monitors/"+itoa(id),
		`{"name":"pub-renamed","kind":"http","target":"http://127.0.0.1:1/health"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}
	m, err := st.GetMonitor(id)
	if err != nil {
		t.Fatalf("回查失败：%v", err)
	}
	if m.IsPublic != 1 {
		t.Fatalf("期望数据库 IsPublic 为 1，实际为 %d", m.IsPublic)
	}
}

func TestUpdateMonitor_IsPublicExplicit(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{Name: "pub", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1, IsPublic: 0})
	if err != nil {
		t.Fatalf("造数据失败：%v", err)
	}
	rec, _ := doJSON(t, srv.Routes(), http.MethodPut, "/api/monitors/"+itoa(id),
		`{"name":"pub-renamed","kind":"http","target":"http://127.0.0.1:1/health","is_public":1}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}
	m, err := st.GetMonitor(id)
	if err != nil {
		t.Fatalf("回查失败：%v", err)
	}
	if m.IsPublic != 1 {
		t.Fatalf("期望数据库 IsPublic 为 1，实际为 %d", m.IsPublic)
	}
}
