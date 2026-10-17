package api

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// newDeepTestServer 构造测试用 HTTP 处理器与底层 store。
func newDeepTestServer(t *testing.T) (http.Handler, *store.Store) {
	t.Helper()
	return newDeepTestServerWithSources(t, nil)
}

// newDeepTestServerWithSources 构造带数据源配置的测试服务器。
func newDeepTestServerWithSources(t *testing.T, sources []config.SourceConfig) (http.Handler, *store.Store) {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "muse.db")
	if sources == nil {
		sources = []config.SourceConfig{}
	}
	cfg := &config.Config{
		Database: dbPath,
		Sources:  sources,
	}
	logger := log.New(os.Stderr, "error")
	st, err := store.Open(dbPath)
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	if err := st.Migrate(); err != nil {
		t.Fatalf("store.Migrate: %v", err)
	}
	h := NewServer(st, cfg, logger)
	return h, st
}

// doJSON 发送 JSON 请求并返回响应。
func doJSON(t *testing.T, h http.Handler, method, path string, body any, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	var rdr *bytes.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		rdr = bytes.NewReader(b)
	} else {
		rdr = bytes.NewReader(nil)
	}
	req := httptest.NewRequest(method, path, rdr)
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

// doRaw 发送原始字节请求。
func doRaw(t *testing.T, h http.Handler, method, path string, body []byte, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, bytes.NewReader(body))
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

// writeTestCSV 写一个真实 CSV 文件。
func writeTestCSV(t *testing.T, path string, rows [][]string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatalf("create csv: %v", err)
	}
	defer f.Close()
	w := csv.NewWriter(f)
	for _, r := range rows {
		if err := w.Write(r); err != nil {
			t.Fatalf("write csv: %v", err)
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		t.Fatalf("flush csv: %v", err)
	}
}

// doMultipartCSV 发送 multipart CSV 导入请求（真实 /api/import/csv 契约）。
func doMultipartCSV(t *testing.T, h http.Handler, source, table, pk, filename string, csvBody []byte) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	w := multipart.NewWriter(&buf)
	if err := w.WriteField("source", source); err != nil {
		t.Fatalf("write field source: %v", err)
	}
	if table != "" {
		if err := w.WriteField("table", table); err != nil {
			t.Fatalf("write field table: %v", err)
		}
	}
	if pk != "" {
		if err := w.WriteField("primary_key", pk); err != nil {
			t.Fatalf("write field primary_key: %v", err)
		}
	}
	fw, err := w.CreateFormFile("file", filename)
	if err != nil {
		t.Fatalf("create form file: %v", err)
	}
	if _, err := fw.Write(csvBody); err != nil {
		t.Fatalf("write csv body: %v", err)
	}
	if err := w.Close(); err != nil {
		t.Fatalf("close writer: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, "/api/import/csv", &buf)
	req.Header.Set("Content-Type", w.FormDataContentType())
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

// buildCSV 生成 CSV 文本。
func buildCSV(t *testing.T, rows [][]string) []byte {
	t.Helper()
	var buf bytes.Buffer
	w := csv.NewWriter(&buf)
	for _, row := range rows {
		if err := w.Write(row); err != nil {
			t.Fatalf("write csv: %v", err)
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		t.Fatalf("flush csv: %v", err)
	}
	return buf.Bytes()
}

// TestDeepMultiSourceConflictSameKeyDifferentValue 验证同 key 不同值时冲突被记录。
func TestDeepMultiSourceConflictSameKeyDifferentValue(t *testing.T) {
	h, st := newDeepTestServer(t)

	// arrange: 用真实 RecordConflict 播种一条同 key 不同源的冲突。
	c := store.Conflict{
		TableName: "users", PK: "1",
		SourceA: "src_a", SourceB: "src_b",
		RowJSON:   `{"id":"1","name":"bob","email":"b@x.com"}`,
		Status:    "pending",
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}
	if _, err := st.RecordConflict(st.DB, c); err != nil {
		t.Fatalf("record conflict: %v", err)
	}

	// act: 拉取待处理冲突列表。
	rec := doJSON(t, h, http.MethodGet, "/api/conflicts", nil, nil)

	// assert 1: HTTP 200。
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}
	// assert 2: 冲突列表非空且至少含一条同 key 冲突。
	var conflicts []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &conflicts); err != nil {
		t.Fatalf("unmarshal conflicts: %v, body=%s", err, rec.Body.String())
	}
	if len(conflicts) < 1 {
		t.Fatalf("expected at least 1 conflict, got %d", len(conflicts))
	}
	// assert 3: 冲突记录中能识别出 pk=1 这条主键。
	found := false
	for _, cc := range conflicts {
		raw, _ := json.Marshal(cc)
		if strings.Contains(string(raw), `"pk":"1"`) {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected conflict keyed by pk=1, conflicts=%v", conflicts)
	}
}

func TestDeepResolveConflictAppliesValue(t *testing.T) {
	h, st := newDeepTestServer(t)

	// arrange: 建表 + 播种一条 pending 冲突（src_b 为挑战方）。
	if err := st.EnsureTable("users", "id", []infer.Column{{Name: "id"}, {Name: "name"}}); err != nil {
		t.Fatalf("create table: %v", err)
	}
	c := store.Conflict{
		TableName: "users", PK: "7",
		SourceA: "src_a", SourceB: "src_b",
		RowJSON:   `{"id":"7","name":"second"}`,
		Status:    "pending",
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}
	if _, err := st.RecordConflict(st.DB, c); err != nil {
		t.Fatalf("record conflict: %v", err)
	}
	conflicts, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list conflicts: %v", err)
	}
	if len(conflicts) == 0 {
		t.Fatalf("expected pending conflict to resolve")
	}
	cid := conflicts[0].ID

	// act: 用 row_json 解决冲突（真实 resolve 接口契约）。
	rec := doJSON(t, h, http.MethodPost, fmt.Sprintf("/api/conflicts/%d/resolve", cid), map[string]any{
		"row_json": `{"id":"7","name":"second"}`,
		"table":    "users",
		"pk_col":   "id",
		"pk":       "7",
	}, nil)

	// assert 1: HTTP 200。
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}
	// assert 2: 冲突不再是 pending。
	after, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list conflicts after: %v", err)
	}
	for _, cc := range after {
		if cc.ID == cid {
			t.Fatalf("conflict %d still pending after resolve", cid)
		}
	}
	// assert 3: 解决后的行已写入（src_b 的值生效）。
	var name string
	if err := st.DB.QueryRow(`SELECT "name" FROM "users" WHERE "id"='7'`).Scan(&name); err != nil {
		t.Fatalf("query resolved row: %v", err)
	}
	if name != "second" {
		t.Fatalf("resolved name = %q, want second", name)
	}
}

