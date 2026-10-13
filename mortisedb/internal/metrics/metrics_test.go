package metrics

import (
	"strings"
	"sync"
	"testing"
)

func TestExpositionFormat(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("test_counter_total", "测试计数器", "a", "b")
	r.RegisterGauge("test_gauge", "测试仪表", "x")
	r.RegisterSummary("test_summary_seconds", "测试摘要", "v")

	r.Inc("test_counter_total", "1", "2")
	r.Inc("test_counter_total", "1", "2")
	r.Set("test_gauge", 42, "label")
	r.Observe("test_summary_seconds", 1.5, "s1")
	r.Observe("test_summary_seconds", 0.5, "s1")

	out := r.Render()

	// HELP/TYPE 行
	for _, want := range []string{
		"# HELP test_counter_total 测试计数器",
		"# TYPE test_counter_total counter",
		"# HELP test_gauge 测试仪表",
		"# TYPE test_gauge gauge",
		"# HELP test_summary_seconds 测试摘要",
		"# TYPE test_summary_seconds summary",
	} {
		if !strings.Contains(out, want) {
			t.Fatalf("缺少行 %q，输出:\n%s", want, out)
		}
	}

	// counter 值
	if !strings.Contains(out, `test_counter_total{a="1",b="2"} 2`) {
		t.Fatalf("counter 值不符，输出:\n%s", out)
	}
	// gauge 值
	if !strings.Contains(out, `test_gauge{x="label"} 42`) {
		t.Fatalf("gauge 值不符，输出:\n%s", out)
	}
	// summary count + sum 成对
	if !strings.Contains(out, `test_summary_seconds_count{v="s1"} 2`) {
		t.Fatalf("summary count 不符，输出:\n%s", out)
	}
	if !strings.Contains(out, `test_summary_seconds_sum{v="s1"} 2`) {
		t.Fatalf("summary sum 不符，输出:\n%s", out)
	}
}

func TestLabelEscaping(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("t_total", "测试", "v")
	r.Inc("t_total", "a\\b\"c\nd")

	out := r.Render()
	// 期望 label 值被转义：\\ \" \n
	if !strings.Contains(out, `t_total{v="a\\b\"c\nd"} 1`) {
		t.Fatalf("转义不符，输出:\n%s", out)
	}
}

func TestConcurrentInc(t *testing.T) {
	r := NewRegistry()
	r.RegisterCounter("c_total", "并发测试", "k")

	var wg sync.WaitGroup
	const goroutines = 16
	const iters = 1000
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < iters; j++ {
				r.Inc("c_total", "shared")
			}
		}()
	}
	wg.Wait()

	out := r.Render()
	want := goroutines * iters
	if !strings.Contains(out, `c_total{k="shared"} `+itoa(want)) {
		t.Fatalf("并发计数不符，期望 %d，输出:\n%s", want, out)
	}
}

func TestRegisterStandardIdempotent(t *testing.T) {
	r := NewRegistry()
	r.RegisterStandard()
	r.RegisterStandard() // 幂等，不应 panic

	out := r.Render()
	for _, want := range []string{
		"mortise_build_info",
		"mortise_sync_rows_total",
		"mortise_sync_runs_total",
		"mortise_sync_last_duration_seconds",
		"mortise_view_duration_seconds",
		"mortise_view_last_duration_seconds",
		"mortise_watermark_lag_seconds",
		"mortise_conflicts_pending",
		"mortise_conflicts_total",
		"mortise_http_requests_total",
		"mortise_http_request_duration_seconds",
		"mortise_db_size_bytes",
		"mortise_uptime_seconds",
	} {
		if !strings.Contains(out, want) {
			t.Fatalf("缺少指标 %q，输出:\n%s", want, out)
		}
	}
	// build_info 值为 1
	if !strings.Contains(out, `mortise_build_info{version="`+BuildVersion+`"} 1`) {
		t.Fatalf("build_info 值不符，输出:\n%s", out)
	}
}

// itoa 极简整数转字符串，避免额外 import。
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
