package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func testV14Setup(t *testing.T, conflict string, priority ...string) (*store.Store, *config.Config) {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { st.Close() })
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	cfg := config.DefaultConfig()
	cfg.Database = filepath.Join(t.TempDir(), "mortise.db")
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Table: "t_v14_main", PrimaryKey: "id"},
		{Name: "s2", Type: "csv", Table: "t_v14_main", PrimaryKey: "id"},
	}
	cfg.Sync.Conflict = conflict
	cfg.Sync.Priority = priority
	return st, cfg
}

func v14Import(t *testing.T, st *store.Store, cfg *config.Config, source, filename, content string, opts importCSVOptions) (importCSVResult, error) {
	t.Helper()
	return importCSVStream(st, cfg, source, strings.NewReader(content), filename, opts)
}

func TestV14ColumnMapping(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	m := map[string]string{"编号": "id", "姓名": "name", "年龄": "age"}
	content := "编号,姓名,年龄\n1,张三,20\n2,李四,30\n3,王五,40\n"
	res, err := v14Import(t, st, cfg, "s1", "mapping.csv", content, importCSVOptions{ColumnMapping: m})
	if err != nil {
		t.Fatalf("import: %v", err)
	}
	if res.Inserted != 3 {
		t.Fatalf("Inserted=%d want 3", res.Inserted)
	}
	var name string
	if err := st.DB.QueryRow("SELECT name FROM t_v14_main WHERE id='1'").Scan(&name); err != nil {
		t.Fatalf("query: %v", err)
	}
	if name != "张三" {
		t.Fatalf("name=%q want 张三", name)
	}
}

func TestV14ColumnMappingInvalidName(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	m := map[string]string{"id": "1bad"}
	content := "id,name\n1,张三\n"
	_, err := v14Import(t, st, cfg, "s1", "bad.csv", content, importCSVOptions{ColumnMapping: m})
	if !errors.Is(err, errImportInvalidColumnName) {
		t.Fatalf("err=%v want errImportInvalidColumnName", err)
	}
}

func TestV14ColumnMappingDuplicate(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	m := map[string]string{"a": "x", "b": "x"}
	content := "a,b\n1,2\n"
	_, err := v14Import(t, st, cfg, "s1", "dup.csv", content, importCSVOptions{ColumnMapping: m})
	if !errors.Is(err, errImportDuplicateColumn) {
		t.Fatalf("err=%v want errImportDuplicateColumn", err)
	}
}

func TestV14ColumnMappingEmptyTarget(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	m := map[string]string{"id": ""}
	content := "id,name\n1,张三\n"
	_, err := v14Import(t, st, cfg, "s1", "empty.csv", content, importCSVOptions{ColumnMapping: m})
	if !errors.Is(err, errImportEmptyColumn) {
		t.Fatalf("err=%v want errImportEmptyColumn", err)
	}
}

func TestV14PrimaryKeyOverride(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	content := "code,name\nc1,张三\nc2,李四\n"
	res, err := v14Import(t, st, cfg, "s1", "pk.csv", content, importCSVOptions{PrimaryKey: "code"})
	if err != nil {
		t.Fatalf("import override pk: %v", err)
	}
	if res.Inserted != 2 {
		t.Fatalf("Inserted=%d want 2", res.Inserted)
	}
	content2 := "code,name\nc3,王五\nc4,赵六\n"
	res2, err := v14Import(t, st, cfg, "s1", "pk2.csv", content2, importCSVOptions{Table: "t_v14_alt", PrimaryKey: "code"})
	if err != nil {
		t.Fatalf("import alt table: %v", err)
	}
	if res2.Table != "t_v14_alt" {
		t.Fatalf("Table=%q want t_v14_alt", res2.Table)
	}
	n, err := st.TableCount("t_v14_alt")
	if err != nil {
		t.Fatalf("count alt: %v", err)
	}
	if n != int64(2) {
		t.Fatalf("alt count=%d want 2", n)
	}
	n2, err := st.TableCount("t_v14_main")
	if err != nil {
		t.Fatalf("count main: %v", err)
	}
	if n2 != int64(2) {
		t.Fatalf("main count=%d want 2", n2)
	}
}

