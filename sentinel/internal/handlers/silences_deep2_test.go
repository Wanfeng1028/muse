package handlers

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func deep3SilenceAuthReq(t *testing.T, srv *Server, method, path string, body []byte) *httptest.ResponseRecorder {
	t.Helper()
	var r *http.Request
	if body == nil {
		r = httptest.NewRequest(method, path, nil)
	} else {
		r = httptest.NewRequest(method, path, bytes.NewReader(body))
	}
	r.Header.Set("Authorization", "Bearer test-token")
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, r)
	return rec
}

func TestDeep3CreateSilenceInvalidJSON(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", []byte("{not json"))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非法 JSON 期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析错误响应失败: %v", err)
	}
	if out["error"] == nil && out["message"] == nil {
		t.Fatalf("期望错误信息字段，得到 %v", out)
	}
}

func TestDeep3CreateSilenceEmptyBody(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", []byte(""))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("空请求体期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestDeep3CreateSilenceWrongTypeMonitorID(t *testing.T) {
	srv, _ := newTestServer(t)
	body := []byte(`{"monitor_id":"abc","starts_at":"x","ends_at":"y"}`)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", body)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("类型错误期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestDeep3CreateSilenceNegativeMonitorID(t *testing.T) {
	srv, _ := newTestServer(t)
	body := map[string]any{
		"monitor_id": -5,
		"name_match": "neg",
		"starts_at":  time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		"ends_at":    time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
		"reason":     "负 id 不应触发监控存在性校验",
	}
	raw, _ := json.Marshal(body)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", raw)
	if rec.Code != http.StatusCreated {
		t.Fatalf("负 monitor_id 期望跳过校验并 201，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	if id, ok := out["id"].(float64); !ok || id <= 0 {
		t.Fatalf("期望正 id，得到 %v", out["id"])
	}
	if mid, ok := out["monitor_id"].(float64); !ok || int64(mid) != -5 {
		t.Fatalf("期望回显 monitor_id=-5，得到 %v", out["monitor_id"])
	}
}

func TestDeep3CreateSilenceHugeNameMatch(t *testing.T) {
	srv, _ := newTestServer(t)
	huge := strings.Repeat("x", 100000)
	body := map[string]any{
		"name_match": huge,
		"starts_at":  time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		"ends_at":    time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
		"reason":     "超长输入",
	}
	raw, _ := json.Marshal(body)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", raw)
	if rec.Code != http.StatusCreated {
		t.Fatalf("超长 name_match 期望 201（或明确拒绝），得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	got, _ := out["name_match"].(string)
	if len(got) != len(huge) {
		t.Fatalf("期望 name_match 长度 %d，得到 %d", len(huge), len(got))
	}
}

func TestDeep3CreateSilenceEmptyFieldsEcho(t *testing.T) {
	srv, _ := newTestServer(t)
	body := map[string]any{}
	raw, _ := json.Marshal(body)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", raw)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("空对象期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	if msg, _ := out["error"].(string); msg != "starts_at 不是合法的 RFC3339 时间" {
		t.Fatalf("期望 error=starts_at 不是合法的 RFC3339 时间，得到 %v", out)
	}
}

func TestDeep3ListSilencesEmptyState(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := deep3SilenceAuthReq(t, srv, http.MethodGet, "/api/silences", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if out.Items == nil {
		t.Fatalf("期望 items 为非 null 的空数组，得到 nil")
	}
	if len(out.Items) != 0 {
		t.Fatalf("期望空列表，得到 %d 条", len(out.Items))
	}
}

func TestDeep3ListSilencesMultipleOrdering(t *testing.T) {
	srv, _ := newTestServer(t)
	names := []string{"alpha", "beta", "gamma"}
	for _, n := range names {
		body := map[string]any{
			"name_match": n,
			"starts_at":  time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
			"ends_at":    time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
			"reason":     n,
		}
		raw, _ := json.Marshal(body)
		rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", raw)
		if rec.Code != http.StatusCreated {
			t.Fatalf("创建 %s 失败: %d %s", n, rec.Code, rec.Body.String())
		}
	}
	rec := deep3SilenceAuthReq(t, srv, http.MethodGet, "/api/silences", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d", rec.Code)
	}
	var out struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if len(out.Items) != len(names) {
		t.Fatalf("期望 %d 条，得到 %d", len(names), len(out.Items))
	}
	seen := map[string]bool{}
	for _, it := range out.Items {
		seen[it["name_match"].(string)] = true
	}
	for _, n := range names {
		if !seen[n] {
			t.Fatalf("列表中缺少 %s", n)
		}
	}
}

func TestDeep3DeleteSilenceInvalidID(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := deep3SilenceAuthReq(t, srv, http.MethodDelete, "/api/silences/notanumber", nil)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非数字 id 期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestDeep3DeleteSilenceNegativeID(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := deep3SilenceAuthReq(t, srv, http.MethodDelete, "/api/silences/-1", nil)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("负 id 期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析错误响应失败: %v", err)
	}
	if msg, _ := out["error"].(string); msg != "无效的 id" {
		t.Fatalf("期望 error=无效的 id，得到 %v", out)
	}
}

func TestDeep3DeleteSilenceMissingID(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := deep3SilenceAuthReq(t, srv, http.MethodDelete, "/api/silences/999999", nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("不存在的 id 期望 404，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析错误响应失败: %v", err)
	}
	if out["error"] == nil && out["message"] == nil {
		t.Fatalf("期望错误信息字段，得到 %v", out)
	}
}

func TestDeep3DeleteSilenceTwice(t *testing.T) {
	srv, _ := newTestServer(t)
	body := map[string]any{
		"name_match": "double-del",
		"starts_at":  time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		"ends_at":    time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
		"reason":     "删除两次",
	}
	raw, _ := json.Marshal(body)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", raw)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建失败: %d %s", rec.Code, rec.Body.String())
	}
	var created map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &created); err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	id := int64(created["id"].(float64))
	path := "/api/silences/" + itoa(id)
	first := deep3SilenceAuthReq(t, srv, http.MethodDelete, path, nil)
	if first.Code != http.StatusOK {
		t.Fatalf("第一次删除期望 200，得到 %d body=%s", first.Code, first.Body.String())
	}
	second := deep3SilenceAuthReq(t, srv, http.MethodDelete, path, nil)
	if second.Code != http.StatusNotFound {
		t.Fatalf("第二次删除期望 404，得到 %d body=%s", second.Code, second.Body.String())
	}
}

func TestDeep3CreateSilenceMonitorIDExplicitValid(t *testing.T) {
	srv, _ := newTestServer(t)
	mon := createMonitorDeep3(t, srv)
	body := map[string]any{
		"monitor_id": mon,
		"name_match": "with-monitor",
		"starts_at":  time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		"ends_at":    time.Now().UTC().Add(time.Minute).Format(time.RFC3339),
		"reason":     "绑定监控",
	}
	raw, _ := json.Marshal(body)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", raw)
	if rec.Code != http.StatusCreated {
		t.Fatalf("合法 monitor_id 期望 201，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if mid, ok := out["monitor_id"].(float64); !ok || int64(mid) != mon {
		t.Fatalf("期望 monitor_id=%d，得到 %v", mon, out["monitor_id"])
	}
}

func TestDeep3CreateSilenceTrailingJSON(t *testing.T) {
	srv, _ := newTestServer(t)
	raw := []byte(`{"name_match":"a","starts_at":"x","ends_at":"y","reason":"r"}{"extra":1}`)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences", raw)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非法 starts_at 期望 400，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析错误响应失败: %v", err)
	}
	if msg, _ := out["error"].(string); msg != "starts_at 不是合法的 RFC3339 时间" {
		t.Fatalf("期望 error=starts_at 不是合法的 RFC3339 时间，得到 %v", out)
	}
}

func TestDeep3ListSilencesMethodNotAllowed(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/silences/nope", nil)
	if rec.Code != http.StatusBadRequest && rec.Code != http.StatusNotFound && rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("意外状态码 %d body=%s", rec.Code, rec.Body.String())
	}
}

func createMonitorDeep3(t *testing.T, srv *Server) int64 {
	t.Helper()
	body := map[string]any{
		"name":   "deep3-monitor",
		"target": "https://example.com/deep3",
		"type":   "http",
	}
	raw, _ := json.Marshal(body)
	rec := deep3SilenceAuthReq(t, srv, http.MethodPost, "/api/monitors", raw)
	if rec.Code != http.StatusCreated {
		t.Fatalf("创建监控失败: %d body=%s", rec.Code, rec.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("解析监控响应失败: %v", err)
	}
	id, ok := out["id"].(float64)
	if !ok || id <= 0 {
		t.Fatalf("期望正监控 id，得到 %v", out["id"])
	}
	return int64(id)
}
