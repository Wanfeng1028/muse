package views

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func newFileTestStore(t *testing.T) *store.Store {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "muse.db")
	st, err := store.Open(path)
	if err != nil {
		t.Fatalf("打开 store 失败: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	t.Cleanup(func() {
		_ = st.Close()
		_ = os.Remove(path)
	})
	return st
}

func mustExec(t *testing.T, st *store.Store, sql string, args ...any) {
	t.Helper()
	if _, err := st.DB.Exec(sql, args...); err != nil {
		t.Fatalf("执行 SQL 失败 sql=%q err=%v", sql, err)
	}
}

func TestAddRejectsNonSelect(t *testing.T) {
	st := newFileTestStore(t)
	mustExec(t, st, "CREATE TABLE t_add_non_select (id INTEGER, v TEXT)")

	err := Add(st, "v_bad", "UPDATE t_add_non_select SET v='x'", "desc")
	if err == nil {
		t.Fatalf("期望报错，实际为 nil")
	}
	if !strings.Contains(err.Error(), "必须以 SELECT 开头") {
		t.Fatalf("错误信息不匹配: %v", err)
	}

	if _, _, err := Run(st, "v_bad", 0); err == nil {
		t.Fatalf("非法视图不应被保存，Run 期望报错")
	} else if !strings.Contains(err.Error(), "获取视图失败") {
		t.Fatalf("Run 错误信息不匹配: %v", err)
	}
}

func TestAddProbeFailureNotSaved(t *testing.T) {
	st := newFileTestStore(t)
	mustExec(t, st, "CREATE TABLE t_probe (id INTEGER, v TEXT)")

	err := Add(st, "v_probe", "SELECT id, v FROM t_not_exist", "desc")
	if err == nil {
		t.Fatalf("试运行应失败，实际为 nil")
	}
	if !strings.Contains(err.Error(), "视图试运行失败") {
		t.Fatalf("错误信息不匹配: %v", err)
	}

	if _, getErr := st.GetView("v_probe"); !errors.Is(getErr, store.ErrNotFound) {
		t.Fatalf("试运行失败不应保存视图，GetView err=%v", getErr)
	}
}

func TestAddThenRunRespectsLimit(t *testing.T) {
	st := newFileTestStore(t)
	mustExec(t, st, "CREATE TABLE t_run (id INTEGER, v TEXT)")
	for i := 1; i <= 5; i++ {
		mustExec(t, st, "INSERT INTO t_run (id, v) VALUES (?, ?)", i, fmt.Sprintf("row-%d", i))
	}

	if err := Add(st, "v_run", "SELECT id, v FROM t_run ORDER BY id", "全部行"); err != nil {
		t.Fatalf("Add 失败: %v", err)
	}

	cols, rows, err := Run(st, "v_run", 2)
	if err != nil {
		t.Fatalf("Run 失败: %v", err)
	}
	if len(cols) != 2 || cols[0] != "id" || cols[1] != "v" {
		t.Fatalf("列名不匹配: %#v", cols)
	}
	if len(rows) != 2 {
		t.Fatalf("LIMIT 2 应返回 2 行，实际 %d", len(rows))
	}
	if rows[0][1] != "row-1" || rows[1][1] != "row-2" {
		t.Fatalf("行内容不匹配: %#v", rows)
	}

	_, allRows, err := Run(st, "v_run", 0)
	if err != nil {
		t.Fatalf("Run limit=0 失败: %v", err)
	}
	if len(allRows) != 5 {
		t.Fatalf("limit=0 应返回全部 5 行，实际 %d", len(allRows))
	}
}

func TestRunRejectsEmptyName(t *testing.T) {
	st := newFileTestStore(t)

	cols, rows, err := Run(st, "   ", 0)
	if err == nil {
		t.Fatalf("空名称应报错")
	}
	if !strings.Contains(err.Error(), "视图名称不能为空") {
		t.Fatalf("错误信息不匹配: %v", err)
	}
	if cols != nil || rows != nil {
		t.Fatalf("出错时应返回 nil 列与 nil 行，实际 cols=%#v rows=%#v", cols, rows)
	}
}

