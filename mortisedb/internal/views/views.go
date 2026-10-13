// Package views 提供数据视图（View）的注册与执行能力。
// 视图本质上是一条被保存下来的 SELECT 语句，可以按名称反复执行。
package views

import (
	"fmt"
	"strings"

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
