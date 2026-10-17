package log

import (
	"context"
	"log/slog"
	"sync"
	"testing"
)

func TestLogInit_DebugEnablesDebug(t *testing.T) {
	Init("debug")
	t.Cleanup(func() { Init("info") })

	if !Logger().Enabled(context.Background(), slog.LevelDebug) {
		t.Fatalf("expected debug level to be enabled after Init(\"debug\")")
	}
}

func TestLogInit_InfoDisablesDebug(t *testing.T) {
	Init("info")
	t.Cleanup(func() { Init("info") })

	l := Logger()
	if l.Enabled(context.Background(), slog.LevelDebug) {
		t.Fatalf("expected debug level to be disabled after Init(\"info\")")
	}
	if !l.Enabled(context.Background(), slog.LevelInfo) {
		t.Fatalf("expected info level to be enabled after Init(\"info\")")
	}
}

func TestLogInit_InvalidFallsBackToInfo(t *testing.T) {
	Init("bogus-level")
	t.Cleanup(func() { Init("info") })

	l := Logger()
	if l.Enabled(context.Background(), slog.LevelDebug) {
		t.Fatalf("expected debug level to be disabled when falling back to info")
	}
	if !l.Enabled(context.Background(), slog.LevelInfo) {
		t.Fatalf("expected info level to be enabled when falling back to info")
	}
}

func TestLogInit_CaseInsensitive(t *testing.T) {
	Init("WARN")
	t.Cleanup(func() { Init("info") })

	l := Logger()
	if l.Enabled(context.Background(), slog.LevelInfo) {
		t.Fatalf("expected info level to be disabled after Init(\"WARN\")")
	}
	if !l.Enabled(context.Background(), slog.LevelWarn) {
		t.Fatalf("expected warn level to be enabled after Init(\"WARN\")")
	}

	Init("warning")
	l = Logger()
	if l.Enabled(context.Background(), slog.LevelInfo) {
		t.Fatalf("expected info level to be disabled after Init(\"warning\")")
	}
	if !l.Enabled(context.Background(), slog.LevelWarn) {
		t.Fatalf("expected warn level to be enabled after Init(\"warning\")")
	}
}

func TestLogger_AlwaysNonNil(t *testing.T) {
	if Logger() == nil {
		t.Fatalf("expected Logger() to be non-nil")
	}
	Init("debug")
	t.Cleanup(func() { Init("info") })
	if Logger() == nil {
		t.Fatalf("expected Logger() to be non-nil after Init")
	}
}

func TestWithRequestID_Roundtrip(t *testing.T) {
	parent := context.Background()
	ctx := WithRequestID(parent, "r-123")

	if got := RequestIDFrom(ctx); got != "r-123" {
		t.Fatalf("expected request id %q, got %q", "r-123", got)
	}
	if got := RequestIDFrom(parent); got != "" {
		t.Fatalf("expected parent context to have empty request id, got %q", got)
	}
}

func TestRequestIDFrom_NilAndWrongType(t *testing.T) {
	if got := RequestIDFrom(nil); got != "" {
		t.Fatalf("expected empty request id from nil context, got %q", got)
	}

	ctx := context.WithValue(context.Background(), struct{}{}, 123)
	if got := RequestIDFrom(ctx); got != "" {
		t.Fatalf("expected empty request id for wrong value type, got %q", got)
	}
}

func TestLogger_ConcurrentSafe(t *testing.T) {
	Init("info")
	t.Cleanup(func() { Init("info") })

	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			l := Logger()
			if l == nil {
				t.Errorf("expected non-nil logger in goroutine")
				return
			}
			l.Info("x")
		}()
	}
	wg.Wait()
}
