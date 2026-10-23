package store

import (
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"sentinel/internal/escalation"
)

func TestWsen_StatusPageCRUD(t *testing.T) {
	s := newTestStore(t)
	tenantID := int64(1)
	slug := "wsen-page"
	title := "WSEN Status Page"

	id, err := s.CreateStatusPage(tenantID, slug, title)
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}
	if id <= 0 {
		t.Fatalf("expected positive id, got %d", id)
	}

	sp, err := s.GetStatusPage(id)
	if err != nil {
		t.Fatalf("GetStatusPage: %v", err)
	}
	if sp.ID != id {
		t.Errorf("ID mismatch: got %d want %d", sp.ID, id)
	}
	if sp.TenantID != tenantID {
		t.Errorf("TenantID mismatch: got %d want %d", sp.TenantID, tenantID)
	}
	if sp.Slug != slug {
		t.Errorf("Slug mismatch: got %q want %q", sp.Slug, slug)
	}
	if sp.Title != title {
		t.Errorf("Title mismatch: got %q want %q", sp.Title, title)
	}
	if sp.Theme != "light" {
		t.Errorf("Theme default mismatch: got %q want %q", sp.Theme, "light")
	}
	if sp.AccentColor != "" {
		t.Errorf("AccentColor default mismatch: got %q want %q", sp.AccentColor, "")
	}

	// ListStatusPages: tenant isolation（status_pages.tenant_id 有外键约束，
	// 且 Store 无 CreateTenant 方法，用不存在的租户断言 WHERE 过滤语义）
	pagesOther, err := s.ListStatusPages(999)
	if err != nil {
		t.Fatalf("ListStatusPages unknown tenant: %v", err)
	}
	if len(pagesOther) != 0 {
		t.Errorf("expected 0 pages for unknown tenant, got %d", len(pagesOther))
	}

	// 同租户第二页：断言按 id 升序
	id2, err := s.CreateStatusPage(tenantID, "wsen-page-2", "WSEN Page 2")
	if err != nil {
		t.Fatalf("CreateStatusPage second: %v", err)
	}
	if id2 <= id {
		t.Errorf("expected id2 > id, got %d, %d", id2, id)
	}

	pages, err := s.ListStatusPages(tenantID)
	if err != nil {
		t.Fatalf("ListStatusPages: %v", err)
	}
	if len(pages) != 2 {
		t.Fatalf("expected 2 pages for tenant %d, got %d", tenantID, len(pages))
	}
	if pages[0].ID != id || pages[1].ID != id2 {
		t.Errorf("ListStatusPages order mismatch: got [%d %d] want [%d %d]", pages[0].ID, pages[1].ID, id, id2)
	}

	// GetStatusPageBySlug hit
	spBySlug, err := s.GetStatusPageBySlug(slug)
	if err != nil {
		t.Fatalf("GetStatusPageBySlug hit: %v", err)
	}
	if spBySlug.ID != id {
		t.Errorf("GetStatusPageBySlug ID mismatch: got %d want %d", spBySlug.ID, id)
	}

	// GetStatusPageBySlug miss
	_, err = s.GetStatusPageBySlug("nonexistent-slug")
	if !errors.Is(err, sql.ErrNoRows) {
		t.Errorf("GetStatusPageBySlug miss: expected sql.ErrNoRows, got %v", err)
	}

	// GetStatusPage miss
	_, err = s.GetStatusPage(999999)
	if !errors.Is(err, sql.ErrNoRows) {
		t.Errorf("GetStatusPage miss: expected sql.ErrNoRows, got %v", err)
	}

	// DeleteStatusPage
	if err := s.DeleteStatusPage(id); err != nil {
		t.Fatalf("DeleteStatusPage: %v", err)
	}
	_, err = s.GetStatusPage(id)
	if !errors.Is(err, sql.ErrNoRows) {
		t.Errorf("GetStatusPage after delete: expected sql.ErrNoRows, got %v", err)
	}

	// Delete non-existent id should not error
	if err := s.DeleteStatusPage(999999); err != nil {
		t.Errorf("DeleteStatusPage non-existent: expected nil error, got %v", err)
	}
}

