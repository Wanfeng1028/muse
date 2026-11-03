package handlers

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"sentinel/internal/store"
)

func helpPublishPage(t *testing.T, srv *Server, st *store.Store) (int64, int64, int64) {
	t.Helper()
	raw := strings.ToLower(t.Name())
	var b strings.Builder
	for _, r := range raw {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-' {
			b.WriteRune(r)
		} else {
			b.WriteRune('-')
		}
	}
	slug := "pg-" + b.String()
	pageID, err := st.CreateStatusPage(1, slug, "服务状态页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	m1, err := st.CreateMonitor(store.Monitor{Name: "alpha-monitor", Target: "https://a.example.com", Kind: "http"})
	if err != nil {
		t.Fatalf("创建 monitor m1 失败: %v", err)
	}
	m2, err := st.CreateMonitor(store.Monitor{Name: "beta-monitor", Target: "https://b.example.com", Kind: "http"})
	if err != nil {
		t.Fatalf("创建 monitor m2 失败: %v", err)
	}
	if err := st.AddMonitorToPage(pageID, m1); err != nil {
		t.Fatalf("关联 m1 失败: %v", err)
	}
	if err := st.AddMonitorToPage(pageID, m2); err != nil {
		t.Fatalf("关联 m2 失败: %v", err)
	}
	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := st.InsertCheck(store.Check{MonitorID: m1, CheckedAt: now, Ok: 1, LatencyMs: 42}); err != nil {
		t.Fatalf("插入 m1 检查失败: %v", err)
	}
	if _, err := st.InsertCheck(store.Check{MonitorID: m2, CheckedAt: now, Ok: 0, LatencyMs: 12}); err != nil {
		t.Fatalf("插入 m2 检查失败: %v", err)
	}
	return pageID, m1, m2
}

type publishResp struct {
	Slug         string `json:"slug"`
	Version      string `json:"version"`
	Path         string `json:"path"`
	MonitorCount int    `json:"monitor_count"`
}

