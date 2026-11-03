package handler

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

// buildMultipartDeep2 构造 multipart 请求体，写入 file 字段。
func buildMultipartDeep2(t *testing.T, fieldName, filename, content string) (*bytes.Buffer, string) {
	t.Helper()
	body := &bytes.Buffer{}
	w := multipart.NewWriter(body)
	fw, err := w.CreateFormFile(fieldName, filename)
	if err != nil {
		t.Fatalf("CreateFormFile: %v", err)
	}
	if _, err := fw.Write([]byte(content)); err != nil {
		t.Fatalf("write content: %v", err)
	}
	if err := w.Close(); err != nil {
		t.Fatalf("close writer: %v", err)
	}
	return body, w.FormDataContentType()
}

// newTestRouterDeep2 用临时文件库构造 router。
func newTestRouterDeep2(t *testing.T) (*httptest.Server, *store.Store) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st := store.New(database)
	cfg := config.Config{}
	r := NewRouter(st, &cfg)
	ts := httptest.NewServer(r)
	t.Cleanup(ts.Close)
	return ts, st
}

// importCSVDeep2 通过 HTTP 上传 CSV 并返回状态码与解析后的 JSON。
func importCSVDeep2(t *testing.T, ts *httptest.Server, filename, content string) (int, map[string]any) {
	t.Helper()
	body, ct := buildMultipartDeep2(t, "file", filename, content)
	req, err := http.NewRequest(http.MethodPost, ts.URL+"/api/import", body)
	if err != nil {
		t.Fatalf("NewRequest: %v", err)
	}
	req.Header.Set("Content-Type", ct)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("Do: %v", err)
	}
	defer resp.Body.Close()
	var m map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&m); err != nil {
		t.Fatalf("decode json: %v", err)
	}
	return resp.StatusCode, m
}

func TestImportValidCSVDeep2(t *testing.T) {
	ts, _ := newTestRouterDeep2(t)
	csvContent := "slug,url,title\n" +
		"a1,https://example.com/a,Title A\n" +
		"b2,https://example.com/b,Title B\n"
	code, m := importCSVDeep2(t, ts, "links.csv", csvContent)
	if code != http.StatusOK {
		t.Fatalf("status = %d, want 200", code)
	}
	imported, ok := m["imported"]
	if !ok {
		t.Fatalf("response missing imported key: %v", m)
	}
	if n, ok := imported.(float64); !ok || int(n) != 2 {
		t.Fatalf("imported = %v, want 2", imported)
	}
	skipped, ok := m["skipped"]
	if !ok {
		t.Fatalf("response missing skipped key: %v", m)
	}
	if n, ok := skipped.(float64); !ok || int(n) != 0 {
		t.Fatalf("skipped = %v, want 0", skipped)
	}
	if _, ok := m["errors"]; !ok {
		t.Fatalf("response missing errs key: %v", m)
	}
}

func TestImportInvalidURLRowDeep2(t *testing.T) {
	ts, _ := newTestRouterDeep2(t)
	csvContent := "slug,url,title\n" +
		"good,https://example.com/ok,Good\n" +
		"bad,not-a-valid-url,Bad\n"
	code, m := importCSVDeep2(t, ts, "links.csv", csvContent)
	if code != http.StatusOK {
		t.Fatalf("status = %d, want 200", code)
	}
	imported, ok := m["imported"]
	if !ok {
		t.Fatalf("missing imported: %v", m)
	}
	if n, ok := imported.(float64); !ok || int(n) != 1 {
		t.Fatalf("imported = %v, want 1", imported)
	}
	errsVal, ok := m["errors"]
	if !ok {
		t.Fatalf("missing errs: %v", m)
	}
	errs, ok := errsVal.([]any)
	if !ok {
		t.Fatalf("errs not a slice: %T", errsVal)
	}
	if len(errs) == 0 {
		t.Fatalf("errs should be non-empty when invalid url present")
	}
}

