package main

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// ---------- 通用辅助 ----------

func writeTempFile(t *testing.T, dir, name, content string) string {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatalf("写文件 %s 失败: %v", p, err)
	}
	return p
}

func mkTempDir(t *testing.T) string {
	t.Helper()
	d, err := os.MkdirTemp("", "mortise-deep-")
	if err != nil {
		t.Fatalf("创建临时目录失败: %v", err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(d) })
	return d
}

// ---------- 多源拼装冲突：同 key 不同值，按 priority 决定胜者 ----------

// assembleConflict 用一个纯函数模拟主程序在 sync 拼装阶段的多源冲突裁决逻辑：
// 同一个 primary key 出现于多个源时，按 priority 列表顺序取优先级最高（列表靠前）的值。
// 返回胜者值以及被覆盖的次数。
func assembleConflict(records map[string]map[string]string, priority []string, key string) (string, int) {
	rank := make(map[string]int, len(priority))
	for i, name := range priority {
		rank[name] = i
	}
	winner := ""
	winnerRank := 1 << 30
	overridden := 0
	for src, fields := range records {
		v, ok := fields[key]
		if !ok {
			continue
		}
		r, known := rank[src]
		if !known {
			r = 1 << 29
		}
		if r < winnerRank {
			if winner != "" {
				overridden++
			}
			winner = v
			winnerRank = r
		} else {
			overridden++
		}
	}
	return winner, overridden
}

func TestAssembleConflictPriority(t *testing.T) {
	records := map[string]map[string]string{
		"orders_csv": {"order_id": "1001", "amount": "99.50"},
		"users_json": {"order_id": "1001", "amount": "88.00"},
		"legacy_xml": {"order_id": "1001", "amount": "77.00"},
	}
	priority := []string{"orders_csv", "users_json"}

	winner, overridden := assembleConflict(records, priority, "amount")
	if winner != "99.50" {
		t.Fatalf("期望优先源 orders_csv 胜出得到 99.50，实际 %q", winner)
	}
	if overridden < 2 {
		t.Fatalf("期望至少 2 个源被覆盖，实际 %d", overridden)
	}

	priority2 := []string{"legacy_xml", "users_json", "orders_csv"}
	winner2, _ := assembleConflict(records, priority2, "amount")
	if winner2 != "77.00" {
		t.Fatalf("调整 priority 后期望 legacy_xml 胜出得到 77.00，实际 %q", winner2)
	}
}

func TestAssembleConflictMissingKey(t *testing.T) {
	records := map[string]map[string]string{
		"orders_csv": {"order_id": "1001"},
		"users_json": {"user_id": "u001"},
	}
	winner, overridden := assembleConflict(records, []string{"orders_csv", "users_json"}, "amount")
	if winner != "" {
		t.Fatalf("无任何源含该 key 时期望空串，实际 %q", winner)
	}
	if overridden != 0 {
		t.Fatalf("无候选时不应有覆盖计数，实际 %d", overridden)
	}
}

// ---------- HMAC Webhook 验签边界 ----------

// verifyWebhook 模拟 serve 子命令中 Webhook 接收端的 HMAC-SHA256 验签。
// 签名头格式：sha256=<hex>；用 hmac.Equal 做定长比较防时序侧信道。
func verifyWebhook(secret []byte, body []byte, sigHeader string) bool {
	const prefix = "sha256="
	if !strings.HasPrefix(sigHeader, prefix) {
		return false
	}
	got, err := hex.DecodeString(sigHeader[len(prefix):])
	if err != nil {
		return false
	}
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	want := mac.Sum(nil)
	return hmac.Equal(got, want)
}

func signBody(secret, body []byte) string {
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	return "sha256=" + hex.EncodeToString(mac.Sum(nil))
}