func doPublish(t *testing.T, srv *Server, pageID int64) (*httptest.ResponseRecorder, publishResp) {
	t.Helper()
	req := newReq(http.MethodPost, "/api/status-pages/"+itoaPub(pageID)+"/publish", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	var pr publishResp
	if rec.Code == http.StatusOK {
		if err := json.Unmarshal(rec.Body.Bytes(), &pr); err != nil {
			t.Fatalf("解析 publish 响应失败: %v", err)
		}
	}
	return rec, pr
}

func itoaPub(v int64) string {
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	var buf [20]byte
	i := len(buf)
	for v > 0 {
		i--
		buf[i] = byte('0' + v%10)
		v /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

func readFileStr(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取文件 %s 失败: %v", path, err)
	}
	return string(data)
}

func TestPublishStatusPage_E2E(t *testing.T) {
	srv, st := newTestServer(t)
	dir := t.TempDir()
	srv.SetPublishDir(dir)
	pageID, _, _ := helpPublishPage(t, srv, st)

	rec, pr := doPublish(t, srv, pageID)
	if rec.Code != http.StatusOK {
		t.Fatalf("publish 期望 200，实际 %d，body=%s", rec.Code, rec.Body.String())
	}
	if pr.Version == "" {
		t.Fatalf("version 不应为空")
	}
	if pr.Slug == "" || !strings.HasPrefix(pr.Slug, "pg-") {
		t.Fatalf("slug 不正确: %q", pr.Slug)
	}
	if pr.MonitorCount != 2 {
		t.Fatalf("monitor_count 期望 2，实际 %d", pr.MonitorCount)
	}
	if fi, err := os.Stat(pr.Path); err != nil || !fi.IsDir() {
		t.Fatalf("发布目录不存在或不是目录: %s, err=%v", pr.Path, err)
	}

	index := readFileStr(t, filepath.Join(pr.Path, "index.html"))
	if !strings.Contains(index, "alpha-monitor") || !strings.Contains(index, "beta-monitor") {
		t.Fatalf("index.html 未包含两个 monitor 名")
	}
	if !strings.Contains(index, "30 天可用性") {
		t.Fatalf("index.html 未包含可用性文案")
	}
	if !strings.Contains(index, "服务状态页") {
		t.Fatalf("index.html 未包含页面标题")
	}

	manifest := readFileStr(t, filepath.Join(pr.Path, "manifest.json"))
	var mf map[string]any
	if err := json.Unmarshal([]byte(manifest), &mf); err != nil {
		t.Fatalf("解析 manifest.json 失败: %v", err)
	}
	if v, _ := mf["version"].(string); v != pr.Version {
		t.Fatalf("manifest version 期望 %q，实际 %v", pr.Version, mf["version"])
	}
}

func TestPublishStatusPage_IncrementalUpdate(t *testing.T) {
	srv, st := newTestServer(t)
	dir := t.TempDir()
	srv.SetPublishDir(dir)
	pageID, m1, _ := helpPublishPage(t, srv, st)

	rec, v1 := doPublish(t, srv, pageID)
	if rec.Code != http.StatusOK {
		t.Fatalf("第一次 publish 期望 200，实际 %d", rec.Code)
	}

	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := st.InsertCheck(store.Check{MonitorID: m1, CheckedAt: now, Ok: 0, LatencyMs: 50}); err != nil {
		t.Fatalf("插入 m1 新检查失败: %v", err)
	}
	time.Sleep(1100 * time.Millisecond)

	rec2, v2 := doPublish(t, srv, pageID)
	if rec2.Code != http.StatusOK {
		t.Fatalf("第二次 publish 期望 200，实际 %d", rec2.Code)
	}
	if v2.Version == v1.Version {
		t.Fatalf("第二次 version 应与第一次不同: %q", v2.Version)
	}

	index := readFileStr(t, filepath.Join(v2.Path, "index.html"))
	if !strings.Contains(index, "故障") {
		t.Fatalf("新 index.html 未包含故障文案")
	}

	histDir := filepath.Join(v2.Path, "history")
	entries, err := os.ReadDir(histDir)
	if err != nil {
		t.Fatalf("读取 history 目录失败: %v", err)
	}
	count := 0
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), "index-") && strings.HasSuffix(e.Name(), ".html") {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("history 下归档文件期望 1 个，实际 %d", count)
	}
}

func TestPublishStatusPage_Rollback(t *testing.T) {
	srv, st := newTestServer(t)
	dir := t.TempDir()
	srv.SetPublishDir(dir)
	pageID, _, m2 := helpPublishPage(t, srv, st)

	rec, v1 := doPublish(t, srv, pageID)
	if rec.Code != http.StatusOK {
		t.Fatalf("第一次 publish 期望 200，实际 %d", rec.Code)
	}
	v1Index := readFileStr(t, filepath.Join(v1.Path, "index.html"))

	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := st.InsertCheck(store.Check{MonitorID: m2, CheckedAt: now, Ok: 1, LatencyMs: 8}); err != nil {
		t.Fatalf("插入 m2 新检查失败: %v", err)
	}
	time.Sleep(1100 * time.Millisecond)

	rec2, v2 := doPublish(t, srv, pageID)
	if rec2.Code != http.StatusOK {
		t.Fatalf("第二次 publish 期望 200，实际 %d", rec2.Code)
	}
	if v2.Version == v1.Version {
		t.Fatalf("第二次 version 应与第一次不同")
	}

	req := newReq(http.MethodPost, "/api/status-pages/"+itoaPub(pageID)+"/publish/rollback", nil)
	rrec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rrec, req)
	if rrec.Code != http.StatusOK {
		t.Fatalf("rollback 期望 200，实际 %d，body=%s", rrec.Code, rrec.Body.String())
	}
	var rb struct {
		Slug            string `json:"slug"`
		RestoredVersion string `json:"restored_version"`
	}
	if err := json.Unmarshal(rrec.Body.Bytes(), &rb); err != nil {
		t.Fatalf("解析 rollback 响应失败: %v", err)
	}
	if rb.RestoredVersion != v1.Version {
		t.Fatalf("restored_version 期望 %q，实际 %q", v1.Version, rb.RestoredVersion)
	}

	after := readFileStr(t, filepath.Join(v2.Path, "index.html"))
	if after != v1Index {
		t.Fatalf("rollback 后 index.html 内容应与 v1 一致")
	}
	manifest := readFileStr(t, filepath.Join(v2.Path, "manifest.json"))
	var mf map[string]any
	if err := json.Unmarshal([]byte(manifest), &mf); err != nil {
		t.Fatalf("解析 manifest.json 失败: %v", err)
	}
	vstr, _ := mf["version"].(string)
	if !strings.HasSuffix(vstr, "-rollback") {
		t.Fatalf("manifest version 期望以 -rollback 结尾，实际 %q", vstr)
	}
}

