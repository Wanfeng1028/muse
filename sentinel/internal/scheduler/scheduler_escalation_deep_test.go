package scheduler

import (
	"fmt"
	"sync"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/escalation"
	"sentinel/internal/store"
)

type escNotifyCall struct {
	Monitor store.Monitor
	Event   string
	Name    string
	Target  string
	At      string
	ErrMsg  string
}

type escNotifyRecorder struct {
	mu    sync.Mutex
	calls []escNotifyCall
}

func (r *escNotifyRecorder) notify(m store.Monitor, event, name, target, at, errMsg string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.calls = append(r.calls, escNotifyCall{
		Monitor: m,
		Event:   event,
		Name:    name,
		Target:  target,
		At:      at,
		ErrMsg:  errMsg,
	})
}

func (r *escNotifyRecorder) count() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.calls)
}

func (r *escNotifyRecorder) snapshot() []escNotifyCall {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]escNotifyCall, len(r.calls))
	copy(out, r.calls)
	return out
}

func newEscTestStore(t *testing.T) *store.Store {
	t.Helper()
	path := fmt.Sprintf("%s/sentinel_esc_%d.db", t.TempDir(), time.Now().UnixNano())
	database, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open 失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	st := store.New(database)
	if err := st.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant 失败: %v", err)
	}
	return st
}

func newEscScheduler(t *testing.T, st *store.Store, rec *escNotifyRecorder) *Scheduler {
	t.Helper()
	return New(st, rec.notify, 1, 60, 0)
}