func TestV14DuplicateWithMapping(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	m := map[string]string{"编号": "id", "姓名": "name"}
	content := "编号,姓名\n1,张三\n2,李四\n"
	first, err := v14Import(t, st, cfg, "s1", "same.csv", content, importCSVOptions{ColumnMapping: m})
	if err != nil {
		t.Fatalf("first import: %v", err)
	}
	second, err := v14Import(t, st, cfg, "s1", "same.csv", content, importCSVOptions{ColumnMapping: m})
	if err != nil {
		t.Fatalf("second import: %v", err)
	}
	if !second.Duplicate {
		t.Fatalf("Duplicate=false want true")
	}
	if second.Inserted != first.Inserted {
		t.Fatalf("second Inserted=%d first=%d", second.Inserted, first.Inserted)
	}
}

func TestV14ConflictManualPending(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	if _, err := v14Import(t, st, cfg, "s1", "a.csv", "id,name\n1,张三\n", importCSVOptions{}); err != nil {
		t.Fatalf("s1 import: %v", err)
	}
	res, err := v14Import(t, st, cfg, "s2", "b.csv", "id,name\n1,李四\n", importCSVOptions{})
	if err != nil {
		t.Fatalf("s2 import: %v", err)
	}
	if res.ConflictsPending != 1 {
		t.Fatalf("ConflictsPending=%d want 1", res.ConflictsPending)
	}
	if len(res.Conflicts) != 1 {
		t.Fatalf("len(Conflicts)=%d want 1", len(res.Conflicts))
	}
	c := res.Conflicts[0]
	if c.SourceA != "s1" || c.SourceB != "s2" {
		t.Fatalf("SourceA=%q SourceB=%q want s1/s2", c.SourceA, c.SourceB)
	}
	if c.Status != "pending" {
		t.Fatalf("Status=%q want pending", c.Status)
	}
	list, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("pending len=%d want 1", len(list))
	}
	var name string
	if err := st.DB.QueryRow("SELECT name FROM t_v14_main WHERE id='1'").Scan(&name); err != nil {
		t.Fatalf("query: %v", err)
	}
	if name != "张三" {
		t.Fatalf("name=%q want 张三", name)
	}
}

func TestV14ConflictPriorityHighWins(t *testing.T) {
	st, cfg := testV14Setup(t, "priority", "s2", "s1")
	if _, err := v14Import(t, st, cfg, "s1", "a.csv", "id,name\n1,张三\n", importCSVOptions{}); err != nil {
		t.Fatalf("s1 import: %v", err)
	}
	res, err := v14Import(t, st, cfg, "s2", "b.csv", "id,name\n1,李四\n", importCSVOptions{})
	if err != nil {
		t.Fatalf("s2 import: %v", err)
	}
	if res.Updated != 1 {
		t.Fatalf("Updated=%d want 1", res.Updated)
	}
	if res.ConflictsPending != 0 {
		t.Fatalf("ConflictsPending=%d want 0", res.ConflictsPending)
	}
	resolved, err := st.ListConflicts("resolved_auto")
	if err != nil {
		t.Fatalf("ListConflicts: %v", err)
	}
	if len(resolved) < 1 {
		t.Fatalf("resolved_auto len=%d want >=1", len(resolved))
	}
	var name string
	if err := st.DB.QueryRow("SELECT name FROM t_v14_main WHERE id='1'").Scan(&name); err != nil {
		t.Fatalf("query: %v", err)
	}
	if name != "李四" {
		t.Fatalf("name=%q want 李四", name)
	}
}