func TestWsen_PageMonitorAssociation(t *testing.T) {
	s := newTestStore(t)
	tenantID := int64(1)

	pageID, err := s.CreateStatusPage(tenantID, "wsen-assoc", "WSEN Assoc")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	// Create two monitors
	monA := Monitor{
		Name:           "wsen-mon-a",
		Kind:           "http",
		Target:         "http://a.example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       tenantID,
		IsPublic:       0,
	}
	monB := Monitor{
		Name:           "wsen-mon-b",
		Kind:           "http",
		Target:         "http://b.example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       tenantID,
		IsPublic:       0,
	}

	idA, err := s.CreateMonitor(monA)
	if err != nil {
		t.Fatalf("CreateMonitor A: %v", err)
	}
	idB, err := s.CreateMonitor(monB)
	if err != nil {
		t.Fatalf("CreateMonitor B: %v", err)
	}

	// AddMonitorToPage idempotent
	if err := s.AddMonitorToPage(pageID, idA); err != nil {
		t.Fatalf("AddMonitorToPage first: %v", err)
	}
	if err := s.AddMonitorToPage(pageID, idA); err != nil {
		t.Fatalf("AddMonitorToPage second: %v", err)
	}

	// Add B as well
	if err := s.AddMonitorToPage(pageID, idB); err != nil {
		t.Fatalf("AddMonitorToPage B: %v", err)
	}

	// ListPageMonitors: should have 2, ordered by m.id ASC
	mons, err := s.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors: %v", err)
	}
	if len(mons) != 2 {
		t.Fatalf("expected 2 monitors, got %d", len(mons))
	}
	if mons[0].ID != idA || mons[1].ID != idB {
		t.Errorf("ListPageMonitors order mismatch: got [%d, %d], want [%d, %d]", mons[0].ID, mons[1].ID, idA, idB)
	}

	// RemoveMonitorFromPage
	if err := s.RemoveMonitorFromPage(pageID, idA); err != nil {
		t.Fatalf("RemoveMonitorFromPage: %v", err)
	}
	mons, err = s.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors after remove: %v", err)
	}
	if len(mons) != 1 {
		t.Fatalf("expected 1 monitor after remove, got %d", len(mons))
	}
	if mons[0].ID != idB {
		t.Errorf("remaining monitor mismatch: got %d want %d", mons[0].ID, idB)
	}

	// Remove non-existent association should not error
	if err := s.RemoveMonitorFromPage(pageID, 999999); err != nil {
		t.Errorf("RemoveMonitorFromPage non-existent: expected nil error, got %v", err)
	}

	// SetMonitorPublic normalization
	// 2 -> 1
	if err := s.SetMonitorPublic(idA, 2); err != nil {
		t.Fatalf("SetMonitorPublic 2: %v", err)
	}
	mA, err := s.GetMonitor(idA)
	if err != nil {
		t.Fatalf("GetMonitor after SetMonitorPublic 2: %v", err)
	}
	if mA.IsPublic != 1 {
		t.Errorf("SetMonitorPublic(2) expected IsPublic=1, got %d", mA.IsPublic)
	}

	// 0 -> 0
	if err := s.SetMonitorPublic(idA, 0); err != nil {
		t.Fatalf("SetMonitorPublic 0: %v", err)
	}
	mA, err = s.GetMonitor(idA)
	if err != nil {
		t.Fatalf("GetMonitor after SetMonitorPublic 0: %v", err)
	}
	if mA.IsPublic != 0 {
		t.Errorf("SetMonitorPublic(0) expected IsPublic=0, got %d", mA.IsPublic)
	}

	// -5 -> 1
	if err := s.SetMonitorPublic(idA, -5); err != nil {
		t.Fatalf("SetMonitorPublic -5: %v", err)
	}
	mA, err = s.GetMonitor(idA)
	if err != nil {
		t.Fatalf("GetMonitor after SetMonitorPublic -5: %v", err)
	}
	if mA.IsPublic != 1 {
		t.Errorf("SetMonitorPublic(-5) expected IsPublic=1, got %d", mA.IsPublic)
	}
}