func TestImportMissingFileFieldDeep2(t *testing.T) {
	ts, _ := newTestRouterDeep2(t)
	body := &bytes.Buffer{}
	w := multipart.NewWriter(body)
	if err := w.WriteField("other", "value"); err != nil {
		t.Fatalf("WriteField: %v", err)
	}
	if err := w.Close(); err != nil {
		t.Fatalf("close: %v", err)
	}
	req, err := http.NewRequest(http.MethodPost, ts.URL+"/api/import", body)
	if err != nil {
		t.Fatalf("NewRequest: %v", err)
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("Do: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
}

func TestImportEmptyFileDeep2(t *testing.T) {
	ts, _ := newTestRouterDeep2(t)
	code, m := importCSVDeep2(t, ts, "empty.csv", "")
	if code != http.StatusOK {
		t.Fatalf("status = %d, want 200", code)
	}
	imported, ok := m["imported"]
	if !ok {
		t.Fatalf("missing imported: %v", m)
	}
	if n, ok := imported.(float64); !ok || int(n) != 0 {
		t.Fatalf("imported = %v, want 0", imported)
	}
}

func TestExportContentTypeAndSlugDeep2(t *testing.T) {
	ts, _ := newTestRouterDeep2(t)
	csvContent := "slug,url,title\n" +
		"exp1,https://example.com/x,Exported\n"
	if code, _ := importCSVDeep2(t, ts, "seed.csv", csvContent); code != http.StatusOK {
		t.Fatalf("seed import status = %d", code)
	}
	resp, err := http.Get(ts.URL + "/api/export.csv")
	if err != nil {
		t.Fatalf("GET export: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "text/csv") {
		t.Fatalf("Content-Type = %q, want contains text/csv", ct)
	}
	if !strings.Contains(ct, "charset=utf-8") {
		t.Fatalf("Content-Type = %q, want charset=utf-8", ct)
	}
	buf := new(bytes.Buffer)
	if _, err := buf.ReadFrom(resp.Body); err != nil {
		t.Fatalf("read body: %v", err)
	}
	if !strings.Contains(buf.String(), "exp1") {
		t.Fatalf("exported csv missing slug exp1: %q", buf.String())
	}
}

func TestExportEmptyStoreDeep2(t *testing.T) {
	ts, _ := newTestRouterDeep2(t)
	resp, err := http.Get(ts.URL + "/api/export.csv")
	if err != nil {
		t.Fatalf("GET export: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	buf := new(bytes.Buffer)
	if _, err := buf.ReadFrom(resp.Body); err != nil {
		t.Fatalf("read body: %v", err)
	}
	rdr := csv.NewReader(bytes.NewReader(buf.Bytes()))
	rows, err := rdr.ReadAll()
	if err != nil {
		t.Fatalf("parse csv: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("rows = %d, want 1 (header only)", len(rows))
	}
}

func TestImportExportRoundTripDeep2(t *testing.T) {
	ts, _ := newTestRouterDeep2(t)
	csvContent := "slug,url,title\n" +
		"rt1,https://example.com/1,One\n" +
		"rt2,https://example.com/2,Two\n"
	code, m := importCSVDeep2(t, ts, "seed.csv", csvContent)
	if code != http.StatusOK {
		t.Fatalf("seed status = %d", code)
	}
	if n, _ := m["imported"].(float64); int(n) != 2 {
		t.Fatalf("seed imported = %v, want 2", m["imported"])
	}

	resp, err := http.Get(ts.URL + "/api/export.csv")
	if err != nil {
		t.Fatalf("GET export: %v", err)
	}
	defer resp.Body.Close()
	exported := new(bytes.Buffer)
	if _, err := exported.ReadFrom(resp.Body); err != nil {
		t.Fatalf("read: %v", err)
	}

	code2, m2 := importCSVDeep2(t, ts, "roundtrip.csv", exported.String())
	if code2 != http.StatusOK {
		t.Fatalf("roundtrip status = %d", code2)
	}
	imported2, _ := m2["imported"].(float64)
	skipped2, _ := m2["skipped"].(float64)
	errs2, _ := m2["errors"].([]any)
	// 原始 2 行 slug 已存在：应被计入 skipped 或 errs，imported 不应为 2。
	if int(imported2) == 2 {
		t.Fatalf("roundtrip imported = 2, expected duplicates handled (skipped=%v errs=%v)", skipped2, errs2)
	}
	if int(skipped2)+len(errs2) == 0 {
		t.Fatalf("roundtrip duplicates neither skipped nor errs: skipped=%v errs=%v", skipped2, errs2)
	}
}

func TestImportNonCSVTextDeep2(t *testing.T) {
	ts, _ := newTestRouterDeep2(t)
	// 纯文本无表头，无有效 CSV 数据行。
	code, m := importCSVDeep2(t, ts, "notes.txt", "this is not csv at all\njust some plain text")
	if code != http.StatusOK {
		t.Fatalf("status = %d, want 200", code)
	}
	imported, ok := m["imported"]
	if !ok {
		t.Fatalf("missing imported: %v", m)
	}
	if n, ok := imported.(float64); !ok || int(n) != 0 {
		t.Fatalf("imported = %v, want 0 for non-csv content", imported)
	}
}
