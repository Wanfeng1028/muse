package handlers

import (
	"net/http"
	"testing"
)

func TestHandleListIncidents_PerPage(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page=2&per_page=10", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}

	if got := body["page"].(float64); got != 2 {
		t.Fatalf("期望 page 为 2，实际为 %v", got)
	}
	if got := body["page_size"].(float64); got != 10 {
		t.Fatalf("期望 page_size 为 10，实际为 %v", got)
	}
	if got := body["total"].(float64); got != 45 {
		t.Fatalf("期望 total 为 45，实际为 %v", got)
	}

	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("期望 items 为数组，实际为 %T", body["items"])
	}
	if len(items) != 10 {
		t.Fatalf("期望 items 长度为 10，实际为 %d", len(items))
	}
}

func TestHandleListIncidents_PerPagePrecedence(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?per_page=5&page_size=20", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}

	if got := body["page_size"].(float64); got != 5 {
		t.Fatalf("期望 page_size 为 5（per_page 优先），实际为 %v", got)
	}
}

func TestHandleListIncidents_PerPageClamp(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?per_page=500", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}

	if got := body["page_size"].(float64); got != 100 {
		t.Fatalf("期望 page_size 被钳制为 100，实际为 %v", got)
	}

	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("期望 items 为数组，实际为 %T", body["items"])
	}
	if len(items) > 100 {
		t.Fatalf("期望 items 长度不超过 100，实际为 %d", len(items))
	}
}

func TestHandleListIncidents_PerPageZero(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?per_page=0", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}

	if got := body["page_size"].(float64); got != 1 {
		t.Fatalf("期望 page_size 为 1，实际为 %v", got)
	}
}

func TestHandleListIncidents_PerPageInvalid(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?per_page=abc", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}

	if got := body["page_size"].(float64); got != 20 {
		t.Fatalf("期望 page_size 为默认值 20，实际为 %v", got)
	}
}

func TestHandleListIncidents_PageZero(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page=0&per_page=10", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}

	if got := body["page"].(float64); got != 1 {
		t.Fatalf("期望 page 为 1，实际为 %v", got)
	}
}

func TestHandleListIncidents_PageHuge(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page=9999&per_page=10", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("期望状态码 200，实际为 %d", rec.Code)
	}

	if got := body["total"].(float64); got != 45 {
		t.Fatalf("期望 total 为 45，实际为 %v", got)
	}

	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("期望 items 为数组，实际为 %T", body["items"])
	}
	if len(items) != 0 {
		t.Fatalf("期望 items 为空数组，实际长度为 %d", len(items))
	}
}