func TestWsen_UpdateStatusPageTheme(t *testing.T) {
	s := newTestStore(t)
	tenantID := int64(1)
	id, err := s.CreateStatusPage(tenantID, "wsen-theme", "WSEN Theme")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}

	// dark + valid accent
	if err := s.UpdateStatusPageTheme(id, "dark", "#1a2B3c"); err != nil {
		t.Fatalf("UpdateStatusPageTheme dark: %v", err)
	}
	sp, err := s.GetStatusPage(id)
	if err != nil {
		t.Fatalf("GetStatusPage after update: %v", err)
	}
	if sp.Theme != "dark" {
		t.Errorf("Theme mismatch: got %q want %q", sp.Theme, "dark")
	}
	if sp.AccentColor != "#1a2B3c" {
		t.Errorf("AccentColor mismatch: got %q want %q", sp.AccentColor, "#1a2B3c")
	}

	// empty accent
	if err := s.UpdateStatusPageTheme(id, "light", ""); err != nil {
		t.Fatalf("UpdateStatusPageTheme empty accent: %v", err)
	}
	sp, err = s.GetStatusPage(id)
	if err != nil {
		t.Fatalf("GetStatusPage after empty accent: %v", err)
	}
	if sp.Theme != "light" {
		t.Errorf("Theme mismatch: got %q want %q", sp.Theme, "light")
	}
	if sp.AccentColor != "" {
		t.Errorf("AccentColor mismatch: got %q want %q", sp.AccentColor, "")
	}

	// invalid theme
	err = s.UpdateStatusPageTheme(id, "blue", "#ffffff")
	if err == nil {
		t.Fatal("expected error for invalid theme")
	}
	if !strings.Contains(err.Error(), "主题非法") {
		t.Errorf("expected error containing 主题非法, got %v", err)
	}

	// invalid accent: #fff (3 digits)
	err = s.UpdateStatusPageTheme(id, "dark", "#fff")
	if err == nil {
		t.Fatal("expected error for #fff")
	}
	if !strings.Contains(err.Error(), "主色非法") {
		t.Errorf("expected error containing 主色非法, got %v", err)
	}

	// invalid accent: red (no #)
	err = s.UpdateStatusPageTheme(id, "dark", "red")
	if err == nil {
		t.Fatal("expected error for red")
	}
	if !strings.Contains(err.Error(), "主色非法") {
		t.Errorf("expected error containing 主色非法, got %v", err)
	}

	// invalid accent: #gggggg
	err = s.UpdateStatusPageTheme(id, "dark", "#gggggg")
	if err == nil {
		t.Fatal("expected error for #gggggg")
	}
	if !strings.Contains(err.Error(), "主色非法") {
		t.Errorf("expected error containing 主色非法, got %v", err)
	}

	// non-existent id + valid params -> sql.ErrNoRows
	err = s.UpdateStatusPageTheme(999999, "dark", "#ffffff")
	if !errors.Is(err, sql.ErrNoRows) {
		t.Errorf("expected sql.ErrNoRows for non-existent id, got %v", err)
	}

	// validation order: theme checked before accent
	err = s.UpdateStatusPageTheme(id, "blue", "#fff")
	if err == nil {
		t.Fatal("expected error for invalid theme + invalid accent")
	}
	if !strings.Contains(err.Error(), "主题非法") {
		t.Errorf("expected theme error first, got %v", err)
	}
}

