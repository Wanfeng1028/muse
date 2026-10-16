package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestMonitorSMSPhones_Invalid400(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	rec, m := doJSON(t, h, http.MethodPost, "/api/monitors", `{"name":"t","kind":"http","target":"https://example.com"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建监控状态码 = %d，期望 201，body=%s", rec.Code, rec.Body.String())
	}
	id, ok := m["id"].(float64)
	if !ok {
		t.Fatalf("创建监控返回体缺少 id，实际 %v", m)
	}

	path := fmt.Sprintf("/api/monitors/%d", int(id))
	rec, body := doJSON(t, h, http.MethodPut, path, `{"name":"t","kind":"http","target":"https://example.com","sms_phones":"123"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("更新状态码 = %d，期望 400，body=%s", rec.Code, rec.Body.String())
	}
	errMsg, _ := body["error"].(string)
	if !strings.Contains(errMsg, "sms_phones") {
		t.Fatalf("错误信息应含 sms_phones，实际 %q", errMsg)
	}
}

func TestMonitorSMSPhones_OK(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	rec, m := doJSON(t, h, http.MethodPost, "/api/monitors", `{"name":"t","kind":"http","target":"https://example.com"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建监控状态码 = %d，期望 201，body=%s", rec.Code, rec.Body.String())
	}
	id, ok := m["id"].(float64)
	if !ok {
		t.Fatalf("创建监控返回体缺少 id，实际 %v", m)
	}

	path := fmt.Sprintf("/api/monitors/%d", int(id))
	rec, _ = doJSON(t, h, http.MethodPut, path, `{"name":"t","kind":"http","target":"https://example.com","notify_channels":"sms,wecom","sms_phones":"13800138000, 13900139000"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("更新状态码 = %d，期望 200，body=%s", rec.Code, rec.Body.String())
	}

	lreq := newReq(http.MethodGet, "/api/monitors", nil)
	lrec := httptest.NewRecorder()
	h.ServeHTTP(lrec, lreq)
	if lrec.Code != http.StatusOK {
		t.Fatalf("列表状态码 = %d，期望 200，body=%s", lrec.Code, lrec.Body.String())
	}
	var arr []map[string]any
	if err := json.Unmarshal(lrec.Body.Bytes(), &arr); err != nil {
		t.Fatalf("列表返回体解析失败: %v, body=%s", err, lrec.Body.String())
	}
	var found map[string]any
	for _, mm := range arr {
		if v, ok := mm["id"].(float64); ok && int64(v) == int64(id) {
			found = mm
			break
		}
	}
	if found == nil {
		t.Fatalf("未在列表中找到 id=%d 的监控", int(id))
	}
	if got, _ := found["sms_phones"].(string); got != "13800138000,13900139000" {
		t.Fatalf("sms_phones = %q，期望 %q", got, "13800138000,13900139000")
	}
	if got, _ := found["notify_channels"].(string); got != "sms,wecom" {
		t.Fatalf("notify_channels = %q，期望 %q", got, "sms,wecom")
	}
}

func TestMonitorSMSPhones_CreateWithSMS(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	rec, m := doJSON(t, h, http.MethodPost, "/api/monitors", `{"name":"t","kind":"http","target":"https://example.com","notify_channels":"sms","sms_phones":"+85212345678"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建监控状态码 = %d，期望 201，body=%s", rec.Code, rec.Body.String())
	}
	if got, _ := m["sms_phones"].(string); got != "+85212345678" {
		t.Fatalf("sms_phones = %q，期望 %q", got, "+85212345678")
	}
}
