package handlers

import (
	"strings"
	"testing"
)

func TestR2_RollbackNoHistory(t *testing.T) {
	srv, st := newTestServer(t)
	srv.SetPublishDir(t.TempDir())
	pageID, _ := st.CreateStatusPage(1, "rb-r2", "t")
	_, err := srv.RollbackStatusPage(pageID)
	if err == nil {
		t.Fatal("expected rollback error when history is empty, got nil")
	}
	if !strings.Contains(err.Error(), "无可回滚版本") {
		t.Fatalf("unexpected error: %v", err)
	}
}
