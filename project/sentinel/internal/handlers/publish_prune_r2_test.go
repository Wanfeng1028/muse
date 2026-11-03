package handlers

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestR2_PruneHistoryKeepsLatest10(t *testing.T) {
	histDir := t.TempDir()

	for i := 1; i <= 12; i++ {
		name := fmt.Sprintf("index-20260101T0000%02d.html", i)
		path := filepath.Join(histDir, name)
		if err := os.WriteFile(path, []byte("v"), 0o644); err != nil {
			t.Fatalf("write %s: %v", name, err)
		}
	}

	notesPath := filepath.Join(histDir, "notes.txt")
	if err := os.WriteFile(notesPath, []byte("keep"), 0o644); err != nil {
		t.Fatalf("write notes.txt: %v", err)
	}

	subDir := filepath.Join(histDir, "sub")
	if err := os.Mkdir(subDir, 0o755); err != nil {
		t.Fatalf("mkdir sub: %v", err)
	}

	if err := pruneHistory(histDir, 10); err != nil {
		t.Fatalf("pruneHistory returned error: %v", err)
	}

	countIndexFiles := func() int {
		entries, err := os.ReadDir(histDir)
		if err != nil {
			t.Fatalf("read dir: %v", err)
		}
		count := 0
		for _, entry := range entries {
			if entry.IsDir() {
				continue
			}
			name := entry.Name()
			if strings.HasPrefix(name, "index-") && strings.HasSuffix(name, ".html") {
				count++
			}
		}
		return count
	}

	if got := countIndexFiles(); got != 10 {
		t.Fatalf("index file count = %d, want 10", got)
	}

	for _, i := range []int{1, 2} {
		name := fmt.Sprintf("index-20260101T0000%02d.html", i)
		if _, err := os.Stat(filepath.Join(histDir, name)); err == nil {
			t.Fatalf("expected %s to be removed", name)
		} else if !os.IsNotExist(err) {
			t.Fatalf("stat %s error = %v, want not exist", name, err)
		}
	}

	if _, err := os.Stat(notesPath); err != nil {
		t.Fatalf("notes.txt should still exist: %v", err)
	}

	if info, err := os.Stat(subDir); err != nil {
		t.Fatalf("sub should still exist: %v", err)
	} else if !info.IsDir() {
		t.Fatalf("sub should remain a directory")
	}

	if err := pruneHistory(histDir, 10); err != nil {
		t.Fatalf("second pruneHistory returned error: %v", err)
	}

	if got := countIndexFiles(); got != 10 {
		t.Fatalf("index file count after second prune = %d, want 10", got)
	}
}
