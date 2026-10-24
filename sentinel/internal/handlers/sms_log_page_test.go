package handlers

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHandleSMSLogPage_ServesEmbeddedPage(t *testing.T) {
	srv := newTestServerForSMSLog(t)
	req := httptest.NewRequest("GET", "/sms-log", nil)
	rec := httptest.NewRecorder()
	srv.handleSMSLogPage(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "sms-log-body") {
		t.Fatalf("页面正文缺少 sms-log-body 标记")
	}
}
