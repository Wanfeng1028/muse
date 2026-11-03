// fake.go 提供 ReadSource 的内存测试替身。
package pgsource

import (
	"context"
	"errors"
	"sort"
	"time"
)

// FakeSource 是 ReadSource 的内存测试替身。
type FakeSource struct {
	cfg       Config
	schemas   []TableSchema
	rows      map[string][]Row
	pkCol     map[string]string
	cursorCol map[string]string
}

// NewFakeSource 构造 FakeSource，配置非法时 panic（fail fast）。
func NewFakeSource(cfg Config, schemas []TableSchema, rows map[string][]Row, pkCol map[string]string, cursorCol map[string]string) *FakeSource {
	if err := cfg.Validate(); err != nil {
		panic(err)
	}
	return &FakeSource{
		cfg:       cfg,
		schemas:   schemas,
		rows:      rows,
		pkCol:     pkCol,
		cursorCol: cursorCol,
	}
}

// PullTables 返回 schema 的深拷贝。
func (f *FakeSource) PullTables(ctx context.Context) ([]TableSchema, error) {
	out := make([]TableSchema, 0, len(f.schemas))
	for _, s := range f.schemas {
		cols := make([]Column, len(s.Columns))
		copy(cols, s.Columns)
		out = append(out, TableSchema{
			Name:       s.Name,
			PrimaryKey: s.PrimaryKey,
			Columns:    cols,
		})
	}
	return out, nil
}

// PullRows 按游标约定返回增量行。
func (f *FakeSource) PullRows(ctx context.Context, table string, since Cursor) ([]Row, error) {
	src, ok := f.rows[table]
	if !ok {
		return nil, errors.New("表不存在: " + table)
	}
	cursorCol := f.cursorCol[table]
	pkCol := f.pkCol[table]

	type entry struct {
		row       Row
		updatedAt time.Time
		pk        string
	}
	filtered := make([]entry, 0, len(src))
	for _, row := range src {
		raw, ok := row[cursorCol]
		if !ok {
			continue
		}
		str, ok := raw.(string)
		if !ok {
			continue
		}
		ts, err := time.Parse(time.RFC3339, str)
		if err != nil {
			continue
		}
		pkVal, ok := row[pkCol]
		if !ok {
			continue
		}
		pkStr, ok := pkVal.(string)
		if !ok {
			continue
		}
		if ts.After(since.UpdatedAt) || (ts.Equal(since.UpdatedAt) && pkStr > since.LastPK) {
			filtered = append(filtered, entry{row: row, updatedAt: ts, pk: pkStr})
		}
	}

	sort.SliceStable(filtered, func(i, j int) bool {
		if !filtered[i].updatedAt.Equal(filtered[j].updatedAt) {
			return filtered[i].updatedAt.Before(filtered[j].updatedAt)
		}
		return filtered[i].pk < filtered[j].pk
	})

	limit := f.cfg.BatchSize
	if len(filtered) > limit {
		filtered = filtered[:limit]
	}

	out := make([]Row, 0, len(filtered))
	for _, e := range filtered {
		out = append(out, deepCopyRow(e.row))
	}
	return out, nil
}

// Close 关闭数据源。
func (f *FakeSource) Close() error {
	return nil
}

// AdvanceCursor 拉取该表全部行并推进游标，用于测试游标推进逻辑。
func (f *FakeSource) AdvanceCursor(table string, cur *Cursor) error {
	if _, ok := f.rows[table]; !ok {
		return errors.New("表不存在: " + table)
	}
	var since Cursor
	for {
		rows, err := f.PullRows(context.Background(), table, since)
		if err != nil {
			return err
		}
		if len(rows) == 0 {
			return nil
		}
		cursorCol := f.cursorCol[table]
		pkCol := f.pkCol[table]
		for _, row := range rows {
			raw, ok := row[cursorCol]
			if !ok {
				continue
			}
			str, ok := raw.(string)
			if !ok {
				continue
			}
			ts, err := time.Parse(time.RFC3339, str)
			if err != nil {
				continue
			}
			pkVal, ok := row[pkCol]
			if !ok {
				continue
			}
			pkStr, ok := pkVal.(string)
			if !ok {
				continue
			}
			cur.Advance(ts, pkStr)
			since = *cur
		}
	}
}

func deepCopyRow(row Row) Row {
	out := make(Row, len(row))
	for k, v := range row {
		out[k] = v
	}
	return out
}
