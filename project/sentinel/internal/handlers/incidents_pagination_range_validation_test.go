package handlers

import (
	"net/http"
	"testing"
)

func TestHandleListIncidents_PageNegative(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, _ := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page=-1", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望状态码 400，实际为 %d", rec.Code)
	}
}

func TestHandleListIncidents_PageSizeZero(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, _ := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page_size=0", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望状态码 400，实际为 %d", rec.Code)
	}
}

func TestHandleListIncidents_PageSize101Returns400(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, _ := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page_size=101", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望状态码 400，实际为 %d", rec.Code)
	}
}

func TestHandleListIncidents_PerPageNegative(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, _ := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?per_page=-5", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望状态码 400，实际为 %d", rec.Code)
	}
}
