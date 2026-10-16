package views

import (
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// Refresh 物化刷新视图：把视图 SQL 的结果全量写入物化表 _mv_<name>。
// 事务内执行：DROP TABLE IF EXISTS 后 CREATE TABLE AS <视图SQL>；成功后记录刷新元信息。
// 返回写入行数。视图不存在返回 store.ErrNotFound；SQL 执行失败返回错误（事务回滚，旧物化表不受影响——注意：DROP 已在事务内，回滚后旧表仍在）。
func Refresh(st *store.Store, name string) (int64, error) {
	v, err := st.GetView(name)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			return 0, store.ErrNotFound
		}
		return 0, fmt.Errorf("读取视图失败: %w", err)
	}

	tbl, err := store.MaterializeTableName(v.Name)
	if err != nil {
		return 0, fmt.Errorf("生成物化表名失败: %w", err)
	}
	quoted := `"` + strings.ReplaceAll(tbl, `"`, `""`) + `"`

	tx, err := st.DB.Begin()
	if err != nil {
		return 0, fmt.Errorf("开启事务失败: %w", err)
	}

	if _, err := tx.Exec("DROP TABLE IF EXISTS " + quoted); err != nil {
		_ = tx.Rollback()
		return 0, fmt.Errorf("删除旧物化表失败: %w", err)
	}

	if _, err := tx.Exec(`CREATE TABLE ` + quoted + ` AS ` + v.SQL); err != nil {
		_ = tx.Rollback()
		return 0, fmt.Errorf("创建物化表失败: %w", err)
	}

	var rows int64
	if err := tx.QueryRow(`SELECT COUNT(*) FROM ` + quoted).Scan(&rows); err != nil {
		_ = tx.Rollback()
		return 0, fmt.Errorf("统计物化表行数失败: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return 0, fmt.Errorf("提交事务失败: %w", err)
	}

	if err := st.RecordViewRefresh(name, rows); err != nil {
		return 0, fmt.Errorf("记录刷新元信息失败: %w", err)
	}

	return rows, nil
}

// RefreshDue 按 YAML 声明的物化策略刷新到期视图：
//   - 声明 materialize.enabled=true 的视图：先 UpdateViewMaterialize(name, true, policy) 同步策略；
//     policy=on_sync → 立即刷新；interval:Xd → 上次刷新时间超过间隔（或从未刷新）才刷新；manual → 跳过；
//   - origin=yaml、库中 Materialized=true、但当前声明未启用物化的视图：UpdateViewMaterialize(name,false,"") 并 DROP TABLE IF EXISTS _mv_<name>（取消物化）。
//
// 返回 refreshed（实际刷新的视图名）、skipped（跳过的）、err（首个失败即返回）。
func RefreshDue(cfg *config.Config, st *store.Store) (refreshed, skipped []string, err error) {
	declared := make(map[string]bool)

	for _, vc := range cfg.Views {
		if vc.Materialize == nil || !vc.Materialize.Enabled {
			continue
		}

		policy := strings.TrimSpace(vc.Materialize.Refresh)
		if policy == "" {
			policy = "on_sync"
		}

		declared[vc.Name] = true

		if err := st.UpdateViewMaterialize(vc.Name, true, policy); err != nil {
			return refreshed, skipped, fmt.Errorf("同步物化策略失败 %s: %w", vc.Name, err)
		}

		switch {
		case policy == "on_sync":
			if _, err := Refresh(st, vc.Name); err != nil {
				return refreshed, skipped, fmt.Errorf("刷新视图失败 %s: %w", vc.Name, err)
			}
			refreshed = append(refreshed, vc.Name)

		case policy == "manual":
			skipped = append(skipped, vc.Name)

		case strings.HasPrefix(policy, "interval:"):
			dur, perr := time.ParseDuration(strings.TrimPrefix(policy, "interval:"))
			if perr != nil {
				return refreshed, skipped, fmt.Errorf("解析刷新间隔失败 %s: %w", vc.Name, perr)
			}

			v, gerr := st.GetView(vc.Name)
			if gerr != nil {
				return refreshed, skipped, fmt.Errorf("读取视图失败 %s: %w", vc.Name, gerr)
			}

			due := true
			if v.LastRefreshAt != "" {
				if t, terr := time.Parse(time.RFC3339, v.LastRefreshAt); terr == nil {
					due = time.Since(t) >= dur
				}
			}

			if !due {
				skipped = append(skipped, vc.Name)
				continue
			}

			if _, err := Refresh(st, vc.Name); err != nil {
				return refreshed, skipped, fmt.Errorf("刷新视图失败 %s: %w", vc.Name, err)
			}
			refreshed = append(refreshed, vc.Name)

		default:
			skipped = append(skipped, vc.Name)
		}
	}

	list, err := st.ListViews()
	if err != nil {
		return refreshed, skipped, fmt.Errorf("列出视图失败: %w", err)
	}

	for _, v := range list {
		if v.Origin != "yaml" {
			continue
		}
		if !v.Materialized {
			continue
		}
		if declared[v.Name] {
			continue
		}

		if err := st.UpdateViewMaterialize(v.Name, false, ""); err != nil {
			return refreshed, skipped, fmt.Errorf("取消物化失败 %s: %w", v.Name, err)
		}

		tbl, merr := store.MaterializeTableName(v.Name)
		if merr != nil {
			return refreshed, skipped, fmt.Errorf("生成物化表名失败 %s: %w", v.Name, merr)
		}
		quoted := `"` + strings.ReplaceAll(tbl, `"`, `""`) + `"`
		if _, derr := st.DB.Exec("DROP TABLE IF EXISTS " + quoted); derr != nil {
			return refreshed, skipped, fmt.Errorf("删除物化表失败 %s: %w", v.Name, derr)
		}
	}

	return refreshed, skipped, nil
}
