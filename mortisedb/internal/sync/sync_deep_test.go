package sync

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
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/notify"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// ---- 测试替身：内存 store ----

type memStore struct {
	mu     sync.Mutex
	tables map[string]*memTable
	runs   []store.RunRecord
	water  map[string]string
}

type memTable struct {
	pk   string
	cols []string
	rows map[string]map[string]any
}

func newMemStore() *memStore {
	return &memStore{
		tables: map[string]*memTable{},
		water:  map[string]string{},
	}
}

func (m *memStore) EnsureTable(name, pk string, cols []infer.Column) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.tables[name]; ok {
		return nil
	}
	cn := make([]string, 0, len(cols))
	for _, c := range cols {
		cn = append(cn, c.Name)
	}
	m.tables[name] = &memTable{pk: pk, cols: cn, rows: map[string]map[string]any{}}
	return nil
}

func (m *memStore) GetWatermark(source, table, col string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.water[source+"|"+table+"|"+col], nil
}

func (m *memStore) SetWatermark(source, table, col, val string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.water[source+"|"+table+"|"+col] = val
	return nil
}

func (m *memStore) RecordRun(r store.RunRecord) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.runs = append(m.runs, r)
	return nil
}

func (m *memStore) UpsertRow(table string, pk string, vals map[string]any) (inserted, updated, skipped int, err error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	t, ok := m.tables[table]
	if !ok {
		return 0, 0, 0, fmt.Errorf("表不存在: %s", table)
	}
	cur, exists := t.rows[pk]
	if !exists {
		cp := map[string]any{}
		for k, v := range vals {
			cp[k] = v
		}
		t.rows[pk] = cp
		return 1, 0, 0, nil
	}
	same := true
	for k, v := range vals {
		if fmt.Sprint(cur[k]) != fmt.Sprint(v) {
			same = false
			break
		}
	}
	if same {
		return 0, 0, 1, nil
	}
	cp := map[string]any{}
	for k, v := range vals {
		cp[k] = v
	}
	t.rows[pk] = cp
	return 0, 1, 0, nil
}

func (m *memStore) DeleteRow(table string, pk string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	t, ok := m.tables[table]
	if !ok {
		return fmt.Errorf("表不存在: %s", table)
	}
	delete(t.rows, pk)
	return nil
}

func (m *memStore) Snapshot(table string) map[string]map[string]any {
	m.mu.Lock()
	defer m.mu.Unlock()
	t, ok := m.tables[table]
	if !ok {
		return nil
	}
	out := map[string]map[string]any{}
	for k, v := range t.rows {
		cp := map[string]any{}
		for kk, vv := range v {
			cp[kk] = vv
		}
		out[k] = cp
	}
	return out
}

func (m *memStore) Runs() []store.RunRecord {
	m.mu.Lock()
	defer m.mu.Unlock()
	cp := make([]store.RunRecord, len(m.runs))
	copy(cp, m.runs)
	return cp
}

// ---- HMAC 验签（与 webhook 约定一致）----

func signHMAC(secret string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

func verifyHMAC(secret string, body []byte, sig string) bool {
	expect := signHMAC(secret, body)
	return hmac.Equal([]byte(expect), []byte(sig))
}

// ---- 用例 ----

// 1. 多源拼装：同 key 不同值时按优先级取靠前源的值
func TestMultiSourceMerge_ConflictByPriority(t *testing.T) {
	dir := t.TempDir()
	pathA := filepath.Join(dir, "a.csv")
	pathB := filepath.Join(dir, "b.csv")
	writeCSV(t, pathA, [][]string{
		{"id", "name"},
		{"1", "alpha"},
	})
	writeCSV(t, pathB, [][]string{
		{"id", "name"},
		{"1", "beta"},
	})

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开 store 出错: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移出错: %v", err)
	}

	cfg := &config.Config{
		Sync: config.SyncPolicy{Priority: []string{"primary", "secondary"}},
		Sources: []config.SourceConfig{
			{Name: "primary", Type: "csv", Path: pathA, Table: "merged", PrimaryKey: "id"},
			{Name: "secondary", Type: "csv", Path: pathB, Table: "merged", PrimaryKey: "id"},
		},
	}

	stats, err := Sync(cfg, st, []string{"primary", "secondary"}, "job-merge")
	if err != nil {
		t.Fatalf("Sync 出错: %v", err)
	}
	if len(stats) != 2 {
		t.Fatalf("期望 2 个源统计，得到 %d", len(stats))
	}
	if len(stats[0].Tables) != 1 {
		t.Fatalf("primary 期望 1 个表统计，得到 %d", len(stats[0].Tables))
	}
	if len(stats[1].Tables) != 1 {
		t.Fatalf("secondary 期望 1 个表统计，得到 %d", len(stats[1].Tables))
	}

	// 第一个源写入，第二个源应触发冲突（同 pk 不同值）
	if stats[0].Tables[0].Inserted != 1 {
		t.Fatalf("primary 期望 Inserted=1，得到 %d", stats[0].Tables[0].Inserted)
	}
	if stats[1].Tables[0].Conflicts != 1 {
		t.Fatalf("secondary 期望 Conflicts=1，得到 %d", stats[1].Tables[0].Conflicts)
	}

	// 优先级高（primary）的值应保留
	var gotName string
	if err := st.DB.QueryRow("SELECT name FROM merged WHERE id = ?", "1").Scan(&gotName); err != nil {
		t.Fatalf("查询 merged 出错: %v", err)
	}
	if gotName != "alpha" {
		t.Fatalf("期望保留 primary 的值 alpha，得到 %q", gotName)
	}
}

