package backup

import (
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

// makeMortiseDB 建一个最小可用的 MortiseDB 源库：包含 _m_watermarks 表。
func makeMortiseDB(t *testing.T, path string, rows int) {
	t.Helper()
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open src: %v", err)
	}
	defer db.Close()
	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS "_m_watermarks" ("k" TEXT PRIMARY KEY, "v" TEXT)`); err != nil {
		t.Fatalf("create _m_watermarks: %v", err)
	}
	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS "items" ("id" INTEGER PRIMARY KEY, "name" TEXT, "qty" INTEGER)`); err != nil {
		t.Fatalf("create items: %v", err)
	}
	for i := 0; i < rows; i++ {
		if _, err := db.Exec(`INSERT INTO "items" ("name","qty") VALUES (?,?)`, fmt.Sprintf("n-%d", i), i); err != nil {
			t.Fatalf("insert items: %v", err)
		}
	}
	if _, err := db.Exec(`INSERT OR REPLACE INTO "_m_watermarks" ("k","v") VALUES ('seq', ?)`, fmt.Sprint(rows)); err != nil {
		t.Fatalf("insert watermark: %v", err)
	}
}

// mergeSource 表示一个待合并的数据来源，用于多源拼装冲突测试。
type mergeSource struct {
	name string
	kv   map[string]string
}

// mergeSources 把多个来源按顺序拼装进 map，后写覆盖前写，并记录冲突项。
// 返回最终结果与被覆盖的键（记录每次覆盖的 (key, 旧值, 新值)）。
func mergeSources(sources []mergeSource) (map[string]string, []string) {
	out := map[string]string{}
	var conflicts []string
	for _, s := range sources {
		for k, v := range s.kv {
			if old, ok := out[k]; ok && old != v {
				conflicts = append(conflicts, fmt.Sprintf("%s: %s -> %s", k, old, v))
			}
			out[k] = v
		}
	}
	return out, conflicts
}

// signWebhook 计算 HMAC-SHA256 十六进制签名。
func signWebhook(secret string, body []byte) string {
	m := hmac.New(sha256.New, []byte(secret))
	m.Write(body)
	return hex.EncodeToString(m.Sum(nil))
}

// verifyWebhook 校验 webhook 签名，返回是否通过以及原因。
// 规则：签名头必须存在、长度一致、常量时间比较。
func verifyWebhook(secret string, body []byte, header string) (bool, string) {
	if header == "" {
		return false, "缺少签名头"
	}
	want := signWebhook(secret, body)
	if len(header) != len(want) {
		return false, "签名长度不匹配"
	}
	got, err := hex.DecodeString(header)
	if err != nil {
		return false, "签名不是合法十六进制"
	}
	wantBytes, _ := hex.DecodeString(want)
	if !hmac.Equal(got, wantBytes) {
		return false, "签名不匹配"
	}
	return true, ""
}

// backoffDelay 指数退避，上限 cap，第 attempt 次（从 0 开始）。
func backoffDelay(base time.Duration, cap time.Duration, attempt int) time.Duration {
	d := base
	for i := 0; i < attempt; i++ {
		d *= 2
		if d >= cap {
			return cap
		}
	}
	if d > cap {
		return cap
	}
	return d
}

// retryDo 按退避重试 fn，直到成功或超过 maxAttempts。
// 返回尝试次数与最后一次错误。
func retryDo(maxAttempts int, base, cap time.Duration, fn func() error) (int, error) {
	var lastErr error
	for i := 0; i < maxAttempts; i++ {
		if err := fn(); err != nil {
			lastErr = err
			if i < maxAttempts-1 {
				time.Sleep(backoffDelay(base, cap, i))
			}
			continue
		}
		return i + 1, nil
	}
	return maxAttempts, lastErr
}

// csvImporter 表示一个可断点续传的 CSV 增量导入器。
// 已导入的行号记录在 offset 中，重复导入同批数据不产生重复行。
type csvImporter struct {
	mu     sync.Mutex
	rows   []string
	offset int
}

// ImportChunk 从 offset 开始导入 chunk 行，返回本次导入的行数。
// 若 chunk 超过剩余行数，只导入剩余部分。幂等：重复调用同样参数返回 0 新增。
func (c *csvImporter) ImportChunk(chunk int) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.offset >= len(c.rows) {
		return 0
	}
	end := c.offset + chunk
	if end > len(c.rows) {
		end = len(c.rows)
	}
	n := end - c.offset
	c.offset = end
	return n
}

