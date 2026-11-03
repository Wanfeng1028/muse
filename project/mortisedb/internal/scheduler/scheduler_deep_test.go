package scheduler

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("store.Open failed: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("st.Migrate failed: %v", err)
	}
	return st
}

func TestSched_StartSkipsInvalidInterval(t *testing.T) {
	var buf bytes.Buffer
	logger := log.New(&buf, "debug")

	cfg := config.DefaultConfig()
	cfg.Jobs = []config.JobConfig{
		{Name: "bad", Interval: "not-a-duration"},
	}

	st := newTestStore(t)
	s := New(cfg, st, logger)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	start := time.Now()
	s.Start(ctx)
	time.Sleep(150 * time.Millisecond)
	s.Stop()
	elapsed := time.Since(start)

	if elapsed >= 5*time.Second {
		t.Fatalf("Stop took too long, possible hang: %v", elapsed)
	}
	out := buf.String()
	if !strings.Contains(out, "解析作业间隔失败") {
		t.Fatalf("expected log to contain 解析作业间隔失败, got: %s", out)
	}
}

func TestSched_StartSkipsNonPositiveInterval(t *testing.T) {
	var buf bytes.Buffer
	logger := log.New(&buf, "debug")

	cfg := config.DefaultConfig()
	cfg.Jobs = []config.JobConfig{
		{Name: "zero", Interval: "0s"},
		{Name: "negative", Interval: "-5s"},
	}

	st := newTestStore(t)
	s := New(cfg, st, logger)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	s.Start(ctx)
	time.Sleep(150 * time.Millisecond)
	s.Stop()

	out := buf.String()
	count := strings.Count(out, "作业间隔必须大于 0")
	if count != 2 {
		t.Fatalf("expected 作业间隔必须大于 0 to appear 2 times, got %d, log: %s", count, out)
	}
}

func TestSched_ValidJobRunsSyncEndToEnd(t *testing.T) {
	dir := t.TempDir()
	csvPath := filepath.Join(dir, "people.csv")
	if err := os.WriteFile(csvPath, []byte("id,name\n1,Alice\n2,Bob\n"), 0o644); err != nil {
		t.Fatalf("write csv failed: %v", err)
	}

	var buf bytes.Buffer
	logger := log.New(&buf, "debug")

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Path: csvPath, Table: "people", PrimaryKey: "id"},
	}
	cfg.Jobs = []config.JobConfig{
		{Name: "job1", Interval: "50ms", Sources: []string{"s1"}},
	}

	st := newTestStore(t)
	s := New(cfg, st, logger)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	s.Start(ctx)
	time.Sleep(600 * time.Millisecond)
	s.Stop()

	out := buf.String()
	if !strings.Contains(out, "作业同步完成") {
		t.Fatalf("expected log to contain 作业同步完成, got: %s", out)
	}

	count, err := st.TableCount("people")
	if err != nil {
		t.Fatalf("st.TableCount failed: %v", err)
	}
	if count != 2 {
		t.Fatalf("expected 2 rows in people, got %d", count)
	}
}

func TestSched_JobErrorDoesNotKillLoop(t *testing.T) {
	var buf bytes.Buffer
	logger := log.New(&buf, "debug")

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{}
	cfg.Jobs = []config.JobConfig{
		{Name: "badjob", Interval: "50ms", Sources: []string{"missing-source"}},
		{Name: "goodjob", Interval: "50ms", Sources: []string{}},
	}

	st := newTestStore(t)
	s := New(cfg, st, logger)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	s.Start(ctx)
	time.Sleep(600 * time.Millisecond)
	s.Stop()

	out := buf.String()
	if !strings.Contains(out, "作业同步失败") {
		t.Fatalf("expected log to contain 作业同步失败, got: %s", out)
	}
	if !strings.Contains(out, "作业同步完成") {
		t.Fatalf("expected log to contain 作业同步完成, got: %s", out)
	}
}

func TestSched_StopWithoutStart(t *testing.T) {
	var buf bytes.Buffer
	logger := log.New(&buf, "debug")

	cfg := config.DefaultConfig()
	st := newTestStore(t)
	s := New(cfg, st, logger)

	done := make(chan struct{})
	go func() {
		defer close(done)
		s.Stop()
	}()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatalf("Stop without Start hung")
	}
}

func TestSched_StopIdempotent(t *testing.T) {
	var buf bytes.Buffer
	logger := log.New(&buf, "debug")

	cfg := config.DefaultConfig()
	cfg.Jobs = []config.JobConfig{
		{Name: "job1", Interval: "50ms", Sources: []string{}},
	}

	st := newTestStore(t)
	s := New(cfg, st, logger)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	s.Start(ctx)
	time.Sleep(120 * time.Millisecond)

	done := make(chan struct{})
	go func() {
		defer close(done)
		s.Stop()
		s.Stop()
	}()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatalf("Stop idempotent call hung")
	}
}
