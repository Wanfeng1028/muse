package escalation

import (
	"reflect"
	"testing"
	"time"
)

func TestDeep2AfterMinutesZeroSkipped(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 0, Channels: []string{"zero"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if got != nil {
		t.Fatalf("expected nil for AfterMinutes==0, got %v", got)
	}
}

func TestDeep2AfterMinutesNegativeSkipped(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: -5, Channels: []string{"neg"}},
		{AfterMinutes: -1, Channels: []string{"neg2"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if got != nil {
		t.Fatalf("expected nil for negative AfterMinutes, got %v", got)
	}
}

func TestDeep2ElapsedEqualsThresholdHits(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(30 * time.Minute)
	policy := []Level{
		{AfterMinutes: 30, Channels: []string{"a"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	want := []Level{{AfterMinutes: 30, Channels: []string{"a"}}}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected elapsed==threshold to hit, want %v got %v", want, got)
	}
}

func TestDeep2ElapsedJustBelowThresholdSkips(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(29*time.Minute + 59*time.Second)
	policy := []Level{
		{AfterMinutes: 30, Channels: []string{"a"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if got != nil {
		t.Fatalf("expected nil when elapsed<threshold, got %v", got)
	}
}

func TestDeep2PolicyOrderPreserved(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 60, Channels: []string{"b"}},
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 30, Channels: []string{"c"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	want := []Level{
		{AfterMinutes: 60, Channels: []string{"b"}},
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 30, Channels: []string{"c"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected policy order preserved, want %v got %v", want, got)
	}
}

func TestDeep2SentDuplicatesStillSkip(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 15, Channels: []string{"a"}},
		{AfterMinutes: 30, Channels: []string{"b"}},
	}
	sent := []int{15, 15, 15}
	got := DueLevels(openedAt, now, sent, policy)
	want := []Level{{AfterMinutes: 30, Channels: []string{"b"}}}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected duplicate sent minutes to skip, want %v got %v", want, got)
	}
}

func TestDeep2NowBeforeOpenedAtNoHit(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	now := openedAt.Add(-10 * time.Minute)
	policy := []Level{
		{AfterMinutes: 1, Channels: []string{"a"}},
		{AfterMinutes: 5, Channels: []string{"b"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if got != nil {
		t.Fatalf("expected nil when now before openedAt, got %v", got)
	}
}

func TestDeep2EmptyPolicyReturnsNil(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	got := DueLevels(openedAt, now, nil, []Level{})
	if got != nil {
		t.Fatalf("expected nil for empty policy, got %v", got)
	}
}

func TestDeep2NilPolicyReturnsNil(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	got := DueLevels(openedAt, now, nil, nil)
	if got != nil {
		t.Fatalf("expected nil for nil policy, got %v", got)
	}
}

func TestDeep2ChannelsPassedThrough(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	channels := []string{"email", "sms", "push"}
	policy := []Level{
		{AfterMinutes: 10, Channels: channels},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if len(got) != 1 {
		t.Fatalf("expected 1 due level, got %d", len(got))
	}
	if !reflect.DeepEqual(got[0].Channels, channels) {
		t.Fatalf("expected channels passed through, want %v got %v", channels, got[0].Channels)
	}
}

func TestDeep2PartialLevelsReached(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(45 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 30, Channels: []string{"b"}},
		{AfterMinutes: 60, Channels: []string{"c"}},
		{AfterMinutes: 120, Channels: []string{"d"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	want := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 30, Channels: []string{"b"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected only reached levels, want %v got %v", want, got)
	}
}

func TestDeep2NilAndEmptySentEquivalent(t *testing.T) {
	openedAt := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 30, Channels: []string{"b"}},
	}
	gotNil := DueLevels(openedAt, now, nil, policy)
	gotEmpty := DueLevels(openedAt, now, []int{}, policy)
	if !reflect.DeepEqual(gotNil, gotEmpty) {
		t.Fatalf("expected nil and empty sent equivalent, nil=%v empty=%v", gotNil, gotEmpty)
	}
	want := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 30, Channels: []string{"b"}},
	}
	if !reflect.DeepEqual(gotNil, want) {
		t.Fatalf("expected both to return all due levels, want %v got %v", want, gotNil)
	}
}