func escCreateMonitor(t *testing.T, st *store.Store, name, target string) int64 {
	t.Helper()
	id, err := st.CreateMonitor(store.Monitor{
		Name:           name,
		Kind:           "http",
		Target:         target,
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor 失败: %v", err)
	}
	return id
}

func escOpenIncident(t *testing.T, st *store.Store, monitorID int64, ago time.Duration, startError string) int64 {
	t.Helper()
	startedAt := time.Now().Add(-ago).UTC().Format(time.RFC3339)
	id, _, err := st.OpenIncident(monitorID, startedAt, startError)
	if err != nil {
		t.Fatalf("OpenIncident 失败: %v", err)
	}
	return id
}

func escContainsInt(xs []int, want int) bool {
	for _, x := range xs {
		if x == want {
			return true
		}
	}
	return false
}

func TestEsc_NoPolicyNoNotify(t *testing.T) {
	st := newEscTestStore(t)
	rec := &escNotifyRecorder{}
	s := newEscScheduler(t, st, rec)

	mid := escCreateMonitor(t, st, "esc-no-policy", "http://example.com/a")
	escOpenIncident(t, st, mid, 10*time.Minute, "boom")

	s.checkEscalations()

	if got := rec.count(); got != 0 {
		t.Fatalf("未设置策略时不应触发通知，实际次数=%d", got)
	}
}

func TestEsc_DueLevelFires(t *testing.T) {
	st := newEscTestStore(t)
	rec := &escNotifyRecorder{}
	s := newEscScheduler(t, st, rec)

	const target = "http://example.com/due"
	mid := escCreateMonitor(t, st, "esc-due", target)
	iid := escOpenIncident(t, st, mid, 10*time.Minute, "conn refused")

	s.SetEscalation([]escalation.Level{
		{AfterMinutes: 5, Channels: []string{"sms", "email"}},
	})

	s.checkEscalations()

	if got := rec.count(); got != 1 {
		t.Fatalf("应恰好触发 1 次通知，实际=%d", got)
	}
	call := rec.snapshot()[0]
	if call.Event != "escalated" {
		t.Errorf("event 期望 escalated，实际=%q", call.Event)
	}
	if call.Target != target {
		t.Errorf("target 期望 %q，实际=%q", target, call.Target)
	}
	if !escContainsSub(call.ErrMsg, "5 分钟") {
		t.Errorf("errMsg 应包含 %q，实际=%q", "5 分钟", call.ErrMsg)
	}
	if !escContainsSub(call.ErrMsg, "conn refused") {
		t.Errorf("errMsg 应包含 %q，实际=%q", "conn refused", call.ErrMsg)
	}

	sent, err := st.SentEscalationLevels(iid)
	if err != nil {
		t.Fatalf("SentEscalationLevels 失败: %v", err)
	}
	if !escContainsInt(sent, 5) {
		t.Fatalf("SentEscalationLevels 应包含 5，实际=%v", sent)
	}
}

func TestEsc_Idempotent(t *testing.T) {
	st := newEscTestStore(t)
	rec := &escNotifyRecorder{}
	s := newEscScheduler(t, st, rec)

	mid := escCreateMonitor(t, st, "esc-idem", "http://example.com/idem")
	escOpenIncident(t, st, mid, 10*time.Minute, "conn refused")

	s.SetEscalation([]escalation.Level{
		{AfterMinutes: 5, Channels: []string{"sms", "email"}},
	})

	s.checkEscalations()
	if got := rec.count(); got != 1 {
		t.Fatalf("首次 checkEscalations 应触发 1 次，实际=%d", got)
	}

	s.checkEscalations()
	if got := rec.count(); got != 1 {
		t.Fatalf("重复 checkEscalations 应保持幂等，实际=%d", got)
	}
}

func TestEsc_NotDueNoNotify(t *testing.T) {
	st := newEscTestStore(t)
	rec := &escNotifyRecorder{}
	s := newEscScheduler(t, st, rec)

	mid := escCreateMonitor(t, st, "esc-notdue", "http://example.com/notdue")
	iid := escOpenIncident(t, st, mid, 10*time.Minute, "slow")

	s.SetEscalation([]escalation.Level{
		{AfterMinutes: 60, Channels: []string{"sms"}},
	})

	s.checkEscalations()

	if got := rec.count(); got != 0 {
		t.Fatalf("未达阈值不应通知，实际=%d", got)
	}
	sent, err := st.SentEscalationLevels(iid)
	if err != nil {
		t.Fatalf("SentEscalationLevels 失败: %v", err)
	}
	if len(sent) != 0 {
		t.Fatalf("未达阈值时升级记录应为空，实际=%v", sent)
	}
}

func TestEsc_MultipleLevels(t *testing.T) {
	st := newEscTestStore(t)
	rec := &escNotifyRecorder{}
	s := newEscScheduler(t, st, rec)

	mid := escCreateMonitor(t, st, "esc-multi", "http://example.com/multi")
	iid := escOpenIncident(t, st, mid, 10*time.Minute, "down")

	s.SetEscalation([]escalation.Level{
		{AfterMinutes: 5, Channels: []string{"sms"}},
		{AfterMinutes: 8, Channels: []string{"email"}},
	})

	s.checkEscalations()

	if got := rec.count(); got != 2 {
		t.Fatalf("两个级别各触发一次应为 2，实际=%d", got)
	}
	sent, err := st.SentEscalationLevels(iid)
	if err != nil {
		t.Fatalf("SentEscalationLevels 失败: %v", err)
	}
	if !escContainsInt(sent, 5) {
		t.Errorf("SentEscalationLevels 应包含 5，实际=%v", sent)
	}
	if !escContainsInt(sent, 8) {
		t.Errorf("SentEscalationLevels 应包含 8，实际=%v", sent)
	}
}

func TestEsc_ClosedIncidentIgnored(t *testing.T) {
	st := newEscTestStore(t)
	rec := &escNotifyRecorder{}
	s := newEscScheduler(t, st, rec)

	mid := escCreateMonitor(t, st, "esc-closed", "http://example.com/closed")
	escOpenIncident(t, st, mid, 10*time.Minute, "brief")

	endedAt := time.Now().UTC().Format(time.RFC3339)
	if err := st.CloseOpenIncident(mid, endedAt, 600); err != nil {
		t.Fatalf("CloseOpenIncident 失败: %v", err)
	}

	s.SetEscalation([]escalation.Level{
		{AfterMinutes: 5, Channels: []string{"sms"}},
	})

	s.checkEscalations()

	if got := rec.count(); got != 0 {
		t.Fatalf("已关闭 incident 不应触发升级，实际=%d", got)
	}
}

func TestEsc_EmptyPolicyDisables(t *testing.T) {
	st := newEscTestStore(t)
	rec := &escNotifyRecorder{}
	s := newEscScheduler(t, st, rec)

	mid := escCreateMonitor(t, st, "esc-empty", "http://example.com/empty")
	escOpenIncident(t, st, mid, 10*time.Minute, "x")

	s.SetEscalation([]escalation.Level{
		{AfterMinutes: 5, Channels: []string{"sms"}},
	})
	s.SetEscalation(nil)

	s.checkEscalations()

	if got := rec.count(); got != 0 {
		t.Fatalf("空策略应禁用升级，实际=%d", got)
	}
}

func escContainsSub(haystack, needle string) bool {
	if needle == "" {
		return true
	}
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
