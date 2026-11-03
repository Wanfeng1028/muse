package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"sentinel/internal/db"
	"sentinel/internal/store"
)

func newTestServerForSMSLog(t *testing.T) *Server {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")
	conn, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	t.Cleanup(func() { conn.Close() })
	st := store.New(conn)
	return New(st, nil, 3)
}

func TestHandleListSMSLog(t *testing.T) {
	srv := newTestServerForSMSLog(t)

	records := []struct {
		phone  string
		status string
		body   string
	}{
		{"13800000001", "sent", "hello one"},
		{"13800000002", "failed", "hello two"},
		{"13800000003", "failed", "hello three"},
	}
	for _, r := range records {
		if err := srv.store.RecordSMSLog(r.phone, r.body, "aliyun", r.status, ""); err != nil {
			t.Fatalf("RecordSMSLog failed: %v", err)
		}
	}

	type smsLogResp struct {
		Logs   []store.SMSLog `json:"logs"`
		Limit  int            `json:"limit"`
		Offset int            `json:"offset"`
	}

	doGet := func(t *testing.T, target string) (*httptest.ResponseRecorder, smsLogResp) {
		t.Helper()
		req := httptest.NewRequest(http.MethodGet, target, nil)
		rec := httptest.NewRecorder()
		srv.handleSMSLogAPI(rec, req)
		var parsed smsLogResp
		if err := json.Unmarshal(rec.Body.Bytes(), &parsed); err != nil {
			t.Fatalf("json.Unmarshal failed for %s: %v, body=%s", target, err, rec.Body.String())
		}
		return rec, parsed
	}

	t.Run("no filter returns all", func(t *testing.T) {
		rec, parsed := doGet(t, "/api/sms/log")
		if rec.Code != http.StatusOK {
			t.Fatalf("status = %d, want %d, body=%s", rec.Code, http.StatusOK, rec.Body.String())
		}
		if len(parsed.Logs) != 3 {
			t.Fatalf("len(logs) = %d, want 3", len(parsed.Logs))
		}
	})

	t.Run("filter by phone", func(t *testing.T) {
		rec, parsed := doGet(t, "/api/sms/log?phone=13800000002")
		if rec.Code != http.StatusOK {
			t.Fatalf("status = %d, want %d, body=%s", rec.Code, http.StatusOK, rec.Body.String())
		}
		if len(parsed.Logs) != 1 {
			t.Fatalf("len(logs) = %d, want 1", len(parsed.Logs))
		}
		if parsed.Logs[0].Phone != "13800000002" {
			t.Fatalf("phone = %q, want %q", parsed.Logs[0].Phone, "13800000002")
		}
	})

	t.Run("filter by status failed", func(t *testing.T) {
		rec, parsed := doGet(t, "/api/sms/log?status=failed")
		if rec.Code != http.StatusOK {
			t.Fatalf("status = %d, want %d, body=%s", rec.Code, http.StatusOK, rec.Body.String())
		}
		if len(parsed.Logs) != 2 {
			t.Fatalf("len(logs) = %d, want 2", len(parsed.Logs))
		}
		for i, l := range parsed.Logs {
			if l.Status != "failed" {
				t.Fatalf("logs[%d].Status = %q, want %q", i, l.Status, "failed")
			}
		}
	})

	t.Run("pagination limit and offset", func(t *testing.T) {
		rec, parsed := doGet(t, "/api/sms/log?limit=2&offset=1")
		if rec.Code != http.StatusOK {
			t.Fatalf("status = %d, want %d, body=%s", rec.Code, http.StatusOK, rec.Body.String())
		}
		if parsed.Limit != 2 {
			t.Fatalf("limit = %d, want 2", parsed.Limit)
		}
		if parsed.Offset != 1 {
			t.Fatalf("offset = %d, want 1", parsed.Offset)
		}
		if len(parsed.Logs) != 2 {
			t.Fatalf("len(logs) = %d, want 2", len(parsed.Logs))
		}
	})
}

func TestHandleListSMSLog_Empty(t *testing.T) {
	srv := newTestServerForSMSLog(t)

	req := httptest.NewRequest(http.MethodGet, "/api/sms/log", nil)
	rec := httptest.NewRecorder()
	srv.handleSMSLogAPI(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d, body=%s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(rec.Body.Bytes(), &raw); err != nil {
		t.Fatalf("json.Unmarshal failed: %v, body=%s", err, rec.Body.String())
	}

	logsRaw, ok := raw["logs"]
	if !ok {
		t.Fatalf("response missing key logs, body=%s", rec.Body.String())
	}
	if string(logsRaw) != "[]" {
		t.Fatalf("logs = %s, want []", string(logsRaw))
	}

	var parsed struct {
		Logs []store.SMSLog `json:"logs"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &parsed); err != nil {
		t.Fatalf("json.Unmarshal failed: %v", err)
	}
	if len(parsed.Logs) != 0 {
		t.Fatalf("len(logs) = %d, want 0", len(parsed.Logs))
	}

	_ = fmt.Sprint(parsed.Logs)
}