func TestSyncFromConfigIdempotentAndUpdate(t *testing.T) {
	st := newFileTestStore(t)
	mustExec(t, st, "CREATE TABLE t_sync (id INTEGER, v TEXT)")
	mustExec(t, st, "INSERT INTO t_sync (id, v) VALUES (1, 'a')")

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_sync_a", SQL: "SELECT id, v FROM t_sync", Description: "第一版"},
			{Name: "v_sync_b", SQL: "SELECT id FROM t_sync", Description: "只取 id"},
		},
	}

	added, updated, removed, err := SyncFromConfig(cfg, st)
	if err != nil {
		t.Fatalf("首次同步失败: %v", err)
	}
	if added != 2 || updated != 0 || removed != 0 {
		t.Fatalf("首次同步计数不匹配: added=%d updated=%d removed=%d", added, updated, removed)
	}

	added, updated, removed, err = SyncFromConfig(cfg, st)
	if err != nil {
		t.Fatalf("二次同步失败: %v", err)
	}
	if added != 0 || updated != 0 || removed != 0 {
		t.Fatalf("幂等同步计数应为全 0: added=%d updated=%d removed=%d", added, updated, removed)
	}

	cfg2 := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_sync_a", SQL: "SELECT id, v FROM t_sync WHERE id > 0", Description: "第一版"},
			{Name: "v_sync_b", SQL: "SELECT id FROM t_sync", Description: "只取 id"},
		},
	}
	added, updated, removed, err = SyncFromConfig(cfg2, st)
	if err != nil {
		t.Fatalf("变更同步失败: %v", err)
	}
	if added != 0 || updated != 1 || removed != 0 {
		t.Fatalf("变更同步计数不匹配: added=%d updated=%d removed=%d", added, updated, removed)
	}
	v, err := st.GetView("v_sync_a")
	if err != nil {
		t.Fatalf("GetView 失败: %v", err)
	}
	if v.SQL != "SELECT id, v FROM t_sync WHERE id > 0" {
		t.Fatalf("SQL 未更新: %q", v.SQL)
	}
	if v.Origin != "yaml" {
		t.Fatalf("origin 应为 yaml，实际 %q", v.Origin)
	}
}

func TestSyncFromConfigRemovesDeletedYAMLKeepsManual(t *testing.T) {
	st := newFileTestStore(t)
	mustExec(t, st, "CREATE TABLE t_clean (id INTEGER)")
	mustExec(t, st, "INSERT INTO t_clean (id) VALUES (1)")

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_keep", SQL: "SELECT id FROM t_clean", Description: "保留"},
			{Name: "v_drop", SQL: "SELECT id FROM t_clean", Description: "将被删"},
		},
	}
	if _, _, _, err := SyncFromConfig(cfg, st); err != nil {
		t.Fatalf("初始同步失败: %v", err)
	}

	if err := st.SaveView("v_manual", "SELECT id FROM t_clean", "手工视图"); err != nil {
		t.Fatalf("保存手工视图失败: %v", err)
	}

	cfg2 := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_keep", SQL: "SELECT id FROM t_clean", Description: "保留"},
		},
	}
	added, updated, removed, err := SyncFromConfig(cfg2, st)
	if err != nil {
		t.Fatalf("清理同步失败: %v", err)
	}
	if added != 0 || updated != 0 || removed != 1 {
		t.Fatalf("清理计数不匹配: added=%d updated=%d removed=%d", added, updated, removed)
	}

	if _, err := st.GetView("v_drop"); !errors.Is(err, store.ErrNotFound) {
		t.Fatalf("v_drop 应已被清理，err=%v", err)
	}
	if _, err := st.GetView("v_keep"); err != nil {
		t.Fatalf("v_keep 不应被清理: %v", err)
	}
	manual, err := st.GetView("v_manual")
	if err != nil {
		t.Fatalf("v_manual 不应被清理: %v", err)
	}
	if manual.Origin != "manual" {
		t.Fatalf("手工视图 origin 应为 manual，实际 %q", manual.Origin)
	}
}

func TestSyncFromConfigRejectsDuplicateDecl(t *testing.T) {
	st := newFileTestStore(t)
	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_dup", SQL: "SELECT 1", Description: "第一次"},
			{Name: "v_dup", SQL: "SELECT 2", Description: "第二次"},
		},
	}
	added, updated, removed, err := SyncFromConfig(cfg, st)
	if err == nil {
		t.Fatalf("重复声明应报错")
	}
	if !strings.Contains(err.Error(), "重复声明") {
		t.Fatalf("错误信息不匹配: %v", err)
	}
	if added != 0 || updated != 0 || removed != 0 {
		t.Fatalf("出错时计数应全 0: added=%d updated=%d removed=%d", added, updated, removed)
	}
}

