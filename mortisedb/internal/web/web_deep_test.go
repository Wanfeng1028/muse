package web

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io/fs"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"
)

// fakeClock 用可控时间推进模拟退避等待，不真实 sleep。
type fakeClock struct {
	mu   sync.Mutex
	now  time.Time
	logs []time.Duration
}

func newFakeClock() *fakeClock {
	return &fakeClock{now: time.Unix(0, 0)}
}

func (c *fakeClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *fakeClock) Sleep(d time.Duration) {
	c.mu.Lock()
	c.logs = append(c.logs, d)
	c.now = c.now.Add(d)
	c.mu.Unlock()
}

func (c *fakeClock) Waits() []time.Duration {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]time.Duration, len(c.logs))
	copy(out, c.logs)
	return out
}

// record 模拟同步导入的记录，用于幂等与断点续传判断。
type record struct {
	Key   string
	Value string
}

// assembler 模拟多源拼装：同名 key 由多个来源提供，先到先得，冲突记录下来。
type assembler struct {
	mu       sync.Mutex
	values   map[string]string
	source   map[string]string
	conflict []string
}

func newAssembler() *assembler {
	return &assembler{
		values: make(map[string]string),
		source: make(map[string]string),
	}
}

func (a *assembler) Put(src, key, value string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if old, ok := a.values[key]; ok {
		if old != value {
			a.conflict = append(a.conflict, key+"@"+a.source[key]+"!="+src)
		}
		return
	}
	a.values[key] = value
	a.source[key] = src
}

func (a *assembler) Get(key string) (string, bool) {
	a.mu.Lock()
	defer a.mu.Unlock()
	v, ok := a.values[key]
	return v, ok
}

func (a *assembler) Conflicts() []string {
	a.mu.Lock()
	defer a.mu.Unlock()
	out := make([]string, len(a.conflict))
	copy(out, a.conflict)
	return out
}

// retry 用固定次数与退避函数重试操作，成功即停，返回调用次数。
func retry(clock *fakeClock, attempts int, base time.Duration, op func(attempt int) error) (int, error) {
	var last error
	for i := 1; i <= attempts; i++ {
		if err := op(i); err == nil {
			return i, nil
		} else {
			last = err
		}
		if i < attempts {
			clock.Sleep(base * time.Duration(1<<uint(i-1)))
		}
	}
	return attempts, last
}

// hmacHex 计算 HMAC-SHA256 十六进制签名（测试辅助）。
func hmacHex(secret, body []byte) string {
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

// verifyWebhook 按 HMAC 规则做常量时间比较，覆盖边界。
func verifyWebhook(secret []byte, body []byte, sig string) bool {
	if len(secret) == 0 || len(sig) == 0 {
		return false
	}
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	want := hex.EncodeToString(mac.Sum(nil))
	if len(want) != len(sig) {
		return false
	}
	var diff byte
	for i := 0; i < len(want); i++ {
		diff |= want[i] ^ sig[i]
	}
	return diff == 0
}

func TestStaticFSReturnsEmbeddedWebUI(t *testing.T) {
	fsys := StaticFS()
	if fsys == nil {
		t.Fatal("StaticFS 返回 nil")
	}
	entries, err := fs.ReadDir(fsys, ".")
	if err != nil {
		t.Fatalf("读取内嵌目录失败: %v", err)
	}
	if len(entries) == 0 {
		t.Fatal("内嵌 webui 目录为空")
	}
	for _, e := range entries {
		if strings.Contains(e.Name(), "..") {
			t.Fatalf("目录项包含非法名: %q", e.Name())
		}
	}
}

func TestStaticFSIsSubOfWebUI(t *testing.T) {
	fsys := StaticFS()
	_, err := fs.Stat(fsys, "index.html")
	if err != nil {
		t.Fatalf("期望存在 index.html: %v", err)
	}
	sub, err := fs.Sub(embedded, "webui")
	if err != nil {
		t.Fatalf("fs.Sub 失败: %v", err)
	}
	got, err := fs.Stat(fsys, "index.html")
	if err != nil {
		t.Fatalf("再次 Stat 失败: %v", err)
	}
	want, err := fs.Stat(sub, "index.html")
	if err != nil {
		t.Fatalf("对照 Stat 失败: %v", err)
	}
	if got.Name() != want.Name() || got.Size() != want.Size() {
		t.Fatalf("StaticFS 与 webui 子目录不一致: %+v vs %+v", got, want)
	}
}

func TestAssemblerFirstSourceWinsAndRecordsConflict(t *testing.T) {
	a := newAssembler()
	a.Put("srcA", "host", "10.0.0.1")
	a.Put("srcB", "host", "10.0.0.2")
	a.Put("srcB", "port", "8080")

	host, ok := a.Get("host")
	if !ok {
		t.Fatal("host 应存在")
	}
	if host != "10.0.0.1" {
		t.Fatalf("同 key 冲突时应保留先到值, got=%q", host)
	}
	port, ok := a.Get("port")
	if !ok || port != "8080" {
		t.Fatalf("port 应来自 srcB, got=%q ok=%v", port, ok)
	}
	conf := a.Conflicts()
	if len(conf) != 1 {
		t.Fatalf("冲突数期望 1, got=%d %v", len(conf), conf)
	}
	if conf[0] != "host@srcA!=srcB" {
		t.Fatalf("冲突记录内容不符, got=%q", conf[0])
	}
}

func TestAssemblerSameValueNoConflict(t *testing.T) {
	a := newAssembler()
	a.Put("srcA", "region", "cn")
	a.Put("srcB", "region", "cn")
	if len(a.Conflicts()) != 0 {
		t.Fatalf("同值不应记录冲突, got=%v", a.Conflicts())
	}
	v, _ := a.Get("region")
	if v != "cn" {
		t.Fatalf("region 值应为 cn, got=%q", v)
	}
}

func TestAssemblerConcurrentPutRaceSafe(t *testing.T) {
	a := newAssembler()
	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			a.Put("src", "k", "v")
			_ = a.Conflicts()
			_, _ = a.Get("k")
		}(i)
	}
	wg.Wait()
	v, ok := a.Get("k")
	if !ok || v != "v" {
		t.Fatalf("并发写入后 k 应稳定为 v, got=%q ok=%v", v, ok)
	}
	if len(a.Conflicts()) != 0 {
		t.Fatalf("同值并发不应产生冲突, got=%v", a.Conflicts())
	}
}

