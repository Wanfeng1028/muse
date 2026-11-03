package seed

import (
	"path/filepath"
	"testing"

	"sentinel/internal/db"
	"sentinel/internal/store"
)

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "sentinel.db")
	sqlDB, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open(%q) failed: %v", path, err)
	}
	t.Cleanup(func() {
		_ = sqlDB.Close()
	})
	st := store.New(sqlDB)
	if err := st.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant() failed: %v", err)
	}
	return st
}

func TestEnsureSeed_EmptyDBSeedsTwo(t *testing.T) {
	st := newTestStore(t)

	before, err := st.ListMonitors()
	if err != nil {
		t.Fatalf("ListMonitors() before seed failed: %v", err)
	}
	if len(before) != 0 {
		t.Fatalf("expected empty store before seed, got %d monitors", len(before))
	}

	EnsureSeed(st)

	after, err := st.ListMonitors()
	if err != nil {
		t.Fatalf("ListMonitors() after seed failed: %v", err)
	}
	if len(after) != 2 {
		t.Fatalf("expected 2 monitors after seed, got %d", len(after))
	}
}

func TestEnsureSeed_SeedContent(t *testing.T) {
	st := newTestStore(t)

	EnsureSeed(st)

	monitors, err := st.ListMonitors()
	if err != nil {
		t.Fatalf("ListMonitors() failed: %v", err)
	}
	if len(monitors) != 2 {
		t.Fatalf("expected 2 monitors after seed, got %d", len(monitors))
	}

	if monitors[0].Name != "示例站点" {
		t.Errorf("monitors[0].Name = %q, want %q", monitors[0].Name, "示例站点")
	}
	if monitors[1].Name != "示例 TCP 端口" {
		t.Errorf("monitors[1].Name = %q, want %q", monitors[1].Name, "示例 TCP 端口")
	}

	for i, m := range monitors {
		if m.Enabled != 0 {
			t.Errorf("monitors[%d].Enabled = %d, want 0", i, m.Enabled)
		}
		if m.TenantID != 1 {
			t.Errorf("monitors[%d].TenantID = %d, want 1", i, m.TenantID)
		}
		if m.IntervalSec != 300 {
			t.Errorf("monitors[%d].IntervalSec = %d, want 300", i, m.IntervalSec)
		}
	}

	if monitors[0].Kind != "http" {
		t.Errorf("monitors[0].Kind = %q, want %q", monitors[0].Kind, "http")
	}
	if monitors[0].Target != "https://example.com" {
		t.Errorf("monitors[0].Target = %q, want %q", monitors[0].Target, "https://example.com")
	}
	if monitors[1].Kind != "tcp" {
		t.Errorf("monitors[1].Kind = %q, want %q", monitors[1].Kind, "tcp")
	}
	if monitors[1].Target != "example.com:80" {
		t.Errorf("monitors[1].Target = %q, want %q", monitors[1].Target, "example.com:80")
	}
}

func TestEnsureSeed_Idempotent(t *testing.T) {
	st := newTestStore(t)

	EnsureSeed(st)
	EnsureSeed(st)

	monitors, err := st.ListMonitors()
	if err != nil {
		t.Fatalf("ListMonitors() failed: %v", err)
	}
	if len(monitors) != 2 {
		t.Fatalf("expected 2 monitors after calling EnsureSeed twice, got %d", len(monitors))
	}
}

func TestEnsureSeed_NonEmptyUntouched(t *testing.T) {
	st := newTestStore(t)

	_, err := st.CreateMonitor(store.Monitor{
		TenantID:       1,
		Name:           "my-site",
		Kind:           "http",
		Target:         "https://my-site.example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor() failed: %v", err)
	}

	EnsureSeed(st)

	monitors, err := st.ListMonitors()
	if err != nil {
		t.Fatalf("ListMonitors() failed: %v", err)
	}
	if len(monitors) != 1 {
		t.Fatalf("expected 1 monitor (seed must not insert), got %d", len(monitors))
	}
	if monitors[0].Name != "my-site" {
		t.Errorf("monitors[0].Name = %q, want %q", monitors[0].Name, "my-site")
	}
}

func TestEnsureSeed_PartialNoReseed(t *testing.T) {
	st := newTestStore(t)

	EnsureSeed(st)

	first, err := st.ListMonitors()
	if err != nil {
		t.Fatalf("ListMonitors() after first seed failed: %v", err)
	}
	if len(first) != 2 {
		t.Fatalf("expected 2 monitors after first seed, got %d", len(first))
	}

	EnsureSeed(st)

	second, err := st.ListMonitors()
	if err != nil {
		t.Fatalf("ListMonitors() after second seed failed: %v", err)
	}
	if len(second) != 2 {
		t.Fatalf("expected 2 monitors after second seed, got %d", len(second))
	}

	if second[0].Name != first[0].Name {
		t.Errorf("monitors[0].Name changed: %q -> %q", first[0].Name, second[0].Name)
	}
	if second[1].Name != first[1].Name {
		t.Errorf("monitors[1].Name changed: %q -> %q", first[1].Name, second[1].Name)
	}
}
