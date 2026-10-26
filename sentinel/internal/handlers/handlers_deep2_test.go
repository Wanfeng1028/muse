package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

// deep3DoJSON 与已有测试的 doJSON 类似但函数名唯一，避免顶层符号冲突。
func deep3DoJSON(t *testing.T, h http.Handler, method, path, body string) (*httptest.ResponseRecorder, map[string]any) {
	t.Helper()
	var rdr *strings.Reader
	if body != "" {
		rdr = strings.NewReader(body)
	} else {
		rdr = strings.NewReader("")
	}
	req := httptest.NewRequest(method, path, rdr)
	if strings.HasPrefix(path, "/api/") {
		req.Header.Set("Authorization", "Bearer "+testToken)
	}
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	var m map[string]any
	if rec.Body.Len() > 0 {
		_ = json.Unmarshal(rec.Body.Bytes(), &m)
	}
	return rec, m
}

func deep3CreateMonitor(t *testing.T, h http.Handler, body string) int64 {
	t.Helper()
	rec, m := deep3DoJSON(t, h, http.MethodPost, "/api/monitors", body)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create monitor failed status=%d body=%s", rec.Code, rec.Body.String())
	}
	id, ok := m["id"].(float64)
	if !ok || id <= 0 {
		t.Fatalf("create monitor missing id: %v", m)
	}
	return int64(id)
}

// TestParseIDLargeValueDeep3 覆盖超大数值边界。
func TestParseIDLargeValueDeep3(t *testing.T) {
	req := httptest.NewRequest("GET", "/monitors/9999999999999999999", nil)
	req.SetPathValue("id", "9999999999999999999")
	id, ok := parseID(req)
	if ok {
		t.Fatalf("expected ok false for overflow id, got id=%d", id)
	}
	if id != 0 {
		t.Fatalf("expected id 0, got %d", id)
	}
}

// TestParseIDPlusSignDeep3 覆盖带加号的数字输入。
func TestParseIDPlusSignDeep3(t *testing.T) {
	req := httptest.NewRequest("GET", "/monitors/+7", nil)
	req.SetPathValue("id", "+7")
	id, ok := parseID(req)
	if !ok {
		t.Fatalf("expected ok true for +7")
	}
	if id != 7 {
		t.Fatalf("expected id 7, got %d", id)
	}
}

// TestParseIDSpacesDeep3 覆盖带空格的非法输入。
func TestParseIDSpacesDeep3(t *testing.T) {
	req := httptest.NewRequest("GET", "/monitors/12", nil)
	req.SetPathValue("id", " 12 ")
	if _, ok := parseID(req); ok {
		t.Fatalf("expected ok false for whitespace-padded id")
	}
}

// TestCheckJSONNullStatusCodeDeep3 校验状态码/证书天数为空时的输出。
func TestCheckJSONNullStatusCodeDeep3(t *testing.T) {
	c := store.Check{
		ID:        1,
		MonitorID: 2,
		Ok:        0,
		LatencyMs: 33,
		Error:     "boom",
	}
	out := checkJSON(c)
	if out["status_code"] != nil {
		t.Fatalf("expected nil status_code, got %v", out["status_code"])
	}
	if out["cert_days_left"] != nil {
		t.Fatalf("expected nil cert_days_left, got %v", out["cert_days_left"])
	}
	if out["ok"] != false {
		t.Fatalf("expected ok=false, got %v", out["ok"])
	}
	if out["latency_ms"] != int64(33) && out["latency_ms"] != 33 {
		t.Fatalf("unexpected latency_ms %v", out["latency_ms"])
	}
}

// TestCheckJSONValidFieldsDeep3 校验有效字段被正确转换。
func TestCheckJSONValidFieldsDeep3(t *testing.T) {
	c := store.Check{
		ID:        10,
		MonitorID: 20,
		Ok:        1,
		LatencyMs: 12,
	}
	c.StatusCode.Valid = true
	c.StatusCode.Int64 = 200
	c.CertDaysLeft.Valid = true
	c.CertDaysLeft.Int64 = 45

	out := checkJSON(c)
	if out["ok"] != true {
		t.Fatalf("expected ok=true, got %v", out["ok"])
	}
	if v, _ := out["status_code"].(int64); v != 200 {
		t.Fatalf("expected status_code 200, got %v", out["status_code"])
	}
	if v, _ := out["cert_days_left"].(int64); v != 45 {
		t.Fatalf("expected cert_days_left 45, got %v", out["cert_days_left"])
	}
}