func TestWsen_IncidentTimeline(t *testing.T) {
	s := newTestStore(t)
	tenantID := int64(1)
	mon := Monitor{
		Name:           "wsen-timeline-mon",
		Kind:           "http",
		Target:         "http://timeline.example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       tenantID,
		IsPublic:       0,
	}
	monID, err := s.CreateMonitor(mon)
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	now := time.Now().UTC()

	// Create 3 closed incidents: now-3h, now-2h, now-1h
	starts := []time.Time{
		now.Add(-3 * time.Hour),
		now.Add(-2 * time.Hour),
		now.Add(-1 * time.Hour),
	}
	for i, st := range starts {
		startedAt := st.Format(time.RFC3339)
		id, created, err := s.OpenIncident(monID, startedAt, fmt.Sprintf("err-%d", i))
		if err != nil {
			t.Fatalf("OpenIncident %d: %v", i, err)
		}
		if !created {
			t.Fatalf("OpenIncident %d: expected created=true", i)
		}
		endedAt := st.Add(5 * time.Minute).Format(time.RFC3339)
		if _, err := s.CloseOpenIncident(monID, endedAt, int64(300)); err != nil {
			t.Fatalf("CloseOpenIncident %d: %v", i, err)
		}
		_ = id
	}

	// Query timeline
	events, err := s.IncidentTimeline(monID, 30, 50)
	if err != nil {
		t.Fatalf("IncidentTimeline: %v", err)
	}
	if len(events) != 3 {
		t.Fatalf("expected 3 events, got %d", len(events))
	}

	// Order: started_at DESC -> now-1h first, now-3h last
	if events[0].StartedAt != starts[2].Format(time.RFC3339) {
		t.Errorf("events[0].StartedAt mismatch: got %s want %s", events[0].StartedAt, starts[2].Format(time.RFC3339))
	}
	if events[1].StartedAt != starts[1].Format(time.RFC3339) {
		t.Errorf("events[1].StartedAt mismatch: got %s want %s", events[1].StartedAt, starts[1].Format(time.RFC3339))
	}
	if events[2].StartedAt != starts[0].Format(time.RFC3339) {
		t.Errorf("events[2].StartedAt mismatch: got %s want %s", events[2].StartedAt, starts[0].Format(time.RFC3339))
	}

	// Closed events: Open=false, EndedAt string, DowntimeSec int64
	for _, ev := range events {
		if ev.Open {
			t.Errorf("expected Open=false for closed event %d", ev.ID)
		}
		if _, ok := ev.EndedAt.(string); !ok {
			t.Errorf("expected EndedAt to be string, got %T", ev.EndedAt)
		}
		if _, ok := ev.DowntimeSec.(int64); !ok {
			t.Errorf("expected DowntimeSec to be int64, got %T", ev.DowntimeSec)
		}
	}

	// Open incident
	openStart := now.Add(-30 * time.Minute)
	openID, created, err := s.OpenIncident(monID, openStart.Format(time.RFC3339), "open-err")
	if err != nil {
		t.Fatalf("OpenIncident open: %v", err)
	}
	if !created {
		t.Fatal("expected created=true for open incident")
	}

	events, err = s.IncidentTimeline(monID, 30, 50)
	if err != nil {
		t.Fatalf("IncidentTimeline with open: %v", err)
	}
	if len(events) != 4 {
		t.Fatalf("expected 4 events, got %d", len(events))
	}

	// Find open event
	var openEv *TimelineEvent
	for i := range events {
		if events[i].ID == openID {
			openEv = &events[i]
			break
		}
	}
	if openEv == nil {
		t.Fatal("open event not found")
	}
	if !openEv.Open {
		t.Error("expected Open=true for open event")
	}
	if openEv.EndedAt != nil {
		t.Errorf("expected EndedAt nil for open event, got %v", openEv.EndedAt)
	}
	if openEv.DowntimeSec != nil {
		t.Errorf("expected DowntimeSec nil for open event, got %v", openEv.DowntimeSec)
	}

	// limit <= 0 -> 50 (we have 4, should return 4 without error)
	events, err = s.IncidentTimeline(monID, 30, 0)
	if err != nil {
		t.Fatalf("IncidentTimeline limit=0: %v", err)
	}
	if len(events) != 4 {
		t.Errorf("expected 4 events with limit=0, got %d", len(events))
	}

	// limit > 200 -> clamped to 200 (function returns normally)
	_, err = s.IncidentTimeline(monID, 30, 500)
	if err != nil {
		t.Fatalf("IncidentTimeline limit=500: %v", err)
	}

	// days filter: create an incident 40 days ago.
	// 先关闭之前打开的未关闭事件，否则 OpenIncident 幂等返回 created=false
	if _, err := s.CloseOpenIncident(monID, now.Format(time.RFC3339), 1800); err != nil {
		t.Fatalf("CloseOpenIncident before old: %v", err)
	}
	oldStart := now.AddDate(0, 0, -40)
	oldID, created, err := s.OpenIncident(monID, oldStart.Format(time.RFC3339), "old-err")
	if err != nil {
		t.Fatalf("OpenIncident old: %v", err)
	}
	if !created {
		t.Fatal("expected created=true for old incident")
	}
	if _, err := s.CloseOpenIncident(monID, oldStart.Add(time.Minute).Format(time.RFC3339), 60); err != nil {
		t.Fatalf("CloseOpenIncident old: %v", err)
	}

	events, err = s.IncidentTimeline(monID, 30, 50)
	if err != nil {
		t.Fatalf("IncidentTimeline days=30: %v", err)
	}
	for _, ev := range events {
		if ev.ID == oldID {
			t.Error("old incident should be filtered out by days=30")
		}
	}

	// days <= 0 -> 30 (same filter)
	events, err = s.IncidentTimeline(monID, 0, 50)
	if err != nil {
		t.Fatalf("IncidentTimeline days=0: %v", err)
	}
	for _, ev := range events {
		if ev.ID == oldID {
			t.Error("old incident should be filtered out by days=0 (defaults to 30)")
		}
	}
}

