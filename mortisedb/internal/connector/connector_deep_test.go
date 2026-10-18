package connector

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
)

// ---------------- 辅助函数 ----------------

func writeCSVFile(t *testing.T, path string, header []string, rows [][]string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatalf("创建 csv 文件失败: %v", err)
	}
	defer f.Close()
	w := csv.NewWriter(f)
	if err := w.Write(header); err != nil {
		t.Fatalf("写入 csv 表头失败: %v", err)
	}
	for _, r := range rows {
		if err := w.Write(r); err != nil {
			t.Fatalf("写入 csv 行失败: %v", err)
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		t.Fatalf("flush csv 失败: %v", err)
	}
}

func writeJSONFile(t *testing.T, path string, data any) {
	t.Helper()
	b, err := json.Marshal(data)
	if err != nil {
		t.Fatalf("序列化 json 失败: %v", err)
	}
	if err := os.WriteFile(path, b, 0o644); err != nil {
		t.Fatalf("写入 json 文件失败: %v", err)
	}
}

// ---------------- 多源拼装冲突（同 key 不同值） ----------------

func TestMergeRowsSameKeyConflictLastWins(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	csvB := filepath.Join(dir, "b.csv")
	writeCSVFile(t, csvA, []string{"id", "name"}, [][]string{{"1", "alice"}})
	writeCSVFile(t, csvB, []string{"id", "name"}, [][]string{{"1", "bob"}})

	srcA, err := Open(config.SourceConfig{
		Name: "a", Type: "csv", Path: csvA, Table: "t", PrimaryKey: "id",
	})
	if err != nil {
		t.Fatalf("打开 csv 源 a 失败: %v", err)
	}
	defer srcA.Close()
	srcB, err := Open(config.SourceConfig{
		Name: "b", Type: "csv", Path: csvB, Table: "t", PrimaryKey: "id",
	})
	if err != nil {
		t.Fatalf("打开 csv 源 b 失败: %v", err)
	}
	defer srcB.Close()

	rowsA, err := srcA.Rows("t", nil)
	if err != nil {
		t.Fatalf("读取源 a 行失败: %v", err)
	}
	rowsB, err := srcB.Rows("t", nil)
	if err != nil {
		t.Fatalf("读取源 b 行失败: %v", err)
	}
	if len(rowsA) != 1 || len(rowsB) != 1 {
		t.Fatalf("源行数不对: a=%d b=%d", len(rowsA), len(rowsB))
	}

	merged := make(map[string]Row)
	for _, r := range rowsA {
		merged["1"] = r
	}
	for _, r := range rowsB {
		merged["1"] = r
	}

	if len(merged) != 1 {
		t.Fatalf("同 key 合并后应只有 1 行, 实际 %d", len(merged))
	}
	got := merged["1"]
	if got["name"] != "bob" {
		t.Fatalf("后写入的源应覆盖前值, 期望 bob, 实际 %v", got["name"])
	}
	if got["id"] != int64(1) {
		t.Fatalf("主键列应为 int64(1), 实际 %T(%v)", got["id"], got["id"])
	}
}

func TestMergeRowsDistinctKeysNoConflict(t *testing.T) {
	dir := t.TempDir()
	csvA := filepath.Join(dir, "a.csv")
	csvB := filepath.Join(dir, "b.csv")
	writeCSVFile(t, csvA, []string{"id", "name"}, [][]string{{"1", "alice"}})
	writeCSVFile(t, csvB, []string{"id", "name"}, [][]string{{"2", "bob"}})

	srcA, err := Open(config.SourceConfig{
		Name: "a", Type: "csv", Path: csvA, Table: "t", PrimaryKey: "id",
	})
	if err != nil {
		t.Fatalf("打开 csv 源 a 失败: %v", err)
	}
	defer srcA.Close()
	srcB, err := Open(config.SourceConfig{
		Name: "b", Type: "csv", Path: csvB, Table: "t", PrimaryKey: "id",
	})
	if err != nil {
		t.Fatalf("打开 csv 源 b 失败: %v", err)
	}
	defer srcB.Close()

	rowsA, err := srcA.Rows("t", nil)
	if err != nil {
		t.Fatalf("读取源 a 行失败: %v", err)
	}
	rowsB, err := srcB.Rows("t", nil)
	if err != nil {
		t.Fatalf("读取源 b 行失败: %v", err)
	}

	merged := make(map[string]Row)
	for _, r := range rowsA {
		merged[fmt.Sprint(r["id"])] = r
	}
	for _, r := range rowsB {
		merged[fmt.Sprint(r["id"])] = r
	}

	if len(merged) != 2 {
		t.Fatalf("不同 key 应保留 2 行, 实际 %d", len(merged))
	}
	if merged["1"]["name"] != "alice" {
		t.Fatalf("key=1 的 name 期望 alice, 实际 %v", merged["1"]["name"])
	}
	if merged["2"]["name"] != "bob" {
		t.Fatalf("key=2 的 name 期望 bob, 实际 %v", merged["2"]["name"])
	}
}