// TestMonitorJSONFieldsDeep3 校验 monitorJSON 的字段映射。
func TestMonitorJSONFieldsDeep3(t *testing.T) {
	m := store.Monitor{
		ID:             3,
		Name:           "svc",
		Kind:           "tcp",
		Target:         "db:5432",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    30,
		Enabled:        1,
		WebhookURL:     "https://hook",
		NotifyChannels: "webhook,sms",
		SMSPhones:      "13800000000",
		TenantID:       2,
		IsPublic:       1,
	}
	out := monitorJSON(m)
	if out["id"] != int64(3) && out["id"] != 3 {
		t.Fatalf("unexpected id %v", out["id"])
	}
	if out["kind"] != "tcp" {
		t.Fatalf("unexpected kind %v", out["kind"])
	}
	if out["notify_channels"] != "webhook,sms" {
		t.Fatalf("unexpected notify_channels %v", out["notify_channels"])
	}
	if out["tenant_id"] != int64(2) && out["tenant_id"] != 2 {
		t.Fatalf("unexpected tenant_id %v", out["tenant_id"])
	}
	if out["is_public"] != int64(1) && out["is_public"] != 1 {
		t.Fatalf("unexpected is_public %v", out["is_public"])
	}
}

// TestWriteErrShapeDeep3 校验错误响应结构与 Content-Type。
func TestWriteErrShapeDeep3(t *testing.T) {
	rec := httptest.NewRecorder()
	writeErr(rec, http.StatusTeapot, "boom")
	if rec.Code != http.StatusTeapot {
		t.Fatalf("expected 418, got %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "application/json") {
		t.Fatalf("unexpected content-type %q", ct)
	}
	var m map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if m["error"] != "boom" {
		t.Fatalf("unexpected error message %q", m["error"])
	}
}

// TestHandleGetMonitorInvalidIDDeep3 覆盖非数字 ID 的路径分支。
func TestHandleGetMonitorInvalidIDDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/monitors/abc", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
	if _, ok := m["error"]; !ok {
		t.Fatalf("expected error field, got %v", m)
	}
}

// TestHandleGetMonitorZeroIDDeep3 覆盖 ID 为 0 的非法分支。
func TestHandleGetMonitorZeroIDDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodGet, "/api/monitors/0", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleGetMonitorNotFoundDeep3 覆盖不存在的监控。
func TestHandleGetMonitorNotFoundDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/monitors/424242", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rec.Code, rec.Body.String())
	}
	if m["error"] == "" || m["error"] == nil {
		t.Fatalf("expected non-empty error, got %v", m)
	}
}

// TestHandleGetMonitorRecentChecksEmptyDeep3 覆盖刚创建无检查记录时 recent_checks 为空数组。
func TestHandleGetMonitorRecentChecksEmptyDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	id := deep3CreateMonitor(t, h, `{"name":"fresh","kind":"http","target":"https://example.com"}`)
	rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/monitors/"+itoa(id), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	rc, ok := m["recent_checks"].([]any)
	if !ok {
		t.Fatalf("recent_checks wrong type: %v", m["recent_checks"])
	}
	if len(rc) != 0 {
		t.Fatalf("expected empty recent_checks, got %v", rc)
	}
}

// TestHandleUpdateMonitorInvalidJSONDeep3 覆盖更新时 JSON 解析失败分支。
func TestHandleUpdateMonitorInvalidJSONDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	id := deep3CreateMonitor(t, h, `{"name":"u","kind":"http","target":"https://example.com"}`)
	rec, m := deep3DoJSON(t, h, http.MethodPut, "/api/monitors/"+itoa(id), `{not json`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
	if _, ok := m["error"]; !ok {
		t.Fatalf("expected error field, got %v", m)
	}
}

// TestHandleUpdateMonitorNotFoundDeep3 覆盖更新不存在监控返回 404。
func TestHandleUpdateMonitorNotFoundDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodPut, "/api/monitors/987654",
		`{"name":"nope","kind":"http","target":"https://example.com"}`)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleDeleteMonitorNotFoundDeep3 覆盖删除不存在监控返回 404。
func TestHandleDeleteMonitorNotFoundDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodDelete, "/api/monitors/123456", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleListChecksNotFoundDeep3 覆盖监控不存在时的检查记录列表。
func TestHandleListChecksNotFoundDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodGet, "/api/monitors/555555/checks", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleListChecksLimitClampDeep3 覆盖 limit 参数的上下界钳制。
func TestHandleListChecksLimitClampDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	id := deep3CreateMonitor(t, h, `{"name":"clamp","kind":"http","target":"https://example.com"}`)

	rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/monitors/"+itoa(id)+"/checks?limit=-5", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for negative limit, got %d body=%s", rec.Code, rec.Body.String())
	}
	if _, ok := m["items"].([]any); !ok {
		t.Fatalf("items wrong type: %v", m["items"])
	}

	rec, m = deep3DoJSON(t, h, http.MethodGet, "/api/monitors/"+itoa(id)+"/checks?limit=99999", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for large limit, got %d body=%s", rec.Code, rec.Body.String())
	}
	if _, ok := m["items"].([]any); !ok {
		t.Fatalf("items wrong type: %v", m["items"])
	}
	if _, ok := m["total"]; !ok {
		t.Fatalf("missing total in response: %v", m)
	}
}