func TestWsen_OpenIncidentIdempotent(t *testing.T) {
	s := newTestStore(t)
	tenantID := int64(1)

	monA := Monitor{
		Name:           "wsen-idem-a",
		Kind:           "http",
		Target:         "http://idem-a.example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       tenantID,
		IsPublic:       0,
	}
	monB := Monitor{
		Name:           "wsen-idem-b",
		Kind:           "http",
		Target:         "http://idem-b.example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       tenantID,
		IsPublic:       0,
	}

	idA, err := s.CreateMonitor(monA)
	if err != nil {
		t.Fatalf("CreateMonitor A: %v", err)
	}
	idB, err := s.CreateMonitor(monB)
	if err != nil {
		t.Fatalf("CreateMonitor B: %v", err)
	}

	now := time.Now().UTC()

	// First open for A
	id1, created, err := s.OpenIncident(idA, now.Add(-10*time.Minute).Format(time.RFC3339), "first")
	if err != nil {
		t.Fatalf("OpenIncident first: %v", err)
	}
	if !created {
		t.Fatal("expected created=true on first open")
	}
	if id1 <= 0 {
		t.Fatalf("expected positive id, got %d", id1)
	}

	// Second open for A while still open -> same id, created=false
	id2, created, err := s.OpenIncident(idA, now.Add(-5*time.Minute).Format(time.RFC3339), "second")
	if err != nil {
		t.Fatalf("OpenIncident second: %v", err)
	}
	if created {
		t.Error("expected created=false on second open while open")
	}
	if id2 != id1 {
		t.Errorf("expected same id %d, got %d", id1, id2)
	}

	// Verify only one open incident for A
	events, err := s.IncidentTimeline(idA, 30, 50)
	if err != nil {
		t.Fatalf("IncidentTimeline A: %v", err)
	}
	openCount := 0
	for _, ev := range events {
		if ev.Open {
			openCount++
		}
	}
	if openCount != 1 {
		t.Errorf("expected 1 open incident for A, got %d", openCount)
	}

	// Close A, then open again -> new id
	if _, err := s.CloseOpenIncident(idA, now.Format(time.RFC3339), 600); err != nil {
		t.Fatalf("CloseOpenIncident A: %v", err)
	}
	id3, created, err := s.OpenIncident(idA, now.Add(-1*time.Minute).Format(time.RFC3339), "third")
	if err != nil {
		t.Fatalf("OpenIncident third: %v", err)
	}
	if !created {
		t.Error("expected created=true after close")
	}
	if id3 == id1 {
		t.Errorf("expected new id, got same %d", id3)
	}

	// Different monitor B should be independent
	idB1, created, err := s.OpenIncident(idB, now.Add(-10*time.Minute).Format(time.RFC3339), "b-first")
	if err != nil {
		t.Fatalf("OpenIncident B: %v", err)
	}
	if !created {
		t.Error("expected created=true for monitor B")
	}
	if idB1 <= 0 {
		t.Fatalf("expected positive id for B, got %d", idB1)
	}
}