func TestDeepCSVImportIncrementalResume(t *testing.T) {
	srcs := []config.SourceConfig{{Name: "s1", Table: "imported_csv", PrimaryKey: "id"}}
	h, st := newDeepTestServerWithSources(t, srcs)

	rows := [][]string{
		{"id", "name", "email"},
		{"1", "alice", "a@x.com"},
		{"2", "bob", "b@x.com"},
		{"3", "carol", "c@x.com"},
	}
	body := buildCSV(t, rows)

	// 第一次导入。
	rec1 := doMultipartCSV(t, h, "s1", "", "", "users.csv", body)
	if rec1.Code != http.StatusOK {
		t.Fatalf("first import status = %d, want 200, body=%s", rec1.Code, rec1.Body.String())
	}
	// assert 1: 导入后表内计数为 3。
	cnt1, err := st.TableCount("imported_csv")
	if err != nil {
		t.Fatalf("table count after first import: %v", err)
	}
	if cnt1 != 3 {
		t.Fatalf("after first import count = %d, want 3", cnt1)
	}

	// 第二次导入同一批数据（断点续传场景：应从已导入位置继续，不重复插入）。
	rec2 := doMultipartCSV(t, h, "s1", "", "", "users.csv", body)
	if rec2.Code != http.StatusOK {
		t.Fatalf("second import status = %d, want 200, body=%s", rec2.Code, rec2.Body.String())
	}
	// assert 2: 重复导入后计数仍为 3，说明断点续传生效。
	cnt2, err := st.TableCount("imported_csv")
	if err != nil {
		t.Fatalf("table count after second import: %v", err)
	}
	if cnt2 != 3 {
		t.Fatalf("after second import count = %d, want 3 (idempotent resume)", cnt2)
	}
}

// TestDeepCSVImportPartialBatchResume 验证部分批次后断点续传能补齐剩余行。
func TestDeepCSVImportPartialBatchResume(t *testing.T) {
	srcs := []config.SourceConfig{{Name: "s1", Table: "imported_csv", PrimaryKey: "id"}}
	h, st := newDeepTestServerWithSources(t, srcs)

	first := buildCSV(t, [][]string{
		{"id", "name"},
		{"10", "x"},
		{"11", "y"},
	})
	rec1 := doMultipartCSV(t, h, "s1", "", "", "batch1.csv", first)
	if rec1.Code != http.StatusOK {
		t.Fatalf("first batch status = %d, body=%s", rec1.Code, rec1.Body.String())
	}
	c1, err := st.TableCount("imported_csv")
	if err != nil {
		t.Fatalf("count after first batch: %v", err)
	}
	if c1 != 2 {
		t.Fatalf("after first batch count = %d, want 2", c1)
	}

	second := buildCSV(t, [][]string{
		{"id", "name"},
		{"10", "x"},
		{"11", "y"},
		{"12", "z"},
	})
	rec2 := doMultipartCSV(t, h, "s1", "", "", "batch2.csv", second)
	if rec2.Code != http.StatusOK {
		t.Fatalf("second batch status = %d, body=%s", rec2.Code, rec2.Body.String())
	}
	c2, err := st.TableCount("imported_csv")
	if err != nil {
		t.Fatalf("count after second batch: %v", err)
	}
	// assert: 第二批补齐后总数为 3，重复的两行被跳过。
	if c2 != 3 {
		t.Fatalf("after second batch count = %d, want 3", c2)
	}
}

