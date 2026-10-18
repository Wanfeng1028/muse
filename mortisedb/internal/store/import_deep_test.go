package store

import (
	"database/sql"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

func newImportTestStore(t *testing.T) *Store {
	t.Helper()
	// 文件库：:memory: 下多连接各有一份空库，并发测试会 no such table
	s, err := Open(filepath.Join(t.TempDir(), "import_test.db"))
	if err != nil {
		t.Fatalf("打开文件库失败: %v", err)
	}
	if _, err := s.DB.Exec(
		`CREATE TABLE "_m_imports" (
			"source" TEXT NOT NULL,
			"file_hash" TEXT NOT NULL,
			"filename" TEXT NOT NULL,
			"rows_total" INTEGER NOT NULL,
			"inserted" INTEGER NOT NULL,
			"updated" INTEGER NOT NULL,
			"error_rows" INTEGER NOT NULL,
			"created_at" TEXT NOT NULL
		)`,
	); err != nil {
		t.Fatalf("建表失败: %v", err)
	}
	t.Cleanup(func() { s.DB.Close() })
	return s
}

func TestRecordImportThenFindImportRoundTrip(t *testing.T) {
	s := newImportTestStore(t)

	ok, err := s.RecordImport("csv", "hash-a", "a.csv", 10, 7, 3, 0)
	if err != nil {
		t.Fatalf("RecordImport 出错: %v", err)
	}
	if !ok {
		t.Fatalf("首次 RecordImport 应插入成功")
	}

	found, summary, err := s.FindImport("csv", "hash-a")
	if err != nil {
		t.Fatalf("FindImport 出错: %v", err)
	}
	if !found {
		t.Fatalf("期望找到导入记录, 实际没找到")
	}
	if summary["filename"] != "a.csv" {
		t.Fatalf("filename 期望 a.csv, 实际 %v", summary["filename"])
	}
	if summary["rows_total"] != 10 {
		t.Fatalf("rows_total 期望 10, 实际 %v", summary["rows_total"])
	}
	if summary["inserted"] != 7 {
		t.Fatalf("inserted 期望 7, 实际 %v", summary["inserted"])
	}
	if summary["updated"] != 3 {
		t.Fatalf("updated 期望 3, 实际 %v", summary["updated"])
	}
	if summary["error_rows"] != 0 {
		t.Fatalf("error_rows 期望 0, 实际 %v", summary["error_rows"])
	}
}

func TestFindImportMissingReturnsNotFound(t *testing.T) {
	s := newImportTestStore(t)

	found, summary, err := s.FindImport("csv", "never-existed")
	if err != nil {
		t.Fatalf("FindImport 出错: %v", err)
	}
	if found {
		t.Fatalf("期望 found=false, 实际 true")
	}
	if summary != nil {
		t.Fatalf("期望 summary=nil, 实际 %v", summary)
	}
}

func TestFindImportSameSourceDifferentHashIsolated(t *testing.T) {
	s := newImportTestStore(t)

	if _, err := s.RecordImport("csv", "hash-1", "one.csv", 5, 5, 0, 0); err != nil {
		t.Fatalf("RecordImport 1 出错: %v", err)
	}
	if _, err := s.RecordImport("csv", "hash-2", "two.csv", 9, 8, 1, 0); err != nil {
		t.Fatalf("RecordImport 2 出错: %v", err)
	}

	found1, summary1, err := s.FindImport("csv", "hash-1")
	if err != nil {
		t.Fatalf("FindImport hash-1 出错: %v", err)
	}
	if !found1 || summary1["filename"] != "one.csv" || summary1["rows_total"] != 5 {
		t.Fatalf("hash-1 记录不匹配: found=%v summary=%v", found1, summary1)
	}

	found2, summary2, err := s.FindImport("csv", "hash-2")
	if err != nil {
		t.Fatalf("FindImport hash-2 出错: %v", err)
	}
	if !found2 || summary2["filename"] != "two.csv" || summary2["rows_total"] != 9 {
		t.Fatalf("hash-2 记录不匹配: found=%v summary=%v", found2, summary2)
	}
}

func TestFindImportSameHashDifferentSourceIsolated(t *testing.T) {
	s := newImportTestStore(t)

	if _, err := s.RecordImport("csv", "shared-hash", "from-csv.csv", 3, 3, 0, 0); err != nil {
		t.Fatalf("RecordImport csv 出错: %v", err)
	}
	if _, err := s.RecordImport("json", "shared-hash", "from-json.json", 4, 4, 0, 0); err != nil {
		t.Fatalf("RecordImport json 出错: %v", err)
	}

	foundCSV, summaryCSV, err := s.FindImport("csv", "shared-hash")
	if err != nil {
		t.Fatalf("FindImport csv 出错: %v", err)
	}
	if !foundCSV || summaryCSV["filename"] != "from-csv.csv" || summaryCSV["rows_total"] != 3 {
		t.Fatalf("csv 记录不匹配: found=%v summary=%v", foundCSV, summaryCSV)
	}

	foundJSON, summaryJSON, err := s.FindImport("json", "shared-hash")
	if err != nil {
		t.Fatalf("FindImport json 出错: %v", err)
	}
	if !foundJSON || summaryJSON["filename"] != "from-json.json" || summaryJSON["rows_total"] != 4 {
		t.Fatalf("json 记录不匹配: found=%v summary=%v", foundJSON, summaryJSON)
	}
}

func TestRecordImportDuplicateKeyReturnsLatestFirstRow(t *testing.T) {
	s := newImportTestStore(t)

	if _, err := s.RecordImport("csv", "dup-hash", "first.csv", 1, 1, 0, 0); err != nil {
		t.Fatalf("第一次 RecordImport 出错: %v", err)
	}
	if _, err := s.RecordImport("csv", "dup-hash", "second.csv", 2, 2, 0, 0); err != nil {
		t.Fatalf("第二次 RecordImport 出错: %v", err)
	}

	found, summary, err := s.FindImport("csv", "dup-hash")
	if err != nil {
		t.Fatalf("FindImport 出错: %v", err)
	}
	if !found {
		t.Fatalf("期望找到记录, 实际没找到")
	}
	if summary["filename"] != "first.csv" {
		t.Fatalf("同 key 冲突时 FindImport 命中 first.csv, 实际 %v", summary["filename"])
	}
	if summary["rows_total"] != 1 {
		t.Fatalf("同 key 冲突时 rows_total 期望 1, 实际 %v", summary["rows_total"])
	}

	var count int
	if err := s.DB.QueryRow(
		`SELECT COUNT(*) FROM "_m_imports" WHERE "source" = ? AND "file_hash" = ?`,
		"csv", "dup-hash",
	).Scan(&count); err != nil {
		t.Fatalf("统计行数出错: %v", err)
	}
	if count != 2 {
		t.Fatalf("期望库里有 2 行, 实际 %d", count)
	}
}

func TestRecordImportCreatedAtIsRFC3339UTC(t *testing.T) {
	s := newImportTestStore(t)

	before := time.Now().UTC().Add(-2 * time.Second)
	if _, err := s.RecordImport("csv", "time-hash", "t.csv", 1, 1, 0, 0); err != nil {
		t.Fatalf("RecordImport 出错: %v", err)
	}
	after := time.Now().UTC().Add(2 * time.Second)

	found, summary, err := s.FindImport("csv", "time-hash")
	if err != nil {
		t.Fatalf("FindImport 出错: %v", err)
	}
	if !found {
		t.Fatalf("期望找到记录, 实际没找到")
	}
	raw, ok := summary["created_at"].(string)
	if !ok {
		t.Fatalf("created_at 类型期望 string, 实际 %T", summary["created_at"])
	}
	parsed, err := time.Parse(time.RFC3339, raw)
	if err != nil {
		t.Fatalf("created_at 不是 RFC3339 格式: %q err=%v", raw, err)
	}
	if parsed.Before(before) || parsed.After(after) {
		t.Fatalf("created_at %v 不在期望区间 [%v, %v]", parsed, before, after)
	}
	if parsed.Location() != time.UTC {
		t.Fatalf("created_at 时区期望 UTC, 实际 %v", parsed.Location())
	}
}

func TestFindImportReturnsErrorWhenTableMissing(t *testing.T) {
	s, err := Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	t.Cleanup(func() { s.DB.Close() })

	found, summary, err := s.FindImport("csv", "any-hash")
	if err == nil {
		t.Fatalf("表不存在时期望返回错误, 实际 nil")
	}
	if found {
		t.Fatalf("出错时期望 found=false, 实际 true")
	}
	if summary != nil {
		t.Fatalf("出错时期望 summary=nil, 实际 %v", summary)
	}
}

func TestRecordImportReturnsErrorWhenTableMissing(t *testing.T) {
	s, err := Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	t.Cleanup(func() { s.DB.Close() })

	_, err = s.RecordImport("csv", "any-hash", "x.csv", 1, 1, 0, 0)
	if err == nil {
		t.Fatalf("表不存在时期望返回错误, 实际 nil")
	}

	var count int
	countErr := s.DB.QueryRow(`SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='_m_imports'`).Scan(&count)
	if countErr != nil {
		t.Fatalf("查询 sqlite_master 出错: %v", countErr)
	}
	if count != 0 {
		t.Fatalf("期望 _m_imports 表不存在, 实际存在")
	}
}

func TestRecordImportIdempotentCheckIsStableAcrossCalls(t *testing.T) {
	s := newImportTestStore(t)

	if _, err := s.RecordImport("csv", "idem-hash", "idem.csv", 100, 90, 10, 0); err != nil {
		t.Fatalf("RecordImport 出错: %v", err)
	}

	found1, summary1, err := s.FindImport("csv", "idem-hash")
	if err != nil {
		t.Fatalf("FindImport 第一次出错: %v", err)
	}
	found2, summary2, err := s.FindImport("csv", "idem-hash")
	if err != nil {
		t.Fatalf("FindImport 第二次出错: %v", err)
	}
	if !found1 || !found2 {
		t.Fatalf("两次都期望找到, 实际 found1=%v found2=%v", found1, found2)
	}
	if summary1["inserted"] != summary2["inserted"] {
		t.Fatalf("inserted 两次不一致: %v vs %v", summary1["inserted"], summary2["inserted"])
	}
	if summary1["created_at"] != summary2["created_at"] {
		t.Fatalf("created_at 两次不一致: %v vs %v", summary1["created_at"], summary2["created_at"])
	}
}

func TestRecordImportAndFindImportConcurrentAccess(t *testing.T) {
	s := newImportTestStore(t)
	if _, err := s.DB.Exec(`PRAGMA journal_mode=WAL`); err != nil {
		t.Fatalf("开启 WAL 失败: %v", err)
	}

	const writers = 6
	var wg sync.WaitGroup
	wg.Add(writers)
	errCh := make(chan error, writers)

	for i := 0; i < writers; i++ {
		go func(idx int) {
			defer wg.Done()
			hash := "conc-hash-" + string(rune('a'+idx))
			if _, err := s.RecordImport("csv", hash, "conc.csv", idx+1, idx+1, 0, 0); err != nil {
				errCh <- err
				return
			}
			found, summary, err := s.FindImport("csv", hash)
			if err != nil {
				errCh <- err
				return
			}
			if !found {
				errCh <- sql.ErrNoRows
				return
			}
			if summary["rows_total"] != idx+1 {
				errCh <- sql.ErrNoRows
				return
			}
		}(i)
	}
	wg.Wait()
	close(errCh)

	for err := range errCh {
		if err != nil {
			t.Fatalf("并发访问出错: %v", err)
		}
	}

	var count int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "_m_imports"`).Scan(&count); err != nil {
		t.Fatalf("统计行数出错: %v", err)
	}
	if count != writers {
		t.Fatalf("期望 %d 行, 实际 %d", writers, count)
	}
}