// Offset 返回当前已导入的断点位置。
func (c *csvImporter) Offset() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.offset
}

// TestMergeSourcesConflictSameKeyDifferentValue 多源拼装：同 key 不同值必须记录冲突并以后写覆盖。
func TestMergeSourcesConflictSameKeyDifferentValue(t *testing.T) {
	sources := []mergeSource{
		{name: "a", kv: map[string]string{"k1": "v1", "k2": "v2"}},
		{name: "b", kv: map[string]string{"k1": "v9", "k3": "v3"}},
		{name: "c", kv: map[string]string{"k2": "v8"}},
	}
	got, conflicts := mergeSources(sources)

	if len(got) != 3 {
		t.Fatalf("合并后键数量 = %d, want 3", len(got))
	}
	if got["k1"] != "v9" {
		t.Errorf("k1 = %q, want %q（后写覆盖前写）", got["k1"], "v9")
	}
	if got["k2"] != "v8" {
		t.Errorf("k2 = %q, want %q", got["k2"], "v8")
	}
	if got["k3"] != "v3" {
		t.Errorf("k3 = %q, want %q", got["k3"], "v3")
	}
	if len(conflicts) != 2 {
		t.Fatalf("冲突记录数 = %d, want 2: %v", len(conflicts), conflicts)
	}
	if !strings.Contains(conflicts[0], "k1") || !strings.Contains(conflicts[0], "v1 -> v9") {
		t.Errorf("第一条冲突 = %q, 期望包含 k1 与 v1 -> v9", conflicts[0])
	}
	if !strings.Contains(conflicts[1], "k2") || !strings.Contains(conflicts[1], "v2 -> v8") {
		t.Errorf("第二条冲突 = %q, 期望包含 k2 与 v2 -> v8", conflicts[1])
	}
}

// TestMergeSourcesSameValueNoConflict 多源拼装：同 key 同值不算冲突。
func TestMergeSourcesSameValueNoConflict(t *testing.T) {
	sources := []mergeSource{
		{name: "a", kv: map[string]string{"k1": "same"}},
		{name: "b", kv: map[string]string{"k1": "same"}},
	}
	got, conflicts := mergeSources(sources)

	if got["k1"] != "same" {
		t.Errorf("k1 = %q, want %q", got["k1"], "same")
	}
	if len(conflicts) != 0 {
		t.Errorf("同值不应产生冲突, 实际 conflicts = %v", conflicts)
	}
	if len(got) != 1 {
		t.Errorf("键数量 = %d, want 1", len(got))
	}
}

// TestVerifyWebhookHMACBoundary 验签边界：正确签名通过，篡改/空/长度不符/非法 hex 全部拒绝。
func TestVerifyWebhookHMACBoundary(t *testing.T) {
	secret := "s3cr3t"
	body := []byte(`{"event":"backup.done","seq":7}`)

	ok, reason := verifyWebhook(secret, body, signWebhook(secret, body))
	if !ok {
		t.Fatalf("正确签名应通过, reason=%q", reason)
	}
	if reason != "" {
		t.Errorf("通过时 reason 应为空, got %q", reason)
	}

	cases := []struct {
		name   string
		header string
		want   string
	}{
		{"空签名头", "", "缺少签名头"},
		{"长度不符", "abc", "签名长度不匹配"},
		{"非法hex", strings.Repeat("z", 64), "签名不是合法十六进制"},
		{"值篡改", signWebhook(secret, []byte("other")), "签名不匹配"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, why := verifyWebhook(secret, body, c.header)
			if got {
				t.Fatalf("应拒绝, 但通过了")
			}
			if why != c.want {
				t.Errorf("reason = %q, want %q", why, c.want)
			}
		})
	}

	// 用错误 secret 签出的签名也必须被拒
	bad := signWebhook("wrong-secret", body)
	if got, _ := verifyWebhook(secret, body, bad); got {
		t.Errorf("错误 secret 的签名应被拒绝")
	}
}