func TestV14ConflictPriorityLowPending(t *testing.T) {
	st, cfg := testV14Setup(t, "priority", "s1", "s2")
	if _, err := v14Import(t, st, cfg, "s1", "a.csv", "id,name\n1,张三\n", importCSVOptions{}); err != nil {
		t.Fatalf("s1 import: %v", err)
	}
	res, err := v14Import(t, st, cfg, "s2", "b.csv", "id,name\n1,李四\n", importCSVOptions{})
	if err != nil {
		t.Fatalf("s2 import: %v", err)
	}
	if res.ConflictsPending != 1 {
		t.Fatalf("ConflictsPending=%d want 1", res.ConflictsPending)
	}
	var name string
	if err := st.DB.QueryRow("SELECT name FROM t_v14_main WHERE id='1'").Scan(&name); err != nil {
		t.Fatalf("query: %v", err)
	}
	if name != "张三" {
		t.Fatalf("name=%q want 张三", name)
	}
}

func TestV14SameSourceUpdateResolves(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	if _, err := v14Import(t, st, cfg, "s1", "a.csv", "id,name\n1,张三\n", importCSVOptions{}); err != nil {
		t.Fatalf("s1 import: %v", err)
	}
	if _, err := v14Import(t, st, cfg, "s2", "b.csv", "id,name\n1,李四\n", importCSVOptions{}); err != nil {
		t.Fatalf("s2 import: %v", err)
	}
	pend, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts: %v", err)
	}
	if len(pend) != 1 {
		t.Fatalf("pending len=%d want 1", len(pend))
	}
	res, err := v14Import(t, st, cfg, "s1", "c.csv", "id,name\n1,王五\n", importCSVOptions{})
	if err != nil {
		t.Fatalf("s1 reimport: %v", err)
	}
	if res.Updated != 1 {
		t.Fatalf("Updated=%d want 1", res.Updated)
	}
	pend2, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts2: %v", err)
	}
	if len(pend2) != 0 {
		t.Fatalf("pending len=%d want 0", len(pend2))
	}
}

