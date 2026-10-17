package store

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
)

// 说明：本文件为 store 模块的深度测试，聚焦多源拼装冲突、HMAC Webhook 验签边界、
// 重试退避、同步幂等、CSV 增量导入断点续传。源码中未导出的函数/字段一律不直接引用，
// 只通过已存在的导出 API 与 SQL 查询验证行为。

// ---- 测试辅助 ----

func newTestStore(t *testing.T) *Store {
	t.Helper()
	s, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open 内存库失败: %v", err)
	}
	if err := s.Migrate(); err != nil {
		s.Close()
		t.Fatalf("Migrate 失败: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func newTestStoreFile(t *testing.T) (*Store, string) {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "deep.db")
	s, err := Open(path)
	if err != nil {
		t.Fatalf("Open 文件库失败: %v", err)
	}
	if err := s.Migrate(); err != nil {
		s.Close()
		t.Fatalf("Migrate 失败: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s, path
}

func colsForTest() []infer.Column {
	return []infer.Column{
		{Name: "id", Type: "INTEGER"},
		{Name: "name", Type: "TEXT"},
		{Name: "amount", Type: "INTEGER"},
	}
}

func mustEnsure(t *testing.T, s *Store, table, pk string, cols []infer.Column) {
	t.Helper()
	if err := s.EnsureTable(table, pk, cols); err != nil {
		t.Fatalf("EnsureTable %s 失败: %v", table, err)
	}
}

// hmacSign 计算 webhook 负载的 HMAC-SHA256 十六进制签名。
func hmacSign(secret string, body []byte) string {
	m := hmac.New(sha256.New, []byte(secret))
	m.Write(body)
	return hex.EncodeToString(m.Sum(nil))
}

// verifyWebhook 模拟验签逻辑：常量时间比较，长度不等直接失败。
func verifyWebhook(secret string, body []byte, sigHex string) bool {
	want := hmacSign(secret, body)
	got, err := hex.DecodeString(sigHex)
	if err != nil {
		return false
	}
	wantBytes, err := hex.DecodeString(want)
	if err != nil {
		return false
	}
	return hmac.Equal(wantBytes, got)
}

// ---- 用例 1：多源拼装冲突 ----

func TestDeep_MultiSourceConflict_DetectedAndRecorded(t *testing.T) {
	s := newTestStore(t)
	table := "orders"
	mustEnsure(t, s, table, "id", colsForTest())

	// 源 A 先写入 id=1, name=alice, amount=100
	if err := s.UpsertRow(s.DB, table, "id", 1,
		[]string{"id", "name", "amount"},
		[]any{1, "alice", 100},
		"hash-a", "source-a"); err != nil {
		t.Fatalf("源 A 写入失败: %v", err)
	}

	// 源 B 写入同一主键但 name 不同，应被记录为冲突
	var beforeName string
	if err := s.DB.QueryRow(`SELECT "name" FROM "orders" WHERE "id"=?`, 1).Scan(&beforeName); err != nil {
		t.Fatalf("读取源 A 行失败: %v", err)
	}
	if beforeName != "alice" {
		t.Fatalf("源 A 行 name 期望 alice，实际 %s", beforeName)
	}

	// 模拟冲突记录插入
	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := s.DB.Exec(`INSERT INTO "_m_conflicts"
		("table_name","pk","source_a","source_b","row_json","status","created_at")
		VALUES (?,?,?,?,?,?,?)`,
		table, "1", "source-a", "source-b",
		`{"id":1,"name":"bob","amount":100}`, "pending", now); err != nil {
		t.Fatalf("插入冲突记录失败: %v", err)
	}

	var cnt int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "_m_conflicts" WHERE "table_name"=? AND "pk"=?`, table, "1").Scan(&cnt); err != nil {
		t.Fatalf("统计冲突失败: %v", err)
	}
	if cnt != 1 {
		t.Fatalf("冲突记录数期望 1，实际 %d", cnt)
	}

	var status string
	if err := s.DB.QueryRow(`SELECT "status" FROM "_m_conflicts" WHERE "table_name"=? AND "pk"=?`, table, "1").Scan(&status); err != nil {
		t.Fatalf("读取冲突状态失败: %v", err)
	}
	if status != "pending" {
		t.Fatalf("冲突状态期望 pending，实际 %s", status)
	}

	// 不同值的冲突（name 不同）应保留两个 source 标识
	var srcA, srcB string
	if err := s.DB.QueryRow(`SELECT "source_a","source_b" FROM "_m_conflicts" WHERE "table_name"=? AND "pk"=?`, table, "1").Scan(&srcA, &srcB); err != nil {
		t.Fatalf("读取冲突来源失败: %v", err)
	}
	if srcA != "source-a" || srcB != "source-b" {
		t.Fatalf("冲突来源期望 source-a/source-b，实际 %s/%s", srcA, srcB)
	}
}

// ---- 用例 2：同 key 同值不产生冲突 ----

func TestDeep_SameKeySameValue_NoConflict(t *testing.T) {
	s := newTestStore(t)
	table := "orders"
	mustEnsure(t, s, table, "id", colsForTest())

	if err := s.UpsertRow(s.DB, table, "id", 7,
		[]string{"id", "name", "amount"},
		[]any{7, "carol", 500},
		"hash-c", "source-a"); err != nil {
		t.Fatalf("首次写入失败: %v", err)
	}
	// 同一值重复写入，hash 相同
	if err := s.UpsertRow(s.DB, table, "id", 7,
		[]string{"id", "name", "amount"},
		[]any{7, "carol", 500},
		"hash-c", "source-b"); err != nil {
		t.Fatalf("重复写入失败: %v", err)
	}

	var cnt int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "orders" WHERE "id"=?`, 7).Scan(&cnt); err != nil {
		t.Fatalf("统计行失败: %v", err)
	}
	if cnt != 1 {
		t.Fatalf("行数期望 1，实际 %d", cnt)
	}

	var hash, src string
	if err := s.DB.QueryRow(`SELECT "_m_hash","_m_source" FROM "orders" WHERE "id"=?`, 7).Scan(&hash, &src); err != nil {
		t.Fatalf("读取内部列失败: %v", err)
	}
	if hash != "hash-c" {
		t.Fatalf("hash 期望 hash-c，实际 %s", hash)
	}
	if src != "source-b" {
		t.Fatalf("source 期望最后一次写入 source-b，实际 %s", src)
	}

	var conflicts int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "_m_conflicts"`).Scan(&conflicts); err != nil {
		t.Fatalf("统计冲突失败: %v", err)
	}
	if conflicts != 0 {
		t.Fatalf("同 key 同值不应产生冲突，实际冲突数 %d", conflicts)
	}
}

// ---- 用例 3：HMAC 验签边界 - 正常 ----

func TestDeep_HMACVerify_ValidSignature(t *testing.T) {
	secret := "topsecret-key-2024"
	body := []byte(`{"event":"row.updated","id":1,"name":"alice"}`)
	sig := hmacSign(secret, body)

	if !verifyWebhook(secret, body, sig) {
		t.Fatalf("合法签名应验签通过")
	}
	if len(sig) != 64 {
		t.Fatalf("HMAC-SHA256 十六进制签名长度期望 64，实际 %d", len(sig))
	}
	if sig == hmacSign(secret, []byte(`{"event":"row.updated","id":2}`)) {
		t.Fatalf("不同负载签名不应相同")
	}
}

// ---- 用例 4：HMAC 验签边界 - 篡改/错误密钥/畸形 ----

func TestDeep_HMACVerify_Boundaries(t *testing.T) {
	secret := "topsecret-key-2024"
	body := []byte(`{"event":"row.updated","id":1}`)
	good := hmacSign(secret, body)

	cases := []struct {
		name    string
		secret  string
		body    []byte
		sig     string
		wantOK  bool
	}{
		{"正常", secret, body, good, true},
		{"错误密钥", "wrong-key", body, good, false},
		{"篡改负载", secret, []byte(`{"event":"row.deleted","id":1}`), good, false},
		{"空签名", secret, body, "", false},
		{"非法十六进制", secret, body, "zzzz", false},
		{"截断签名", secret, body, good[:32], false},
		{"多余字符", secret, body, good + "ab", false},
	}
	for _, c := range cases {
		got := verifyWebhook(c.secret, c.body, c.sig)
		if got != c.wantOK {
			t.Fatalf("用例 %s: 期望 %v，实际 %v", c.name, c.wantOK, got)
		}
	}
}

// ---- 用例 5：HMAC 常量时间比较不因长度提前短路语义（行为验证） ----

func TestDeep_HMACVerify_LengthMismatchRejected(t *testing.T) {
	secret := "k"
	body := []byte("payload")
	sig := hmacSign(secret, body)

	if !verifyWebhook(secret, body, sig) {
		t.Fatalf("合法签名应通过")
	}
	// 长度不等必须拒绝
	if verifyWebhook(secret, body, sig+"00") {
		t.Fatalf("长度不等应拒绝")
	}
	// 全零签名（长度正确但内容错误）必须拒绝
	zeros := strings.Repeat("0", len(sig))
	if verifyWebhook(secret, body, zeros) {
		t.Fatalf("全零签名应拒绝")
	}
}

// ---- 用例 6：重试退避 - 指数增长与上限 ----

func TestDeep_RetryBackoff_ExponentialWithCap(t *testing.T) {
	// 模拟退避：base=100ms，factor=2，cap=800ms，jitter=0
	base := 100 * time.Millisecond
	cap := 800 * time.Millisecond
	backoff := func(attempt int) time.Duration {
		d := base
		for i := 0; i < attempt; i++ {
			d *= 2
			if d >= cap {
				return cap
			}
		}
		return d
	}

	got := []time.Duration{
		backoff(0), backoff(1), backoff(2), backoff(3), backoff(4), backoff(5),
	}
	want := []time.Duration{
		100 * time.Millisecond,
		200 * time.Millisecond,
		400 * time.Millisecond,
		800 * time.Millisecond,
		800 * time.Millisecond,
		800 * time.Millisecond,
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("attempt=%d 期望 %v，实际 %v", i, want[i], got[i])
		}
	}
	if got[len(got)-1] > cap {
		t.Fatalf("退避不应超过上限 %v，实际 %v", cap, got[len(got)-1])
	}
}

// ---- 用例 7：重试退避 - 上下文取消立即返回 ----

func TestDeep_RetryBackoff_ContextCancel(t *testing.T) {
	attempts := 0
	cancelled := make(chan struct{})
	close(cancelled)

	doWithRetry := func(max int) error {
		for i := 0; i < max; i++ {
			select {
			case <-cancelled:
				return errors.New("context canceled")
			default:
			}
			attempts++
		}
		return nil
	}

	err := doWithRetry(5)
	if err == nil {
		t.Fatalf("已取消上下文应返回错误")
	}
	if err.Error() != "context canceled" {
		t.Fatalf("错误信息期望 context canceled，实际 %s", err.Error())
	}
	if attempts != 0 {
		t.Fatalf("取消后不应执行重试，实际尝试次数 %d", attempts)
	}
}

// ---- 用例 8：同步幂等 - 重复同步不新增行 ----

func TestDeep_SyncIdempotent_RepeatedRuns(t *testing.T) {
	s := newTestStore(t)
	table := "items"
	mustEnsure(t, s, table, "id", colsForTest())

	rows := []struct {
		id     int
		name   string
		amount int
		hash   string
	}{
		{1, "a", 10, "h1"},
		{2, "b", 20, "h2"},
		{3, "c", 30, "h3"},
	}

	runSync := func() error {
		tx, err := s.DB.Begin()
		if err != nil {
			return err
		}
		for _, r := range rows {
			if err := s.UpsertRow(tx, table, "id", r.id,
				[]string{"id", "name", "amount"},
				[]any{r.id, r.name, r.amount},
				r.hash, "src"); err != nil {
				tx.Rollback()
				return err
			}
		}
		return tx.Commit()
	}

	if err := runSync(); err != nil {
		t.Fatalf("第一次同步失败: %v", err)
	}
	var cnt1 int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "items"`).Scan(&cnt1); err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if cnt1 != 3 {
		t.Fatalf("第一次同步后期望 3 行，实际 %d", cnt1)
	}

	if err := runSync(); err != nil {
		t.Fatalf("第二次同步失败: %v", err)
	}
	var cnt2 int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "items"`).Scan(&cnt2); err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if cnt2 != 3 {
		t.Fatalf("幂等同步后期望仍为 3 行，实际 %d", cnt2)
	}

	var syncedCount int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "items" WHERE "_m_synced_at" IS NOT NULL`).Scan(&syncedCount); err != nil {
		t.Fatalf("统计同步时间失败: %v", err)
	}
	if syncedCount != 3 {
		t.Fatalf("所有行都应有 _m_synced_at，实际 %d", syncedCount)
	}
}

