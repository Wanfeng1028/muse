package handlers

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSnapshotArchiveFullCycle(t *testing.T) {
	srv, st := newTestServer(t)

	pageID, err := st.CreateStatusPage(1, "snap-arch-page", "归档测试页")
	if err != nil {
		t.Fatalf("创建状态页面失败: %v", err)
	}

	// POST 生成快照
	genPath := fmt.Sprintf("/api/status-pages/%d/snapshots", pageID)
	req := newReq(http.MethodPost, genPath, nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("期望 POST 生成快照返回 201，实际返回 %d", rec.Code)
	}
	var genResult map[string]any
	if err := json.NewDecoder(rec.Body).Decode(&genResult); err != nil {
		t.Fatalf("解析生成快照响应 JSON 失败: %v", err)
	}
	snapID := genResult["id"]
	if snapID == nil || jsonNumberToFloat(snapID) <= 0 {
		t.Fatalf("期望生成快照 id > 0，实际得到 %v", snapID)
	}
	sizeBytes := genResult["size_bytes"]
	if sizeBytes == nil || jsonNumberToFloat(sizeBytes) <= 0 {
		t.Fatalf("期望 size_bytes > 0，实际得到 %v", sizeBytes)
	}

	// GET 列表
	listPath := fmt.Sprintf("/api/status-pages/%d/snapshots", pageID)
	req = newReq(http.MethodGet, listPath, nil)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 GET 快照列表返回 200，实际返回 %d", rec.Code)
	}
	var listResult map[string]any
	if err := json.NewDecoder(rec.Body).Decode(&listResult); err != nil {
		t.Fatalf("解析快照列表响应 JSON 失败: %v", err)
	}
	total := jsonNumberToFloat(listResult["total"])
	if total != 1 {
		t.Fatalf("期望列表 total == 1，实际为 %v", total)
	}
	items, ok := listResult["items"].([]any)
	if !ok || len(items) != 1 {
		t.Fatalf("期望 items 长度为 1，实际为 %v", items)
	}
	firstItem, ok := items[0].(map[string]any)
	if !ok {
		t.Fatalf("期望 items[0] 为对象，实际类型不符合")
	}
	if firstItem["id"] != snapID {
		t.Fatalf("期望 items[0].id 等于生成 id %v，实际为 %v", snapID, firstItem["id"])
	}
	if _, hasHTML := firstItem["html"]; hasHTML {
		t.Fatalf("期望列表 JSON 中不含 html 键，但实际存在")
	}

	// GET 单个下载
	downloadPath := fmt.Sprintf("/api/status-pages/%d/snapshots/%v", pageID, snapID)
	req = newReq(http.MethodGet, downloadPath, nil)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 GET 单个快照下载返回 200，实际返回 %d", rec.Code)
	}
	ct := rec.Header().Get("Content-Type")
	if !strings.Contains(ct, "text/html") {
		t.Fatalf("期望 Content-Type 含 text/html，实际为 %s", ct)
	}
	cd := rec.Header().Get("Content-Disposition")
	if !strings.Contains(cd, "attachment") {
		t.Fatalf("期望 Content-Disposition 含 attachment，实际为 %s", cd)
	}
	bodyBytes, _ := io.ReadAll(rec.Body)
	if !strings.Contains(string(bodyBytes), "<html") {
		t.Fatalf("期望下载体含 <html，实际体前 200 字符: %s", truncateString(string(bodyBytes), 200))
	}

	// DELETE 删除
	delPath := fmt.Sprintf("/api/status-pages/%d/snapshots/%v", pageID, snapID)
	req = newReq(http.MethodDelete, delPath, nil)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("期望 DELETE 快照返回 204，实际返回 %d", rec.Code)
	}

	// GET 列表确认 total==0
	req = newReq(http.MethodGet, listPath, nil)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望删除后 GET 列表返回 200，实际返回 %d", rec.Code)
	}
	if err := json.NewDecoder(rec.Body).Decode(&listResult); err != nil {
		t.Fatalf("解析删除后列表响应 JSON 失败: %v", err)
	}
	total = jsonNumberToFloat(listResult["total"])
	if total != 0 {
		t.Fatalf("期望删除后列表 total == 0，实际为 %v", total)
	}
}