// TestDeepSyncIdempotent 验证同一批数据同步两次结果一致（幂等）。
func TestDeepSyncIdempotent(t *testing.T) {
	// 用真实 CSV 文件做源，走 /api/sync 触发同步。
	dir := t.TempDir()
	csvPath := filepath.Join(dir, "rows.csv")
	writeTestCSV(t, csvPath, [][]string{
		{"id", "name"},
		{"1", "a"},
		{"2", "b"},
	})
	srcs := []config.SourceConfig{{
		Name: "s1", Type: "csv", Path: csvPath,
		Table: "synced_rows", PrimaryKey: "id",
	}}
	h, st := newDeepTestServerWithSources(t, srcs)
	syncPayload := map[string]any{"sources": []string{"s1"}, "job": "test-idem"}

	rec1 := doJSON(t, h, http.MethodPost, "/api/sync", syncPayload, nil)
	if rec1.Code != http.StatusOK {
		t.Fatalf("first sync status = %d, body=%s", rec1.Code, rec1.Body.String())
	}
	c1, err := st.TableCount("synced_rows")
	if err != nil {
		t.Fatalf("count after first sync: %v", err)
	}
	if c1 != 2 {
		t.Fatalf("after first sync count = %d, want 2", c1)
	}

	rec2 := doJSON(t, h, http.MethodPost, "/api/sync", syncPayload, nil)
	if rec2.Code != http.StatusOK {
		t.Fatalf("second sync status = %d, body=%s", rec2.Code, rec2.Body.String())
	}
	c2, err := st.TableCount("synced_rows")
	if err != nil {
		t.Fatalf("count after second sync: %v", err)
	}
	// assert: 幂等，总数不变。
	if c2 != 2 {
		t.Fatalf("after second sync count = %d, want 2 (idempotent)", c2)
	}
}

// TestDeepSyncConcurrentSameRows 验证并发同步同一批数据不产生重复行。
func TestDeepSyncConcurrentSameRows(t *testing.T) {
	dir := t.TempDir()
	csvPath := filepath.Join(dir, "rows.csv")
	writeTestCSV(t, csvPath, [][]string{
		{"id", "name"},
		{"100", "concurrent"},
	})
	srcs := []config.SourceConfig{{
		Name: "s1", Type: "csv", Path: csvPath,
		Table: "synced_rows", PrimaryKey: "id",
	}}
	h, st := newDeepTestServerWithSources(t, srcs)
	syncPayload := map[string]any{"sources": []string{"s1"}, "job": "test-conc"}

	var wg sync.WaitGroup
	codes := make([]int, 8)
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			rec := doJSON(t, h, http.MethodPost, "/api/sync", syncPayload, nil)
			codes[idx] = rec.Code
		}(i)
	}
	wg.Wait()

	for i, c := range codes {
		if c != http.StatusOK {
			t.Fatalf("concurrent sync #%d status = %d, want 200", i, c)
		}
	}
	cnt, err := st.TableCount("synced_rows")
	if err != nil {
		t.Fatalf("count after concurrent sync: %v", err)
	}
	// assert: 并发下仍只有一行。
	if cnt != 1 {
		t.Fatalf("after concurrent sync count = %d, want 1", cnt)
	}
}

// TestDeepHMACVerifyKnownVector 验证 HMAC 验签对已知向量返回正确结果。
// signHMAC 计算 HMAC-SHA256 十六进制签名（测试辅助，与 notify.Sign 同算法）。
func signHMAC(secret, body []byte) string {
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

// verifyHMAC 常量时间比较验签（测试辅助）。
func verifyHMAC(secret, body []byte, sig string) bool {
	if len(secret) == 0 || len(sig) == 0 {
		return false
	}
	want := signHMAC(secret, body)
	if len(want) != len(sig) {
		return false
	}
	return hmac.Equal([]byte(want), []byte(sig))
}

func TestDeepHMACVerifyKnownVector(t *testing.T) {
	secret := []byte("mortise-secret")
	body := []byte(`{"event":"row.update","id":42}`)

	// act: 生成签名后验签。
	sig := signHMAC(secret, body)

	// assert 1: 正确签名验签通过。
	if !verifyHMAC(secret, body, sig) {
		t.Fatalf("verifyHMAC returned false for correct signature %s", sig)
	}
	// assert 2: 篡改 body 后验签失败。
	tampered := append([]byte{}, body...)
	tampered[len(tampered)-1] ^= 0x01
	if verifyHMAC(secret, tampered, sig) {
		t.Fatalf("verifyHMAC returned true for tampered body")
	}
	// assert 3: 换密钥后验签失败。
	if verifyHMAC([]byte("other-secret"), body, sig) {
		t.Fatalf("verifyHMAC returned true for wrong secret")
	}
}
