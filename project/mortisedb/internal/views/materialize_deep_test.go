package views

import (
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func newMatFileTestStore(t *testing.T) *store.Store {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "muse_test.db")
	st, err := store.Open(dbPath)
	if err != nil {
		t.Fatalf("打开测试库失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	t.Cleanup(func() {
		_ = st.Close()
	})
	return st
}

func seedTable(t *testing.T, st *store.Store, ddl string) {
	t.Helper()
	if _, err := st.DB.Exec(ddl); err != nil {
		t.Fatalf("执行建表语句失败: %v", err)
	}
}

func createView(t *testing.T, st *store.Store, name, sql string) {
	t.Helper()
	if err := st.SaveView(name, sql, "yaml"); err != nil {
		t.Fatalf("写入视图失败: %v", err)
	}
}

func TestRefreshNotFound(t *testing.T) {
	st := newMatFileTestStore(t)

	rows, err := Refresh(st, "不存在的视图")
	if !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("期望 ErrNotFound, 实际: %v", err)
	}
	if rows != 0 {
		t.Fatalf("视图不存在时行数应为 0, 实际: %d", rows)
	}
}

func TestRefreshMaterializesAndIsIdempotent(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)`)
	if _, err := st.DB.Exec(`INSERT INTO orders (id, amount) VALUES (1, 10), (2, 20), (3, 30)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "big_orders", `SELECT id, amount FROM orders WHERE amount >= 20`)

	first, err := Refresh(st, "big_orders")
	if err != nil {
		t.Fatalf("首次刷新失败: %v", err)
	}
	if first != 2 {
		t.Fatalf("首次刷新行数应为 2, 实际: %d", first)
	}

	tbl, err := store.MaterializeTableName("big_orders")
	if err != nil {
		t.Fatalf("生成物化表名失败: %v", err)
	}
	var cnt int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "` + tbl + `"`).Scan(&cnt); err != nil {
		t.Fatalf("查询物化表失败: %v", err)
	}
	if cnt != 2 {
		t.Fatalf("物化表应有 2 行, 实际: %d", cnt)
	}

	second, err := Refresh(st, "big_orders")
	if err != nil {
		t.Fatalf("二次刷新失败: %v", err)
	}
	if second != 2 {
		t.Fatalf("二次刷新行数应仍为 2, 实际: %d", second)
	}
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "` + tbl + `"`).Scan(&cnt); err != nil {
		t.Fatalf("二次查询物化表失败: %v", err)
	}
	if cnt != 2 {
		t.Fatalf("二次刷新后物化表应仍为 2 行, 实际: %d", cnt)
	}
}

func TestRefreshBadSQLKeepsOldMaterializedTable(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)`)
	if _, err := st.DB.Exec(`INSERT INTO items (id, name) VALUES (1, 'a'), (2, 'b')`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "items_view", `SELECT id, name FROM items`)

	rows, err := Refresh(st, "items_view")
	if err != nil {
		t.Fatalf("首次刷新失败: %v", err)
	}
	if rows != 2 {
		t.Fatalf("首次刷新行数应为 2, 实际: %d", rows)
	}

	if err := st.SaveView("items_view", `SELECT FROM WHERE`, "yaml"); err != nil {
		t.Fatalf("更新视图为错误 SQL 失败: %v", err)
	}

	_, err = Refresh(st, "items_view")
	if err == nil {
		t.Fatalf("错误 SQL 刷新应返回错误")
	}

	tbl, merr := store.MaterializeTableName("items_view")
	if merr != nil {
		t.Fatalf("生成物化表名失败: %v", merr)
	}
	var cnt int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "` + tbl + `"`).Scan(&cnt); err != nil {
		t.Fatalf("回滚后旧物化表应仍存在, 查询失败: %v", err)
	}
	if cnt != 2 {
		t.Fatalf("回滚后旧物化表应保留 2 行, 实际: %d", cnt)
	}
}