func TestSnapshotArchivePageNotFound(t *testing.T) {
	srv, _ := newTestServer(t)

	fakePageID := 999999

	// POST 生成快照 → 404
	genPath := fmt.Sprintf("/api/status-pages/%d/snapshots", fakePageID)
	req := newReq(http.MethodPost, genPath, nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("期望对不存在页面 POST 生成快照返回 404，实际返回 %d", rec.Code)
	}

	// GET 列表 → 404
	listPath := fmt.Sprintf("/api/status-pages/%d/snapshots", fakePageID)
	req = newReq(http.MethodGet, listPath, nil)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("期望对不存在页面 GET 快照列表返回 404，实际返回 %d", rec.Code)
	}
}

func TestSnapshotArchiveCrossPageIsolation(t *testing.T) {
	srv, st := newTestServer(t)

	pageA, err := st.CreateStatusPage(1, "page-a", "页面A")
	if err != nil {
		t.Fatalf("创建页面A失败: %v", err)
	}
	pageB, err := st.CreateStatusPage(1, "page-b", "页面B")
	if err != nil {
		t.Fatalf("创建页面B失败: %v", err)
	}

	// 给 A 生成快照
	genPathA := fmt.Sprintf("/api/status-pages/%d/snapshots", pageA)
	req := newReq(http.MethodPost, genPathA, nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("期望为页面A生成快照返回 201，实际返回 %d", rec.Code)
	}
	var genResult map[string]any
	if err := json.NewDecoder(rec.Body).Decode(&genResult); err != nil {
		t.Fatalf("解析生成快照响应 JSON 失败: %v", err)
	}
	snapID := genResult["id"]

	// 在 B 的路径下 GET 该快照 → 404
	downloadPathB := fmt.Sprintf("/api/status-pages/%d/snapshots/%v", pageB, snapID)
	req = newReq(http.MethodGet, downloadPathB, nil)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("期望跨页 GET 快照返回 404，实际返回 %d", rec.Code)
	}

	// 在 B 的路径下 DELETE 该快照 → 404
	delPathB := fmt.Sprintf("/api/status-pages/%d/snapshots/%v", pageB, snapID)
	req = newReq(http.MethodDelete, delPathB, nil)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("期望跨页 DELETE 快照返回 404，实际返回 %d", rec.Code)
	}
}

func TestSnapshotScheduleUpdate(t *testing.T) {
	srv, st := newTestServer(t)

	pageID, err := st.CreateStatusPage(1, "snap-sched-page", "调度测试页")
	if err != nil {
		t.Fatalf("创建状态页面失败: %v", err)
	}

	schedPath := fmt.Sprintf("/api/status-pages/%d/snapshot-schedule", pageID)

	// PUT daily → 200
	body := bytes.NewBufferString(`{"schedule":"daily"}`)
	req := newReq(http.MethodPut, schedPath, body)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 PUT schedule=daily 返回 200，实际返回 %d", rec.Code)
	}
	var result map[string]any
	if err := json.NewDecoder(rec.Body).Decode(&result); err != nil {
		t.Fatalf("解析调度响应 JSON 失败: %v", err)
	}
	if result["snapshot_schedule"] != "daily" {
		t.Fatalf("期望 snapshot_schedule == daily，实际为 %v", result["snapshot_schedule"])
	}

	// PUT hourly → 200
	body = bytes.NewBufferString(`{"schedule":"hourly"}`)
	req = newReq(http.MethodPut, schedPath, body)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 PUT schedule=hourly 返回 200，实际返回 %d", rec.Code)
	}

	// PUT bogus → 400
	body = bytes.NewBufferString(`{"schedule":"bogus"}`)
	req = newReq(http.MethodPut, schedPath, body)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望 PUT schedule=bogus 返回 400，实际返回 %d", rec.Code)
	}

	// PUT 非法 JSON → 400
	body = bytes.NewBufferString(`{bad`)
	req = newReq(http.MethodPut, schedPath, body)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("期望 PUT 非法 JSON 返回 400，实际返回 %d", rec.Code)
	}
}

