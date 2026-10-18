package metrics

import (
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"
)

// TestRegisterCounterIdempotentAndOrderStable 验证同名重复注册不会覆盖已有系列，
// 且输出顺序保持注册先后。
func TestRegisterCounterIdempotentAndOrderStable(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("alpha_total", "first help", "code")
	r.RegisterCounter("beta_total", "second help")

	// 再次以不同 help 注册同名指标，应返回已有指标，不改变 help。
	r.RegisterCounter("alpha_total", "changed help", "code")

	r.Inc("alpha_total", "200")
	r.Inc("beta_total")

	out := r.Render()

	if !strings.Contains(out, "# HELP alpha_total first help\n") {
		t.Fatalf("重复注册后 help 被改写，输出为:\n%s", out)
	}
	if strings.Contains(out, "changed help") {
		t.Fatalf("重复注册写入了新 help，输出为:\n%s", out)
	}

	idxAlpha := strings.Index(out, "# HELP alpha_total")
	idxBeta := strings.Index(out, "# HELP beta_total")
	if idxAlpha < 0 || idxBeta < 0 {
		t.Fatalf("缺少指标输出，输出为:\n%s", out)
	}
	if idxAlpha > idxBeta {
		t.Fatalf("输出顺序未按注册顺序，alpha 应在 beta 前，输出为:\n%s", out)
	}
}

// TestMultiSourceConflictSameKeyDifferentValue 模拟多源拼装：同一 label key
// 被不同来源写入不同值。Counter 为累加语义，冲突值应累加而不是相互覆盖。
func TestMultiSourceConflictSameKeyDifferentValue(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("ingest_total", "ingest counter", "source")

	// 源 A 写入 3，源 B 对同一 source 写入 7。
	r.Add("ingest_total", 3, "src-a")
	r.Add("ingest_total", 7, "src-a")

	// 另一个不同 source 保持独立。
	r.Add("ingest_total", 5, "src-b")

	out := r.Render()

	if !strings.Contains(out, `ingest_total{source="src-a"} 10`) {
		t.Fatalf("同 key 不同值未按 counter 累加，输出为:\n%s", out)
	}
	if !strings.Contains(out, `ingest_total{source="src-b"} 5`) {
		t.Fatalf("不同 key 的值被污染，输出为:\n%s", out)
	}

	// Gauge 为覆盖语义：后写入者胜出。
	r.RegisterGauge("queue_depth", "queue depth", "source")
	r.Set("queue_depth", 100, "src-a")
	r.Set("queue_depth", 42, "src-a")
	out2 := r.Render()
	if !strings.Contains(out2, `queue_depth{source="src-a"} 42`) {
		t.Fatalf("gauge 冲突未以后写覆盖，输出为:\n%s", out2)
	}
	if strings.Contains(out2, `queue_depth{source="src-a"} 100`) {
		t.Fatalf("gauge 仍保留旧值，输出为:\n%s", out2)
	}
}

// TestSummaryObserveAccumulates 验证 Summary 的 count/sum 在多源观测下正确累计，
// 且同一 key 的观测互相叠加。
func TestSummaryObserveAccumulates(t *testing.T) {
	r := NewRegistry()
	r.RegisterSummary("latency_seconds", "request latency", "route")

	r.Observe("latency_seconds", 0.1, "/a")
	r.Observe("latency_seconds", 0.2, "/a")
	r.Observe("latency_seconds", 0.3, "/a")

	out := r.Render()

	if !strings.Contains(out, `latency_seconds_count{route="/a"} 3`) {
		t.Fatalf("summary count 不正确，输出为:\n%s", out)
	}
	if !strings.Contains(out, `latency_seconds_sum{route="/a"} 0.6`) {
		t.Fatalf("summary sum 不正确，输出为:\n%s", out)
	}
}

