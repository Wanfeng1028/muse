
package passalert

import (
	"sync"
	"testing"
	"time"
)

func TestRecordFail_FiresOnceOnCrossing(t *testing.T) {
	tr := NewTracker(3, time.Minute)
	base := time.Unix(1700000000, 0)

	if got := tr.RecordFail("s", base); got != false {
		t.Fatalf("第 1 次 RecordFail 期望 false，实际 %v", got)
	}
	if got := tr.RecordFail("s", base.Add(1*time.Second)); got != false {
		t.Fatalf("第 2 次 RecordFail 期望 false，实际 %v", got)
	}
	if got := tr.RecordFail("s", base.Add(2*time.Second)); got != true {
		t.Fatalf("第 3 次 RecordFail 期望 true（跨越阈值），实际 %v", got)
	}
	if got := tr.RecordFail("s", base.Add(3*time.Second)); got != false {
		t.Fatalf("第 4 次 RecordFail 期望 false（持续超阈值不重复），实际 %v", got)
	}
}

func TestRecordFail_RearmAfterWindowSlides(t *testing.T) {
	tr := NewTracker(3, time.Minute)
	base := time.Unix(1700000000, 0)

	if got := tr.RecordFail("s", base); got != false {
		t.Fatalf("t=0 期望 false，实际 %v", got)
	}
	if got := tr.RecordFail("s", base.Add(1*time.Second)); got != false {
		t.Fatalf("t=1s 期望 false，实际 %v", got)
	}
	if got := tr.RecordFail("s", base.Add(2*time.Second)); got != true {
		t.Fatalf("t=2s 期望 true（首次触发），实际 %v", got)
	}

	// t=61s：cutoff=1s，t=0 被裁掉；窗口内 t=1s? 注意 t=1s <= cutoff=1s 也被裁掉；
	// 只剩 t=2s 与本次 t=61s，count=2 < 3 → false 且重新布防。
	if got := tr.RecordFail("s", base.Add(61*time.Second)); got != false {
		t.Fatalf("t=61s 期望 false（重新布防），实际 %v", got)
	}

	// t=62s：cutoff=2s，t=2s <= cutoff 被裁掉；只剩 t=61s 与本次 t=62s，count=2 → false。
	if got := tr.RecordFail("s", base.Add(62*time.Second)); got != false {
		t.Fatalf("t=62s 期望 false，实际 %v", got)
	}

	// t=63s：cutoff=3s，窗口内 t=61s,62s,63s，count=3 → true（再次触发）。
	if got := tr.RecordFail("s", base.Add(63*time.Second)); got != true {
		t.Fatalf("t=63s 期望 true（再次触发），实际 %v", got)
	}
}

func TestRecordFail_WindowSlidesOldEvents(t *testing.T) {
	tr := NewTracker(2, time.Minute)
	base := time.Unix(1700000000, 0)

	if got := tr.RecordFail("s", base); got != false {
		t.Fatalf("t=0 期望 false，实际 %v", got)
	}
	// t=61s：cutoff=1s，t=0 被裁掉，count=1 → false。
	if got := tr.RecordFail("s", base.Add(61*time.Second)); got != false {
		t.Fatalf("t=61s 期望 false（旧事件被裁），实际 %v", got)
	}
}

func TestRecordFail_EmptySlug(t *testing.T) {
	tr := NewTracker(3, time.Minute)
	if got := tr.RecordFail("", time.Unix(1700000000, 0)); got != false {
		t.Fatalf("空 slug 期望 false，实际 %v", got)
	}
}

func TestNewTracker_Defaults(t *testing.T) {
	tr := NewTracker(0, 0)
	base := time.Unix(1700000000, 0)
	var last bool
	for i := 0; i < 10; i++ {
		last = tr.RecordFail("s", base.Add(time.Duration(i)*time.Second))
	}
	if last != true {
		t.Fatalf("默认阈值 10，第 10 次期望 true，实际 %v", last)
	}
}

func TestFailCount_DoesNotRecord(t *testing.T) {
	tr := NewTracker(5, time.Minute)
	base := time.Unix(1700000000, 0)
	tr.RecordFail("s", base)
	tr.RecordFail("s", base.Add(1*time.Second))

	if got := tr.FailCount("s", base.Add(2*time.Second)); got != 2 {
		t.Fatalf("FailCount 期望 2，实际 %d", got)
	}
	if got := tr.FailCount("s", base.Add(3*time.Second)); got != 2 {
		t.Fatalf("再次 FailCount 仍期望 2（不记录新事件），实际 %d", got)
	}
}

func TestRecordFail_Concurrent(t *testing.T) {
	tr := NewTracker(1000, time.Minute)
	base := time.Unix(1700000000, 0)

	var wg sync.WaitGroup
	for g := 0; g < 50; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 20; i++ {
				tr.RecordFail("s", base)
			}
		}()
	}
	wg.Wait()

	if got := tr.FailCount("s", base); got != 1000 {
		t.Fatalf("并发后 FailCount 期望 1000，实际 %d", got)
	}
}

func TestConfigure_RebuildsDefault(t *testing.T) {
	Configure(2, time.Minute)
	defer Configure(10, 5*time.Minute)

	base := time.Unix(1700000000, 0)
	if got := Default.RecordFail("cfg", base); got != false {
		t.Fatalf("Configure 后第 1 次期望 false，实际 %v", got)
	}
	if got := Default.RecordFail("cfg", base.Add(1*time.Second)); got != true {
		t.Fatalf("Configure 后第 2 次期望 true（阈值 2），实际 %v", got)
	}
	Default.Reset()
	if got := Default.FailCount("cfg", base.Add(1*time.Second)); got != 0 {
		t.Fatalf("Reset 后期望 0，实际 %d", got)
	}
}