func TestVerifyWebhookBoundaries(t *testing.T) {
	secret := []byte("mortise-secret-key")
	body := []byte(`{"event":"sync.done","job":"manual"}`)
	good := signBody(secret, body)

	if !verifyWebhook(secret, body, good) {
		t.Fatal("正确签名应验签通过")
	}
	if verifyWebhook(secret, body, "") {
		t.Fatal("空签名头必须拒绝")
	}
	if verifyWebhook(secret, body, "sha256=") {
		t.Fatal("只有前缀无 hex 必须拒绝")
	}
	if verifyWebhook(secret, body, "sha1="+good[len("sha256="):]) {
		t.Fatal("算法前缀不符必须拒绝")
	}
	if verifyWebhook(secret, body, "sha256=zzzz") {
		t.Fatal("非 hex 字符必须拒绝")
	}
	if verifyWebhook(secret, body, good[:len(good)-2]) {
		t.Fatal("截断的签名必须拒绝")
	}
	if verifyWebhook(secret, body, strings.ToUpper(good)) {
		t.Fatal("大小写不同（hex 大写）与原始签名不等，必须拒绝")
	}
	tampered := append([]byte{}, body...)
	tampered[0] = '{' + 1
	if verifyWebhook(secret, tampered, good) {
		t.Fatal("body 被篡改后必须拒绝")
	}
	if verifyWebhook([]byte("other-secret"), body, good) {
		t.Fatal("密钥不符必须拒绝")
	}
}

func TestWebhookHTTPHandler(t *testing.T) {
	secret := []byte("hook-secret")
	var mu sync.Mutex
	received := 0
	handler := func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		if !verifyWebhook(secret, b, r.Header.Get("X-Mortise-Signature")) {
			http.Error(w, "invalid signature", http.StatusUnauthorized)
			return
		}
		mu.Lock()
		received++
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}
	srv := httptest.NewServer(http.HandlerFunc(handler))
	defer srv.Close()

	body := []byte(`{"event":"csv.incremental"}`)
	req, err := http.NewRequest(http.MethodPost, srv.URL, bytes.NewReader(body))
	if err != nil {
		t.Fatalf("构造请求失败: %v", err)
	}
	req.Header.Set("X-Mortise-Signature", signBody(secret, body))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("请求失败: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("合法请求期望 200，实际 %d", resp.StatusCode)
	}

	badReq, _ := http.NewRequest(http.MethodPost, srv.URL, bytes.NewReader(body))
	badReq.Header.Set("X-Mortise-Signature", "sha256=deadbeef")
	badResp, err := http.DefaultClient.Do(badReq)
	if err != nil {
		t.Fatalf("非法请求失败: %v", err)
	}
	defer badResp.Body.Close()
	if badResp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("非法签名期望 401，实际 %d", badResp.StatusCode)
	}
	mu.Lock()
	got := received
	mu.Unlock()
	if got != 1 {
		t.Fatalf("只有合法请求应被计数，期望 1，实际 %d", got)
	}
}

// ---------- 重试退避 ----------

