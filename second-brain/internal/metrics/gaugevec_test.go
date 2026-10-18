package metrics

import (
	"strings"
	"testing"
)

func TestGaugeVecUnknownNameIgnored(t *testing.T) {
	r := New()
	r.SetGaugeLabelsFunc("nope", func() map[string]float64 {
		return map[string]float64{"x": 1}
	})
	out := r.render()
	if strings.Contains(out, "nope") {
		t.Fatalf("unknown gauge vec name should be ignored, got:\n%s", out)
	}
}

func TestGaugeVecSortedAndFormatted(t *testing.T) {
	r := New()
	r.SetGaugeLabelsFunc("reviews_due_by_user", func() map[string]float64 {
		return map[string]float64{"bob": 2, "alice": 5}
	})
	out := r.render()
	if !strings.Contains(out, `reviews_due_by_user{user="alice"} 5`) {
		t.Fatalf("missing alice sample, got:\n%s", out)
	}
	if !strings.Contains(out, `reviews_due_by_user{user="bob"} 2`) {
		t.Fatalf("missing bob sample, got:\n%s", out)
	}
	aliceIdx := strings.Index(out, `reviews_due_by_user{user="alice"}`)
	bobIdx := strings.Index(out, `reviews_due_by_user{user="bob"}`)
	if aliceIdx < 0 || bobIdx < 0 {
		t.Fatalf("missing sample lines, got:\n%s", out)
	}
	if aliceIdx > bobIdx {
		t.Fatalf("expected alice before bob (sorted), got:\n%s", out)
	}
}

func TestGaugeVecLabelEscaping(t *testing.T) {
	r := New()
	r.SetGaugeLabelsFunc("reviews_due_by_user", func() map[string]float64 {
		return map[string]float64{`a"b\c`: 3}
	})
	out := r.render()
	want := `reviews_due_by_user{user="a\"b\\c"} 3`
	if !strings.Contains(out, want) {
		t.Fatalf("expected escaped label %q in output, got:\n%s", want, out)
	}
}

func TestGaugeVecPanicHandled(t *testing.T) {
	r := New()
	r.SetGaugeLabelsFunc("reviews_due_by_user", func() map[string]float64 {
		panic("boom")
	})
	out := r.render()
	if !strings.Contains(out, "# TYPE reviews_due_by_user gauge") {
		t.Fatalf("expected HELP/TYPE header for reviews_due_by_user, got:\n%s", out)
	}
	if strings.Contains(out, `reviews_due_by_user{`) {
		t.Fatalf("panic should yield no samples, got:\n%s", out)
	}
}

func TestGaugeVecNilRemoves(t *testing.T) {
	r := New()
	r.SetGaugeLabelsFunc("reviews_due_by_user", func() map[string]float64 {
		return map[string]float64{"alice": 1}
	})
	r.SetGaugeLabelsFunc("reviews_due_by_user", nil)
	out := r.render()
	if strings.Contains(out, "reviews_due_by_user") {
		t.Fatalf("nil func should remove metric, got:\n%s", out)
	}
}