func TestSnapshotDownloadNotFound(t *testing.T) {
	srv, st := newTestServer(t)

	pageID, err := st.CreateStatusPage(1, "snap-dl-404-page", "下载404测试页")
	if err != nil {
		t.Fatalf("创建状态页面失败: %v", err)
	}

	downloadPath := fmt.Sprintf("/api/status-pages/%d/snapshots/999999", pageID)
	req := newReq(http.MethodGet, downloadPath, nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("期望下载不存在快照返回 404，实际返回 %d", rec.Code)
	}
}

func TestSnapshotListLimit(t *testing.T) {
	srv, st := newTestServer(t)

	pageID, err := st.CreateStatusPage(1, "snap-limit-page", "限制测试页")
	if err != nil {
		t.Fatalf("创建状态页面失败: %v", err)
	}

	genPath := fmt.Sprintf("/api/status-pages/%d/snapshots", pageID)

	// 生成 3 条快照
	for i := 0; i < 3; i++ {
		req := newReq(http.MethodPost, genPath, nil)
		rec := httptest.NewRecorder()
		srv.Routes().ServeHTTP(rec, req)
		if rec.Code != http.StatusCreated {
			t.Fatalf("期望第 %d 次生成快照返回 201，实际返回 %d", i+1, rec.Code)
		}
	}

	// GET 列表 limit=2
	listPath := fmt.Sprintf("/api/status-pages/%d/snapshots?limit=2", pageID)
	req := newReq(http.MethodGet, listPath, nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 GET 快照列表 limit=2 返回 200，实际返回 %d", rec.Code)
	}
	var listResult map[string]any
	if err := json.NewDecoder(rec.Body).Decode(&listResult); err != nil {
		t.Fatalf("解析快照列表响应 JSON 失败: %v", err)
	}
	items, ok := listResult["items"].([]any)
	if !ok || len(items) != 2 {
		t.Fatalf("期望 items 长度为 2，实际为 %v", items)
	}
}

func TestGenerateAndStoreSnapshotContent(t *testing.T) {
	srv, st := newTestServer(t)

	pageID, err := st.CreateStatusPage(1, "snap-content-page", "归档测试页")
	if err != nil {
		t.Fatalf("创建状态页面失败: %v", err)
	}

	snapID, err := srv.GenerateAndStoreSnapshot(pageID, "manual")
	if err != nil {
		t.Fatalf("期望 GenerateAndStoreSnapshot 无错，实际出错: %v", err)
	}
	if snapID <= 0 {
		t.Fatalf("期望返回 id > 0，实际为 %d", snapID)
	}

	snap, err := st.GetStatusSnapshot(snapID)
	if err != nil {
		t.Fatalf("期望 GetStatusSnapshot 无错，实际出错: %v", err)
	}
	if !strings.Contains(snap.HTML, "归档测试页") {
		t.Fatalf("期望快照 HTML 含页面标题 归档测试页，实际 HTML 前 300 字符: %s", truncateString(snap.HTML, 300))
	}
	if snap.Generator != "manual" {
		t.Fatalf("期望 Generator == manual，实际为 %s", snap.Generator)
	}
}

func jsonNumberToFloat(v any) float64 {
	switch n := v.(type) {
	case json.Number:
		f, _ := n.Float64()
		return f
	case float64:
		return n
	case int:
		return float64(n)
	case int64:
		return float64(n)
	default:
		return -1
	}
}

func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen]
}
