package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
)

func guardRowsLen(v any) int {
	if v == nil {
		return 0
	}
	if arr, ok := v.([]any); ok {
		return len(arr)
	}
	return 0
}

func TestGuard_ParseLimitMatrix(t *testing.T) {
	if got := parseLimit("", 100); got != 100 {
		t.Fatalf("parseLimit(\"\",100)=%d want 100", got)
	}
	if got := parseLimit("abc", 100); got != 100 {
		t.Fatalf("parseLimit(\"abc\",100)=%d want 100", got)
	}
	if got := parseLimit("-3", 100); got != 100 {
		t.Fatalf("parseLimit(\"-3\",100)=%d want 100", got)
	}
	if got := parseLimit("0", 100); got != 0 {
		t.Fatalf("parseLimit(\"0\",100)=%d want 0", got)
	}
	if got := parseLimit("50", 100); got != 50 {
		t.Fatalf("parseLimit(\"50\",100)=%d want 50", got)
	}
	if got := parseLimit("999999", 100); got != 999999 {
		t.Fatalf("parseLimit(\"999999\",100)=%d want 999999", got)
	}
}

func TestGuard_EscapeIdentMatrix(t *testing.T) {
	if got := escapeIdent(`a"b`); got != `a""b` {
		t.Fatalf("escapeIdent(`a\"b`)=%q want %q", got, `a""b`)
	}
	if got := escapeIdent("plain"); got != "plain" {
		t.Fatalf("escapeIdent(\"plain\")=%q want %q", got, "plain")
	}
	if got := escapeIdent(""); got != "" {
		t.Fatalf("escapeIdent(\"\")=%q want %q", got, "")
	}
}

func TestGuard_TableRows_UnknownTable(t *testing.T) {
	_, srv := newTestServer(t)
	req := httptest.NewRequest("GET", "/api/tables/nope/rows", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("unknown table status=%d want %d body=%s", rec.Code, http.StatusInternalServerError, rec.Body.String())
	}
}

func TestGuard_TableRows_InjectionNeutralized(t *testing.T) {
	st, srv := newTestServer(t)
	name := `users"; DROP TABLE "users`
	req := httptest.NewRequest("GET", "/api/tables/"+url.PathEscape(name)+"/rows", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("injection status=%d want %d body=%s", rec.Code, http.StatusInternalServerError, rec.Body.String())
	}
	total, err := st.TableCount("users")
	if err != nil {
		t.Fatalf("TableCount after injection: %v", err)
	}
	if total != 2 {
		t.Fatalf("users table destroyed by injection: total=%d want 2", total)
	}
}

func TestGuard_TableRows_LimitNegativeFallsBack(t *testing.T) {
	st, srv := newTestServer(t)
	for i := 3; i <= 152; i++ {
		if err := st.UpsertRow(st.DB, "users", "id", int64(i), []string{"id", "name", "age"}, []any{int64(i), "n", int64(20)}, "h", "srcA"); err != nil {
			t.Fatalf("UpsertRow i=%d: %v", i, err)
		}
	}
	req := httptest.NewRequest("GET", "/api/tables/users/rows?limit=-5", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("limit=-5 status=%d want %d body=%s", rec.Code, http.StatusOK, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if n := guardRowsLen(body["rows"]); n != 100 {
		t.Fatalf("rows len=%d want 100", n)
	}
	totalF, ok := body["total"].(float64)
	if !ok {
		t.Fatalf("total missing or wrong type: %v", body["total"])
	}
	if int(totalF) != 152 {
		t.Fatalf("total=%d want 152", int(totalF))
	}
}

func TestGuard_TableRows_OffsetBeyondTotal(t *testing.T) {
	_, srv := newTestServer(t)
	req := httptest.NewRequest("GET", "/api/tables/users/rows?offset=500", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("offset=500 status=%d want %d body=%s", rec.Code, http.StatusOK, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if n := guardRowsLen(body["rows"]); n != 0 {
		t.Fatalf("rows len=%d want 0", n)
	}
}

func TestGuard_TableRows_LimitZero(t *testing.T) {
	_, srv := newTestServer(t)
	req := httptest.NewRequest("GET", "/api/tables/users/rows?limit=0", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("limit=0 status=%d want %d body=%s", rec.Code, http.StatusOK, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if n := guardRowsLen(body["rows"]); n != 0 {
		t.Fatalf("rows len=%d want 0", n)
	}
	totalF, ok := body["total"].(float64)
	if !ok {
		t.Fatalf("total missing or wrong type: %v", body["total"])
	}
	if int(totalF) != 2 {
		t.Fatalf("total=%d want 2", int(totalF))
	}
}

func TestGuard_ViewRows_UnknownView(t *testing.T) {
	_, srv := newTestServer(t)
	req := httptest.NewRequest("GET", "/api/views/no-such-view/rows", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("unknown view status=%d want %d body=%s", rec.Code, http.StatusInternalServerError, rec.Body.String())
	}
}

func TestGuard_Tables_ListsUsers(t *testing.T) {
	_, srv := newTestServer(t)
	req := httptest.NewRequest("GET", "/api/tables", nil)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("tables status=%d want %d body=%s", rec.Code, http.StatusOK, rec.Body.String())
	}
	var arr []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &arr); err != nil {
		t.Fatalf("decode tables: %v body=%s", err, rec.Body.String())
	}
	found := false
	for _, e := range arr {
		name, _ := e["name"].(string)
		if name != "users" {
			continue
		}
		rowsF, ok := e["rows"].(float64)
		if !ok {
			t.Fatalf("users rows wrong type: %v", e["rows"])
		}
		if int(rowsF) != 2 {
			t.Fatalf("users rows=%d want 2", int(rowsF))
		}
		found = true
	}
	if !found {
		t.Fatalf("users not present in tables listing: %v", arr)
	}
}