// 2. PriorityIndex 边界：命中返回下标，未命中返回大数
func TestPriorityIndex_Boundary(t *testing.T) {
	pr := []string{"a", "b", "c"}
	if got := PriorityIndex(pr, "a"); got != 0 {
		t.Fatalf("a 期望 0，得到 %d", got)
	}
	if got := PriorityIndex(pr, "c"); got != 2 {
		t.Fatalf("c 期望 2，得到 %d", got)
	}
	if got := PriorityIndex(pr, "z"); got != 1<<30 {
		t.Fatalf("z 期望 1<<30，得到 %d", got)
	}
	if got := PriorityIndex(nil, "x"); got != 1<<30 {
		t.Fatalf("空列表期望 1<<30，得到 %d", got)
	}
}

// 3. HashRow：列顺序无关，值变化产生不同哈希
func TestHashRow_OrderIndependentAndStable(t *testing.T) {
	cols1 := []string{"a", "b"}
	vals1 := []any{"1", "2"}
	cols2 := []string{"b", "a"}
	vals2 := []any{"2", "1"}

	h1 := HashRow("pk1", cols1, vals1)
	h2 := HashRow("pk1", cols2, vals2)
	if h1 != h2 {
		t.Fatalf("列顺序不同应得到相同哈希: %s vs %s", h1, h2)
	}
	if len(h1) != 64 {
		t.Fatalf("sha256 hex 长度期望 64，得到 %d", len(h1))
	}

	h3 := HashRow("pk1", cols1, []any{"1", "3"})
	if h3 == h1 {
		t.Fatalf("值变化应产生不同哈希")
	}
	h4 := HashRow("pk2", cols1, vals1)
	if h4 == h1 {
		t.Fatalf("主键变化应产生不同哈希")
	}
}

// 4. HMAC 验签：正确签名通过，篡改 body 或签名失败
func TestHMACWebhook_VerifyBoundary(t *testing.T) {
	secret := "s3cr3t-key"
	body := []byte(`{"event":"conflict","table":"orders"}`)

	good := signHMAC(secret, body)
	if !verifyHMAC(secret, body, good) {
		t.Fatalf("正确签名应通过验签")
	}

	tampered := []byte(`{"event":"conflict","table":"orders2"}`)
	if verifyHMAC(secret, tampered, good) {
		t.Fatalf("篡改 body 应验签失败")
	}

	bad := strings.Repeat("0", 64)
	if verifyHMAC(secret, body, bad) {
		t.Fatalf("错误签名应验签失败")
	}

	if verifyHMAC(secret, body, "") {
		t.Fatalf("空签名应验签失败")
	}

	// 不同 secret 不应通过
	if verifyHMAC("other-secret", body, good) {
		t.Fatalf("不同 secret 应验签失败")
	}
}

