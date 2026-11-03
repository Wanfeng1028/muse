package store

import (
	"database/sql"
	"errors"
	"path/filepath"
	"testing"

	"sentinel/internal/db"
)

// newTestStore 在 t.TempDir() 下创建 sqlite 文件、打开数据库并执行迁移，返回 *Store。
func newTestStore(t *testing.T) *Store {
	t.Helper()
	path := filepath.Join(t.TempDir(), "test.db")
	d, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { _ = d.Close() })
	return New(d)
}

// TestCreateMonitorTenantAndPublic 验证 CreateMonitor 能读写 tenant_id / is_public 新列。
func TestCreateMonitorTenantAndPublic(t *testing.T) {
	s := newTestStore(t)

	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	id, err := s.CreateMonitor(Monitor{
		Name:           "site",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
		IsPublic:       1,
		WebhookURL:     "",
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	if id == 0 {
		t.Fatalf("CreateMonitor returned zero id")
	}

	got, err := s.GetMonitor(id)
	if err != nil {
		t.Fatalf("GetMonitor: %v", err)
	}
	if got.TenantID != 1 {
		t.Errorf("TenantID = %d, want 1", got.TenantID)
	}
	if got.IsPublic != 1 {
		t.Errorf("IsPublic = %d, want 1", got.IsPublic)
	}

	// 更新后重新读取验证。
	got.TenantID = 2
	got.IsPublic = 0
	if err := s.UpdateMonitor(id, got); err != nil {
		t.Fatalf("UpdateMonitor: %v", err)
	}
	got2, err := s.GetMonitor(id)
	if err != nil {
		t.Fatalf("GetMonitor after update: %v", err)
	}
	if got2.TenantID != 2 {
		t.Errorf("after update TenantID = %d, want 2", got2.TenantID)
	}
	if got2.IsPublic != 0 {
		t.Errorf("after update IsPublic = %d, want 0", got2.IsPublic)
	}
}

// TestListMonitorsByTenant 验证按租户过滤。
func TestListMonitorsByTenant(t *testing.T) {
	s := newTestStore(t)

	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	mk := func(name string, tenantID int64) int64 {
		id, err := s.CreateMonitor(Monitor{
			Name:           name,
			Kind:           "http",
			Target:         "https://example.com",
			Method:         "GET",
			ExpectedStatus: 200,
			TimeoutSec:     5,
			IntervalSec:    60,
			Enabled:        1,
			TenantID:       tenantID,
			IsPublic:       0,
		})
		if err != nil {
			t.Fatalf("CreateMonitor(%s): %v", name, err)
		}
		return id
	}

	idA1 := mk("a1", 1)
	idA2 := mk("a2", 1)
	_ = mk("b1", 2)

	got, err := s.ListMonitorsByTenant(1)
	if err != nil {
		t.Fatalf("ListMonitorsByTenant: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("len = %d, want 2", len(got))
	}
	if got[0].ID != idA1 || got[1].ID != idA2 {
		t.Errorf("ids = [%d,%d], want [%d,%d]", got[0].ID, got[1].ID, idA1, idA2)
	}
	for _, m := range got {
		if m.TenantID != 1 {
			t.Errorf("TenantID = %d, want 1", m.TenantID)
		}
	}

	gotB, err := s.ListMonitorsByTenant(2)
	if err != nil {
		t.Fatalf("ListMonitorsByTenant(2): %v", err)
	}
	if len(gotB) != 1 {
		t.Fatalf("tenant 2 len = %d, want 1", len(gotB))
	}

	// 无匹配租户应返回空。
	gotEmpty, err := s.ListMonitorsByTenant(999)
	if err != nil {
		t.Fatalf("ListMonitorsByTenant(999): %v", err)
	}
	if len(gotEmpty) != 0 {
		t.Fatalf("tenant 999 len = %d, want 0", len(gotEmpty))
	}
}

// TestCreateAndListUsers 验证 CreateUser / ListUsers。
func TestCreateAndListUsers(t *testing.T) {
	s := newTestStore(t)

	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	id1, err := s.CreateUser(1, "alice", "hash-alice")
	if err != nil {
		t.Fatalf("CreateUser(alice): %v", err)
	}
	id2, err := s.CreateUser(1, "bob", "hash-bob")
	if err != nil {
		t.Fatalf("CreateUser(bob): %v", err)
	}
	if id1 == 0 || id2 == 0 || id1 == id2 {
		t.Fatalf("unexpected ids: %d, %d", id1, id2)
	}

	users, err := s.ListUsers()
	if err != nil {
		t.Fatalf("ListUsers: %v", err)
	}
	if len(users) != 2 {
		t.Fatalf("len = %d, want 2", len(users))
	}
	if users[0].ID != id1 || users[0].Name != "alice" || users[0].TokenHash != "hash-alice" {
		t.Errorf("users[0] = %+v", users[0])
	}
	if users[1].ID != id2 || users[1].Name != "bob" || users[1].TokenHash != "hash-bob" {
		t.Errorf("users[1] = %+v", users[1])
	}
	for _, u := range users {
		if u.TenantID != 1 {
			t.Errorf("TenantID = %d, want 1", u.TenantID)
		}
		if u.CreatedAt == "" {
			t.Errorf("CreatedAt is empty for %q", u.Name)
		}
	}
}

// TestEnsureDefaultTenantIdempotent 验证 EnsureDefaultTenant 幂等（调用两次不报错）。
func TestEnsureDefaultTenantIdempotent(t *testing.T) {
	s := newTestStore(t)

	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("first EnsureDefaultTenant: %v", err)
	}
	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("second EnsureDefaultTenant: %v", err)
	}

	var n int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM tenants`).Scan(&n); err != nil {
		t.Fatalf("count tenants: %v", err)
	}
	if n != 1 {
		t.Fatalf("tenants count = %d, want 1", n)
	}

	var name string
	if err := s.db.QueryRow(`SELECT name FROM tenants WHERE id = 1`).Scan(&name); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			t.Fatalf("default tenant id=1 missing")
		}
		t.Fatalf("select default tenant: %v", err)
	}
	if name != "default" {
		t.Errorf("name = %q, want %q", name, "default")
	}
}
