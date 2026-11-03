package store

import "testing"

func TestRecordAndListSMSLogMonitor(t *testing.T) {
	s := newTestStore(t)

	// 监控 7：两条（sent / failed）
	if err := s.RecordSMSLogForMonitor("13800000001", "monitor 7 ok", "aliyun", "sent", "", 7); err != nil {
		t.Fatalf("RecordSMSLogForMonitor monitor 7 sent: %v", err)
	}
	if err := s.RecordSMSLogForMonitor("13800000002", "monitor 7 fail", "aliyun", "failed", "provider timeout", 7); err != nil {
		t.Fatalf("RecordSMSLogForMonitor monitor 7 failed: %v", err)
	}
	// 监控 9：一条（sent）
	if err := s.RecordSMSLogForMonitor("13800000003", "monitor 9 ok", "aliyun", "sent", "", 9); err != nil {
		t.Fatalf("RecordSMSLogForMonitor monitor 9 sent: %v", err)
	}

	// monitorID 为 nil：不过滤，应查到全部 3 条
	logs, total, err := s.ListSMSLogFiltered("", "", nil, 100, 0)
	if err != nil {
		t.Fatalf("ListSMSLogFiltered nil monitorID: %v", err)
	}
	if total != 3 {
		t.Fatalf("nil monitorID: total = %d, want 3", total)
	}
	if len(logs) != 3 {
		t.Fatalf("nil monitorID: got %d logs, want 3", len(logs))
	}

	// monitorID = 7：应查到 2 条，且 MonitorID 全为 7
	monitor7 := int64(7)
	logs, total, err = s.ListSMSLogFiltered("", "", &monitor7, 100, 0)
	if err != nil {
		t.Fatalf("ListSMSLogFiltered monitorID 7: %v", err)
	}
	if total != 2 {
		t.Fatalf("monitorID 7: total = %d, want 2", total)
	}
	if len(logs) != 2 {
		t.Fatalf("monitorID 7: got %d logs, want 2", len(logs))
	}
	for _, lg := range logs {
		if lg.MonitorID != 7 {
			t.Errorf("monitorID 7: got MonitorID %d, want 7", lg.MonitorID)
		}
	}

	// monitorID = 9：应查到 1 条
	monitor9 := int64(9)
	logs, total, err = s.ListSMSLogFiltered("", "", &monitor9, 100, 0)
	if err != nil {
		t.Fatalf("ListSMSLogFiltered monitorID 9: %v", err)
	}
	if total != 1 {
		t.Fatalf("monitorID 9: total = %d, want 1", total)
	}
	if len(logs) != 1 {
		t.Fatalf("monitorID 9: got %d logs, want 1", len(logs))
	}

	// 旧接口写入 1 条，MonitorID 应为 0
	if err := s.RecordSMSLog("13800000004", "legacy log", "aliyun", "sent", ""); err != nil {
		t.Fatalf("RecordSMSLog legacy: %v", err)
	}
	monitor0 := int64(0)
	logs, total, err = s.ListSMSLogFiltered("", "", &monitor0, 100, 0)
	if err != nil {
		t.Fatalf("ListSMSLogFiltered monitorID 0: %v", err)
	}
	if total != 1 {
		t.Fatalf("monitorID 0: total = %d, want 1", total)
	}
	if len(logs) != 1 {
		t.Fatalf("monitorID 0: got %d logs, want 1", len(logs))
	}
	if logs[0].MonitorID != 0 {
		t.Fatalf("monitorID 0: got MonitorID %d, want 0", logs[0].MonitorID)
	}
}
