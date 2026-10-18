// types.go 定义 pgsource 包的基础数据结构与 PG 类型到 mortisedb 内部类型的映射。
package pgsource

import (
	"strings"
)

// Column 描述一列的元信息。
type Column struct {
	Name        string `json:"name"`
	PGType      string `json:"pg_type"`
	MortiseType string `json:"mortise_type"`
}

// TableSchema 描述一张表的元信息。
type TableSchema struct {
	Name       string   `json:"name"`
	PrimaryKey string   `json:"primary_key"`
	Columns    []Column `json:"columns"`
}

// Row 表示一行数据。
type Row = map[string]any

// MapPGType 将 PostgreSQL 类型映射为 mortisedb 内部类型。
func MapPGType(pgType string) string {
	switch strings.ToLower(pgType) {
	case "text", "varchar", "character varying", "char", "character",
		"json", "jsonb", "uuid", "inet", "cidr", "macaddr":
		return "TEXT"
	case "int2", "int4", "int8", "smallint", "integer", "bigint",
		"serial", "bigserial":
		return "INTEGER"
	case "numeric", "decimal", "real", "float4", "float8", "double precision":
		return "REAL"
	case "bool", "boolean":
		return "BOOLEAN"
	case "timestamp", "timestamptz", "date", "time", "timetz", "interval":
		return "DATETIME"
	case "bytea":
		return "BLOB"
	default:
		return "TEXT"
	}
}

// ColumnNames 按 Columns 顺序返回列名。
func (s TableSchema) ColumnNames() []string {
	names := make([]string, 0, len(s.Columns))
	for _, c := range s.Columns {
		names = append(names, c.Name)
	}
	return names
}