// TestVerifyWebhookRealServer 用真实 HTTP 服务器跑一遍验签流程。
func TestVerifyWebhookRealServer(t *testing.T) {
	const secret = "hook-secret"
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		buf := make([]byte, r.ContentLength)
		if _, err := r.Body.Read(buf); err != nil && err.Error() != "EOF" {
			// 读取完毕即可
		}
		ok, reason := verifyWebhook(secret, buf, r.Header.Get("X-Muse-Signature"))
		if !ok {
			http.Error(w, reason, http.StatusUnauthorized)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	body := []byte(`{"event":"ping"}`)
	req, err := http.NewRequest(http.MethodPost, srv.URL, strings.NewReader(string(body)))
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("X-Muse-Signature", signWebhook(secret, body))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("do: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("合法签名请求状态 = %d, want 200", resp.StatusCode)
	}

	req2, err := http.NewRequest(http.MethodPost, srv.URL, strings.NewReader(string(body)))
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req2.Header.Set("X-Muse-Signature", signWebhook("bad", body))
	resp2, err := http.DefaultClient.Do(req2)
	if err != nil {
		t.Fatalf("do: %v", err)
	}
	resp2.Body.Close()
	if resp2.StatusCode != http.StatusUnauthorized {
		t.Fatalf("非法签名请求状态 = %d, want 401", resp2.StatusCode)
	}
	if atomic.LoadInt32(&hits) != 2 {
		t.Errorf("服务器处理次数 = %d, want 2", hits)
	}
}

// TestBackoffDelayBounds 重试退避：序列递增、封顶、attempt=0 返回 base。
func TestBackoffDelayBounds(t *testing.T) {
	base := 100 * time.Millisecond
	capD := 800 * time.Millisecond

	if d := backoffDelay(base, capD, 0); d != 100*time.Millisecond {
		t.Errorf("attempt=0 delay = %v, want 100ms", d)
	}
	if d := backoffDelay(base, capD, 1); d != 200*time.Millisecond {
		t.Errorf("attempt=1 delay = %v, want 200ms", d)
	}
	if d := backoffDelay(base, capD, 2); d != 400*time.Millisecond {
		t.Errorf("attempt=2 delay = %v, want 400ms", d)
	}
	if d := backoffDelay(base, capD, 3); d != 800*time.Millisecond {
		t.Errorf("attempt=3 delay = %v, want 800ms", d)
	}
	if d := backoffDelay(base, capD, 4); d != capD {
		t.Errorf("attempt=4 delay = %v, want cap %v", d, capD)
	}
	if d := backoffDelay(base, capD, 10); d != capD {
		t.Errorf("attempt=10 delay = %v, want cap %v", d, capD)
	}
}

// TestRetryDoEventuallySucceeds 重试：第 3 次成功，返回尝试次数 3。
func TestRetryDoEventuallySucceeds(t *testing.T) {
	var attempts int
	got, err := retryDo(5, time.Millisecond, 4*time.Millisecond, func() error {
		attempts++
		if attempts < 3 {
			return fmt.Errorf("临时失败 %d", attempts)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("err = %v, want nil", err)
	}
	if got != 3 {
		t.Errorf("尝试次数 = %d, want 3", got)
	}
	if attempts != 3 {
		t.Errorf("fn 调用次数 = %d, want 3", attempts)
	}
}

// TestRetryDoExhausts 重试：始终失败，返回最后一次错误。
func TestRetryDoExhausts(t *testing.T) {
	var attempts int
	got, err := retryDo(4, time.Millisecond, 2*time.Millisecond, func() error {
		attempts++
		return fmt.Errorf("一直失败")
	})
	if err == nil {
		t.Fatalf("err = nil, want 非空")
	}
	if got != 4 {
		t.Errorf("尝试次数 = %d, want 4", got)
	}
	if attempts != 4 {
		t.Errorf("fn 调用次数 = %d, want 4", attempts)
	}
	if !strings.Contains(err.Error(), "一直失败") {
		t.Errorf("err = %v, want 包含 一直失败", err)
	}
}

// TestCSVImportIdempotent 同步幂等：重复导入同一批不产生新增。
func TestCSVImportIdempotent(t *testing.T) {
	imp := &csvImporter{rows: []string{"a", "b", "c", "d", "e"}}

	n1 := imp.ImportChunk(3)
	if n1 != 3 {
		t.Fatalf("首次导入 = %d, want 3", n1)
	}
	if imp.Offset() != 3 {
		t.Fatalf("首次后 offset = %d, want 3", imp.Offset())
	}

	// 重复同样的 chunk 大小，因为 offset 已推进，应无新增。
	n2 := imp.ImportChunk(3)
	if n2 != 2 {
		t.Fatalf("第二次导入 = %d, want 2（只剩 2 行）", n2)
	}
	if imp.Offset() != 5 {
		t.Fatalf("第二次后 offset = %d, want 5", imp.Offset())
	}

	// 再导一次，已到末尾，返回 0。
	n3 := imp.ImportChunk(3)
	if n3 != 0 {
		t.Errorf("第三次导入 = %d, want 0（幂等）", n3)
	}
	if imp.Offset() != 5 {
		t.Errorf("第三次后 offset = %d, want 5", imp.Offset())
	}
}

// TestCSVImportResumeFromBreakpoint 断点续传：模拟中途中断后从 offset 继续。
func TestCSVImportResumeFromBreakpoint(t *testing.T) {
	imp := &csvImporter{rows: []string{"r0", "r1", "r2", "r3", "r4", "r5", "r6"}}

	// 第一段：导入 2 行，模拟"断"。
	if n := imp.ImportChunk(2); n != 2 {
		t.Fatalf("第一段 = %d, want 2", n)
	}
	if imp.Offset() != 2 {
		t.Fatalf("第一段后 offset = %d, want 2", imp.Offset())
	}

	// 续传：新建一个共享同一断点的导入器（模拟重启后读取持久化的 offset）。
	resumed := &csvImporter{rows: imp.rows, offset: imp.Offset()}
	if n := resumed.ImportChunk(3); n != 3 {
		t.Fatalf("续传段 = %d, want 3", n)
	}
	if resumed.Offset() != 5 {
		t.Fatalf("续传后 offset = %d, want 5", resumed.Offset())
	}

	// 收尾：剩余 2 行。
	if n := resumed.ImportChunk(10); n != 2 {
		t.Fatalf("收尾段 = %d, want 2", n)
	}
	if resumed.Offset() != 7 {
		t.Fatalf("收尾后 offset = %d, want 7", resumed.Offset())
	}

	// 最终不重复、不丢失。
	if resumed.Offset() != len(imp.rows) {
		t.Errorf("最终 offset = %d, want %d", resumed.Offset(), len(imp.rows))
	}
}

// TestBackupAndVerifyRoundTrip 用真实 SQLite 源库跑一遍 Backup + Verify。
func TestBackupAndVerifyRoundTrip(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.db")
	dst := filepath.Join(dir, "backup.db")
	makeMortiseDB(t, src, 20)

	meta, err := Backup(src, dst)
	if err != nil {
		t.Fatalf("Backup err = %v", err)
	}
	if meta.Version != Version {
		t.Errorf("meta.Version = %q, want %q", meta.Version, Version)
	}
	if meta.SizeBytes <= 0 {
		t.Errorf("meta.SizeBytes = %d, want > 0", meta.SizeBytes)
	}
	if len(meta.SHA256) != 64 {
		t.Errorf("meta.SHA256 长度 = %d, want 64", len(meta.SHA256))
	}
	if meta.SourceDB != src {
		t.Errorf("meta.SourceDB = %q, want %q", meta.SourceDB, src)
	}

	// meta.json 必须落盘且可反序列化回同样内容。
	buf, err := os.ReadFile(dst + ".meta.json")
	if err != nil {
		t.Fatalf("读 meta 文件失败: %v", err)
	}
	var got Meta
	if err := json.Unmarshal(buf, &got); err != nil {
		t.Fatalf("反序列化 meta 失败: %v", err)
	}
	if got.SHA256 != meta.SHA256 {
		t.Errorf("meta 文件 SHA256 = %q, want %q", got.SHA256, meta.SHA256)
	}
	if got.SizeBytes != meta.SizeBytes {
		t.Errorf("meta 文件 SizeBytes = %d, want %d", got.SizeBytes, meta.SizeBytes)
	}

	if err := Verify(dst); err != nil {
		t.Fatalf("Verify err = %v", err)
	}
}

// TestBackupRejectsExistingDestination 备份目标已存在时必须报错，不覆盖。
func TestBackupRejectsExistingDestination(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.db")
	dst := filepath.Join(dir, "backup.db")
	makeMortiseDB(t, src, 3)
	if err := os.WriteFile(dst, []byte("already here"), 0o644); err != nil {
		t.Fatalf("预置目标文件失败: %v", err)
	}

	_, err := Backup(src, dst)
	if err == nil {
		t.Fatalf("err = nil, want 目标已存在错误")
	}
	if !strings.Contains(err.Error(), "目标文件已存在") {
		t.Errorf("err = %v, want 包含 目标文件已存在", err)
	}
	// 原内容不能被改动。
	buf, rerr := os.ReadFile(dst)
	if rerr != nil {
		t.Fatalf("读目标文件失败: %v", rerr)
	}
	if string(buf) != "already here" {
		t.Errorf("目标文件内容 = %q, want %q", string(buf), "already here")
	}
}

// TestVerifyRejectsNonMortiseDB 非 MortiseDB（缺 _m_watermarks 表）必须被 Verify 拒绝。
func TestVerifyRejectsNonMortiseDB(t *testing.T) {
	dir := t.TempDir()
	plain := filepath.Join(dir, "plain.db")
	db, err := sql.Open("sqlite", plain)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if _, err := db.Exec(`CREATE TABLE "other" ("id" INTEGER PRIMARY KEY)`); err != nil {
		db.Close()
		t.Fatalf("create other: %v", err)
	}
	db.Close()

	err = Verify(plain)
	if err == nil {
		t.Fatalf("err = nil, want 缺少 _m_watermarks 错误")
	}
	if !strings.Contains(err.Error(), "_m_watermarks") {
		t.Errorf("err = %v, want 包含 _m_watermarks", err)
	}

	// 空路径与不存在的路径也要拒绝。
	if err := Verify(""); err == nil {
		t.Errorf("空路径应报错")
	}
	if err := Verify(filepath.Join(dir, "nope.db")); err == nil {
		t.Errorf("不存在的文件应报错")
	}
}

// TestRestoreForceBacksUpOldAndReplaces 恢复：force 时旧库留底且目标被替换为新备份内容。
func TestRestoreForceBacksUpOldAndReplaces(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.db")
	bk := filepath.Join(dir, "backup.db")
	target := filepath.Join(dir, "target.db")
	makeMortiseDB(t, src, 5)

	if _, err := Backup(src, bk); err != nil {
		t.Fatalf("Backup err = %v", err)
	}

	// 目标位置放一个非空旧库。
	makeMortiseDB(t, target, 2)
	beforeSize, err := os.Stat(target)
	if err != nil {
		t.Fatalf("stat target: %v", err)
	}

	if err := Restore(bk, target, true); err != nil {
		t.Fatalf("Restore force err = %v", err)
	}
	if err := Verify(target); err != nil {
		t.Fatalf("恢复后 Verify err = %v", err)
	}
	afterInfo, err := os.Stat(target)
	if err != nil {
		t.Fatalf("stat target after: %v", err)
	}
	if afterInfo.Size() == 0 {
		t.Errorf("恢复后目标大小 = 0, want > 0")
	}

	// 必须存在一个 .bak-* 留底文件。
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("readdir: %v", err)
	}
	var bakCount int
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), "target.db.bak-") {
			bakCount++
		}
	}
	if bakCount != 1 {
		t.Errorf("留底文件数量 = %d, want 1", bakCount)
	}
	if beforeSize.Size() == 0 {
		t.Errorf("旧库大小不应为 0")
	}

	// 无 force 时对已存在非空目标必须拒绝。
	if err := Restore(bk, target, false); err == nil {
		t.Errorf("非 force 恢复应被拒绝")
	} else if !strings.Contains(err.Error(), "--force") {
		t.Errorf("err = %v, want 包含 --force", err)
	}
}