// TestHandleStatsNotFoundDeep3 覆盖统计不存在监控返回 404。
func TestHandleStatsNotFoundDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodGet, "/api/monitors/777777/stats", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleStatsDaysClampDeep3 覆盖 days 参数钳制与统计字段存在性。
func TestHandleStatsDaysClampDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	id := deep3CreateMonitor(t, h, `{"name":"stats","kind":"http","target":"https://example.com"}`)

	for _, q := range []string{"?days=0", "?days=-3", "?days=9999", "?days=abc"} {
		rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/monitors/"+itoa(id)+"/stats"+q, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("days=%q expected 200, got %d body=%s", q, rec.Code, rec.Body.String())
		}
		for _, key := range []string{"uptime_pct", "avg_latency_ms", "total_checks", "down_incidents"} {
			if _, ok := m[key]; !ok {
				t.Fatalf("days=%q missing %s in %v", q, key, m)
			}
		}
	}
}

// TestHandleCheckNowNotFoundDeep3 覆盖立即检查不存在监控返回 404。
func TestHandleCheckNowNotFoundDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodPost, "/api/monitors/888888/check", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleCheckNowInvalidIDDeep3 覆盖立即检查非法 ID 返回 400。
func TestHandleCheckNowInvalidIDDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodPost, "/api/monitors/xyz/check", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleListIncidentsLimitClampDeep3 覆盖事件列表 limit 钳制。
func TestHandleListIncidentsLimitClampDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	for _, q := range []string{"?limit=0", "?limit=-9", "?limit=5000", "?limit=bad"} {
		rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/incidents"+q, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("limit=%q expected 200, got %d body=%s", q, rec.Code, rec.Body.String())
		}
		if _, ok := m["items"].([]any); !ok {
			t.Fatalf("limit=%q items wrong type: %v", q, m["items"])
		}
	}
}

// TestHandleListIncidentsMonitorIDNonNumericDeep3 覆盖 monitor_id 非法时返回 400（v0.20.8 合同变更：此前回退为 0 返回 200）。
func TestHandleListIncidentsMonitorIDNonNumericDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodGet, "/api/incidents?monitor_id=notanumber", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleCreateMonitorInvalidJSONDeep3 覆盖创建请求体解析失败。
func TestHandleCreateMonitorInvalidJSONDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodPost, "/api/monitors", `{"name":`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
	if _, ok := m["error"]; !ok {
		t.Fatalf("expected error field, got %v", m)
	}
}

// TestHandleCreateMonitorValidationErrorDeep3 覆盖校验失败返回 400 且带中文错误。
func TestHandleCreateMonitorValidationErrorDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodPost, "/api/monitors",
		`{"name":"bad","kind":"tcp","target":"nocolon"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
	msg, _ := m["error"].(string)
	if !strings.Contains(msg, "host:port") {
		t.Fatalf("expected host:port error message, got %q", msg)
	}
}

// TestHandleCreateMonitorTCPSuccessDeep3 覆盖 TCP 类型创建成功及字段回显。
func TestHandleCreateMonitorTCPSuccessDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodPost, "/api/monitors",
		`{"name":"db","kind":"tcp","target":"127.0.0.1:5432","interval_sec":30,"timeout_sec":3,"enabled":0}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d body=%s", rec.Code, rec.Body.String())
	}
	if m["kind"] != "tcp" {
		t.Fatalf("expected kind tcp, got %v", m["kind"])
	}
	if m["target"] != "127.0.0.1:5432" {
		t.Fatalf("unexpected target %v", m["target"])
	}
	if v, _ := m["interval_sec"].(float64); int(v) != 30 {
		t.Fatalf("unexpected interval_sec %v", m["interval_sec"])
	}
	if v, _ := m["timeout_sec"].(float64); int(v) != 3 {
		t.Fatalf("unexpected timeout_sec %v", m["timeout_sec"])
	}
	if v, _ := m["enabled"].(float64); int(v) != 0 {
		t.Fatalf("unexpected enabled %v", m["enabled"])
	}
}

