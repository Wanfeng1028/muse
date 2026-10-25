package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"sentinel/internal/store"
)

type smsLogValidationResp struct {
	Logs   []store.SMSLog `json:"logs"`
	Total  int            `json:"total"`
	Limit  int            `json:"limit"`
	Offset int            `json:"offset"`
}

func TestHandleSMSLogValidation(t *testing.T) {
	srv := newTestServerForSMSLog(t)

	// Seed three logs as described
	srv.store.RecordSMSLogForMonitor("13800000001", "hello one", "aliyun", "sent", "", 5)
	srv.store.RecordSMSLogForMonitor("13800000002", "fail two", "aliyun", "failed", "", 6)
	srv.store.RecordSMSLog("13800000003", "fail three", "aliyun", "failed", "")

	t.Run("status=sent returns 200 and logs all have status sent", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?status=sent", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusOK {
			t.Errorf("expected status 200, got %d", rr.Code)
			return
		}

		var resp smsLogValidationResp
		if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}

		if len(resp.Logs) != 1 {
			t.Errorf("expected 1 log, got %d", len(resp.Logs))
		}
		for i, l := range resp.Logs {
			if l.Status != "sent" {
				t.Errorf("log %d status expected 'sent', got '%s'", i, l.Status)
			}
		}
	})

	t.Run("status=failed returns 200 and logs all have status failed", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?status=failed", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusOK {
			t.Errorf("expected status 200, got %d", rr.Code)
			return
		}

		var resp smsLogValidationResp
		if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}

		if len(resp.Logs) != 2 {
			t.Errorf("expected 2 logs, got %d", len(resp.Logs))
		}
		for i, log := range resp.Logs {
			if log.Status != "failed" {
				t.Errorf("log %d status expected 'failed', got '%s'", i, log.Status)
			}
		}
	})

	t.Run("status=pending returns 400", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?status=pending", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400, got %d", rr.Code)
		}
	})

	t.Run("status=SENT returns 400", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?status=SENT", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400, got %d", rr.Code)
		}
	})

	t.Run("limit=abc returns 400", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?limit=abc", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400, got %d", rr.Code)
		}
	})

	t.Run("offset=abc returns 400", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?offset=abc", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400, got %d", rr.Code)
		}
	})

	t.Run("limit=2 returns 200 and limit field is 2 and logs length is 2", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?limit=2", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusOK {
			t.Errorf("expected status 200, got %d", rr.Code)
			return
		}

		var resp smsLogValidationResp
		if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}

		if resp.Limit != 2 {
			t.Errorf("expected limit field 2, got %d", resp.Limit)
		}
		if len(resp.Logs) != 2 {
			t.Errorf("expected 2 logs, got %d", len(resp.Logs))
		}
	})

	t.Run("monitor_id=-1 returns 400", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log?monitor_id=-1", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400, got %d", rr.Code)
		}
	})

	t.Run("no params returns 200 and total equals seed total 3", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/sms/log", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)

		if rr.Code != http.StatusOK {
			t.Errorf("expected status 200, got %d", rr.Code)
			return
		}

		var resp smsLogValidationResp
		if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
			t.Fatalf("failed to decode response: %v", err)
		}

		if resp.Total != 3 {
			t.Errorf("expected total 3, got %d", resp.Total)
		}
	})
}
