package api

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func testImportCfg() *config.Config {
	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Table: "t1", PrimaryKey: "id"},
	}
	return cfg
}

func testImportStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开 store 失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	cols := []infer.Column{
		{Name: "id", Type: "INTEGER"},
		{Name: "name", Type: "TEXT"},
		{Name: "age", Type: "INTEGER"},
	}
	if err := st.EnsureTable("t1", "id", cols); err != nil {
		t.Fatalf("建表失败: %v", err)
	}
	return st
}

func TestImportCSVBasicInsert(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()
	body := "id,name\n1,a\n2,b\n"
	res, err := importCSV(st, cfg, "s1", strings.NewReader(body), "basic.csv")
	if err != nil {
		t.Fatalf("导入失败: %v", err)
	}
	if res.TotalRows != 2 {
		t.Errorf("TotalRows = %d, want 2", res.TotalRows)
	}
	if res.Inserted != 2 {
		t.Errorf("Inserted = %d, want 2", res.Inserted)
	}
	if res.Updated != 0 {
		t.Errorf("Updated = %d, want 0", res.Updated)
	}
	if res.ErrorRows != 0 {
		t.Errorf("ErrorRows = %d, want 0", res.ErrorRows)
	}
	if res.Duplicate {
		t.Errorf("Duplicate = true, want false")
	}
	cnt, err := st.TableCount("t1")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt != 2 {
		t.Errorf("TableCount(t1) = %d, want 2", cnt)
	}
}

func TestImportCSVIncrementalInsertAndUpdate(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()

	a := "id,name\n1,a\n2,b\n3,c\n"
	resA, err := importCSV(st, cfg, "s1", strings.NewReader(a), "a.csv")
	if err != nil {
		t.Fatalf("导入 A 失败: %v", err)
	}
	if resA.Inserted != 3 {
		t.Errorf("A.Inserted = %d, want 3", resA.Inserted)
	}

	b := "id,name\n1,a\n2,b\n3,c\n4,d\n"
	resB, err := importCSV(st, cfg, "s1", strings.NewReader(b), "b.csv")
	if err != nil {
		t.Fatalf("导入 B 失败: %v", err)
	}
	if resB.Inserted != 1 {
		t.Errorf("B.Inserted = %d, want 1", resB.Inserted)
	}
	if resB.Unchanged != 3 {
		t.Errorf("B.Unchanged = %d, want 3", resB.Unchanged)
	}

	c := "id,name\n1,a\n2,bb\n3,c\n4,d\n"
	resC, err := importCSV(st, cfg, "s1", strings.NewReader(c), "c.csv")
	if err != nil {
		t.Fatalf("导入 C 失败: %v", err)
	}
	if resC.Updated != 1 {
		t.Errorf("C.Updated = %d, want 1", resC.Updated)
	}
	if resC.Unchanged != 3 {
		t.Errorf("C.Unchanged = %d, want 3", resC.Unchanged)
	}
}

func TestImportCSVIdempotent(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()
	body := "id,name\n1,a\n2,b\n"

	first, err := importCSV(st, cfg, "s1", strings.NewReader(body), "same.csv")
	if err != nil {
		t.Fatalf("首次导入失败: %v", err)
	}
	second, err := importCSV(st, cfg, "s1", strings.NewReader(body), "same.csv")
	if err != nil {
		t.Fatalf("二次导入失败: %v", err)
	}
	if !second.Duplicate {
		t.Errorf("second.Duplicate = false, want true")
	}
	if second.Inserted != first.Inserted {
		t.Errorf("second.Inserted = %d, want %d", second.Inserted, first.Inserted)
	}
	if second.Updated != first.Updated {
		t.Errorf("second.Updated = %d, want %d", second.Updated, first.Updated)
	}
}

func TestImportCSVBadRows(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()
	body := "id,name\n1,ok\n,empty-pk\n2\n3,ok2\n"
	res, err := importCSV(st, cfg, "s1", strings.NewReader(body), "bad.csv")
	if err != nil {
		t.Fatalf("导入失败: %v", err)
	}
	if res.Inserted != 2 {
		t.Errorf("Inserted = %d, want 2", res.Inserted)
	}
	if res.ErrorRows != 2 {
		t.Errorf("ErrorRows = %d, want 2", res.ErrorRows)
	}
	if len(res.Errors) != 2 {
		t.Fatalf("len(Errors) = %d, want 2", len(res.Errors))
	}
	lines := map[int]bool{}
	for _, e := range res.Errors {
		lines[e.Line] = true
	}
	if !lines[3] {
		t.Errorf("errors 缺少行号 3: %+v", res.Errors)
	}
	if !lines[4] {
		t.Errorf("errors 缺少行号 4: %+v", res.Errors)
	}
	cnt, err := st.TableCount("t1")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt != 2 {
		t.Errorf("TableCount(t1) = %d, want 2", cnt)
	}
}