// TestHandleStatusPageEmptySlugDeep3 覆盖 slug 为空时的 400 分支。
func TestHandleStatusPageEmptySlugDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/status/", nil)
	req.SetPathValue("slug", "")
	srv.handleStatusPage(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
	var m map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if m["error"] == "" {
		t.Fatalf("expected non-empty error message")
	}
}

// TestHandleStatusPageWhitespaceSlugDeep3 覆盖仅空白 slug 的 400 分支。
func TestHandleStatusPageWhitespaceSlugDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/status/%20", nil)
	req.SetPathValue("slug", "   ")
	srv.handleStatusPage(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleSMSLogAPIPaginationDeep3 覆盖短信日志 API 的分页参数解析。
func TestHandleSMSLogAPIPaginationDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/sms/log?limit=10&offset=5", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	if v, _ := m["limit"].(float64); int(v) != 10 {
		t.Fatalf("expected limit 10, got %v", m["limit"])
	}
	if v, _ := m["offset"].(float64); int(v) != 5 {
		t.Fatalf("expected offset 5, got %v", m["offset"])
	}
	if _, ok := m["logs"]; !ok {
		t.Fatalf("missing logs field: %v", m)
	}
	if _, ok := m["total"]; !ok {
		t.Fatalf("missing total field: %v", m)
	}
}

// TestHandleSMSLogAPIInvalidParamsDeep3 覆盖非法 limit/offset 返回 400（v0.20.6 起收紧：
// 非法 limit/offset 不再静默回退默认值，与投递接口的严格校验口径一致）。
func TestHandleSMSLogAPIInvalidParamsDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, _ := deep3DoJSON(t, h, http.MethodGet, "/api/sms/log?limit=abc&offset=xyz", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestHandleMetricsContentTypeDeep3 覆盖 metrics 端点响应头与 200。
func TestHandleMetricsContentTypeDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/metrics", nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	ct := rec.Header().Get("Content-Type")
	if !strings.Contains(ct, "text/plain") {
		t.Fatalf("expected text/plain content-type, got %q", ct)
	}
}

// TestHandleReadyzStatusDeep3 覆盖 readyz 端点返回 ready 或 not ready。
func TestHandleReadyzStatusDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/readyz", "")
	if rec.Code != http.StatusOK && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("unexpected status %d body=%s", rec.Code, rec.Body.String())
	}
	status, _ := m["status"].(string)
	if status != "ready" && status != "not ready" {
		t.Fatalf("unexpected readyz status %q", status)
	}
}

// TestHandleHealthzShapeDeep3 覆盖 healthz 端点响应结构。
func TestHandleHealthzShapeDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/healthz", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if m["status"] != "ok" {
		t.Fatalf("expected status ok, got %v", m["status"])
	}
}

// TestHandleListMonitorsEmptyDeep3 覆盖空监控列表返回空数组而非 null。
func TestHandleListMonitorsEmptyDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	req := httptest.NewRequest(http.MethodGet, "/api/monitors", nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	var list []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &list); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, rec.Body.String())
	}
	if list == nil {
		t.Fatalf("expected non-nil empty slice, got null")
	}
	if len(list) != 0 {
		t.Fatalf("expected empty list, got %d", len(list))
	}
}

// TestHandleOverviewEmptyDeep3 覆盖无监控时概览零值。
func TestHandleOverviewEmptyDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	rec, m := deep3DoJSON(t, h, http.MethodGet, "/api/overview", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	for _, key := range []string{"total", "enabled", "up", "down", "unknown", "checks_24h", "incidents_7d"} {
		v, ok := m[key].(float64)
		if !ok {
			t.Fatalf("missing/invalid %s: %v", key, m[key])
		}
		if v != 0 {
			t.Fatalf("expected %s=0, got %v", key, v)
		}
	}
}

// TestValidateMonitorNotifyChannelsNormalizeDeep3 覆盖 notify_channels 归一化。
func TestValidateMonitorNotifyChannelsNormalizeDeep3(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
		NotifyChannels: " webhook , sms ",
	}
	if err := validateMonitor(m); err != nil {
		t.Fatalf("expected valid notify_channels, got %v", err)
	}
	if strings.Contains(m.NotifyChannels, " ") {
		t.Fatalf("expected normalized channels, got %q", m.NotifyChannels)
	}
	if !strings.Contains(m.NotifyChannels, "webhook") || !strings.Contains(m.NotifyChannels, "sms") {
		t.Fatalf("expected webhook and sms, got %q", m.NotifyChannels)
	}
}