// ---------------- HMAC Webhook 验签边界 ----------------

type hmacVerifier struct {
	secret []byte
}

func (v hmacVerifier) sign(body []byte) string {
	m := hmac.New(sha256.New, v.secret)
	m.Write(body)
	return hex.EncodeToString(m.Sum(nil))
}

func (v hmacVerifier) verify(body []byte, sig string) bool {
	want := v.sign(body)
	return hmac.Equal([]byte(want), []byte(sig))
}

func TestHMACVerifyValidSignature(t *testing.T) {
	v := hmacVerifier{secret: []byte("s3cr3t")}
	body := []byte(`{"event":"sync","id":7}`)
	sig := v.sign(body)

	if !v.verify(body, sig) {
		t.Fatalf("合法签名应验签通过")
	}
	if len(sig) != 64 {
		t.Fatalf("sha256 十六进制长度应为 64, 实际 %d", len(sig))
	}
	if v.verify(body, strings.ToUpper(sig)) {
		t.Fatalf("大小写不同的十六进制在 hmac.Equal 逐字节比较下应视为不通过")
	}
}

func TestHMACVerifyTamperedBody(t *testing.T) {
	v := hmacVerifier{secret: []byte("s3cr3t")}
	body := []byte(`{"event":"sync","id":7}`)
	sig := v.sign(body)
	tampered := []byte(`{"event":"sync","id":8}`)

	if v.verify(tampered, sig) {
		t.Fatalf("被篡改的 body 不应验签通过")
	}
	if v.verify(body, sig) != true {
		t.Fatalf("原始 body 应验签通过")
	}
}

func TestHMACVerifyEmptyAndWrongSecret(t *testing.T) {
	v1 := hmacVerifier{secret: []byte("s3cr3t")}
	v2 := hmacVerifier{secret: []byte("other")}
	body := []byte("payload")

	if v1.verify(body, "") {
		t.Fatalf("空签名不应通过")
	}
	sig1 := v1.sign(body)
	if v2.verify(body, sig1) {
		t.Fatalf("不同密钥签出的签名不应通过")
	}
	if !v1.verify(body, sig1) {
		t.Fatalf("同密钥签名应通过")
	}
}

// ---------------- 重试退避 ----------------

type backoff struct {
	base   time.Duration
	factor float64
	max    time.Duration
}

func (b backoff) delay(attempt int) time.Duration {
	if attempt <= 1 {
		return b.base
	}
	d := float64(b.base)
	for i := 1; i < attempt; i++ {
		d *= b.factor
	}
	if d > float64(b.max) {
		return b.max
	}
	return time.Duration(d)
}

func TestBackoffDelayGrowsExponentially(t *testing.T) {
	b := backoff{base: 100 * time.Millisecond, factor: 2.0, max: 2 * time.Second}

	if got := b.delay(1); got != 100*time.Millisecond {
		t.Fatalf("第 1 次退避期望 100ms, 实际 %v", got)
	}
	if got := b.delay(2); got != 200*time.Millisecond {
		t.Fatalf("第 2 次退避期望 200ms, 实际 %v", got)
	}
	if got := b.delay(3); got != 400*time.Millisecond {
		t.Fatalf("第 3 次退避期望 400ms, 实际 %v", got)
	}
	if got := b.delay(4); got != 800*time.Millisecond {
		t.Fatalf("第 4 次退避期望 800ms, 实际 %v", got)
	}
}

func TestBackoffDelayCappedAtMax(t *testing.T) {
	b := backoff{base: 100 * time.Millisecond, factor: 2.0, max: 2 * time.Second}

	for attempt := 1; attempt <= 20; attempt++ {
		d := b.delay(attempt)
		if d > b.max {
			t.Fatalf("第 %d 次退避 %v 超过上限 %v", attempt, d, b.max)
		}
	}
	if got := b.delay(10); got != b.max {
		t.Fatalf("第 10 次退避应触顶 %v, 实际 %v", b.max, got)
	}
}

type retryRunner struct {
	failures int32
	calls    int32
	delays   []time.Duration
}

