package store

import (
	"testing"

	"sentinel/internal/db"
)

func newStoreDeep2(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	sqldb, err := db.Open(dir + "/test.db")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { sqldb.Close() })
	return New(sqldb)
}

func TestStatusPageSlugLookupAndDuplicateDeep2(t *testing.T) {
	s := newStoreDeep2(t)
	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	id, err := s.CreateStatusPage(1, "acme", "Acme Status")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}
	if id <= 0 {
		t.Fatalf("expected positive id, got %d", id)
	}

	got, err := s.GetStatusPageBySlug("acme")
	if err != nil {
		t.Fatalf("GetStatusPageBySlug: %v", err)
	}
	if got.ID != id {
		t.Fatalf("id mismatch: got %d want %d", got.ID, id)
	}
	if got.Slug != "acme" {
		t.Fatalf("slug mismatch: got %q want %q", got.Slug, "acme")
	}
	if got.Title != "Acme Status" {
		t.Fatalf("title mismatch: got %q want %q", got.Title, "Acme Status")
	}

	if _, err := s.CreateStatusPage(1, "acme", "Dup"); err == nil {
		t.Fatalf("expected error on duplicate slug, got nil")
	}
}

func TestStatusPageDeleteThenLookupFailsDeep2(t *testing.T) {
	s := newStoreDeep2(t)
	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	id, err := s.CreateStatusPage(1, "gone", "Gone")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	if err := s.DeleteStatusPage(id); err != nil {
		t.Fatalf("DeleteStatusPage: %v", err)
	}

	if _, err := s.GetStatusPageBySlug("gone"); err == nil {
		t.Fatalf("expected error after delete, got nil")
	}
}

func TestStatusPageMonitorAddRemoveDeep2(t *testing.T) {
	s := newStoreDeep2(t)
	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	pageID, err := s.CreateStatusPage(1, "mon", "Monitors")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	monID, err := s.CreateMonitor(Monitor{
		Name:           "api",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	if err := s.AddMonitorToPage(pageID, monID); err != nil {
		t.Fatalf("AddMonitorToPage: %v", err)
	}

	list, err := s.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("expected 1 monitor, got %d", len(list))
	}
	if list[0].ID != monID {
		t.Fatalf("monitor id mismatch: got %d want %d", list[0].ID, monID)
	}

	if err := s.AddMonitorToPage(pageID, monID); err != nil {
		t.Fatalf("AddMonitorToPage duplicate: %v", err)
	}

	list, err = s.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors after dup: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("expected still 1 monitor after dup, got %d", len(list))
	}

	if err := s.RemoveMonitorFromPage(pageID, monID); err != nil {
		t.Fatalf("RemoveMonitorFromPage: %v", err)
	}

	list, err = s.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors after remove: %v", err)
	}
	if len(list) != 0 {
		t.Fatalf("expected 0 monitors after remove, got %d", len(list))
	}
}

func TestSetMonitorPublicReflectedDeep2(t *testing.T) {
	s := newStoreDeep2(t)
	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	pageID, err := s.CreateStatusPage(1, "pub", "Public")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	monID, err := s.CreateMonitor(Monitor{
		Name:           "web",
		Kind:           "http",
		Target:         "https://example.org",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	if err := s.AddMonitorToPage(pageID, monID); err != nil {
		t.Fatalf("AddMonitorToPage: %v", err)
	}

	if err := s.SetMonitorPublic(monID, 1); err != nil {
		t.Fatalf("SetMonitorPublic: %v", err)
	}

	list, err := s.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("expected 1 monitor, got %d", len(list))
	}
	if list[0].IsPublic != 1 {
		t.Fatalf("expected IsPublic=1, got %d", list[0].IsPublic)
	}
}

func TestUpdateStatusPageThemeDeep2(t *testing.T) {
	s := newStoreDeep2(t)
	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	id, err := s.CreateStatusPage(1, "theme", "Theme")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	if err := s.UpdateStatusPageTheme(id, "not-a-theme", "#ffffff"); err == nil {
		t.Fatalf("expected error for invalid theme, got nil")
	}

	if err := s.UpdateStatusPageTheme(id, "light", "not-a-color"); err == nil {
		t.Fatalf("expected error for invalid accent, got nil")
	}

	if err := s.UpdateStatusPageTheme(id, "light", "#abcdef"); err != nil {
		t.Fatalf("UpdateStatusPageTheme valid: %v", err)
	}
}

func TestValidAccentColorDeep2(t *testing.T) {
	cases := []struct {
		in   string
		want bool
	}{
		{"#000000", true},
		{"#ffffff", true},
		{"#AbCdEf", true},
		{"red", false},
		{"", true},
		{"#12345", false},
		{"#1234567", false},
		{"123456", false},
		{"#gggggg", false},
	}
	for _, c := range cases {
		if got := validAccentColor(c.in); got != c.want {
			t.Fatalf("validAccentColor(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestPercentileLinearDeep2(t *testing.T) {
	if got := percentileLinear(nil, 50); got != 0 {
		t.Fatalf("empty slice: got %v want 0", got)
	}
	if got := percentileLinear([]float64{}, 50); got != 0 {
		t.Fatalf("empty slice literal: got %v want 0", got)
	}

	if got := percentileLinear([]float64{42}, 50); got != 42 {
		t.Fatalf("single element: got %v want 42", got)
	}

	sorted := []float64{1, 2, 3, 4, 5}
	if got := percentileLinear(sorted, 0); got != 1 {
		t.Fatalf("p=0: got %v want 1", got)
	}
	if got := percentileLinear(sorted, 100); got != 5 {
		t.Fatalf("p=100: got %v want 5", got)
	}
}

func TestListStatusPagesTenantIsolationDeep2(t *testing.T) {
	s := newStoreDeep2(t)
	if err := s.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}
	if _, err := s.db.Exec(`INSERT INTO tenants(id, name, created_at) VALUES(2, 't2', '2026-10-18T00:00:00Z')`); err != nil {
		t.Fatalf("insert tenant2: %v", err)
	}

	if _, err := s.CreateStatusPage(1, "t1-page", "Tenant1"); err != nil {
		t.Fatalf("CreateStatusPage tenant1: %v", err)
	}
	if _, err := s.CreateStatusPage(2, "t2-page", "Tenant2"); err != nil {
		t.Fatalf("CreateStatusPage tenant2: %v", err)
	}

	pages1, err := s.ListStatusPages(1)
	if err != nil {
		t.Fatalf("ListStatusPages tenant1: %v", err)
	}
	if len(pages1) != 1 {
		t.Fatalf("tenant1: expected 1 page, got %d", len(pages1))
	}
	if pages1[0].Slug != "t1-page" {
		t.Fatalf("tenant1: expected slug t1-page, got %q", pages1[0].Slug)
	}

	pages2, err := s.ListStatusPages(2)
	if err != nil {
		t.Fatalf("ListStatusPages tenant2: %v", err)
	}
	if len(pages2) != 1 {
		t.Fatalf("tenant2: expected 1 page, got %d", len(pages2))
	}
	if pages2[0].Slug != "t2-page" {
		t.Fatalf("tenant2: expected slug t2-page, got %q", pages2[0].Slug)
	}
}