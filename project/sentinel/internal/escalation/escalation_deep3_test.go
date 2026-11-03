package escalation

import (
	"reflect"
	"testing"
	"time"
)

func TestDeep3SentMinutesNotInPolicyIgnored(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(200 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 20, Channels: []string{"b"}},
	}
	sent := []int{999, 12345, 7}
	got := DueLevels(openedAt, now, sent, policy)
	want := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 20, Channels: []string{"b"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected sent minutes absent from policy to be ignored, want %v got %v", want, got)
	}
}

func TestDeep3AllLevelsSentReturnsNil(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(500 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 30, Channels: []string{"b"}},
		{AfterMinutes: 60, Channels: []string{"c"}},
	}
	sent := []int{10, 30, 60}
	got := DueLevels(openedAt, now, sent, policy)
	if got != nil {
		t.Fatalf("expected nil when every level already sent, got %v", got)
	}
}

func TestDeep3DuplicateAfterMinutesBothReturned(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 10, Channels: []string{"b"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	want := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 10, Channels: []string{"b"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected both same-minute levels returned when unsent, want %v got %v", want, got)
	}
}

func TestDeep3DuplicateAfterMinutesBothSkippedWhenSent(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 10, Channels: []string{"b"}},
		{AfterMinutes: 20, Channels: []string{"c"}},
	}
	sent := []int{10}
	got := DueLevels(openedAt, now, sent, policy)
	want := []Level{
		{AfterMinutes: 20, Channels: []string{"c"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected single sent entry to skip both duplicates, want %v got %v", want, got)
	}
}

func TestDeep3ZeroSentMinutesWithZeroPolicyNoInteraction(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 0, Channels: []string{"zero"}},
	}
	sent := []int{0}
	got := DueLevels(openedAt, now, sent, policy)
	if got != nil {
		t.Fatalf("expected nil with zero-threshold policy regardless of sent, got %v", got)
	}
}

func TestDeep3NegativeSentMinutesNoEffect(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
	}
	sent := []int{-1, -100}
	got := DueLevels(openedAt, now, sent, policy)
	want := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected negative sent minutes not to affect positive thresholds, want %v got %v", want, got)
	}
}

func TestDeep3HugeAfterMinutesNotReached(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 1000000, Channels: []string{"far"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if got != nil {
		t.Fatalf("expected nil when threshold far beyond elapsed, got %v", got)
	}
}

func TestDeep3LargeSentSlicePerformance(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(1000 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 20, Channels: []string{"b"}},
		{AfterMinutes: 30, Channels: []string{"c"}},
	}
	sent := make([]int, 0, 5000)
	for i := 0; i < 5000; i++ {
		sent = append(sent, i)
	}
	got := DueLevels(openedAt, now, sent, policy)
	if got != nil {
		t.Fatalf("expected nil when all thresholds among large sent set, got %v", got)
	}
}

func TestDeep3LongPolicyAllDue(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(10000 * time.Minute)
	policy := make([]Level, 0, 200)
	for i := 1; i <= 200; i++ {
		policy = append(policy, Level{AfterMinutes: i, Channels: []string{"ch"}})
	}
	got := DueLevels(openedAt, now, nil, policy)
	if len(got) != 200 {
		t.Fatalf("expected 200 due levels, got %d", len(got))
	}
	for i, lv := range got {
		if lv.AfterMinutes != i+1 {
			t.Fatalf("order broken at index %d: got %d", i, lv.AfterMinutes)
		}
	}
}

func TestDeep3LongPolicyPartialReached(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(50 * time.Minute)
	policy := make([]Level, 0, 100)
	for i := 1; i <= 100; i++ {
		policy = append(policy, Level{AfterMinutes: i, Channels: []string{"ch"}})
	}
	got := DueLevels(openedAt, now, nil, policy)
	if len(got) != 50 {
		t.Fatalf("expected 50 due levels, got %d", len(got))
	}
	if got[len(got)-1].AfterMinutes != 50 {
		t.Fatalf("expected last due level minute 50, got %d", got[len(got)-1].AfterMinutes)
	}
}

func TestDeep3LongPolicyPartialSent(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := make([]Level, 0, 100)
	for i := 1; i <= 100; i++ {
		policy = append(policy, Level{AfterMinutes: i, Channels: []string{"ch"}})
	}
	sent := make([]int, 0, 50)
	for i := 1; i <= 50; i++ {
		sent = append(sent, i)
	}
	got := DueLevels(openedAt, now, sent, policy)
	if len(got) != 50 {
		t.Fatalf("expected 50 remaining due levels, got %d", len(got))
	}
	if got[0].AfterMinutes != 51 {
		t.Fatalf("expected first remaining minute 51, got %d", got[0].AfterMinutes)
	}
	if got[len(got)-1].AfterMinutes != 100 {
		t.Fatalf("expected last remaining minute 100, got %d", got[len(got)-1].AfterMinutes)
	}
}