func (r *retryRunner) run(maxAttempts int, b backoff, fn func() error) error {
	var lastErr error
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		atomic.AddInt32(&r.calls, 1)
		if err := fn(); err != nil {
			lastErr = err
			if attempt < maxAttempts {
				r.delays = append(r.delays, b.delay(attempt))
			}
			continue
		}
		return nil
	}
	return lastErr
}

func TestRetrySucceedsAfterTransientFailures(t *testing.T) {
	r := &retryRunner{failures: 2}
	b := backoff{base: 1 * time.Millisecond, factor: 2.0, max: 10 * time.Millisecond}

	err := r.run(5, b, func() error {
		if atomic.AddInt32(&r.failures, -1) >= 0 {
			return errTransient
		}
		return nil
	})
	if err != nil {
		t.Fatalf("预期重试后成功, 实际错误 %v", err)
	}
	if got := atomic.LoadInt32(&r.calls); got != 3 {
		t.Fatalf("预期调用 3 次 (2 次失败 + 1 次成功), 实际 %d", got)
	}
	if len(r.delays) != 2 {
		t.Fatalf("预期 2 次退避记录, 实际 %d", len(r.delays))
	}
	if r.delays[0] != 1*time.Millisecond || r.delays[1] != 2*time.Millisecond {
		t.Fatalf("退避序列期望 [1ms 2ms], 实际 %v", r.delays)
	}
}

type transientErr struct{}

func (transientErr) Error() string { return "transient" }

var errTransient = transientErr{}

func TestRetryExhaustsAttempts(t *testing.T) {
	r := &retryRunner{}
	b := backoff{base: 1 * time.Millisecond, factor: 2.0, max: 10 * time.Millisecond}

	err := r.run(3, b, func() error {
		return errTransient
	})
	if err == nil {
		t.Fatalf("全部失败时应返回错误")
	}
	if got := atomic.LoadInt32(&r.calls); got != 3 {
		t.Fatalf("预期调用 3 次, 实际 %d", got)
	}
	if len(r.delays) != 2 {
		t.Fatalf("最后一次失败不应记录退避, 预期 2 次, 实际 %d", len(r.delays))
	}
}

// ---------------- 同步幂等 ----------------

type idempotentSink struct {
	mu   sync.Mutex
	keys map[string]int
	rows int
}

func (s *idempotentSink) apply(row Row, primary string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	k, _ := row[primary].(string)
	if k == "" {
		if v, ok := row[primary].(int64); ok {
			k = int64ToString(v)
		}
	}
	if _, ok := s.keys[k]; ok {
		return
	}
	s.keys[k] = 1
	s.rows++
}

func int64ToString(v int64) string {
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

func TestSyncIdempotentReplaySameBatch(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "in.csv")
	writeCSVFile(t, p, []string{"id", "name"}, [][]string{
		{"1", "alice"},
		{"2", "bob"},
	})

	src, err := Open(config.SourceConfig{
		Name: "in", Type: "csv", Path: p, Table: "t", PrimaryKey: "id",
	})
	if err != nil {
		t.Fatalf("打开 csv 失败: %v", err)
	}
	defer src.Close()

	sink := &idempotentSink{keys: map[string]int{}}
	for round := 0; round < 3; round++ {
		rows, err := src.Rows("t", nil)
		if err != nil {
			t.Fatalf("第 %d 轮读取失败: %v", round, err)
		}
		for _, r := range rows {
			sink.apply(r, "id")
		}
	}

	if sink.rows != 2 {
		t.Fatalf("幂等同步 3 轮后应只有 2 行, 实际 %d", sink.rows)
	}
	if len(sink.keys) != 2 {
		t.Fatalf("应记录 2 个主键, 实际 %d", len(sink.keys))
	}
}

func TestSyncIdempotentConcurrentApply(t *testing.T) {
	sink := &idempotentSink{keys: map[string]int{}}
	rows := []Row{
		{"id": "1", "name": "alice"},
		{"id": "2", "name": "bob"},
		{"id": "3", "name": "carol"},
	}

	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for _, r := range rows {
				sink.apply(r, "id")
			}
		}()
	}
	wg.Wait()

	if sink.rows != 3 {
		t.Fatalf("并发幂等应用后应只有 3 行, 实际 %d", sink.rows)
	}
	if len(sink.keys) != 3 {
		t.Fatalf("应记录 3 个主键, 实际 %d", len(sink.keys))
	}
}

// ---------------- CSV 增量导入断点续传 ----------------

type cursorStore struct {
	mu     sync.Mutex
	cursor string
}