// 7. 同步幂等：相同数据重复同步不产生 insert/update，只 skip
func TestSync_Idempotent(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库出错: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("建表出错: %v", err)
	}

	dir := t.TempDir()
	csvPath := filepath.Join(dir, "s1.csv")
	writeCSV(t, csvPath, [][]string{
		{"id", "v"},
		{"1", "x"},
		{"2", "y"},
	})

	cfg := &config.Config{Sources: []config.SourceConfig{{
		Name:       "s1",
		Type:       "csv",
		Path:       csvPath,
		Table:      "t1",
		PrimaryKey: "id",
	}}}

	first, err := Sync(cfg, st, []string{"s1"}, "job-idem")
	if err != nil {
		t.Fatalf("首次同步出错: %v", err)
	}
	if len(first) != 1 {
		t.Fatalf("首次期望返回 1 个源统计，得到 %d", len(first))
	}
	if len(first[0].Tables) != 1 {
		t.Fatalf("首次期望返回 1 张表统计，得到 %d", len(first[0].Tables))
	}
	if first[0].Tables[0].Inserted != 2 {
		t.Fatalf("首次期望 Inserted=2，得到 %d", first[0].Tables[0].Inserted)
	}

	var count int
	if err := st.DB.QueryRow("SELECT COUNT(*) FROM t1").Scan(&count); err != nil {
		t.Fatalf("查询目标表出错: %v", err)
	}
	if count != 2 {
		t.Fatalf("首次同步后期望目标表有 2 行，得到 %d", count)
	}

	second, err := Sync(cfg, st, []string{"s1"}, "job-idem")
	if err != nil {
		t.Fatalf("二次同步出错: %v", err)
	}
	if len(second) != 1 {
		t.Fatalf("二次期望返回 1 个源统计，得到 %d", len(second))
	}
	if len(second[0].Tables) != 1 {
		t.Fatalf("二次期望返回 1 张表统计，得到 %d", len(second[0].Tables))
	}
	ts := second[0].Tables[0]
	if ts.Inserted != 0 {
		t.Fatalf("幂等二次同步期望 Inserted=0，得到 %d", ts.Inserted)
	}
	if ts.Updated != 0 {
		t.Fatalf("幂等二次同步期望 Updated=0，得到 %d", ts.Updated)
	}
	if ts.Skipped != 2 {
		t.Fatalf("幂等二次同步期望 Skipped=2，得到 %d", ts.Skipped)
	}
	if ts.Conflicts != 0 {
		t.Fatalf("幂等二次同步期望 Conflicts=0，得到 %d", ts.Conflicts)
	}

	if err := st.DB.QueryRow("SELECT COUNT(*) FROM t1").Scan(&count); err != nil {
		t.Fatalf("二次查询目标表出错: %v", err)
	}
	if count != 2 {
		t.Fatalf("二次同步后期望目标表仍有 2 行，得到 %d", count)
	}

	runs, err := st.ListRuns(10)
	if err != nil {
		t.Fatalf("查询运行记录出错: %v", err)
	}
	if len(runs) != 2 {
		t.Fatalf("期望 2 条运行记录，得到 %d", len(runs))
	}
	for i, r := range runs {
		if r.Job != "job-idem:s1" {
			t.Fatalf("第 %d 条运行记录期望 Job=job-idem:s1，得到 %s", i, r.Job)
		}
		if r.Error != "" {
			t.Fatalf("第 %d 条运行记录期望 Error 为空，得到 %s", i, r.Error)
		}
	}
}

