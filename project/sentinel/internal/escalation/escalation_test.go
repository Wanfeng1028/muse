package escalation

import (
"testing"
"time"
)

func TestDueLevelsNotReached(t *testing.T) {
opened := time.Now()
now := opened.Add(5 * time.Minute)
policy := []Level{{AfterMinutes: 15, Channels: []string{"wecom"}}}
got := DueLevels(opened, now, nil, policy)
if len(got) != 0 {
t.Fatalf("expected 0 levels, got %d", len(got))
}
}

func TestDueLevelsFirstReached(t *testing.T) {
opened := time.Now()
now := opened.Add(20 * time.Minute)
policy := []Level{{AfterMinutes: 15, Channels: []string{"wecom"}}}
got := DueLevels(opened, now, nil, policy)
if len(got) != 1 {
t.Fatalf("expected 1 level, got %d", len(got))
}
if got[0].AfterMinutes != 15 {
t.Fatalf("expected 15, got %d", got[0].AfterMinutes)
}
}

func TestDueLevelsSkipsSent(t *testing.T) {
opened := time.Now()
now := opened.Add(20 * time.Minute)
policy := []Level{{AfterMinutes: 15, Channels: []string{"wecom"}}}
got := DueLevels(opened, now, []int{15}, policy)
if len(got) != 0 {
t.Fatalf("expected 0 levels, got %d", len(got))
}
}

func TestDueLevelsTwoLevels(t *testing.T) {
opened := time.Now()
now := opened.Add(40 * time.Minute)
policy := []Level{
{AfterMinutes: 15, Channels: []string{"wecom"}},
{AfterMinutes: 30, Channels: []string{"wecom", "smtp"}},
}
got := DueLevels(opened, now, nil, policy)
if len(got) != 2 {
t.Fatalf("expected 2 levels, got %d", len(got))
}
if got[0].AfterMinutes != 15 || got[1].AfterMinutes != 30 {
t.Fatalf("order wrong: %+v", got)
}
}