func (c *cursorStore) load() string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.cursor
}

func (c *cursorStore) save(v string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.cursor = v
}

func TestCSVIncrementalResumeFromCheckpoint(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "inc.csv")
	writeCSVFile(t, p, []string{"id", "name", "updated_at"}, [][]string{
		{"1", "alice", "2024-01-01"},
		{"2", "bob", "2024-01-02"},
		{"3", "carol", "2024-01-03"},
	})

	src, err := Open(config.SourceConfig{
		Name: "inc", Type: "csv", Path: p, Table: "t", PrimaryKey: "id",
	})
	if err != nil {
		t.Fatalf("打开 csv 失败: %v", err)
	}
	defer src.Close()

	store := &cursorStore{}

	first, err := src.Rows("t", map[string]string{"updated_at": "2024-01-01"})
	if err != nil {
		t.Fatalf("首轮增量读取失败: %v", err)
	}
	if len(first) != 2 {
		t.Fatalf("since=2024-01-01 应读到 2 行, 实际 %d", len(first))
	}
	store.save("2024-01-02")

	resumed, err := src.Rows("t", map[string]string{"updated_at": store.load()})
	if err != nil {
		t.Fatalf("续传读取失败: %v", err)
	}
	if len(resumed) != 1 {
		t.Fatalf("从断点 2024-01-02 续传应读到 1 行, 实际 %d", len(resumed))
	}
	if resumed[0]["id"] != int64(3) {
		t.Fatalf("续传行主键期望 int64(3), 实际 %v", resumed[0]["id"])
	}
	if store.load() != "2024-01-02" {
		t.Fatalf("断点应保持 2024-01-02, 实际 %s", store.load())
	}
}

func TestCSVIncrementalNoNewRowsAfterFullSync(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "inc.csv")
	writeCSVFile(t, p, []string{"id", "name", "updated_at"}, [][]string{
		{"1", "alice", "2024-01-01"},
		{"2", "bob", "2024-01-02"},
	})

	src, err := Open(config.SourceConfig{
		Name: "inc", Type: "csv", Path: p, Table: "t", PrimaryKey: "id",
	})
	if err != nil {
		t.Fatalf("打开 csv 失败: %v", err)
	}
	defer src.Close()

	full, err := src.Rows("t", nil)
	if err != nil {
		t.Fatalf("全量读取失败: %v", err)
	}
	if len(full) != 2 {
		t.Fatalf("全量应 2 行, 实际 %d", len(full))
	}

	latest := ""
	for _, r := range full {
		if s, ok := r["updated_at"].(string); ok && s > latest {
			latest = s
		}
	}
	if latest != "2024-01-02T00:00:00Z" {
		t.Fatalf("最新断点期望 2024-01-02T00:00:00Z, 实际 %s", latest)
	}

	tail, err := src.Rows("t", map[string]string{"updated_at": latest})
	if err != nil {
		t.Fatalf("续传读取失败: %v", err)
	}
	if len(tail) != 0 {
		t.Fatalf("断点为最新时不应有新行, 实际 %d", len(tail))
	}
	if len(full) != 2 {
		t.Fatalf("全量结果不应被后续读取改变, 实际 %d", len(full))
	}
}

func TestCSVIncrementalSortedStableOrder(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "inc.csv")
	writeCSVFile(t, p, []string{"id", "updated_at"}, [][]string{
		{"1", "2024-01-01"},
		{"2", "2024-01-03"},
		{"3", "2024-01-02"},
	})

	src, err := Open(config.SourceConfig{
		Name: "inc", Type: "csv", Path: p, Table: "t", PrimaryKey: "id",
	})
	if err != nil {
		t.Fatalf("打开 csv 失败: %v", err)
	}
	defer src.Close()

	rows, err := src.Rows("t", map[string]string{"updated_at": "2024-01-01"})
	if err != nil {
		t.Fatalf("读取失败: %v", err)
	}
	ids := make([]string, 0, len(rows))
	for _, r := range rows {
		if s, ok := r["id"].(string); ok {
			ids = append(ids, s)
		} else {
			ids = append(ids, int64ToString(r["id"].(int64)))
		}
	}
	sort.Strings(ids)
	want := []string{"2", "3"}
	if len(ids) != len(want) {
		t.Fatalf("行数期望 %d, 实际 %d", len(want), len(ids))
	}
	for i := range want {
		if ids[i] != want[i] {
			t.Fatalf("排序后第 %d 项期望 %s, 实际 %s", i, want[i], ids[i])
		}
	}
}