func TestDeep3EmptyChannelsSlicePreserved(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if len(got) != 1 {
		t.Fatalf("expected 1 due level, got %d", len(got))
	}
	if got[0].Channels == nil {
		t.Fatalf("expected non-nil empty channels preserved, got nil")
	}
	if len(got[0].Channels) != 0 {
		t.Fatalf("expected empty channels preserved, got %v", got[0].Channels)
	}
}

func TestDeep3NilChannelsPreserved(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: nil},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if len(got) != 1 {
		t.Fatalf("expected 1 due level, got %d", len(got))
	}
	if got[0].Channels != nil {
		t.Fatalf("expected nil channels preserved, got %v", got[0].Channels)
	}
}

func TestDeep3NowEqualsOpenedAtZeroElapsed(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 12, 0, 0, 0, time.UTC)
	now := openedAt
	policy := []Level{
		{AfterMinutes: 1, Channels: []string{"a"}},
		{AfterMinutes: 0, Channels: []string{"b"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if got != nil {
		t.Fatalf("expected nil when elapsed is zero, got %v", got)
	}
}

func TestDeep3ElapsedExactOneMinuteHitsOne(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(time.Minute)
	policy := []Level{
		{AfterMinutes: 1, Channels: []string{"a"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	want := []Level{{AfterMinutes: 1, Channels: []string{"a"}}}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected exact one minute to hit, want %v got %v", want, got)
	}
}

func TestDeep3ElapsedSubSecondBelowOneMinute(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(time.Minute - time.Nanosecond)
	policy := []Level{
		{AfterMinutes: 1, Channels: []string{"a"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if got != nil {
		t.Fatalf("expected nil one nanosecond below threshold, got %v", got)
	}
}

func TestDeep3OutputSliceIndependentOfPolicy(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 20, Channels: []string{"b"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	if len(got) != 2 {
		t.Fatalf("expected 2 due levels, got %d", len(got))
	}
	got[0].AfterMinutes = 999
	got[0].Channels = []string{"mutated"}
	if policy[0].AfterMinutes != 10 {
		t.Fatalf("mutating output changed policy AfterMinutes: %d", policy[0].AfterMinutes)
	}
	if !reflect.DeepEqual(policy[0].Channels, []string{"a"}) {
		t.Fatalf("mutating output channels changed policy: %v", policy[0].Channels)
	}
}

func TestDeep3MixedZeroNegativePositiveOrder(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 0, Channels: []string{"zero"}},
		{AfterMinutes: -1, Channels: []string{"neg"}},
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 5, Channels: []string{"b"}},
		{AfterMinutes: 0, Channels: []string{"zero2"}},
		{AfterMinutes: 30, Channels: []string{"c"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	want := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 5, Channels: []string{"b"}},
		{AfterMinutes: 30, Channels: []string{"c"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected only positive thresholds in original order, want %v got %v", want, got)
	}
}

func TestDeep3SentPartialWithMixedThresholds(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(100 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 20, Channels: []string{"b"}},
		{AfterMinutes: 30, Channels: []string{"c"}},
		{AfterMinutes: 40, Channels: []string{"d"}},
	}
	sent := []int{10, 30, 999, 0, -5}
	got := DueLevels(openedAt, now, sent, policy)
	want := []Level{
		{AfterMinutes: 20, Channels: []string{"b"}},
		{AfterMinutes: 40, Channels: []string{"d"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected only unsent thresholds returned, want %v got %v", want, got)
	}
}

func TestDeep3SentAllWithExtrasReturnsNil(t *testing.T) {
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	now := openedAt.Add(1000 * time.Minute)
	policy := []Level{
		{AfterMinutes: 10, Channels: []string{"a"}},
		{AfterMinutes: 20, Channels: []string{"b"}},
	}
	sent := []int{10, 20, 30, 40, 50}
	got := DueLevels(openedAt, now, sent, policy)
	if got != nil {
		t.Fatalf("expected nil when all policy thresholds sent, got %v", got)
	}
}

func TestDeep3NonUTCClockStillWorks(t *testing.T) {
	loc := time.FixedZone("X", 3600*5)
	openedAt := time.Date(2024, 5, 1, 0, 0, 0, 0, loc)
	now := openedAt.Add(45 * time.Minute)
	policy := []Level{
		{AfterMinutes: 30, Channels: []string{"a"}},
		{AfterMinutes: 60, Channels: []string{"b"}},
	}
	got := DueLevels(openedAt, now, nil, policy)
	want := []Level{
		{AfterMinutes: 30, Channels: []string{"a"}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected only 30-minute level due, want %v got %v", want, got)
	}
}
