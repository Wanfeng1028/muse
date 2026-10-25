package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"sentinel/internal/store"
)

func TestHandleListSMSLogMonitor(t *testing.T) {
	srv := newTestServerForSMSLog(t)

	if err := srv.store.RecordSMSLogForMonitor("13800000001", "cpu usage high", "aliyun", "sent", "", 5); err != nil {
		t.Fatalf("record sent sms log for monitor 5: %v", err)
	}
	if err := srv.store.RecordSMSLogForMonitor("13800000002", "disk usage high", "aliyun", "failed", "provider timeout", 6); err != nil {
		t.Fatalf("record failed sms log for monitor 6: %v", err)
	}

	type response struct {
		Logs   []store.SMSLog `json:"logs"`
		Total  int            `json:"total"`
		Limit  int            `json:"limit"`
		Offset int            `json:"offset"`
	}

	t.Run("filter by monitor id", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?monitor_id=5", nil)
		rec := httptest.NewRecorder()

		srv.handleSMSLogAPI(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("status code = %d, want %d", rec.Code, http.StatusOK)
		}

		var resp response
		if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
			t.Fatalf("unmarshal response body: %v", err)
		}
		if len(resp.Logs) != 1 {
			t.Fatalf("logs length = %d, want 1", len(resp.Logs))
		}
		if resp.Logs[0].MonitorID != 5 {
			t.Errorf("monitor_id = %d, want 5", resp.Logs[0].MonitorID)
		}
		if resp.Total != 1 {
			t.Errorf("total = %d, want 1", resp.Total)
		}
	})

	t.Run("invalid monitor id", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?monitor_id=abc", nil)
		rec := httptest.NewRecorder()

		srv.handleSMSLogAPI(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Fatalf("status code = %d, want %d", rec.Code, http.StatusBadRequest)
		}
	})

	t.Run("list without filter", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log", nil)
		rec := httptest.NewRecorder()

		srv.handleSMSLogAPI(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("status code = %d, want %d", rec.Code, http.StatusOK)
		}

		var resp response
		if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
			t.Fatalf("unmarshal response body: %v", err)
		}
		if len(resp.Logs) != 2 {
			t.Fatalf("logs length = %d, want 2", len(resp.Logs))
		}
		if resp.Total != 2 {
			t.Errorf("total = %d, want 2", resp.Total)
		}
	})
}