func v14HTTPImport(t *testing.T, srv http.Handler, source, filename, content, mapping string) *httptest.ResponseRecorder {
	t.Helper()
	body := &bytes.Buffer{}
	mw := multipart.NewWriter(body)
	fw, err := mw.CreateFormFile("file", filename)
	if err != nil {
		t.Fatalf("create form file: %v", err)
	}
	if _, err := io.WriteString(fw, content); err != nil {
		t.Fatalf("write form file: %v", err)
	}
	if err := mw.WriteField("source", source); err != nil {
		t.Fatalf("write source: %v", err)
	}
	if mapping != "" {
		if err := mw.WriteField("column_mapping", mapping); err != nil {
			t.Fatalf("write mapping: %v", err)
		}
	}
	if err := mw.Close(); err != nil {
		t.Fatalf("close mw: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, "/api/import/csv", body)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	return rec
}

func TestV14HTTP409(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	srv := NewServer(st, cfg, log.New(io.Discard, "info"))
	rec1 := v14HTTPImport(t, srv, "s1", "a.csv", "id,name\n1,张三\n", "")
	if rec1.Code != http.StatusOK {
		t.Fatalf("first code=%d want 200 body=%s", rec1.Code, rec1.Body.String())
	}
	rec2 := v14HTTPImport(t, srv, "s2", "b.csv", "id,name\n1,李四\n", "")
	if rec2.Code != http.StatusConflict {
		t.Fatalf("second code=%d want 409 body=%s", rec2.Code, rec2.Body.String())
	}
	if !strings.Contains(rec2.Body.String(), `"status":"pending"`) {
		t.Fatalf("body=%s want status pending", rec2.Body.String())
	}
}

func TestV14HTTPNewEndpointOK(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	srv := NewServer(st, cfg, log.New(io.Discard, "info"))
	rec := v14HTTPImport(t, srv, "s1", "ok.csv", "id,name\n1,张三\n", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d want 200 body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `"table":"t_v14_main"`) {
		t.Fatalf("body=%s want table t_v14_main", rec.Body.String())
	}
	rec2 := v14HTTPImport(t, srv, "s1", "bad.csv", "id,name\n1,张三\n", "{bad json")
	if rec2.Code != http.StatusBadRequest {
		t.Fatalf("bad mapping code=%d want 400 body=%s", rec2.Code, rec2.Body.String())
	}
}

type v14SizeReader struct {
	remaining int64
}

func (r *v14SizeReader) Read(p []byte) (int, error) {
	if r.remaining <= 0 {
		return 0, io.EOF
	}
	n := int64(len(p))
	if n > r.remaining {
		n = r.remaining
	}
	if n > 64*1024 {
		n = 64 * 1024
	}
	for i := int64(0); i < n; i++ {
		p[i] = 'a'
	}
	r.remaining -= n
	return int(n), nil
}

func TestV14FileTooLarge(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	r := &v14SizeReader{remaining: 33 << 20}
	_, err := importCSVStream(st, cfg, "s1", r, "big.csv", importCSVOptions{})
	if !errors.Is(err, errImportFileTooLarge) {
		t.Fatalf("err=%v want errImportFileTooLarge", err)
	}
}

func TestV14LargeFileStreaming50k(t *testing.T) {
	st, cfg := testV14Setup(t, "manual")
	items := []string{"龙井", "普洱", "铁观音", "白牡丹", "正山小种"}
	cities := []string{"杭州", "上海", "广州", "成都", "武汉"}
	customers := []string{"陈建国", "林晓梅", "王志强", "赵雪", "刘洋"}
	amounts := []string{"128", "256", "388", "588"}
	var sb strings.Builder
	sb.WriteString("order_id,customer,item,amount,city\n")
	const total = 50000
	for i := 0; i < total; i++ {
		fmt.Fprintf(&sb, "%d,%s,%s,%s,%s\n",
			i+1,
			customers[i%len(customers)],
			items[i%len(items)],
			amounts[i%len(amounts)],
			cities[i%len(cities)],
		)
	}
	content := sb.String()
	start := time.Now()
	res, err := v14Import(t, st, cfg, "s1", "orders.csv", content, importCSVOptions{PrimaryKey: "order_id"})
	if err != nil {
		t.Fatalf("import 50k: %v", err)
	}
	if res.Inserted != total {
		t.Fatalf("Inserted=%d want %d", res.Inserted, total)
	}
	if res.ErrorRows != 0 {
		t.Fatalf("ErrorRows=%d want 0", res.ErrorRows)
	}
	if elapsed := time.Since(start); elapsed >= 60*time.Second {
		t.Fatalf("elapsed=%v want <60s", elapsed)
	}

	lines := strings.Split(strings.TrimRight(content, "\n"), "\n")
	lines[25000] = "25000,陈建国,龙井,999,杭州"
	modified := strings.Join(lines, "\n") + "\n"
	res2, err := v14Import(t, st, cfg, "s1", "orders2.csv", modified, importCSVOptions{PrimaryKey: "order_id"})
	if err != nil {
		t.Fatalf("import modified: %v", err)
	}
	if res2.Updated != 1 {
		t.Fatalf("Updated=%d want 1", res2.Updated)
	}
	if res2.Unchanged != total-1 {
		t.Fatalf("Unchanged=%d want %d", res2.Unchanged, total-1)
	}

	dir := filepath.Join(filepath.Dir(cfg.Database), ".import-tmp")
	entries, err := os.ReadDir(dir)
	if err != nil {
		if !os.IsNotExist(err) {
			t.Fatalf("read tmp dir: %v", err)
		}
	} else if len(entries) != 0 {
		names := make([]string, 0, len(entries))
		for _, e := range entries {
			names = append(names, e.Name())
		}
		t.Fatalf("leftover tmp files: %v", names)
	}
}

var _ = json.Marshal