func TestWebhookVerifyAcceptsCorrectSignature(t *testing.T) {
	secret := []byte("s3cr3t")
	body := []byte(`{"event":"push"}`)
	sig := hmacHex(secret, body)
	if !verifyWebhook(secret, body, sig) {
		t.Fatal("正确签名应通过")
	}
	if verifyWebhook(secret, []byte(`{"event":"pull"}`), sig) {
		t.Fatal("body 改动后签名应失败")
	}
	if verifyWebhook([]byte("other"), body, sig) {
		t.Fatal("secret 改动后签名应失败")
	}
}

func TestWebhookVerifyBoundaryEmptyAndShortSig(t *testing.T) {
	secret := []byte("k")
	body := []byte("x")
	good := hmacHex(secret, body)
	if verifyWebhook(nil, body, good) {
		t.Fatal("空 secret 应拒绝")
	}
	if verifyWebhook(secret, body, "") {
		t.Fatal("空签名应拒绝")
	}
	if verifyWebhook(secret, body, good[:len(good)-1]) {
		t.Fatal("短签名应拒绝")
	}
	if verifyWebhook(secret, body, good+"0") {
		t.Fatal("长签名应拒绝")
	}
}

func TestRetryBackoffDoublesAndStopsOnSuccess(t *testing.T) {
	clock := newFakeClock()
	attempts, err := retry(clock, 4, 10*time.Millisecond, func(attempt int) error {
		if attempt < 3 {
			return errors.New("boom")
		}
		return nil
	})
	if err != nil {
		t.Fatalf("第三次应成功, err=%v", err)
	}
	if attempts != 3 {
		t.Fatalf("调用次数期望 3, got=%d", attempts)
	}
	waits := clock.Waits()
	want := []time.Duration{10 * time.Millisecond, 20 * time.Millisecond}
	if len(waits) != len(want) {
		t.Fatalf("退避次数期望 %d, got=%d %v", len(want), len(waits), waits)
	}
	for i := range want {
		if waits[i] != want[i] {
			t.Fatalf("第 %d 次退避期望 %v, got=%v", i+1, want[i], waits[i])
		}
	}
}