func TestSyncFromConfigRejectsMissingName(t *testing.T) {
	st := newFileTestStore(t)
	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "  ", SQL: "SELECT 1", Description: "空名"},
		},
	}
	added, updated, removed, err := SyncFromConfig(cfg, st)
	if err == nil {
		t.Fatalf("空名应报错")
	}
	if !strings.Contains(err.Error(), "缺少名称") {
		t.Fatalf("错误信息不匹配: %v", err)
	}
	if added != 0 || updated != 0 || removed != 0 {
		t.Fatalf("出错时计数应全 0: added=%d updated=%d removed=%d", added, updated, removed)
	}
}

func TestSyncFromConfigDetectsWhitespaceChange(t *testing.T) {
	st := newFileTestStore(t)
	mustExec(t, st, "CREATE TABLE t_ws (id INTEGER)")
	mustExec(t, st, "INSERT INTO t_ws (id) VALUES (7)")

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_ws", SQL: "SELECT id FROM t_ws", Description: "d"},
		},
	}
	if _, _, _, err := SyncFromConfig(cfg, st); err != nil {
		t.Fatalf("初始同步失败: %v", err)
	}

	cfg2 := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_ws", SQL: "SELECT id  FROM t_ws", Description: "d"},
		},
	}
	added, updated, removed, err := SyncFromConfig(cfg2, st)
	if err != nil {
		t.Fatalf("空白变更同步失败: %v", err)
	}
	if added != 0 || updated != 1 || removed != 0 {
		t.Fatalf("空白变更应算一次更新: added=%d updated=%d removed=%d", added, updated, removed)
	}
	v, err := st.GetView("v_ws")
	if err != nil {
		t.Fatalf("GetView 失败: %v", err)
	}
	if v.SQL != "SELECT id  FROM t_ws" {
		t.Fatalf("空白变更未写入: %q", v.SQL)
	}

	cols, rows, err := Run(st, "v_ws", 0)
	if err != nil {
		t.Fatalf("Run 失败: %v", err)
	}
	if len(cols) != 1 || cols[0] != "id" {
		t.Fatalf("列不匹配: %#v", cols)
	}
	if len(rows) != 1 || rows[0][0] != int64(7) {
		t.Fatalf("行不匹配: %#v", rows)
	}
}

func TestSyncFromConfigConcurrentSameConfig(t *testing.T) {
	st := newFileTestStore(t)
	mustExec(t, st, "CREATE TABLE t_conc (id INTEGER)")
	mustExec(t, st, "INSERT INTO t_conc (id) VALUES (1)")

	cfg := &config.Config{
		Views: []config.ViewConfig{
			{Name: "v_conc_a", SQL: "SELECT id FROM t_conc", Description: "a"},
			{Name: "v_conc_b", SQL: "SELECT id FROM t_conc", Description: "b"},
			{Name: "v_conc_c", SQL: "SELECT id FROM t_conc", Description: "c"},
		},
	}

	const workers = 4
	var wg sync.WaitGroup
	errCh := make(chan error, workers)
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, _, _, err := SyncFromConfig(cfg, st); err != nil {
				errCh <- err
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Fatalf("并发同步出错: %v", err)
	}

	views, err := st.ListViews()
	if err != nil {
		t.Fatalf("ListViews 失败: %v", err)
	}
	count := 0
	for _, v := range views {
		if strings.HasPrefix(v.Name, "v_conc_") {
			count++
			if v.Origin != "yaml" {
				t.Fatalf("并发后 origin 应为 yaml，实际 %q", v.Origin)
			}
		}
	}
	if count != 3 {
		t.Fatalf("并发同步后应恰好 3 个视图，实际 %d", count)
	}
}

func TestRunAfterViewDropped(t *testing.T) {
	st := newFileTestStore(t)
	mustExec(t, st, "CREATE TABLE t_drop (id INTEGER)")
	mustExec(t, st, "INSERT INTO t_drop (id) VALUES (1)")

	if err := Add(st, "v_drop_me", "SELECT id FROM t_drop", "将被删"); err != nil {
		t.Fatalf("Add 失败: %v", err)
	}
	if err := st.DropView("v_drop_me"); err != nil {
		t.Fatalf("DropView 失败: %v", err)
	}

	cols, rows, err := Run(st, "v_drop_me", 0)
	if err == nil {
		t.Fatalf("视图已删，Run 应报错")
	}
	if !strings.Contains(err.Error(), "获取视图失败") {
		t.Fatalf("错误信息不匹配: %v", err)
	}
	if cols != nil || rows != nil {
		t.Fatalf("出错时应返回 nil，实际 cols=%#v rows=%#v", cols, rows)
	}
}