// TestValidateMonitorNotifyChannelsInvalidDeep3 覆盖非法 notify_channels。
func TestValidateMonitorNotifyChannelsInvalidDeep3(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
		NotifyChannels: "bogus",
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for invalid notify_channels, got nil")
	}
}

// TestValidateMonitorSMSPhonesInvalidDeep3 覆盖非法 sms_phones。
func TestValidateMonitorSMSPhonesInvalidDeep3(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
		SMSPhones:      "not-a-phone",
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for invalid sms_phones, got nil")
	}
}

// TestValidateMonitorTrimsWhitespaceDeep3 覆盖各字段去除首尾空白。
func TestValidateMonitorTrimsWhitespaceDeep3(t *testing.T) {
	m := &store.Monitor{
		Name:           "  padded  ",
		Kind:           "  http  ",
		Target:         "  https://example.com  ",
		Method:         "  GET  ",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	if err := validateMonitor(m); err != nil {
		t.Fatalf("expected valid after trim, got %v", err)
	}
	if m.Name != "padded" {
		t.Fatalf("expected trimmed name, got %q", m.Name)
	}
	if m.Kind != "http" {
		t.Fatalf("expected trimmed kind, got %q", m.Kind)
	}
	if m.Target != "https://example.com" {
		t.Fatalf("expected trimmed target, got %q", m.Target)
	}
	if m.Method != "GET" {
		t.Fatalf("expected trimmed method, got %q", m.Method)
	}
}

// TestValidateMonitorHTTPBoundaryStatusDeep3 覆盖 expected_status 边界 100/599。
func TestValidateMonitorHTTPBoundaryStatusDeep3(t *testing.T) {
	low := &store.Monitor{
		Name: "x", Kind: "http", Target: "https://example.com", Method: "GET",
		ExpectedStatus: 100, TimeoutSec: 10, IntervalSec: 60, Enabled: 1,
	}
	if err := validateMonitor(low); err != nil {
		t.Fatalf("expected 100 valid, got %v", err)
	}
	high := &store.Monitor{
		Name: "x", Kind: "http", Target: "https://example.com", Method: "GET",
		ExpectedStatus: 599, TimeoutSec: 10, IntervalSec: 60, Enabled: 1,
	}
	if err := validateMonitor(high); err != nil {
		t.Fatalf("expected 599 valid, got %v", err)
	}
}

// TestValidateMonitorTimeoutBoundaryDeep3 覆盖 timeout 边界 1/60。
func TestValidateMonitorTimeoutBoundaryDeep3(t *testing.T) {
	low := &store.Monitor{
		Name: "x", Kind: "http", Target: "https://example.com", Method: "GET",
		ExpectedStatus: 200, TimeoutSec: 1, IntervalSec: 60, Enabled: 1,
	}
	if err := validateMonitor(low); err != nil {
		t.Fatalf("expected timeout 1 valid, got %v", err)
	}
	high := &store.Monitor{
		Name: "x", Kind: "http", Target: "https://example.com", Method: "GET",
		ExpectedStatus: 200, TimeoutSec: 60, IntervalSec: 60, Enabled: 1,
	}
	if err := validateMonitor(high); err != nil {
		t.Fatalf("expected timeout 60 valid, got %v", err)
	}
}

// TestValidateMonitorIntervalBoundaryDeep3 覆盖 interval 边界 10/3600。
func TestValidateMonitorIntervalBoundaryDeep3(t *testing.T) {
	low := &store.Monitor{
		Name: "x", Kind: "http", Target: "https://example.com", Method: "GET",
		ExpectedStatus: 200, TimeoutSec: 10, IntervalSec: 10, Enabled: 1,
	}
	if err := validateMonitor(low); err != nil {
		t.Fatalf("expected interval 10 valid, got %v", err)
	}
	high := &store.Monitor{
		Name: "x", Kind: "http", Target: "https://example.com", Method: "GET",
		ExpectedStatus: 200, TimeoutSec: 10, IntervalSec: 3600, Enabled: 1,
	}
	if err := validateMonitor(high); err != nil {
		t.Fatalf("expected interval 3600 valid, got %v", err)
	}
}

// TestToMonitorEmptyStringMethodKeepsDefaultDeep3 覆盖 method 为空串时保留默认 GET。
func TestToMonitorEmptyStringMethodKeepsDefaultDeep3(t *testing.T) {
	method := ""
	name := "svc"
	kind := "http"
	target := "https://example.com"
	in := &monitorInput{
		Name:   &name,
		Kind:   &kind,
		Target: &target,
		Method: &method,
	}
	m := in.toMonitor()
	if m.Method != "GET" {
		t.Fatalf("expected default GET for empty method, got %q", m.Method)
	}
}