// TestAddUnknownMetricIsNoop 验证向未注册指标写入不会 panic，也不会凭空创建指标。
func TestAddUnknownMetricIsNoop(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("known_total", "known")

	// 未注册指标：这些调用应当被安全忽略。
	r.Add("ghost_total", 1, "x")
	r.Inc("ghost_total")
	r.Set("ghost_gauge", 9)
	r.Observe("ghost_summary", 3)

	out := r.Render()

	if strings.Contains(out, "ghost_total") || strings.Contains(out, "ghost_gauge") || strings.Contains(out, "ghost_summary") {
		t.Fatalf("未注册指标被写入了输出，输出为:\n%s", out)
	}
	if !strings.Contains(out, "# HELP known_total known\n") {
		t.Fatalf("已注册指标丢失，输出为:\n%s", out)
	}
}

// TestLabelEscapingAndFormatting 验证 label 值中的反斜杠、双引号、换行被正确转义，
// 并且无 label 指标不输出花括号。
func TestLabelEscapingAndFormatting(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("escaped_total", "escaped", "path")
	r.Inc("escaped_total", "a\\b\"c\nd")

	out := r.Render()

	if !strings.Contains(out, `escaped_total{path="a\\b\"c\nd"} 1`) {
		t.Fatalf("label 转义不正确，输出为:\n%s", out)
	}

	r.RegisterCounter("noleaf_total", "no labels")
	r.Inc("noleaf_total")
	out2 := r.Render()
	if !strings.Contains(out2, "noleaf_total 1\n") {
		t.Fatalf("无 label 指标未按裸名输出，输出为:\n%s", out2)
	}
	if strings.Contains(out2, "noleaf_total{") {
		t.Fatalf("无 label 指标不应带花括号，输出为:\n%s", out2)
	}
}

// TestRenderContainsHelpAndType 验证每个指标都输出 HELP 与 TYPE 头，TYPE 与注册类型一致。
func TestRenderContainsHelpAndType(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("c_total", "counter help")
	r.RegisterGauge("g", "gauge help")
	r.RegisterSummary("s", "summary help")

	out := r.Render()

	wants := []string{
		"# HELP c_total counter help\n",
		"# TYPE c_total counter\n",
		"# HELP g gauge help\n",
		"# TYPE g gauge\n",
		"# HELP s summary help\n",
		"# TYPE s summary\n",
	}
	for _, w := range wants {
		if !strings.Contains(out, w) {
			t.Fatalf("缺少输出片段 %q，输出为:\n%s", w, out)
		}
	}
}

// TestSeriesOrderStableByFirstSeen 验证同一指标下多个系列按首次出现顺序输出，
// 保证 /metrics 文本稳定。
func TestSeriesOrderStableByFirstSeen(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("ordered_total", "ordered", "k")

	r.Inc("ordered_total", "first")
	r.Inc("ordered_total", "second")
	r.Inc("ordered_total", "third")
	// 再次写入 first，不应改变顺序。
	r.Inc("ordered_total", "first")

	out := r.Render()

	iFirst := strings.Index(out, `ordered_total{k="first"}`)
	iSecond := strings.Index(out, `ordered_total{k="second"}`)
	iThird := strings.Index(out, `ordered_total{k="third"}`)
	if iFirst < 0 || iSecond < 0 || iThird < 0 {
		t.Fatalf("缺少系列输出，输出为:\n%s", out)
	}
	if !(iFirst < iSecond && iSecond < iThird) {
		t.Fatalf("系列顺序不是首次出现顺序，输出为:\n%s", out)
	}
	if !strings.Contains(out, `ordered_total{k="first"} 2`) {
		t.Fatalf("重复写入未累加，输出为:\n%s", out)
	}
}

// TestBuildVersionDefault 验证 BuildVersion 默认值，并可被 api 层覆盖。
func TestBuildVersionDefault(t *testing.T) {
	if BuildVersion == "" {
		t.Fatalf("BuildVersion 不应为空")
	}
	original := BuildVersion
	defer func() { BuildVersion = original }()

	BuildVersion = "9.9.9-test"
	if BuildVersion != "9.9.9-test" {
		t.Fatalf("BuildVersion 覆盖失败，当前为 %q", BuildVersion)
	}
}

