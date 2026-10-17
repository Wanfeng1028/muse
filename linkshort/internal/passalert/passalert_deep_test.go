package passalert

import (
	"sync"
	"testing"
	"time"
)

func TestRecordFailTriggersOnceAtThreshold(t *testing.T) {
	tr := NewTracker(3, time.Minute)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	if got := tr.RecordFail("slug-a", base); got != false {
		t.Fatalf("first fail should not trigger, got %v", got)
	}
	if got := tr.RecordFail("slug-a", base.Add(1*time.Second)); got != false {
		t.Fatalf("second fail should not trigger, got %v", got)
	}
	if got := tr.RecordFail("slug-a", base.Add(2*time.Second)); got != true {
		t.Fatalf("third fail should trigger, got %v", got)
	}
	if got := tr.RecordFail("slug-a", base.Add(3*time.Second)); got != false {
		t.Fatalf("fourth fail should not re-trigger, got %v", got)
	}
	if got := tr.FailCount("slug-a", base.Add(3*time.Second)); got != 4 {
		t.Fatalf("FailCount = %d, want 4", got)
	}
}

func TestRecordFailRearmsAfterCountFallsBelow(t *testing.T) {
	tr := NewTracker(2, 30*time.Second)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	tr.RecordFail("s", base)
	if got := tr.RecordFail("s", base.Add(1*time.Second)); got != true {
		t.Fatalf("threshold crossing should trigger, got %v", got)
	}
	if got := tr.RecordFail("s", base.Add(2*time.Second)); got != false {
		t.Fatalf("still above threshold should not trigger, got %v", got)
	}
	later := base.Add(2 * time.Minute)
	if got := tr.RecordFail("s", later); got != false {
		t.Fatalf("after window expiry count drops below, should not trigger, got %v", got)
	}
	if got := tr.FailCount("s", later); got != 1 {
		t.Fatalf("FailCount after expiry = %d, want 1", got)
	}
	if got := tr.RecordFail("s", later.Add(1*time.Second)); got != true {
		t.Fatalf("re-armed crossing should trigger, got %v", got)
	}
}

func TestRecordFailBoundaryAtExactWindowEdge(t *testing.T) {
	tr := NewTracker(2, 10*time.Second)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	tr.RecordFail("edge", base)
	exactEdge := base.Add(10 * time.Second)
	// 注：产品窗口为左开区间 (cutoff, now]，恰在 cutoff 上的事件被丢弃，不触发
	if got := tr.RecordFail("edge", exactEdge); got != false {
		t.Fatalf("event exactly at cutoff boundary should be dropped, got %v", got)
	}
	if got := tr.FailCount("edge", exactEdge); got != 1 {
		t.Fatalf("FailCount at exact edge = %d, want 1", got)
	}
	justInside := base.Add(10*time.Second - time.Nanosecond)
	tr.Reset()
	tr.RecordFail("edge", base)
	if got := tr.RecordFail("edge", justInside); got != true {
		t.Fatalf("event one nanosecond inside window should be kept, got %v", got)
	}
	if got := tr.FailCount("edge", justInside); got != 2 {
		t.Fatalf("FailCount inside window = %d, want 2", got)
	}
}

func TestRecordFailEmptySlugIgnored(t *testing.T) {
	tr := NewTracker(1, time.Minute)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	if got := tr.RecordFail("", base); got != false {
		t.Fatalf("empty slug should not trigger, got %v", got)
	}
	if got := tr.FailCount("", base); got != 0 {
		t.Fatalf("FailCount for empty slug = %d, want 0", got)
	}
	if got := tr.RecordFail("", base.Add(time.Second)); got != false {
		t.Fatalf("empty slug repeated should not trigger, got %v", got)
	}
}

func TestFailCountDoesNotRecordAndIsolatesSlugs(t *testing.T) {
	tr := NewTracker(5, time.Minute)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	tr.RecordFail("a", base)
	tr.RecordFail("a", base.Add(1*time.Second))
	tr.RecordFail("b", base.Add(1*time.Second))

	if got := tr.FailCount("a", base.Add(2*time.Second)); got != 2 {
		t.Fatalf("FailCount a = %d, want 2", got)
	}
	if got := tr.FailCount("b", base.Add(2*time.Second)); got != 1 {
		t.Fatalf("FailCount b = %d, want 1", got)
	}
	if got := tr.FailCount("a", base.Add(2*time.Second)); got != 2 {
		t.Fatalf("FailCount a after read = %d, want 2", got)
	}
	if got := tr.FailCount("missing", base.Add(2*time.Second)); got != 0 {
		t.Fatalf("FailCount missing = %d, want 0", got)
	}
}