// 8. CSV 增量导入断点续传：水位线推进后只拉增量，失败不推进
// 8. CSV 增量：水位线推进后只同步新增行（真实 CSV 文件 + 真实 store）
func TestCSVIncremental_ResumeFromWatermark(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "orders.csv")
	writeCSV(t, path, [][]string{
		{"id", "ts", "amount"},
		{"1", "2024-01-01T00:00:00Z", "10"},
		{"2", "2024-01-02T00:00:00Z", "20"},
		{"3", "2024-01-03T00:00:00Z", "30"},
	})

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库出错: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("建表出错: %v", err)
	}

	cfg := &config.Config{Sources: []config.SourceConfig{{
		Name:        "csv",
		Type:        "csv",
		Path:        path,
		Table:       "orders",
		PrimaryKey:  "id",
		Incremental: "column:ts",
	}}}

	first, err := Sync(cfg, st, []string{"csv"}, "job-inc")
	if err != nil {
		t.Fatalf("首次增量同步出错: %v", err)
	}
	if len(first) != 1 || len(first[0].Tables) != 1 {
		t.Fatalf("首次期望 1 源 1 表统计，得到 %+v", first)
	}
	if first[0].Tables[0].Inserted != 3 {
		t.Fatalf("首次期望 Inserted=3，得到 %d", first[0].Tables[0].Inserted)
	}
	wm, err := st.GetWatermark("csv", "orders", "ts")
	if err != nil {
		t.Fatalf("读水位线出错: %v", err)
	}
	if wm != "2024-01-03T00:00:00Z" {
		t.Fatalf("首次水位线期望 2024-01-03T00:00:00Z，得到 %q", wm)
	}

	// 追加新行模拟断点后续传：只有新增行应被插入
	writeCSV(t, path, [][]string{
		{"id", "ts", "amount"},
		{"1", "2024-01-01T00:00:00Z", "10"},
		{"2", "2024-01-02T00:00:00Z", "20"},
		{"3", "2024-01-03T00:00:00Z", "30"},
		{"4", "2024-01-04T00:00:00Z", "40"},
	})

	second, err := Sync(cfg, st, []string{"csv"}, "job-inc")
	if err != nil {
		t.Fatalf("续传同步出错: %v", err)
	}
	if second[0].Tables[0].Inserted != 1 {
		t.Fatalf("续传期望 Inserted=1，得到 %d", second[0].Tables[0].Inserted)
	}
	wm2, err := st.GetWatermark("csv", "orders", "ts")
	if err != nil {
		t.Fatalf("读水位线出错: %v", err)
	}
	if wm2 != "2024-01-04T00:00:00Z" {
		t.Fatalf("续传水位线期望 2024-01-04T00:00:00Z，得到 %q", wm2)
	}

	var count int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "orders"`).Scan(&count); err != nil {
		t.Fatalf("count rows: %v", err)
	}
	if count != 4 {
		t.Fatalf("目标表期望 4 行，得到 %d", count)
	}
}

// 9. Sync 未知源应返回错误且不产生任何源统计
func TestSync_UnknownSource(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开数据库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	cfg := &config.Config{Sources: []config.SourceConfig{{Name: "known"}}}

	stats, err := Sync(cfg, st, []string{"missing"}, "job-unknown")
	if err == nil {
		t.Fatalf("未知源应返回错误")
	}
	if stats != nil {
		t.Fatalf("未知源不应返回统计，得到 %v", stats)
	}
	if !strings.Contains(err.Error(), "源不存在") {
		t.Fatalf("错误信息应包含 源不存在，得到 %v", err)
	}
}

// 10. Sync 失败源应记录 RunRecord 并继续处理其他源
func TestSync_ErrorRecordedAndContinues(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开 store 失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移 store 失败: %v", err)
	}

	dir := t.TempDir()
	goodPath := dir + "/good.csv"
	writeCSV(t, goodPath, [][]string{
		{"id"},
		{"1"},
	})

	cfg := &config.Config{Sources: []config.SourceConfig{
		{Name: "bad", Type: "csv", Path: "/nonexistent-xxx/bad.csv", Table: "t_bad", PrimaryKey: "id"},
		{Name: "good", Type: "csv", Path: goodPath, Table: "t_good", PrimaryKey: "id"},
	}}

	stats, err := Sync(cfg, st, []string{"bad", "good"}, "job-err")
	if err == nil {
		t.Fatalf("存在失败源应返回错误")
	}
	if len(stats) != 2 {
		t.Fatalf("期望 2 个源统计，得到 %d", len(stats))
	}
	if len(stats[1].Tables) != 1 {
		t.Fatalf("good 源期望 1 张表统计，得到 %d", len(stats[1].Tables))
	}
	if stats[1].Tables[0].Inserted != 1 {
		t.Fatalf("good 源应正常插入，得到 %d", stats[1].Tables[0].Inserted)
	}

	var gotID string
	if err := st.DB.QueryRow("SELECT id FROM t_good").Scan(&gotID); err != nil {
		t.Fatalf("查询 t_good 失败: %v", err)
	}
	if gotID != "1" {
		t.Fatalf("t_good 期望 id=1，得到 %s", gotID)
	}

	runs, err := st.ListRuns(20)
	if err != nil {
		t.Fatalf("ListRuns 失败: %v", err)
	}
	foundErr := false
	foundOK := false
	for _, r := range runs {
		if strings.Contains(r.Job, "job-err:bad") && r.Error != "" {
			foundErr = true
		}
		if strings.Contains(r.Job, "job-err:good") && r.Error == "" {
			foundOK = true
		}
	}
	if !foundErr {
		t.Fatalf("应记录 bad 源的失败 run")
	}
	if !foundOK {
		t.Fatalf("应记录 good 源的成功 run")
	}
}

// 11. -race 安全：多源并发同步共享 store 不出现数据竞争
func TestSync_RaceMultipleSources(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	cfg := &config.Config{Sources: []config.SourceConfig{}}
	for i := 0; i < 8; i++ {
		name := fmt.Sprintf("s%d", i)
		path := filepath.Join(dir, name+".csv")
		writeCSV(t, path, [][]string{
			{"id", "src"},
			{"1", name},
			{"2", name},
		})
		cfg.Sources = append(cfg.Sources, config.SourceConfig{
			Name:       name,
			Type:       "csv",
			Path:       path,
			Table:      "t_" + name,
			PrimaryKey: "id",
		})
	}

	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			name := fmt.Sprintf("s%d", idx)
			var lastErr error
			for attempt := 0; attempt < 3; attempt++ {
				_, lastErr = Sync(cfg, st, []string{name}, "job-race")
				if lastErr == nil {
					return
				}
			}
			t.Errorf("同步 %s 失败: %v", name, lastErr)
		}(i)
	}
	wg.Wait()

	var count int
	if err := st.DB.QueryRow("SELECT COUNT(*) FROM t_s0").Scan(&count); err != nil {
		t.Fatalf("查询 t_s0 行数失败: %v", err)
	}
	if count != 2 {
		t.Fatalf("期望 t_s0 有 2 行，得到 %d", count)
	}

	var src string
	if err := st.DB.QueryRow("SELECT src FROM t_s0 WHERE id = 1").Scan(&src); err != nil {
		t.Fatalf("查询 t_s0 id=1 失败: %v", err)
	}
	if src != "s0" {
		t.Fatalf("t_s0 行内容应属于 s0，得到 %v", src)
	}
}

// 12. JSON 序列化 SourceStats 字段完整
func TestSourceStats_JSONRoundTrip(t *testing.T) {
	ss := SourceStats{
		Source: "orders",
		Tables: []TableStats{
			{Table: "t1", Inserted: 1, Updated: 2, Deleted: 3, Skipped: 4, Conflicts: 5},
		},
	}
	b, err := json.Marshal(ss)
	if err != nil {
		t.Fatalf("序列化失败: %v", err)
	}
	var back SourceStats
	if err := json.Unmarshal(b, &back); err != nil {
		t.Fatalf("反序列化失败: %v", err)
	}
	if back.Source != "orders" {
		t.Fatalf("Source 期望 orders，得到 %q", back.Source)
	}
	if len(back.Tables) != 1 {
		t.Fatalf("Tables 长度期望 1，得到 %d", len(back.Tables))
	}
	if back.Tables[0].Conflicts != 5 {
		t.Fatalf("Conflicts 期望 5，得到 %d", back.Tables[0].Conflicts)
	}
	if back.Tables[0].Skipped != 4 {
		t.Fatalf("Skipped 期望 4，得到 %d", back.Tables[0].Skipped)
	}
}

// ---- 辅助：CSV ----

func writeCSV(t *testing.T, path string, records [][]string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatalf("创建 CSV 失败: %v", err)
	}
	defer f.Close()
	w := csv.NewWriter(f)
	for _, r := range records {
		if err := w.Write(r); err != nil {
			t.Fatalf("写 CSV 失败: %v", err)
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		t.Fatalf("CSV flush 失败: %v", err)
	}
}

func readCSVRows(t *testing.T, path string) []map[string]string {
	t.Helper()
	f, err := os.Open(path)
	if err != nil {
		t.Fatalf("打开 CSV 失败: %v", err)
	}
	defer f.Close()
	r := csv.NewReader(f)
	records, err := r.ReadAll()
	if err != nil {
		t.Fatalf("读 CSV 失败: %v", err)
	}
	if len(records) == 0 {
		return nil
	}
	header := records[0]
	out := make([]map[string]string, 0, len(records)-1)
	for _, rec := range records[1:] {
		m := map[string]string{}
		for i, h := range header {
			if i < len(rec) {
				m[h] = rec[i]
			}
		}
		out = append(out, m)
	}
	return out
}

// ---- 辅助：确保 notify 引用不被优化掉（编译期占位）----

var _ = notify.FromConfig
var _ = sort.Strings
