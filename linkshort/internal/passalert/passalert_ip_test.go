package passalert

import (
	"testing"
	"time"
)

func TestRecordIPFail_TriggersAtThreshold(t *testing.T) {
	now := time.Now()
	tracker := NewTrackerWithIPThreshold(3, time.Minute, 3)

	if tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("first IP failure should not trigger")
	}
	if tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("second IP failure should not trigger")
	}
	if !tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("third IP failure should trigger")
	}
}

func TestRecordIPFail_BelowThreshold(t *testing.T) {
	now := time.Now()
	tracker := NewTrackerWithIPThreshold(3, time.Minute, 3)

	if tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("first IP failure should not trigger")
	}
	if tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("second IP failure should not trigger")
	}
	if got := tracker.IPFailCount("1.2.3.4", now); got != 2 {
		t.Fatalf("IPFailCount() = %d, want 2", got)
	}
}

func TestRecordIPFail_NoRepeatWhileAbove(t *testing.T) {
	now := time.Now()
	tracker := NewTrackerWithIPThreshold(3, time.Minute, 3)

	tracker.RecordIPFail("1.2.3.4", now)
	tracker.RecordIPFail("1.2.3.4", now)
	if !tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("third IP failure should trigger")
	}
	if tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("fourth IP failure should not trigger again")
	}
}

func TestRecordIPFail_RearmAfterWindow(t *testing.T) {
	now := time.Now()
	tracker := NewTrackerWithIPThreshold(10, time.Minute, 2)

	// 第 1 次：计数 1 < 2，布防，不触发。
	if tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("first IP failure should not trigger below threshold")
	}
	// 第 2 次：计数 2 >= 2，从阈值下方跨越，触发。
	if !tracker.RecordIPFail("1.2.3.4", now.Add(time.Second)) {
		t.Fatal("second IP failure should trigger at threshold")
	}
	// 窗口滑出旧事件后：新事件计数 1 < 2，重布防但不触发。
	if tracker.RecordIPFail("1.2.3.4", now.Add(2*time.Minute)) {
		t.Fatal("failure after window slide should re-arm without triggering")
	}
	// 再来一次：计数 2 >= 2，再次跨越触发。
	if !tracker.RecordIPFail("1.2.3.4", now.Add(2*time.Minute).Add(time.Second)) {
		t.Fatal("failure after re-arm should trigger again")
	}
}

func TestRecordIPFail_EmptyIP(t *testing.T) {
	now := time.Now()
	tracker := NewTrackerWithIPThreshold(3, time.Minute, 3)

	if tracker.RecordIPFail("", now) {
		t.Fatal("empty IP should not trigger")
	}
	if got := tracker.IPFailCount("", now); got != 0 {
		t.Fatalf("IPFailCount() = %d, want 0", got)
	}
}

func TestRecordIPFail_IndependentFromSlug(t *testing.T) {
	now := time.Now()
	tracker := NewTrackerWithIPThreshold(3, time.Minute, 3)

	tracker.RecordFail("s", now)
	tracker.RecordFail("s", now)
	if !tracker.RecordFail("s", now) {
		t.Fatal("third slug failure should trigger")
	}

	if tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("first IP failure should not trigger")
	}
	if tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("second IP failure should not trigger")
	}
	if !tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("third IP failure should trigger")
	}
}

func TestIPFailCount_WindowExpiry(t *testing.T) {
	now := time.Now()
	tracker := NewTrackerWithIPThreshold(3, time.Minute, 3)

	tracker.RecordIPFail("1.2.3.4", now)
	if got := tracker.IPFailCount("1.2.3.4", now.Add(2*time.Minute)); got != 0 {
		t.Fatalf("IPFailCount() after window expiry = %d, want 0", got)
	}
}

func TestNewTrackerWithIPThreshold_DefaultFallback(t *testing.T) {
	now := time.Now()
	tracker := NewTrackerWithIPThreshold(3, time.Minute, 0)

	for i := 1; i < 20; i++ {
		if tracker.RecordIPFail("1.2.3.4", now) {
			t.Fatalf("IP failure %d should not trigger", i)
		}
	}
	if !tracker.RecordIPFail("1.2.3.4", now) {
		t.Fatal("20th IP failure should trigger with the default threshold")
	}
}