func TestRetryExhaustsAndReturnsLastError(t *testing.T) {
	clock := newFakeClock()
	sentinel := errors.New("always")
	attempts, err := retry(clock, 3, time.Millisecond, func(int) error { return sentinel })
	if attempts != 3 {
		t.Fatalf("调用次数期望 3, got=%d", attempts)
	}
	if !errors.Is(err, sentinel) {
		t.Fatalf("应返回最后一次错误, got=%v", err)
	}
	waits := clock.Waits()
	if len(waits) != 2 {
		t.Fatalf("3 次尝试应退避 2 次, got=%d %v", len(waits), waits)
	}
	if waits[0] != time.Millisecond || waits[1] != 2*time.Millisecond {
		t.Fatalf("退避序列不符, got=%v", waits)
	}
}

// syncer 用主键做幂等：重复 key 跳过，返回本次实际导入的条数。
func syncOnce(applied map[string]record, batch []record) int {
	n := 0
	for _, r := range batch {
		if _, ok := applied[r.Key]; ok {
			continue
		}
		applied[r.Key] = r
		n++
	}
	return n
}

func TestSyncIdempotentOnReplay(t *testing.T) {
	applied := make(map[string]record)
	batch := []record{
		{Key: "a", Value: "1"},
		{Key: "b", Value: "2"},
		{Key: "c", Value: "3"},
	}
	first := syncOnce(applied, batch)
	second := syncOnce(applied, batch)
	if first != 3 {
		t.Fatalf("首次导入期望 3, got=%d", first)
	}
	if second != 0 {
		t.Fatalf("重放应幂等为 0, got=%d", second)
	}
	if len(applied) != 3 {
		t.Fatalf("去重后应保留 3 条, got=%d", len(applied))
	}
	if applied["b"].Value != "2" {
		t.Fatalf("b 的值应为 2, got=%q", applied["b"].Value)
	}
}

func TestSyncIdempotentPartialOverlap(t *testing.T) {
	applied := make(map[string]record)
	if n := syncOnce(applied, []record{{Key: "a", Value: "1"}}); n != 1 {
		t.Fatalf("首批期望 1, got=%d", n)
	}
	batch := []record{
		{Key: "a", Value: "1"},
		{Key: "b", Value: "2"},
	}
	if n := syncOnce(applied, batch); n != 1 {
		t.Fatalf("重叠批应只导入新增 1 条, got=%d", n)
	}
	if applied["a"].Value != "1" || applied["b"].Value != "2" {
		t.Fatalf("重叠批结果不符: %+v", applied)
	}
}

// csvResume 模拟 CSV 增量导入：记录已消费行号，续传从断点继续。
type csvResume struct {
	mu     sync.Mutex
	offset int
	seen   []string
}

func (c *csvResume) Import(rows []string) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	start := c.offset
	if start > len(rows) {
		start = len(rows)
	}
	for i := start; i < len(rows); i++ {
		c.seen = append(c.seen, rows[i])
	}
	c.offset = len(rows)
	return c.offset - start
}

func (c *csvResume) Offset() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.offset
}

func (c *csvResume) Seen() []string {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]string, len(c.seen))
	copy(out, c.seen)
	return out
}

func TestCSVResumeFromCheckpoint(t *testing.T) {
	c := &csvResume{}
	rows := []string{"r1", "r2", "r3", "r4", "r5"}
	if n := c.Import(rows[:2]); n != 2 {
		t.Fatalf("首次导入期望 2, got=%d", n)
	}
	if c.Offset() != 2 {
		t.Fatalf("断点应为 2, got=%d", c.Offset())
	}
	if n := c.Import(rows); n != 3 {
		t.Fatalf("续传期望 3, got=%d", n)
	}
	got := c.Seen()
	want := []string{"r1", "r2", "r3", "r4", "r5"}
	if len(got) != len(want) {
		t.Fatalf("累计消费期望 %d, got=%d %v", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("第 %d 行期望 %q, got=%q", i, want[i], got[i])
		}
	}
}

func TestCSVResumeNoDuplicateOnReplay(t *testing.T) {
	c := &csvResume{}
	rows := []string{"a", "b", "c"}
	c.Import(rows)
	replay := c.Import(rows)
	if replay != 0 {
		t.Fatalf("同一文件重放应导入 0, got=%d", replay)
	}
	seen := c.Seen()
	sort.Strings(seen)
	if len(seen) != 3 {
		t.Fatalf("累计消费应为 3 条, got=%d %v", len(seen), seen)
	}
	if seen[0] != "a" || seen[1] != "b" || seen[2] != "c" {
		t.Fatalf("消费内容不符: %v", seen)
	}
}