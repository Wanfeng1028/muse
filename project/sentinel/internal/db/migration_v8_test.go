package db

import (
	"database/sql"
	"path/filepath"
	"testing"

	"sentinel/internal/store"
)

// TestMigrationV8_FreshDB 验证新库能补上 sms_phones 列，并能通过 store 层原样写入读出。
func TestMigrationV8_FreshDB(t *testing.T) {
	path := filepath.Join(t.TempDir(), "fresh.db")
	conn, err := Open(path)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer conn.Close()

	cols := tableColumns(t, conn, "monitors")
	if !cols["sms_phones"] {
		t.Fatalf("monitors 缺少 sms_phones 列: %v", cols)
	}

	s := store.New(conn)
	id, err := s.CreateMonitor(store.Monitor{
		Name:           "sms-monitor",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
		IsPublic:       0,
		WebhookURL:     "",
		NotifyChannels: "sms",
		SMSPhones:      "13800138000,13900139000",
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	got, err := s.GetMonitor(id)
	if err != nil {
		t.Fatalf("GetMonitor: %v", err)
	}
	if got.SMSPhones != "13800138000,13900139000" {
		t.Fatalf("SMSPhones 期望 %q，实际 %q", "13800138000,13900139000", got.SMSPhones)
	}
}

// TestMigrationV8_LegacyUpgrade 验证老库（仅迁移到 version 7）升级后新列存在、老数据保留、新列按 DEFAULT 回填。
func TestMigrationV8_LegacyUpgrade(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy.db")

	raw, err := sql.Open("sqlite", "file:"+path+"?_pragma=busy_timeout(5000)")
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	if err := ensureMigrationsTable(raw); err != nil {
		t.Fatalf("ensureMigrationsTable: %v", err)
	}
	for i := 0; i <= 6; i++ {
		if err := applyMigration(raw, migrations[i]); err != nil {
			t.Fatalf("applyMigration[%d]: %v", i, err)
		}
	}
	// v2 引入的列（tenant_id/is_public/notify_channels）由 Open() 流程中的 ensureMonitorColumns 补齐，
	// 手工造老库时同样调用一次，得到与真实 v7 库一致的结构。
	if err := ensureMonitorColumns(raw); err != nil {
		t.Fatalf("ensureMonitorColumns: %v", err)
	}
	if _, err := raw.Exec(
		`INSERT INTO monitors
			(name, kind, target, method, expected_status, timeout_sec, interval_sec, enabled, tenant_id, is_public, webhook_url, notify_channels, created_at, updated_at)
			VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
		"legacy", "http", "https://legacy.example.com", "GET", 200, 5, 60, 1, 1, 0, "", "email", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z",
	); err != nil {
		t.Fatalf("插入老数据: %v", err)
	}
	if err := raw.Close(); err != nil {
		t.Fatalf("关闭老库: %v", err)
	}

	conn, err := Open(path)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer conn.Close()

	cols := tableColumns(t, conn, "monitors")
	if !cols["sms_phones"] {
		t.Fatalf("升级后 monitors 缺少 sms_phones 列: %v", cols)
	}

	var (
		name      string
		smsPhones string
	)
	if err := conn.QueryRow(`SELECT name, sms_phones FROM monitors WHERE name = ?`, "legacy").Scan(&name, &smsPhones); err != nil {
		t.Fatalf("查询老数据: %v", err)
	}
	if name != "legacy" {
		t.Fatalf("老数据行丢失或 name 不符: %q", name)
	}
	if smsPhones != "" {
		t.Fatalf("sms_phones 期望按 DEFAULT 回填为 %q，实际 %q", "", smsPhones)
	}
}
