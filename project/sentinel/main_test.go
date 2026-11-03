package main

import (
	"path/filepath"
	"strings"
	"testing"

	"sentinel/internal/config"
	"sentinel/internal/db"
	"sentinel/internal/notify"
	"sentinel/internal/store"
)

func TestBuildNotifier_MockSMSLoggerRecords(t *testing.T) {
	dir := t.TempDir()
	sqlDB, err := db.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer sqlDB.Close()

	st := store.New(sqlDB)

	cfg := config.Config{SMSMode: "mock"}
	ntf, err := buildNotifier(cfg, st)
	if err != nil {
		t.Fatalf("buildNotifier: %v", err)
	}
	if ntf.SMSLogger == nil {
		t.Fatal("SMSLogger is nil")
	}

	errs := ntf.Notify(
		notify.Target{NotifyChannels: "sms", SMSPhones: "13800138000"},
		"down", "冒烟站", "http://127.0.0.1:9/dead", "2026-10-25T05:00:00Z", "连接被拒绝",
	)
	if len(errs) > 0 {
		t.Fatalf("Notify returned errors: %v", errs)
	}

	logs, total, err := st.ListSMSLog("13800138000", "sent", 10, 0)
	if err != nil {
		t.Fatalf("ListSMSLog: %v", err)
	}
	if total < 1 {
		t.Fatalf("expected total >= 1, got %d", total)
	}
	if logs[0].Phone != "13800138000" {
		t.Errorf("Phone = %q, want %q", logs[0].Phone, "13800138000")
	}
	if logs[0].Status != "sent" {
		t.Errorf("Status = %q, want %q", logs[0].Status, "sent")
	}
	if logs[0].Provider != "mock" {
		t.Errorf("Provider = %q, want %q", logs[0].Provider, "mock")
	}
	if !strings.Contains(logs[0].Message, "冒烟站") {
		t.Errorf("Message = %q, want containing %q", logs[0].Message, "冒烟站")
	}
}

func TestBuildNotifier_InvalidModeErrors(t *testing.T) {
	dir := t.TempDir()
	sqlDB, err := db.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer sqlDB.Close()

	st := store.New(sqlDB)

	cfg := config.Config{SMSMode: "carrierpigeon"}
	if _, err := buildNotifier(cfg, st); err == nil {
		t.Fatal("expected error for invalid SMS mode, got nil")
	}
}
