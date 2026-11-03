package views

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
)

func TestMvR2B40CancelDropsTable(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t1 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t1 (id) VALUES (1)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	if err := st.SaveYAMLView("vy", `SELECT id FROM t1`, "d"); err != nil {
		t.Fatalf("保存 YAML 视图失败: %v", err)
	}

	cfg := &config.Config{Views: []config.ViewConfig{{Name: "vy", SQL: `SELECT id FROM t1`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "on_sync"}}}}
	if _, _, err := RefreshDue(cfg, st); err != nil {
		t.Fatalf("RefreshDue 首次调用失败: %v", err)
	}

	var n int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "sqlite_master" WHERE "type"='table' AND "name"='_mv_vy'`).Scan(&n); err != nil {
		t.Fatalf("查询物化表存在性失败: %v", err)
	}
	if n != 1 {
		t.Fatalf("期望物化表 _mv_vy 存在, 实际 count=%d", n)
	}

	cfg2 := &config.Config{Views: []config.ViewConfig{}}
	if _, _, err := RefreshDue(cfg2, st); err != nil {
		t.Fatalf("RefreshDue 取消调用失败: %v", err)
	}

	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "sqlite_master" WHERE "type"='table' AND "name"='_mv_vy'`).Scan(&n); err != nil {
		t.Fatalf("查询物化表存在性失败: %v", err)
	}
	if n != 0 {
		t.Fatalf("期望物化表 _mv_vy 已被删除, 实际 count=%d", n)
	}

	v, err := st.GetView("vy")
	if err != nil {
		t.Fatalf("GetView 失败: %v", err)
	}
	if v.Materialized {
		t.Fatalf("期望视图 vy Materialized=false, 实际为 true")
	}
	if v.RefreshPolicy != "" {
		t.Fatalf("期望视图 vy RefreshPolicy 为空, 实际为 %q", v.RefreshPolicy)
	}
}

func TestMvR2B40ManualOriginNotCancelled(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t1 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t1 (id) VALUES (1)`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "vm", `SELECT id FROM t1`)
	if err := st.UpdateViewMaterialize("vm", true, "on_sync"); err != nil {
		t.Fatalf("UpdateViewMaterialize 失败: %v", err)
	}
	if _, err := Refresh(st, "vm"); err != nil {
		t.Fatalf("Refresh 失败: %v", err)
	}

	var n int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "sqlite_master" WHERE "type"='table' AND "name"='_mv_vm'`).Scan(&n); err != nil {
		t.Fatalf("查询物化表存在性失败: %v", err)
	}
	if n != 1 {
		t.Fatalf("期望物化表 _mv_vm 存在, 实际 count=%d", n)
	}

	cfg := &config.Config{Views: []config.ViewConfig{}}
	if _, _, err := RefreshDue(cfg, st); err != nil {
		t.Fatalf("RefreshDue 调用失败: %v", err)
	}

	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "sqlite_master" WHERE "type"='table' AND "name"='_mv_vm'`).Scan(&n); err != nil {
		t.Fatalf("查询物化表存在性失败: %v", err)
	}
	if n != 1 {
		t.Fatalf("期望 manual origin 的物化表 _mv_vm 仍存在, 实际 count=%d", n)
	}
}
