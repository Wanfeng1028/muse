// Package views 提供数据视图（View）的注册与执行能力。
// 视图本质上是一条被保存下来的 SELECT 语句，可以按名称反复执行。
package views

import (
	"errors"
	"fmt"
	"strings"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// Add 校验并保存一个视图。
// name 为视图名称，sql 为视图的 SELECT 语句，desc 为描述。
// 校验规则：sql 去空白后必须以 SELECT 开头（大小写不敏感）。
// 试运行：用 "SELECT * FROM (" + sql + ") LIMIT 1" 执行，失败则返回错误。
func Add(st *store.Store, name, sql, desc string) error {
	if st == nil {
		return fmt.Errorf("store 为空")
	}
	if strings.TrimSpace(name) == "" {
		return fmt.Errorf("视图名称不能为空")
	}
	trimmed := strings.TrimSpace(sql)
	if trimmed == "" {
		return fmt.Errorf("视图 SQL 不能为空")
	}
	// 必须以 SELECT 开头（大小写不敏感）
	if !strings.HasPrefix(strings.ToUpper(trimmed), "SELECT") {
		return fmt.Errorf("视图 SQL 必须以 SELECT 开头")
	}

	// 试运行：外包一层子查询，限制返回 1 行，仅用于验证 SQL 合法性
	probe := "SELECT * FROM (" + sql + ") LIMIT 1"
	if _, _, err := st.Query(probe); err != nil {
		return fmt.Errorf("视图试运行失败: %w", err)
	}

	// 试运行通过后保存视图
	if err := st.SaveView(name, sql, desc); err != nil {
		return fmt.Errorf("保存视图失败: %w", err)
	}
	return nil
}

// Run 执行指定名称的视图。
// name 为视图名称，limit 为返回行数上限（<=0 时不加 LIMIT）。
// 返回列名、行数据。
func Run(st *store.Store, name string, limit int) ([]string, [][]any, error) {
	if st == nil {
		return nil, nil, fmt.Errorf("store 为空")
	}
	if strings.TrimSpace(name) == "" {
		return nil, nil, fmt.Errorf("视图名称不能为空")
	}

	// 取出视图定义
	v, err := st.GetView(name)
	if err != nil {
		return nil, nil, fmt.Errorf("获取视图失败: %w", err)
	}

	// 外包一层子查询执行，附加 LIMIT
	query := "SELECT * FROM (" + v.SQL + ")"
	var args []any
	if limit > 0 {
		query += " LIMIT ?"
		args = append(args, limit)
	}

	cols, rows, err := st.Query(query, args...)
	if err != nil {
		return nil, nil, fmt.Errorf("执行视图失败: %w", err)
	}
	return cols, rows, nil
}

// SyncFromConfig 把配置中 views 段声明的视图幂等注册进 _m_views。
// - 不存在的声明 → 新增（origin=yaml），added++
// - 已存在且 SQL 或描述变化 → 更新，updated++
// - 已存在且完全相同 → 不动（幂等）
// - 库中 origin=yaml 但配置里已删除的 → 清理，removed++
// - 手工视图（origin=manual）永不清理
// 注意：不做 SQL 试运行——注册时目标表可能尚未同步出来，合法性由 Run 时与 views add 的试运行兜底。
// 返回 (added, updated, removed, err)。
func SyncFromConfig(cfg *config.Config, st *store.Store) (added, updated, removed int, err error) {
	if cfg == nil {
		return 0, 0, 0, fmt.Errorf("配置为空")
	}
	if st == nil {
		return 0, 0, 0, fmt.Errorf("store 为空")
	}

	// 声明名集合，用于后续清理判定。
	declared := make(map[string]struct{}, len(cfg.Views))

	for i, vc := range cfg.Views {
		name := strings.TrimSpace(vc.Name)
		if name == "" {
			return 0, 0, 0, fmt.Errorf("第 %d 个视图声明缺少名称", i+1)
		}
		// SQL 去空白后必须以 SELECT 开头（大小写不敏感）。
		trimmedSQL := strings.TrimSpace(vc.SQL)
		if len(trimmedSQL) < 6 || !strings.EqualFold(trimmedSQL[:6], "SELECT") {
			return 0, 0, 0, fmt.Errorf("视图 %q 的 SQL 必须以 SELECT 开头", name)
		}

		// 同名声明重复视为配置错误，提前暴露。
		if _, dup := declared[name]; dup {
			return 0, 0, 0, fmt.Errorf("视图 %q 在配置中重复声明", name)
		}
		declared[name] = struct{}{}

		// 存原始声明值（不 trim），保证"改空白也算变更"可检测。
		sqlStr := vc.SQL
		desc := vc.Description

		existing, getErr := st.GetView(name)
		if errors.Is(getErr, store.ErrNotFound) {
			if err := st.SaveYAMLView(name, sqlStr, desc); err != nil {
				return added, updated, removed, fmt.Errorf("注册视图 %q 失败: %w", name, err)
			}
			added++
			continue
		}
		if getErr != nil {
			return added, updated, removed, fmt.Errorf("查询视图 %q 失败: %w", name, getErr)
		}
		// 已存在：SQL 或描述变化则更新。
		if existing.SQL != sqlStr || existing.Description != desc {
			if err := st.SaveYAMLView(name, sqlStr, desc); err != nil {
				return added, updated, removed, fmt.Errorf("更新视图 %q 失败: %w", name, err)
			}
			updated++
		}
	}

	// 清理：库中 origin=yaml 但配置里已删除的。
	views, listErr := st.ListViews()
	if listErr != nil {
		return added, updated, removed, fmt.Errorf("列举视图失败: %w", listErr)
	}
	for _, v := range views {
		if v.Origin != "yaml" {
			continue
		}
		if _, ok := declared[v.Name]; ok {
			continue
		}
		if err := st.DropView(v.Name); err != nil {
			return added, updated, removed, fmt.Errorf("清理视图 %q 失败: %w", v.Name, err)
		}
		removed++
	}

	return added, updated, removed, nil
}
