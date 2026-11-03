package store

import (
	"database/sql"
	"errors"
	"strings"
	"testing"
)

func TestR2_UpdateStatusPageThemeValidate(t *testing.T) {
	st := newTestStore(t)

	pageID, err := st.CreateStatusPage(1, "pg-r2c", "t")
	if err != nil {
		t.Fatalf("CreateStatusPage returned error: %v", err)
	}
	if pageID <= 0 {
		t.Fatalf("CreateStatusPage returned non-positive id: %d", pageID)
	}

	err = st.UpdateStatusPageTheme(pageID, "blue", "")
	if err == nil {
		t.Fatal("expected error for invalid theme, got nil")
	}
	if !strings.Contains(err.Error(), "主题非法") {
		t.Fatalf("expected invalid theme error to contain 主题非法, got %q", err.Error())
	}

	err = st.UpdateStatusPageTheme(pageID, "dark", "red")
	if err == nil {
		t.Fatal("expected error for invalid accent color, got nil")
	}
	if !strings.Contains(err.Error(), "主色非法") {
		t.Fatalf("expected invalid accent color error to contain 主色非法, got %q", err.Error())
	}

	err = st.UpdateStatusPageTheme(pageID, "dark", "#1a2b3c")
	if err != nil {
		t.Fatalf("expected no error for valid theme and accent color, got %v", err)
	}

	sp, err := st.GetStatusPage(pageID)
	if err != nil {
		t.Fatalf("GetStatusPage returned error: %v", err)
	}
	if sp.Theme != "dark" {
		t.Fatalf("expected theme dark, got %q", sp.Theme)
	}
	if sp.AccentColor != "#1a2b3c" {
		t.Fatalf("expected accent color #1a2b3c, got %q", sp.AccentColor)
	}

	err = st.UpdateStatusPageTheme(pageID, "light", "")
	if err != nil {
		t.Fatalf("expected no error for empty accent color, got %v", err)
	}

	err = st.UpdateStatusPageTheme(999999, "dark", "")
	if err == nil {
		t.Fatal("expected error for missing status page, got nil")
	}
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("expected sql.ErrNoRows for missing status page, got %v", err)
	}
}