func TestPublishStatusPage_PublishFailure(t *testing.T) {
	srv, st := newTestServer(t)
	dir := t.TempDir()
	srv.SetPublishDir(dir)
	pageID, _, _ := helpPublishPage(t, srv, st)

	rec, v1 := doPublish(t, srv, pageID)
	if rec.Code != http.StatusOK {
		t.Fatalf("首次 publish 期望 200，实际 %d", rec.Code)
	}
	orig := readFileStr(t, filepath.Join(v1.Path, "index.html"))

	bad := filepath.Join(dir, "index.html")
	if err := os.WriteFile(bad, []byte("occupied"), 0o644); err != nil {
		t.Fatalf("写入占用文件失败: %v", err)
	}
	srv.SetPublishDir(bad)

	rec2, _ := doPublish(t, srv, pageID)
	if rec2.Code != http.StatusInternalServerError {
		t.Fatalf("失败场景期望 500，实际 %d，body=%s", rec2.Code, rec2.Body.String())
	}

	after := readFileStr(t, filepath.Join(v1.Path, "index.html"))
	if after != orig {
		t.Fatalf("发布失败后旧 index.html 不应被修改")
	}
}

func TestPublishInfo(t *testing.T) {
	srv, st := newTestServer(t)
	dir := t.TempDir()
	srv.SetPublishDir(dir)
	pageID, _, _ := helpPublishPage(t, srv, st)

	req := newReq(http.MethodGet, "/api/status-pages/"+itoaPub(pageID)+"/publish", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("GET publish 期望 200，实际 %d", rec.Code)
	}
	var info struct {
		Published bool   `json:"published"`
		Version   string `json:"version"`
	}
	body, _ := io.ReadAll(rec.Body)
	if err := json.Unmarshal(body, &info); err != nil {
		t.Fatalf("解析 GET publish 响应失败: %v", err)
	}
	if info.Published {
		t.Fatalf("发布前 published 应为 false")
	}

	rec2, pr := doPublish(t, srv, pageID)
	if rec2.Code != http.StatusOK {
		t.Fatalf("publish 期望 200，实际 %d", rec2.Code)
	}

	req2 := newReq(http.MethodGet, "/api/status-pages/"+itoaPub(pageID)+"/publish", nil)
	rec3 := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec3, req2)
	if rec3.Code != http.StatusOK {
		t.Fatalf("再次 GET publish 期望 200，实际 %d", rec3.Code)
	}
	var info2 struct {
		Published bool   `json:"published"`
		Version   string `json:"version"`
	}
	if err := json.Unmarshal(rec3.Body.Bytes(), &info2); err != nil {
		t.Fatalf("解析再次 GET publish 响应失败: %v", err)
	}
	if !info2.Published {
		t.Fatalf("发布后 published 应为 true")
	}
	if info2.Version == "" {
		t.Fatalf("发布后 version 不应为空")
	}
	if pr.Version == "" {
		t.Fatalf("publish 返回 version 不应为空")
	}
}