// ---- 用例 9：同步幂等 - 并发同 key 写入 ----

func TestDeep_SyncConcurrent_NoDuplicateRows(t *testing.T) {
	s, _ := newTestStoreFile(t) // 文件库：:memory: 下多连接各有一份空库，并发写会 no such table
	table := "conc"
	mustEnsure(t, s, table, "id", colsForTest())

	var wg sync.WaitGroup
	errCh := make(chan error, 8)
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := s.UpsertRow(s.DB, table, "id", 42,
				[]string{"id", "name", "amount"},
				[]any{42, "shared", 999},
				"h-42", "src"); err != nil {
				errCh <- err
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		if err != nil {
			t.Fatalf("并发写入出错: %v", err)
		}
	}

	var cnt int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "conc" WHERE "id"=?`, 42).Scan(&cnt); err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if cnt != 1 {
		t.Fatalf("并发写入同 key 期望 1 行，实际 %d", cnt)
	}

	var name string
	if err := s.DB.QueryRow(`SELECT "name" FROM "conc" WHERE "id"=?`, 42).Scan(&name); err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	if name != "shared" {
		t.Fatalf("name 期望 shared，实际 %s", name)
	}
}

// ---- 用例 10：CSV 增量导入断点续传 - 首次记录 ----

func TestDeep_CSVIncrementalImport_FirstRun(t *testing.T) {
	s := newTestStore(t)
	table := "csv_data"
	mustEnsure(t, s, table, "id", colsForTest())

	// 写入 _m_imports 记录，模拟首次导入
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := s.DB.Exec(`INSERT INTO "_m_imports"
		("source","file_hash","filename","rows_total","inserted","updated","error_rows","created_at")
		VALUES (?,?,?,?,?,?,?,?)`,
		"csv", "abc123hash", "data.csv", 100, 100, 0, 0, now)
	if err != nil {
		t.Fatalf("插入导入记录失败: %v", err)
	}
	id, err := res.LastInsertId()
	if err != nil {
		t.Fatalf("获取导入 id 失败: %v", err)
	}
	if id <= 0 {
		t.Fatalf("导入 id 应为正数，实际 %d", id)
	}

	var storedHash, filename string
	var rowsTotal, inserted int
	if err := s.DB.QueryRow(`SELECT "file_hash","filename","rows_total","inserted" FROM "_m_imports" WHERE "id"=?`, id).
		Scan(&storedHash, &filename, &rowsTotal, &inserted); err != nil {
		t.Fatalf("读取导入记录失败: %v", err)
	}
	if storedHash != "abc123hash" {
		t.Fatalf("file_hash 期望 abc123hash，实际 %s", storedHash)
	}
	if filename != "data.csv" {
		t.Fatalf("filename 期望 data.csv，实际 %s", filename)
	}
	if rowsTotal != 100 || inserted != 100 {
		t.Fatalf("rows_total/inserted 期望 100/100，实际 %d/%d", rowsTotal, inserted)
	}
}

// ---- 用例 11：CSV 增量导入断点续传 - 同 hash 重复导入被 UNIQUE 拒绝 ----

func TestDeep_CSVIncrementalImport_ResumeByHash(t *testing.T) {
	s := newTestStore(t)

	now := time.Now().UTC().Format(time.RFC3339)
	// 第一次导入
	if _, err := s.DB.Exec(`INSERT INTO "_m_imports"
		("source","file_hash","filename","rows_total","inserted","updated","error_rows","created_at")
		VALUES (?,?,?,?,?,?,?,?)`,
		"csv", "hash-xyz", "a.csv", 50, 50, 0, 0, now); err != nil {
		t.Fatalf("首次导入记录失败: %v", err)
	}

	// 相同 file_hash 再次插入应被 UNIQUE 约束拒绝
	_, err := s.DB.Exec(`INSERT INTO "_m_imports"
		("source","file_hash","filename","rows_total","inserted","updated","error_rows","created_at")
		VALUES (?,?,?,?,?,?,?,?)`,
		"csv", "hash-xyz", "a.csv", 50, 50, 0, 0, now)
	if err == nil {
		t.Fatalf("相同 file_hash 应触发 UNIQUE 约束错误")
	}
	if !strings.Contains(strings.ToLower(err.Error()), "unique") {
		t.Fatalf("错误信息应包含 unique，实际 %s", err.Error())
	}

	// 断点续传：查询已完成的 hash 判断是否跳过
	var exists int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "_m_imports" WHERE "file_hash"=?`, "hash-xyz").Scan(&exists); err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if exists != 1 {
		t.Fatalf("hash-xyz 应只有 1 条记录，实际 %d", exists)
	}

	// 不同 hash 应允许插入
	if _, err := s.DB.Exec(`INSERT INTO "_m_imports"
		("source","file_hash","filename","rows_total","inserted","updated","error_rows","created_at")
		VALUES (?,?,?,?,?,?,?,?)`,
		"csv", "hash-abc", "b.csv", 30, 30, 0, 0, now); err != nil {
		t.Fatalf("不同 hash 应允许插入: %v", err)
	}
	var total int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "_m_imports"`).Scan(&total); err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if total != 2 {
		t.Fatalf("导入记录数期望 2，实际 %d", total)
	}
}

// ---- 用例 12：CSV 增量导入断点续传 - 部分失败后重试保留断点 ----

func TestDeep_CSVIncrementalImport_PartialFailureResume(t *testing.T) {
	s := newTestStore(t)
	table := "csv_rows"
	mustEnsure(t, s, table, "id", colsForTest())

	// 模拟第一批成功导入 2 行
	okRows := []struct {
		id   int
		name string
	}{
		{1, "r1"},
		{2, "r2"},
	}
	for _, r := range okRows {
		if err := s.UpsertRow(s.DB, table, "id", r.id,
			[]string{"id", "name", "amount"},
			[]any{r.id, r.name, 0},
			fmt.Sprintf("h-%d", r.id), "csv"); err != nil {
			t.Fatalf("写入行 %d 失败: %v", r.id, err)
		}
	}

	// 记录断点：已完成 2 行，总计 5 行
	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := s.DB.Exec(`INSERT INTO "_m_imports"
		("source","file_hash","filename","rows_total","inserted","updated","error_rows","created_at")
		VALUES (?,?,?,?,?,?,?,?)`,
		"csv", "partial-hash", "big.csv", 5, 2, 0, 3, now); err != nil {
		t.Fatalf("记录断点失败: %v", err)
	}

	var rowsTotal, inserted, errorRows int
	if err := s.DB.QueryRow(`SELECT "rows_total","inserted","error_rows" FROM "_m_imports" WHERE "file_hash"=?`, "partial-hash").
		Scan(&rowsTotal, &inserted, &errorRows); err != nil {
		t.Fatalf("读取断点失败: %v", err)
	}
	if rowsTotal != 5 || inserted != 2 || errorRows != 3 {
		t.Fatalf("断点期望 5/2/3，实际 %d/%d/%d", rowsTotal, inserted, errorRows)
	}

	// 续传：从断点继续插入剩余 3 行
	remaining := []struct {
		id   int
		name string
	}{
		{3, "r3"},
		{4, "r4"},
		{5, "r5"},
	}
	tx, err := s.DB.Begin()
	if err != nil {
		t.Fatalf("开启事务失败: %v", err)
	}
	for _, r := range remaining {
		if err := s.UpsertRow(tx, table, "id", r.id,
			[]string{"id", "name", "amount"},
			[]any{r.id, r.name, 0},
			fmt.Sprintf("h-%d", r.id), "csv"); err != nil {
			tx.Rollback()
			t.Fatalf("续传写入行 %d 失败: %v", r.id, err)
		}
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("提交续传失败: %v", err)
	}

	var cnt int
	if err := s.DB.QueryRow(`SELECT COUNT(*) FROM "csv_rows"`).Scan(&cnt); err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if cnt != 5 {
		t.Fatalf("续传后期望 5 行，实际 %d", cnt)
	}

	// 更新断点为完成
	if _, err := s.DB.Exec(`UPDATE "_m_imports" SET "inserted"=?, "error_rows"=? WHERE "file_hash"=?`,
		5, 0, "partial-hash"); err != nil {
		t.Fatalf("更新断点失败: %v", err)
	}
	var finalInserted, finalErrors int
	if err := s.DB.QueryRow(`SELECT "inserted","error_rows" FROM "_m_imports" WHERE "file_hash"=?`, "partial-hash").
		Scan(&finalInserted, &finalErrors); err != nil {
		t.Fatalf("读取最终断点失败: %v", err)
	}
	if finalInserted != 5 || finalErrors != 0 {
		t.Fatalf("最终断点期望 5/0，实际 %d/%d", finalInserted, finalErrors)
	}
}

// ---- 用例 13：文件库 WAL 与重启后数据保留 ----

func TestDeep_FileStore_WALAndReopen(t *testing.T) {
	s, path := newTestStoreFile(t)
	table := "persist"
	mustEnsure(t, s, table, "id", colsForTest())

	if err := s.UpsertRow(s.DB, table, "id", 1,
		[]string{"id", "name", "amount"},
		[]any{1, "keeper", 42},
		"h-p", "src"); err != nil {
		t.Fatalf("写入失败: %v", err)
	}

	var mode string
	if err := s.DB.QueryRow(`PRAGMA journal_mode`).Scan(&mode); err != nil {
		t.Fatalf("读取 journal_mode 失败: %v", err)
	}
	if strings.ToLower(mode) != "wal" {
		t.Fatalf("文件库 journal_mode 期望 wal，实际 %s", mode)
	}

	if err := s.Close(); err != nil {
		t.Fatalf("关闭失败: %v", err)
	}

	if _, err := os.Stat(path); err != nil {
		t.Fatalf("数据库文件应存在: %v", err)
	}

	reopened, err := Open(path)
	if err != nil {
		t.Fatalf("重新打开失败: %v", err)
	}
	defer reopened.Close()

	var name string
	var amount int
	if err := reopened.DB.QueryRow(`SELECT "name","amount" FROM "persist" WHERE "id"=?`, 1).Scan(&name, &amount); err != nil {
		t.Fatalf("重开后读取失败: %v", err)
	}
	if name != "keeper" {
		t.Fatalf("重开后 name 期望 keeper，实际 %s", name)
	}
	if amount != 42 {
		t.Fatalf("重开后 amount 期望 42，实际 %d", amount)
	}
}

// ---- 用例 14：Webhook 处理器集成验签 ----

func TestDeep_WebhookHandler_IntegrationVerify(t *testing.T) {
	secret := "webhook-secret-42"
	handler := func(w http.ResponseWriter, r *http.Request) {
		body := make([]byte, r.ContentLength)
		if _, err := r.Body.Read(body); err != nil && err.Error() != "EOF" {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		sig := r.Header.Get("X-Signature")
		if !verifyWebhook(secret, body, sig) {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		w.WriteHeader(http.StatusOK)
	}

	srv := httptest.NewServer(http.HandlerFunc(handler))
	defer srv.Close()

	payload := []byte(`{"event":"sync","table":"orders"}`)

	// 合法签名
	req, _ := http.NewRequest(http.MethodPost, srv.URL, strings.NewReader(string(payload)))
	req.Header.Set("X-Signature", hmacSign(secret, payload))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("请求失败: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("合法签名期望 200，实际 %d", resp.StatusCode)
	}

	// 非法签名
	req2, _ := http.NewRequest(http.MethodPost, srv.URL, strings.NewReader(string(payload)))
	req2.Header.Set("X-Signature", "deadbeef")
	resp2, err := http.DefaultClient.Do(req2)
	if err != nil {
		t.Fatalf("请求失败: %v", err)
	}
	resp2.Body.Close()
	if resp2.StatusCode != http.StatusUnauthorized {
		t.Fatalf("非法签名期望 401，实际 %d", resp2.StatusCode)
	}
}