func TestWsen_EscalationDueLevels(t *testing.T) {
	now := time.Now().UTC()

	// Case 1: 10m elapsed, policy 5m and 30m, sent nil -> only 5m
	policy := []escalation.Level{
		{AfterMinutes: 5, Channels: []string{"wecom"}},
		{AfterMinutes: 30, Channels: []string{"sms"}},
	}
	openedAt := now.Add(-10 * time.Minute)
	got := escalation.DueLevels(openedAt, now, nil, policy)
	if len(got) != 1 {
		t.Fatalf("case1: expected 1 level, got %d", len(got))
	}
	if got[0].AfterMinutes != 5 {
		t.Errorf("case1: expected AfterMinutes=5, got %d", got[0].AfterMinutes)
	}

	// Case 2: 40m elapsed, sent [5] -> only 30m
	openedAt = now.Add(-40 * time.Minute)
	got = escalation.DueLevels(openedAt, now, []int{5}, policy)
	if len(got) != 1 {
		t.Fatalf("case2: expected 1 level, got %d", len(got))
	}
	if got[0].AfterMinutes != 30 {
		t.Errorf("case2: expected AfterMinutes=30, got %d", got[0].AfterMinutes)
	}

	// Case 3: 40m elapsed, sent [5,30] -> empty
	got = escalation.DueLevels(openedAt, now, []int{5, 30}, policy)
	if len(got) != 0 {
		t.Errorf("case3: expected 0 levels, got %d", len(got))
	}

	// Case 4: 1m elapsed -> empty
	openedAt = now.Add(-1 * time.Minute)
	got = escalation.DueLevels(openedAt, now, nil, policy)
	if len(got) != 0 {
		t.Errorf("case4: expected 0 levels, got %d", len(got))
	}

	// Case 5: policy with AfterMinutes <= 0 -> skipped
	policyWithZero := []escalation.Level{
		{AfterMinutes: 0, Channels: []string{"wecom"}},
		{AfterMinutes: -5, Channels: []string{"sms"}},
		{AfterMinutes: 5, Channels: []string{"email"}},
	}
	openedAt = now.Add(-10 * time.Minute)
	got = escalation.DueLevels(openedAt, now, nil, policyWithZero)
	if len(got) != 1 {
		t.Fatalf("case5: expected 1 level, got %d", len(got))
	}
	if got[0].AfterMinutes != 5 {
		t.Errorf("case5: expected AfterMinutes=5, got %d", got[0].AfterMinutes)
	}

	// Case 6: policy order preserved (30 before 5)
	policyReordered := []escalation.Level{
		{AfterMinutes: 30, Channels: []string{"sms"}},
		{AfterMinutes: 5, Channels: []string{"wecom"}},
	}
	openedAt = now.Add(-40 * time.Minute)
	got = escalation.DueLevels(openedAt, now, nil, policyReordered)
	if len(got) != 2 {
		t.Fatalf("case6: expected 2 levels, got %d", len(got))
	}
	if got[0].AfterMinutes != 30 {
		t.Errorf("case6: expected first AfterMinutes=30, got %d", got[0].AfterMinutes)
	}
	if got[1].AfterMinutes != 5 {
		t.Errorf("case6: expected second AfterMinutes=5, got %d", got[1].AfterMinutes)
	}

	// Case 7: exact threshold with buffer
	openedAt = now.Add(-5 * time.Minute).Add(-1 * time.Second)
	got = escalation.DueLevels(openedAt, now, nil, policy)
	if len(got) != 1 {
		t.Fatalf("case7: expected 1 level, got %d", len(got))
	}
	if got[0].AfterMinutes != 5 {
		t.Errorf("case7: expected AfterMinutes=5, got %d", got[0].AfterMinutes)
	}
}