func TestResetClearsEventsAndArmedState(t *testing.T) {
	tr := NewTracker(2, time.Minute)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	tr.RecordFail("r", base)
	if got := tr.RecordFail("r", base.Add(1*time.Second)); got != true {
		t.Fatalf("crossing should trigger, got %v", got)
	}
	tr.Reset()
	if got := tr.FailCount("r", base.Add(2*time.Second)); got != 0 {
		t.Fatalf("FailCount after reset = %d, want 0", got)
	}
	if got := tr.RecordFail("r", base.Add(3*time.Second)); got != false {
		t.Fatalf("first fail after reset should not trigger, got %v", got)
	}
	if got := tr.RecordFail("r", base.Add(4*time.Second)); got != true {
		t.Fatalf("second fail after reset should trigger, got %v", got)
	}
}

func TestNewTrackerDefaults(t *testing.T) {
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	zero := NewTracker(0, 0)
	if zero.threshold != 10 {
		t.Fatalf("default threshold = %d, want 10", zero.threshold)
	}
	if zero.window != 5*time.Minute {
		t.Fatalf("default window = %v, want 5m", zero.window)
	}
	if got := zero.FailCount("x", base); got != 0 {
		t.Fatalf("new tracker FailCount = %d, want 0", got)
	}

	neg := NewTracker(-3, -1*time.Second)
	if neg.threshold != 10 {
		t.Fatalf("negative threshold fallback = %d, want 10", neg.threshold)
	}
	if neg.window != 5*time.Minute {
		t.Fatalf("negative window fallback = %v, want 5m", neg.window)
	}

	custom := NewTracker(4, 2*time.Second)
	if custom.threshold != 4 {
		t.Fatalf("custom threshold = %d, want 4", custom.threshold)
	}
	if custom.window != 2*time.Second {
		t.Fatalf("custom window = %v, want 2s", custom.window)
	}
}

func TestConfigureRebuildsDefault(t *testing.T) {
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	Configure(2, time.Minute)
	if Default.threshold != 2 {
		t.Fatalf("Default.threshold after Configure = %d, want 2", Default.threshold)
	}
	if Default.window != time.Minute {
		t.Fatalf("Default.window after Configure = %v, want 1m", Default.window)
	}
	if got := Default.RecordFail("cfg", base); got != false {
		t.Fatalf("first fail on configured default should not trigger, got %v", got)
	}
	if got := Default.RecordFail("cfg", base.Add(1*time.Second)); got != true {
		t.Fatalf("second fail on configured default should trigger, got %v", got)
	}

	Configure(0, 0)
	if Default.threshold != 10 {
		t.Fatalf("Default.threshold fallback = %d, want 10", Default.threshold)
	}
	if Default.window != 5*time.Minute {
		t.Fatalf("Default.window fallback = %v, want 5m", Default.window)
	}
}

func TestRecordFailConcurrentCrossingFiresExactlyOnce(t *testing.T) {
	const threshold = 50
	tr := NewTracker(threshold, time.Minute)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	var wg sync.WaitGroup
	var mu sync.Mutex
	triggers := 0
	start := make(chan struct{})

	for i := 0; i < threshold; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			<-start
			if tr.RecordFail("hot", base.Add(time.Duration(i)*time.Millisecond)) {
				mu.Lock()
				triggers++
				mu.Unlock()
			}
		}(i)
	}
	close(start)
	wg.Wait()

	if triggers != 1 {
		t.Fatalf("concurrent crossing triggers = %d, want 1", triggers)
	}
	// 注：用 now=base+1min-1ms 使 cutoff 略早于 base，含入 base 时刻事件（左开区间语义）
	if got := tr.FailCount("hot", base.Add(time.Minute-time.Millisecond)); got != threshold {
		t.Fatalf("FailCount after concurrent = %d, want %d", got, threshold)
	}
}

func TestFailCountConcurrentReadsAreRaceFree(t *testing.T) {
	tr := NewTracker(100, time.Minute)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	for i := 0; i < 30; i++ {
		tr.RecordFail("r", base.Add(time.Duration(i)*time.Millisecond))
	}

	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for j := 0; j < 50; j++ {
				_ = tr.FailCount("r", base.Add(time.Second))
			}
		}()
	}
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			<-start
			tr.RecordFail("r", base.Add(time.Duration(100+i)*time.Millisecond))
		}(i)
	}
	close(start)
	wg.Wait()

	if got := tr.FailCount("r", base.Add(time.Second)); got != 40 {
		t.Fatalf("FailCount final = %d, want 40", got)
	}
	// 注：产品 FailCount 仅按 cutoff 过滤未来事件亦计入；查询早于事件的时间属非现实场景，不断言
}