// TestStartTimeMonotonic 验证 StartTime 返回注册表创建时间，且不被后续操作改变。
func TestStartTimeMonotonic(t *testing.T) {
	r := NewRegistry()
	t0 := r.StartTime()
	if t0.IsZero() {
		t.Fatalf("StartTime 不应为零值")
	}
	r.RegisterCounter("x_total", "x")
	r.Inc("x_total")
	time.Sleep(2 * time.Millisecond)
	t1 := r.StartTime()
	if !t0.Equal(t1) {
		t.Fatalf("StartTime 不应变化: t0=%v t1=%v", t0, t1)
	}
}

// TestDefaultRegistrySingleton 验证 Default 返回同一个全局注册表实例。
func TestDefaultRegistrySingleton(t *testing.T) {
	a := Default()
	b := Default()
	if a == nil || b == nil {
		t.Fatalf("Default 不应返回 nil")
	}
	if a != b {
		t.Fatalf("Default 应返回同一实例")
	}
	a.RegisterCounter("default_singleton_total", "singleton")
	a.Inc("default_singleton_total")
	if !strings.Contains(b.Render(), "default_singleton_total 1") {
		t.Fatalf("同一实例写入未生效，输出为:\n%s", b.Render())
	}
}

// TestConcurrentWritesRaceSafe 在 -race 下验证并发写入同一指标不产生数据竞争，
// 且最终累加值精确。
func TestConcurrentWritesRaceSafe(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("concurrent_total", "concurrent", "w")
	r.RegisterSummary("concurrent_summary", "concurrent summary", "w")

	const goroutines = 16
	const perGoroutine = 500

	var wg sync.WaitGroup
	for g := 0; g < goroutines; g++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			label := fmt.Sprintf("w-%d", id)
			for i := 0; i < perGoroutine; i++ {
				r.Inc("concurrent_total", label)
				r.Observe("concurrent_summary", 1, label)
			}
		}(g)
	}
	wg.Wait()

	out := r.Render()
	for g := 0; g < goroutines; g++ {
		label := fmt.Sprintf("w-%d", g)
		wantCounter := fmt.Sprintf(`concurrent_total{w="%s"} %d`, label, perGoroutine)
		if !strings.Contains(out, wantCounter) {
			t.Fatalf("并发 counter 值不正确，缺少 %q，输出为:\n%s", wantCounter, out)
		}
		wantCount := fmt.Sprintf(`concurrent_summary_count{w="%s"} %d`, label, perGoroutine)
		if !strings.Contains(out, wantCount) {
			t.Fatalf("并发 summary count 不正确，缺少 %q，输出为:\n%s", wantCount, out)
		}
		wantSum := fmt.Sprintf(`concurrent_summary_sum{w="%s"} %d`, label, perGoroutine)
		if !strings.Contains(out, wantSum) {
			t.Fatalf("并发 summary sum 不正确，缺少 %q，输出为:\n%s", wantSum, out)
		}
	}
}

// TestRenderConcurrentWithWrites 在 -race 下验证 Render 与写入并发不产生数据竞争，
// 且每次 Render 都是自洽快照（不 panic、非空）。
func TestRenderConcurrentWithWrites(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("snap_total", "snapshot", "k")
	r.RegisterGauge("snap_gauge", "snapshot gauge", "k")

	stop := make(chan struct{})
	var wg sync.WaitGroup

	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			select {
			case <-stop:
				return
			default:
				r.Inc("snap_total", "a")
				r.Set("snap_gauge", 1, "a")
			}
		}
	}()

	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			select {
			case <-stop:
				return
			default:
				out := r.Render()
				if !strings.Contains(out, "# TYPE snap_total counter") {
					t.Errorf("Render 快照缺少 counter 头:\n%s", out)
					return
				}
			}
		}
	}()

	time.Sleep(50 * time.Millisecond)
	close(stop)
	wg.Wait()

	final := r.Render()
	if !strings.Contains(final, "# TYPE snap_gauge gauge") {
		t.Fatalf("最终 Render 缺少 gauge 头:\n%s", final)
	}
	if !strings.Contains(final, `snap_total{k="a"}`) {
		t.Fatalf("最终 Render 缺少系列:\n%s", final)
	}
}