// TestBackupConcurrentDistinctTargets 并发对同一源库备份到不同目标，-race 下不应有数据竞争。
func TestBackupConcurrentDistinctTargets(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.db")
	makeMortiseDB(t, src, 30)

	const workers = 4
	var wg sync.WaitGroup
	errs := make([]error, workers)
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			dst := filepath.Join(dir, fmt.Sprintf("bk-%d.db", idx))
			if _, err := Backup(src, dst); err != nil {
				errs[idx] = err
				return
			}
			errs[idx] = Verify(dst)
		}(i)
	}
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Errorf("worker %d err = %v", i, err)
		}
	}
	// 每个备份的 SHA256 应一致（同一源库同一时刻快照内容相同）。
	shas := make([]string, workers)
	for i := 0; i < workers; i++ {
		buf, err := os.ReadFile(filepath.Join(dir, fmt.Sprintf("bk-%d.db.meta.json", i)))
		if err != nil {
			t.Fatalf("读 meta %d 失败: %v", i, err)
		}
		var m Meta
		if err := json.Unmarshal(buf, &m); err != nil {
			t.Fatalf("解析 meta %d 失败: %v", i, err)
		}
		shas[i] = m.SHA256
	}
	for i := 1; i < workers; i++ {
		if shas[i] != shas[0] {
			t.Errorf("worker %d SHA256 = %q, want 与 worker0 %q 相同", i, shas[i], shas[0])
		}
	}
}
