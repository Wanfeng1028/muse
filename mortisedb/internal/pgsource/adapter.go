package pgsource

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/connector"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
)

// Adapter bridges a ReadSource into the connector.Source interface.
type Adapter struct {
	name      string
	src       ReadSource
	cursorCol string
	mu        sync.Mutex
	cursors   map[string]Cursor
	schemas   map[string]TableSchema
}

// NewAdapter constructs an Adapter; empty cursorCol defaults to updated_at.
func NewAdapter(name string, src ReadSource, cursorCol string) *Adapter {
	if cursorCol == "" {
		cursorCol = "updated_at"
	}
	return &Adapter{
		name:      name,
		src:       src,
		cursorCol: cursorCol,
		cursors:   make(map[string]Cursor),
		schemas:   make(map[string]TableSchema),
	}
}

// Name returns the adapter name.
func (a *Adapter) Name() string {
	return a.name
}

// Tables pulls schemas from the source and converts to connector.TableInfo.
func (a *Adapter) Tables() ([]connector.TableInfo, error) {
	schemas, err := a.src.PullTables(context.Background())
	if err != nil {
		return nil, err
	}
	out := make([]connector.TableInfo, 0, len(schemas))
	a.mu.Lock()
	defer a.mu.Unlock()
	for _, s := range schemas {
		cols := make([]infer.Column, 0, len(s.Columns))
		for _, c := range s.Columns {
			cols = append(cols, infer.Column{Name: c.Name, Type: c.MortiseType})
		}
		out = append(out, connector.TableInfo{
			Name:        s.Name,
			SourceTable: s.Name,
			Primary:     s.PrimaryKey,
			Columns:     cols,
		})
		a.schemas[s.Name] = s
	}
	return out, nil
}

// Rows pulls incremental rows for table using since map.
func (a *Adapter) Rows(table string, since map[string]string) ([]Row, error) {
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

// Close closes the underlying source.
func (a *Adapter) Close() error {
	return a.src.Close()
}

var _ connector.Source = (*Adapter)(nil)