func TestRefreshMultiSourceConflict(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE src_a (key TEXT, val TEXT)`)
	seedTable(t, st, `CREATE TABLE src_b (key TEXT, val TEXT)`)
	if _, err := st.DB.Exec(`INSERT INTO src_a (key, val) VALUES ('k1', 'from_a'), ('k2', 'only_a')`); err != nil {
		t.Fatalf("插入 src_a 失败: %v", err)
	}
	if _, err := st.DB.Exec(`INSERT INTO src_b (key, val) VALUES ('k1', 'from_b'), ('k3', 'only_b')`); err != nil {
		t.Fatalf("插入 src_b 失败: %v", err)
	}

	createView(t, st, "merged", `SELECT key, val FROM src_a UNION ALL SELECT key, val FROM src_b`)

	rows, err := Refresh(st, "merged")
	if err != nil {
		t.Fatalf("刷新合并视图失败: %v", err)
	}
	if rows != 4 {
		t.Fatalf("UNION ALL 应保留 4 行(同 key 不合并), 实际: %d", rows)
	}

	tbl, merr := store.MaterializeTableName("merged")
	if merr != nil {
		t.Fatalf("生成物化表名失败: %v", merr)
	}
	var distinctVals int
	if err := st.DB.QueryRow(`SELECT COUNT(DISTINCT val) FROM "` + tbl + `" WHERE key = 'k1'`).Scan(&distinctVals); err != nil {
		t.Fatalf("查询 k1 值失败: %v", err)
	}
	if distinctVals != 2 {
		t.Fatalf("k1 应有两个不同值, 实际: %d", distinctVals)
	}

	if err := st.SaveView("merged", `SELECT key, val FROM src_b UNION SELECT key, val FROM src_a`, "yaml"); err != nil {
		t.Fatalf("更新视图为 UNION 失败: %v", err)
	}
	rows, err = Refresh(st, "merged")
	if err != nil {
		t.Fatalf("刷新 UNION 视图失败: %v", err)
	}
	if rows != 4 {
		t.Fatalf("UNION 去重后应为 4 行, 实际: %d", rows)
	}
}

func TestRefreshDueOnSyncAndManual(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t1 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t1 (id) VALUES (1), (2)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "v_sync", `SELECT id FROM t1`)
	createView(t, st, "v_manual", `SELECT id FROM t1`)

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_sync", SQL: `SELECT id FROM t1`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "on_sync"}},
			{Name: "v_manual", SQL: `SELECT id FROM t1`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "manual"}},
		},
	}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue 失败: %v", err)
	}
	if len(refreshed) != 1 || refreshed[0] != "v_sync" {
		t.Fatalf("refreshed 应为 [v_sync], 实际: %v", refreshed)
	}
	if len(skipped) != 1 || skipped[0] != "v_manual" {
		t.Fatalf("skipped 应为 [v_manual], 实际: %v", skipped)
	}

	v, err := st.GetView("v_manual")
	if err != nil {
		t.Fatalf("读取 v_manual 失败: %v", err)
	}
	if !v.Materialized {
		t.Fatalf("v_manual 策略应已同步为已物化")
	}
	if v.LastRefreshAt != "" {
		t.Fatalf("manual 策略不应刷新, LastRefreshAt 应为空, 实际: %s", v.LastRefreshAt)
	}
}

func TestRefreshDueIntervalRetryBackoff(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t2 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t2 (id) VALUES (1)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "v_int", `SELECT id FROM t2`)

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_int", SQL: `SELECT id FROM t2`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "interval:1h"}},
		},
	}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("首次 RefreshDue 失败: %v", err)
	}
	if len(refreshed) != 1 || refreshed[0] != "v_int" {
		t.Fatalf("首次应刷新 v_int, 实际 refreshed=%v", refreshed)
	}
	if len(skipped) != 0 {
		t.Fatalf("首次 skipped 应为空, 实际: %v", skipped)
	}

	refreshed, skipped, err = RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("第二次 RefreshDue 失败: %v", err)
	}
	if len(refreshed) != 0 {
		t.Fatalf("间隔未到不应刷新, 实际 refreshed=%v", refreshed)
	}
	if len(skipped) != 1 || skipped[0] != "v_int" {
		t.Fatalf("间隔未到应跳过 v_int, 实际 skipped=%v", skipped)
	}

	v, err := st.GetView("v_int")
	if err != nil {
		t.Fatalf("读取 v_int 失败: %v", err)
	}
	if v.LastRefreshAt == "" {
		t.Fatalf("首次刷新后 LastRefreshAt 不应为空")
	}
	last, perr := time.Parse(time.RFC3339, v.LastRefreshAt)
	if perr != nil {
		t.Fatalf("LastRefreshAt 不是 RFC3339: %v", perr)
	}
	if time.Since(last) > time.Minute {
		t.Fatalf("LastRefreshAt 应接近当前时间, 实际: %s", v.LastRefreshAt)
	}
}

func TestRefreshDueCancelsYAMLOriginNotDeclared(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t3 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t3 (id) VALUES (1)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	if err := st.SaveYAMLView("v_cancel", `SELECT id FROM t3`, ""); err != nil {
		t.Fatalf("写入视图失败: %v", err)
	}

	cfgEnable := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_cancel", SQL: `SELECT id FROM t3`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "on_sync"}},
		},
	}
	if _, _, err := RefreshDue(cfgEnable, st); err != nil {
		t.Fatalf("启用物化 RefreshDue 失败: %v", err)
	}
	tbl, merr := store.MaterializeTableName("v_cancel")
	if merr != nil {
		t.Fatalf("生成物化表名失败: %v", merr)
	}
	var cnt int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "` + tbl + `"`).Scan(&cnt); err != nil {
		t.Fatalf("物化表应存在, 查询失败: %v", err)
	}
	if cnt != 1 {
		t.Fatalf("物化表应有 1 行, 实际: %d", cnt)
	}

	cfgEmpty := &config.Config{Views: []config.ViewConfig{}}
	if _, _, err := RefreshDue(cfgEmpty, st); err != nil {
		t.Fatalf("取消物化 RefreshDue 失败: %v", err)
	}

	v, err := st.GetView("v_cancel")
	if err != nil {
		t.Fatalf("读取 v_cancel 失败: %v", err)
	}
	if v.Materialized {
		t.Fatalf("取消后 Materialized 应为 false")
	}

	var name string
	err = st.DB.QueryRow(`SELECT name FROM sqlite_master WHERE type='table' AND name=?`, tbl).Scan(&name)
	if err == nil {
		t.Fatalf("物化表 %s 应已被删除, 实际仍存在", tbl)
	}
}

