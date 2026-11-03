// iface.go 定义配置、游标、连接串校验以及数据源接口。
package pgsource

import (
	"context"
	"errors"
	"net/url"
	"time"
)

// Cursor 表示一次增量拉取的游标位置。
type Cursor struct {
	UpdatedAt time.Time `json:"updated_at"`
	LastPK    string    `json:"last_pk"`
}

// Config 表示数据源配置。
type Config struct {
	ConnStr      string   `yaml:"conn_str" json:"conn_str"`
	Tables       []string `yaml:"tables" json:"tables"`
	CursorColumn string   `yaml:"cursor_column" json:"cursor_column"`
	BatchSize    int      `yaml:"batch_size" json:"batch_size"`
}

// Validate 校验并补全配置。
func (c *Config) Validate() error {
	if c.ConnStr == "" {
		return errors.New("ConnStr 不能为空")
	}
	if len(c.Tables) == 0 {
		return errors.New("Tables 不能为空")
	}
	if c.CursorColumn == "" {
		c.CursorColumn = "updated_at"
	}
	if c.BatchSize <= 0 {
		c.BatchSize = 1000
	}
	if _, err := EnsureReadOnlyConnStr(c.ConnStr); err != nil {
		return err
	}
	return nil
}

// Advance 尝试推进游标，返回是否发生了推进。
func (cur *Cursor) Advance(updatedAt time.Time, pk string) bool {
	if updatedAt.After(cur.UpdatedAt) {
		cur.UpdatedAt = updatedAt
		cur.LastPK = pk
		return true
	}
	if updatedAt.Equal(cur.UpdatedAt) && pk > cur.LastPK {
		cur.LastPK = pk
		return true
	}
	return false
}

// EnsureReadOnlyConnStr 校验并改写连接串为只读模式。
func EnsureReadOnlyConnStr(raw string) (string, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return "", err
	}
	if u.Scheme != "postgres" && u.Scheme != "postgresql" {
		return "", errors.New("连接串 scheme 必须是 postgres 或 postgresql")
	}
	q := u.Query()
	if !q.Has("default_transaction_read_only") {
		q.Set("default_transaction_read_only", "on")
		u.RawQuery = q.Encode()
	}
	return u.String(), nil
}

// ReadSource 是增量只读数据源接口。
//
// PullRows 约定：返回按 (updated_at ASC, pk ASC) 排序的行，只返回"新于游标"的行
// （updated_at > since.UpdatedAt，或 updated_at == since.UpdatedAt 且 pk > since.LastPK），
// 最多 BatchSize 行；Row 中必须包含主键列与游标列。
type ReadSource interface {
	PullTables(ctx context.Context) ([]TableSchema, error)
	PullRows(ctx context.Context, table string, since Cursor) ([]Row, error)
	Close() error
}