func TestImportCSVEmptyFile(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()
	_, err := importCSV(st, cfg, "s1", strings.NewReader(""), "empty.csv")
	if !errors.Is(err, errImportEmptyFile) {
		t.Fatalf("err = %v, want errImportEmptyFile", err)
	}
}

func TestImportCSVMissingPrimaryKeyColumn(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()
	body := "name,age\na,1\n"
	_, err := importCSV(st, cfg, "s1", strings.NewReader(body), "nopk.csv")
	if !errors.Is(err, errImportPrimaryKeyMissing) {
		t.Fatalf("err = %v, want errImportPrimaryKeyMissing", err)
	}
}

func TestImportCSVUnknownSource(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()
	body := "id,name\n1,a\n"
	_, err := importCSV(st, cfg, "nope", strings.NewReader(body), "u.csv")
	if !errors.Is(err, errImportSourceNotFound) {
		t.Fatalf("err = %v, want errImportSourceNotFound", err)
	}
}

func TestImportCSVSourceNotConfigured(t *testing.T) {
	st := testImportStore(t)
	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Table: "", PrimaryKey: "id"},
	}
	body := "id,name\n1,a\n"
	_, err := importCSV(st, cfg, "s1", strings.NewReader(body), "nc.csv")
	if !errors.Is(err, errImportSourceNotConfigured) {
		t.Fatalf("err = %v, want errImportSourceNotConfigured", err)
	}
}

func TestImportCSV10kRowsPerf(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()
	var b strings.Builder
	b.WriteString("id,name\n")
	for i := 1; i <= 10000; i++ {
		fmt.Fprintf(&b, "%d,n%d\n", i, i)
	}
	start := time.Now()
	res, err := importCSV(st, cfg, "s1", strings.NewReader(b.String()), "big.csv")
	elapsed := time.Since(start)
	if err != nil {
		t.Fatalf("导入失败: %v", err)
	}
	if res.Inserted != 10000 {
		t.Errorf("Inserted = %d, want 10000", res.Inserted)
	}
	if res.ErrorRows != 0 {
		t.Errorf("ErrorRows = %d, want 0", res.ErrorRows)
	}
	if elapsed > 30*time.Second {
		t.Errorf("导入耗时 %v 超过 30 秒", elapsed)
	}
}

func TestImportCSVHTTP(t *testing.T) {
	st := testImportStore(t)
	cfg := testImportCfg()
	srv := NewServer(st, cfg, log.New(io.Discard, "info"))

	body := &bytes.Buffer{}
	mw := multipart.NewWriter(body)
	fw, err := mw.CreateFormFile("file", "data.csv")
	if err != nil {
		t.Fatalf("CreateFormFile 失败: %v", err)
	}
	if _, err := io.WriteString(fw, "id,name\n1,a\n2,b\n"); err != nil {
		t.Fatalf("写入 multipart 失败: %v", err)
	}
	if err := mw.Close(); err != nil {
		t.Fatalf("Close multipart 失败: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/sources/s1/import-csv", body)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "\"duplicate\":false") {
		t.Errorf("body = %s, want duplicate=false", rec.Body.String())
	}

	body2 := &bytes.Buffer{}
	mw2 := multipart.NewWriter(body2)
	fw2, err := mw2.CreateFormFile("file", "data.csv")
	if err != nil {
		t.Fatalf("CreateFormFile 失败: %v", err)
	}
	if _, err := io.WriteString(fw2, "id,name\n1,a\n"); err != nil {
		t.Fatalf("写入 multipart 失败: %v", err)
	}
	if err := mw2.Close(); err != nil {
		t.Fatalf("Close multipart 失败: %v", err)
	}
	req2 := httptest.NewRequest(http.MethodPost, "/api/sources/nope/import-csv", body2)
	req2.Header.Set("Content-Type", mw2.FormDataContentType())
	rec2 := httptest.NewRecorder()
	srv.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusNotFound {
		t.Fatalf("unknown source status = %d, want 404, body=%s", rec2.Code, rec2.Body.String())
	}
	if !strings.Contains(rec2.Body.String(), "\"error\"") {
		t.Errorf("body = %s, want error field", rec2.Body.String())
	}
}