func TestRefreshDueInvalidInterval(t *testing.T) {
	st := newMatFileTestStore(t)
	createView(t, st, "v_bad", `SELECT 1`)

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_bad", SQL: `SELECT 1`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "interval:notaduration"}},
		},
	}

	_, _, err := RefreshDue(cfg, st)
	if err == nil {
		t.Fatalf("非法 interval 应返回错误")
	}
	if !contains(err.Error(), "解析刷新间隔失败") {
		t.Fatalf("错误信息应包含解析刷新间隔失败, 实际: %v", err)
	}
}

func TestRefreshDueEmptyPolicyDefaultsOnSync(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t4 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t4 (id) VALUES (1), (2), (3)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "v_default", `SELECT id FROM t4`)

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_default", SQL: `SELECT id FROM t4`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "   "}},
		},
	}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue 失败: %v", err)
	}
	if len(refreshed) != 1 || refreshed[0] != "v_default" {
		t.Fatalf("空策略应默认 on_sync 立即刷新, 实际 refreshed=%v", refreshed)
	}
	if len(skipped) != 0 {
		t.Fatalf("skipped 应为空, 实际: %v", skipped)
	}

	v, err := st.GetView("v_default")
	if err != nil {
		t.Fatalf("读取 v_default 失败: %v", err)
	}
	if !v.Materialized {
		t.Fatalf("v_default 应已物化")
	}
	if v.RefreshPolicy != "on_sync" {
		t.Fatalf("策略应同步为 on_sync, 实际: %s", v.RefreshPolicy)
	}
}

func TestRefreshDueUnknownPolicySkips(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t5 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t5 (id) VALUES (1)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "v_unknown", `SELECT id FROM t5`)

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_unknown", SQL: `SELECT id FROM t5`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "on_demand"}},
		},
	}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue 失败: %v", err)
	}
	if len(refreshed) != 0 {
		t.Fatalf("未知策略不应刷新, 实际 refreshed=%v", refreshed)
	}
	if len(skipped) != 1 || skipped[0] != "v_unknown" {
		t.Fatalf("未知策略应跳过, 实际 skipped=%v", skipped)
	}

	v, err := st.GetView("v_unknown")
	if err != nil {
		t.Fatalf("读取 v_unknown 失败: %v", err)
	}
	if !v.Materialized {
		t.Fatalf("未知策略下 Materialized 应同步为 true")
	}
	if v.LastRefreshAt != "" {
		t.Fatalf("未知策略不应刷新, LastRefreshAt 应为空, 实际: %s", v.LastRefreshAt)
	}
}

func TestRefreshDueDisabledViewNotCancelled(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t6 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t6 (id) VALUES (1)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}

	if err := st.SaveView("v_manual_origin", `SELECT id FROM t6`, "manual"); err != nil {
		t.Fatalf("写入非 yaml 来源视图失败: %v", err)
	}
	if err := st.UpdateViewMaterialize("v_manual_origin", true, "on_sync"); err != nil {
		t.Fatalf("标记物化失败: %v", err)
	}
	if _, err := Refresh(st, "v_manual_origin"); err != nil {
		t.Fatalf("刷新失败: %v", err)
	}

	cfg := &config.Config{Views: []config.ViewConfig{}}
	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue 失败: %v", err)
	}
	if len(refreshed) != 0 {
		t.Fatalf("refreshed 应为空, 实际: %v", refreshed)
	}
	if len(skipped) != 0 {
		t.Fatalf("skipped 应为空, 实际: %v", skipped)
	}

	v, err := st.GetView("v_manual_origin")
	if err != nil {
		t.Fatalf("读取 v_manual_origin 失败: %v", err)
	}
	if !v.Materialized {
		t.Fatalf("非 yaml 来源不应被取消物化")
	}

	tbl, merr := store.MaterializeTableName("v_manual_origin")
	if merr != nil {
		t.Fatalf("生成物化表名失败: %v", merr)
	}
	var cnt int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "` + tbl + `"`).Scan(&cnt); err != nil {
		t.Fatalf("非 yaml 物化表应存在, 查询失败: %v", err)
	}
	if cnt != 1 {
		t.Fatalf("物化表应有 1 行, 实际: %d", cnt)
	}
}

func contains(s, sub string) bool {
	if len(sub) == 0 {
		return true
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
