package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHandleSMSLogRangeValidation(t *testing.T) {
	seed := func(t *testing.T, srv *Server) {
		srv.store.RecordSMSLogForMonitor("13800000001", "hello one", "aliyun", "sent", "", 5)
		srv.store.RecordSMSLogForMonitor("13800000002", "hello two", "aliyun", "sent", "", 5)
		srv.store.RecordSMSLog("13800000003", "fail three", "aliyun", "failed", "")
	}

	t.Run("limit_0_returns_400", func(t *testing.T) {
		srv := newTestServerForSMSLog(t)
		seed(t, srv)
		req := httptest.NewRequest("GET", "/sms-logs?limit=0", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)
		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400 for limit=0, got %d", rr.Code)
		}
	})

	t.Run("limit_negative_returns_400", func(t *testing.T) {
		srv := newTestServerForSMSLog(t)
		seed(t, srv)
		req := httptest.NewRequest("GET", "/sms-logs?limit=-5", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)
		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400 for limit=-5, got %d", rr.Code)
		}
	})

	t.Run("limit_over_1000_returns_400", func(t *testing.T) {
		srv := newTestServerForSMSLog(t)
		seed(t, srv)
		req := httptest.NewRequest("GET", "/sms-logs?limit=1001", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)
		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400 for limit=1001, got %d", rr.Code)
		}
	})

	t.Run("limit_1000_returns_200", func(t *testing.T) {
		srv := newTestServerForSMSLog(t)
		seed(t, srv)
		req := httptest.NewRequest("GET", "/sms-logs?limit=1000", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("expected status 200 for limit=1000, got %d", rr.Code)
		}
		var resp smsLogValidationResp
		if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
			t.Fatalf("failed to unmarshal response: %v", err)
		}
		if resp.Limit != 1000 {
			t.Errorf("expected limit=1000, got %d", resp.Limit)
		}
	})

	t.Run("offset_negative_returns_400", func(t *testing.T) {
		srv := newTestServerForSMSLog(t)
		seed(t, srv)
		req := httptest.NewRequest("GET", "/sms-logs?offset=-1", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)
		if rr.Code != http.StatusBadRequest {
			t.Errorf("expected status 400 for offset=-1, got %d", rr.Code)
		}
	})

	t.Run("offset_zero_returns_200", func(t *testing.T) {
		srv := newTestServerForSMSLog(t)
		seed(t, srv)
		req := httptest.NewRequest("GET", "/sms-logs?offset=0", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("expected status 200 for offset=0, got %d", rr.Code)
		}
		var resp smsLogValidationResp
		if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
			t.Fatalf("failed to unmarshal response: %v", err)
		}
		if resp.Offset != 0 {
			t.Errorf("expected offset=0, got %d", resp.Offset)
		}
	})

	t.Run("no_params_returns_defaults", func(t *testing.T) {
		srv := newTestServerForSMSLog(t)
		seed(t, srv)
		req := httptest.NewRequest("GET", "/sms-logs", nil)
		rr := httptest.NewRecorder()
		srv.handleSMSLogAPI(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("expected status 200 for no params, got %d", rr.Code)
		}
		var resp smsLogValidationResp
		if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
			t.Fatalf("failed to unmarshal response: %v", err)
		}
		if resp.Limit != 50 {
			t.Errorf("expected limit=50, got %d", resp.Limit)
		}
		if resp.Total != 3 {
			t.Errorf("expected total=3, got %d", resp.Total)
		}
	})
}
