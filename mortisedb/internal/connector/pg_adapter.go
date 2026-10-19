package connector

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/pgsource"
)

// PGAdapter 把 pgsource.ReadSource 桥接为 connector.Source。
type PGAdapter struct {
	name      string
	src       pgsource.ReadSource
	cursorCol string
	mu        sync.Mutex
	cursors   map[string]pgsource.Cursor
	schemas   map[string]pgsource.TableSchema
}

// NewPGAdapter 构造 PGAdapter；cursorCol 为空时默认 updated_at。
func NewPGAdapter(name string, src pgsource.ReadSource, cursorCol string) *PGAdapter {
	if cursorCol == "" {
		cursorCol = "updated_at"
	}
	return &PGAdapter{
		name:      name,
		src:       src,
		cursorCol: cursorCol,
		cursors:   make(map[string]pgsource.Cursor),
		schemas:   make(map[string]pgsource.TableSchema),
	}
}

// Name 返回适配器名称。
func (a *PGAdapter) Name() string {
	return a.name
}

// Tables 拉取源端表结构并转换为 connector.TableInfo。
func (a *PGAdapter) Tables() ([]TableInfo, error) {
	schemas, err := a.src.PullTables(context.Background())
	if err != nil {
		return nil, err
	}
	out := make([]TableInfo, 0, len(schemas))
	a.mu.Lock()
	defer a.mu.Unlock()
	for _, s := range schemas {
		cols := make([]infer.Column, 0, len(s.Columns))
		for _, c := range s.Columns {
			cols = append(cols, infer.Column{Name: c.Name, Type: c.MortiseType})
		}
		out = append(out, TableInfo{
			Name:        s.Name,
			SourceTable: s.Name,
			Primary:     s.PrimaryKey,
			Columns:     cols,
		})
		a.schemas[s.Name] = s
	}
	return out, nil
}

// Rows 按 since 游标拉取表的增量行。
func (a *PGAdapter) Rows(table string, since map[string]string) ([]Row, error) {
	a.mu.Lock()
	cur := a.cursors[table]
	if since != nil {
		if v, ok := since[a.cursorCol]; ok && v != "" {
			ts, err := time.Parse(time.RFC3339, v)
			if err != nil {
				a.mu.Unlock()
				return nil, err
			}
			cur.UpdatedAt = ts
		}
		if v, ok := since[a.cursorCol+":pk"]; ok {
			cur.LastPK = v
		}
	}
	schema, ok := a.schemas[table]
	a.mu.Unlock()

	if !ok {
		if _, err := a.Tables(); err != nil {
			return nil, err
		}
		a.mu.Lock()
		schema = a.schemas[table]
		a.mu.Unlock()
	}

	rows, err := a.src.PullRows(context.Background(), table, cur)
	if err != nil {
		return nil, err
	}

	pkCol := schema.PrimaryKey
	for _, row := range rows {
		var ts time.Time
		haveTS := false
		if raw, ok := row[a.cursorCol]; ok {
			switch v := raw.(type) {
			case time.Time:
				ts = v
				haveTS = true
			case string:
				if parsed, perr := time.Parse(time.RFC3339, v); perr == nil {
					ts = parsed
					haveTS = true
				}
			}
		}
		if !haveTS {
			continue
		}
		var pkStr string
		if pkCol != "" {
			if v, ok := row[pkCol]; ok {
				pkStr = fmt.Sprint(v)
			}
		}
		cur.Advance(ts, pkStr)
	}

	a.mu.Lock()
	a.cursors[table] = cur
	a.mu.Unlock()

	return rows, nil
}

// Close 关闭底层数据源。
func (a *PGAdapter) Close() error {
	return a.src.Close()
}

var _ Source = (*PGAdapter)(nil)
