// Package store 提供数据存储访问能力。
package store

// Ping 检测数据库连接是否可用。
func (s *Store) Ping() error { return s.db.Ping() }