// backoff 计算第 attempt 次（从 0 开始）重试前的等待时长：base * 2^attempt，上限 cap。
func backoff(attempt int, base, cap time.Duration) time.Duration {
	if attempt < 0 {
		return base
	}
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

// retryDo 模拟主程序里的重试循环：返回实际尝试次数与最终错误。
func retryDo(maxAttempts int, base, cap time.Duration, sleep func(time.Duration), fn func(attempt int) error) (int, error) {
	var err error
	for i := 0; i < maxAttempts; i++ {
		err = fn(i)
		if err == nil {
			return i + 1, nil
		}
		if i < maxAttempts-1 {
			sleep(backoff(i, base, cap))
		}
	}
	return maxAttempts, err
}

func TestBackoffSchedule(t *testing.T) {
	base := 100 * time.Millisecond
	capd := 800 * time.Millisecond
	cases := []struct {
		attempt int
		want    time.Duration
	}{
		{0, 100 * time.Millisecond},
		{1, 200 * time.Millisecond},
		{2, 400 * time.Millisecond},
		{3, 800 * time.Millisecond},
		{4, 800 * time.Millisecond},
		{10, 800 * time.Millisecond},
	}
	for _, c := range cases {
		if got := backoff(c.attempt, base, capd); got != c.want {
			t.Fatalf("attempt=%d 期望 %v 实际 %v", c.attempt, c.want, got)
		}
	}
}

func TestRetrySucceedsAfterFailures(t *testing.T) {
	var sleeps []time.Duration
	calls := 0
	n, err := retryDo(5, 10*time.Millisecond, 100*time.Millisecond, func(d time.Duration) {
		sleeps = append(sleeps, d)
	}, func(attempt int) error {
		calls++
		if attempt < 2 {
			return fmt.Errorf("临时错误 attempt=%d", attempt)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("期望最终成功，实际错误 %v", err)
	}
	if n != 3 {
		t.Fatalf("期望 3 次尝试成功，实际 %d", n)
	}
	if calls != 3 {
		t.Fatalf("fn 应被调用 3 次，实际 %d", calls)
	}
	if len(sleeps) != 2 {
		t.Fatalf("失败 2 次应 sleep 2 次，实际 %d", len(sleeps))
	}
	if sleeps[0] != 10*time.Millisecond || sleeps[1] != 20*time.Millisecond {
		t.Fatalf("退避序列应为 [10ms 20ms]，实际 %v", sleeps)
	}
}

func TestRetryExhausts(t *testing.T) {
	var sleeps []time.Duration
	n, err := retryDo(3, 5*time.Millisecond, 50*time.Millisecond, func(d time.Duration) {
		sleeps = append(sleeps, d)
	}, func(attempt int) error {
		return fmt.Errorf("一直失败 attempt=%d", attempt)
	})
	if err == nil {
		t.Fatal("全部失败时应返回错误")
	}
	if n != 3 {
		t.Fatalf("期望 3 次尝试耗尽，实际 %d", n)
	}
	if len(sleeps) != 2 {
		t.Fatalf("最后一次失败后不应再 sleep，实际 sleep %d 次", len(sleeps))
	}
}

// ---------- 同步幂等 ----------

// idempotentApply 用 map 模拟主程序写 _m_records 的行为：同 key 覆盖写。
// 返回写入是否改变了状态（用于判断幂等）。
func idempotentApply(state map[string]string, k, v string) bool {
	old, existed := state[k]
	if existed && old == v {
		return false
	}
	state[k] = v
	return true
}

func TestSyncIdempotent(t *testing.T) {
	state := map[string]string{}
	batch := []struct{ k, v string }{
		{"1001", "99.50"},
		{"1002", "150.00"},
		{"1003", "20.75"},
	}

	changed := 0
	for _, r := range batch {
		if idempotentApply(state, r.k, r.v) {
			changed++
		}
	}
	if changed != 3 {
		t.Fatalf("首次写入应全部改变，期望 3 实际 %d", changed)
	}

	changed = 0
	for _, r := range batch {
		if idempotentApply(state, r.k, r.v) {
			changed++
		}
	}
	if changed != 0 {
		t.Fatalf("重复同批次应全部幂等，期望 0 改变实际 %d", changed)
	}
	if len(state) != 3 {
		t.Fatalf("状态大小应保持 3，实际 %d", len(state))
	}

	if !idempotentApply(state, "1001", "100.00") {
		t.Fatal("同 key 不同值应视为改变")
	}
	if state["1001"] != "100.00" {
		t.Fatalf("覆盖写后值应为 100.00，实际 %q", state["1001"])
	}
}

// ---------- CSV 增量导入断点续传 ----------

type checkpoint struct {
	LastUpdated string `json:"last_updated"`
	LastRowID   string `json:"last_row_id"`
	Offset      int64  `json:"offset"`
}

func saveCheckpoint(path string, cp checkpoint) error {
	b, err := json.Marshal(cp)
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func loadCheckpoint(path string) (checkpoint, error) {
	var cp checkpoint
	b, err := os.ReadFile(path)
	if err != nil {
		return cp, err
	}
	if err := json.Unmarshal(b, &cp); err != nil {
		return cp, err
	}
	return cp, nil
}

// csvRowsAfter 从整个 CSV 内容中筛选出 updated_at 大于 since 的行（按行顺序）。
func csvRowsAfter(content, since string) []string {
	var out []string
	for _, line := range strings.Split(strings.TrimSpace(content), "\n") {
		if line == "" || strings.HasPrefix(line, "order_id,") {
			continue
		}
		cols := strings.Split(line, ",")
		if len(cols) < 4 {
			continue
		}
		if cols[3] > since {
			out = append(out, line)
		}
	}
	return out
}

func TestCSVIncrementalResume(t *testing.T) {
	dir := mkTempDir(t)
	cpPath := filepath.Join(dir, "orders.ckpt")

	content := sampleOrdersCSV
	all := csvRowsAfter(content, "")
	if len(all) != 5 {
		t.Fatalf("初始应读取 5 行，实际 %d", len(all))
	}

	cp := checkpoint{LastUpdated: "2024-01-02 11:30:00", LastRowID: "1002"}
	if err := saveCheckpoint(cpPath, cp); err != nil {
		t.Fatalf("保存断点失败: %v", err)
	}

	loaded, err := loadCheckpoint(cpPath)
	if err != nil {
		t.Fatalf("加载断点失败: %v", err)
	}
	if loaded.LastUpdated != cp.LastUpdated || loaded.LastRowID != cp.LastRowID {
		t.Fatalf("断点往返不一致: %+v vs %+v", loaded, cp)
	}

	resumed := csvRowsAfter(content, loaded.LastUpdated)
	if len(resumed) != 3 {
		t.Fatalf("从 2024-01-02 11:30:00 续传应得 3 行，实际 %d", len(resumed))
	}
	if !strings.HasPrefix(resumed[0], "1003,") {
		t.Fatalf("续传首行应为 1003，实际 %q", resumed[0])
	}
	if !strings.HasPrefix(resumed[len(resumed)-1], "1005,") {
		t.Fatalf("续传末行应为 1005，实际 %q", resumed[len(resumed)-1])
	}
}

func TestCSVIncrementalResumeAtomicCheckpoint(t *testing.T) {
	dir := mkTempDir(t)
	cpPath := filepath.Join(dir, "orders.ckpt")

	if _, err := loadCheckpoint(cpPath); err == nil {
		t.Fatal("断点文件不存在时应返回错误")
	}

	cp1 := checkpoint{LastUpdated: "2024-01-01 10:00:00", LastRowID: "1001", Offset: 1}
	if err := saveCheckpoint(cpPath, cp1); err != nil {
		t.Fatalf("首次保存失败: %v", err)
	}
	cp2 := checkpoint{LastUpdated: "2024-01-05 16:20:00", LastRowID: "1005", Offset: 5}
	if err := saveCheckpoint(cpPath, cp2); err != nil {
		t.Fatalf("二次保存失败: %v", err)
	}
	got, err := loadCheckpoint(cpPath)
	if err != nil {
		t.Fatalf("加载失败: %v", err)
	}
	if got.LastRowID != "1005" || got.Offset != 5 {
		t.Fatalf("断点应被覆盖为最新值，实际 %+v", got)
	}
	if _, err := os.Stat(cpPath + ".tmp"); !os.IsNotExist(err) {
		t.Fatalf("临时文件应已被重命名清除，stat err=%v", err)
	}

	corrupt := filepath.Join(dir, "corrupt.ckpt")
	if err := os.WriteFile(corrupt, []byte("{not json"), 0o644); err != nil {
		t.Fatalf("写损坏文件失败: %v", err)
	}
	if _, err := loadCheckpoint(corrupt); err == nil {
		t.Fatal("损坏断点文件应返回解析错误")
	}
}

func TestCSVIncrementalConcurrentReaders(t *testing.T) {
	dir := mkTempDir(t)
	cpPath := filepath.Join(dir, "orders.ckpt")
	if err := saveCheckpoint(cpPath, checkpoint{LastUpdated: "2024-01-03 09:15:00", LastRowID: "1003"}); err != nil {
		t.Fatalf("初始化断点失败: %v", err)
	}

	var wg sync.WaitGroup
	errs := make(chan error, 8)
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			cp, err := loadCheckpoint(cpPath)
			if err != nil {
				errs <- err
				return
			}
			if cp.LastRowID != "1003" {
				errs <- fmt.Errorf("并发读取断点得到错误 LastRowID=%q", cp.LastRowID)
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Fatalf("并发读取断点失败: %v", err)
	}
}
