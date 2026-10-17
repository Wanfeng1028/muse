package store

import (
	"path/filepath"
	"testing"
	"time"
)

func openPushStatusTestStore(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "push_status_deep.db")
	store, err := Open(dbPath)
	if err != nil {
		t.Fatalf("打开数据库失败: %v", err)
	}
	t.Cleanup(func() {
		_ = store.Close()
	})
	return store
}

func insertPushStatusLog(t *testing.T, s *Store, date, channel, user, status, createdAt string) {
	t.Helper()
	normalized := NormalizeUser(user)
	_, err := s.db.Exec(
		`INSERT INTO push_log (date, channel, user_id, status, created_at) VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(date, channel, user_id) DO UPDATE SET status=excluded.status, created_at=excluded.created_at`,
		date, channel, normalized, status, createdAt,
	)
	if err != nil {
		t.Fatalf("插入 push_log 失败: %v", err)
	}
}

func TestPushLogStatusDeep(t *testing.T) {
	t.Run("复习调度跨天边界", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-03-01", "wechat", "u-cross", "sent", "2024-03-01T23:59:59+08:00")
		insertPushStatusLog(t, s, "2024-03-02", "wechat", "u-cross", "failed", "2024-03-02T00:00:01+08:00")

		status1, ok1 := s.PushLogStatus("2024-03-01", "wechat", "u-cross")
		if !ok1 {
			t.Fatalf("跨天前一日应查到记录")
		}
		if status1 != "sent" {
			t.Fatalf("跨天前一日状态应为 sent，实际 %q", status1)
		}

		status2, ok2 := s.PushLogStatus("2024-03-02", "wechat", "u-cross")
		if !ok2 {
			t.Fatalf("跨天后一日应查到记录")
		}
		if status2 != "failed" {
			t.Fatalf("跨天后一日状态应为 failed，实际 %q", status2)
		}
	})

	t.Run("闰日调度", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-02-29", "email", "u-leap", "sent", "2024-02-29T08:00:00+08:00")

		status, ok := s.PushLogStatus("2024-02-29", "email", "u-leap")
		if !ok {
			t.Fatalf("闰日应查到记录")
		}
		if status != "sent" {
			t.Fatalf("闰日状态应为 sent，实际 %q", status)
		}

		_, okMissing := s.PushLogStatus("2024-02-30", "email", "u-leap")
		if okMissing {
			t.Fatalf("非法日期 2024-02-30 不应查到记录")
		}
	})

	t.Run("时区相同日期不同时刻", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-06-15", "sms", "u-tz", "sent", "2024-06-15T00:30:00+08:00")
		insertPushStatusLog(t, s, "2024-06-15", "sms", "u-tz", "failed", "2024-06-15T23:30:00+08:00")

		status, ok := s.PushLogStatus("2024-06-15", "sms", "u-tz")
		if !ok {
			t.Fatalf("同时区同日期应查到记录")
		}
		if status != "failed" {
			t.Fatalf("同日期最新状态应为 failed，实际 %q", status)
		}
	})

	t.Run("SM-2 极端 EF 值通道", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-07-01", "ef-1.3", "u-ef-low", "sent", "2024-07-01T10:00:00+08:00")
		insertPushStatusLog(t, s, "2024-07-01", "ef-2.5", "u-ef-mid", "sent", "2024-07-01T10:00:00+08:00")
		insertPushStatusLog(t, s, "2024-07-01", "ef-3.0", "u-ef-max", "sent", "2024-07-01T10:00:00+08:00")

		statusLow, okLow := s.PushLogStatus("2024-07-01", "ef-1.3", "u-ef-low")
		if !okLow {
			t.Fatalf("EF 下限 1.3 应查到记录")
		}
		if statusLow != "sent" {
			t.Fatalf("EF 下限状态应为 sent，实际 %q", statusLow)
		}

		statusMax, okMax := s.PushLogStatus("2024-07-01", "ef-3.0", "u-ef-max")
		if !okMax {
			t.Fatalf("EF 上限 3.0 应查到记录")
		}
		if statusMax != "sent" {
			t.Fatalf("EF 上限状态应为 sent，实际 %q", statusMax)
		}

		_, okMissing := s.PushLogStatus("2024-07-01", "ef-1.2", "u-ef-low")
		if okMissing {
			t.Fatalf("EF 低于下限的通道不应查到记录")
		}
	})

	t.Run("双链解析嵌套括号", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-08-01", "wiki", "u-nest", "sent", "2024-08-01T09:00:00+08:00")

		status, ok := s.PushLogStatus("2024-08-01", "wiki", "u-nest")
		if !ok {
			t.Fatalf("嵌套双链通道应查到记录")
		}
		if status != "sent" {
			t.Fatalf("嵌套双链状态应为 sent，实际 %q", status)
		}

		_, okMissing := s.PushLogStatus("2024-08-01", "wiki-nested", "u-nest")
		if okMissing {
			t.Fatalf("不同通道名不应查到记录")
		}
	})

	t.Run("双链解析中文标题", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-08-02", "中文标题", "用户甲", "sent", "2024-08-02T09:00:00+08:00")

		status, ok := s.PushLogStatus("2024-08-02", "中文标题", "用户甲")
		if !ok {
			t.Fatalf("中文标题与中文用户应查到记录")
		}
		if status != "sent" {
			t.Fatalf("中文标题状态应为 sent，实际 %q", status)
		}

		_, okMissing := s.PushLogStatus("2024-08-02", "中文标题", "用户乙")
		if okMissing {
			t.Fatalf("不同中文用户不应查到记录")
		}
	})

	t.Run("附件白名单绕过尝试", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-09-01", "attach", "u-attach", "sent", "2024-09-01T09:00:00+08:00")

		status, ok := s.PushLogStatus("2024-09-01", "attach", "u-attach")
		if !ok {
			t.Fatalf("正常附件通道应查到记录")
		}
		if status != "sent" {
			t.Fatalf("正常附件状态应为 sent，实际 %q", status)
		}

		_, okBypass := s.PushLogStatus("2024-09-01", "attach/../../etc/passwd", "u-attach")
		if okBypass {
			t.Fatalf("路径穿越通道不应查到记录")
		}
	})

	t.Run("导出 ZipSlip 路径", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-10-01", "export", "u-zip", "sent", "2024-10-01T09:00:00+08:00")

		status, ok := s.PushLogStatus("2024-10-01", "export", "u-zip")
		if !ok {
			t.Fatalf("正常导出通道应查到记录")
		}
		if status != "sent" {
			t.Fatalf("正常导出状态应为 sent，实际 %q", status)
		}

		_, okSlip := s.PushLogStatus("2024-10-01", "../../../etc/shadow", "u-zip")
		if okSlip {
			t.Fatalf("ZipSlip 通道不应查到记录")
		}
	})

	t.Run("多用户隔离", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-11-01", "wechat", "user-a", "sent", "2024-11-01T09:00:00+08:00")
		insertPushStatusLog(t, s, "2024-11-01", "wechat", "user-b", "failed", "2024-11-01T09:00:00+08:00")

		statusA, okA := s.PushLogStatus("2024-11-01", "wechat", "user-a")
		if !okA {
			t.Fatalf("user-a 应查到记录")
		}
		if statusA != "sent" {
			t.Fatalf("user-a 状态应为 sent，实际 %q", statusA)
		}

		statusB, okB := s.PushLogStatus("2024-11-01", "wechat", "user-b")
		if !okB {
			t.Fatalf("user-b 应查到记录")
		}
		if statusB != "failed" {
			t.Fatalf("user-b 状态应为 failed，实际 %q", statusB)
		}

		_, okC := s.PushLogStatus("2024-11-01", "wechat", "user-c")
		if okC {
			t.Fatalf("未写入的 user-c 不应查到记录")
		}
	})

	t.Run("用户归一化查询一致", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		insertPushStatusLog(t, s, "2024-12-01", "wechat", "  User-Trim  ", "sent", "2024-12-01T09:00:00+08:00")

		status, ok := s.PushLogStatus("2024-12-01", "wechat", "user-trim")
		if !ok {
			t.Fatalf("归一化后用户应查到记录")
		}
		if status != "sent" {
			t.Fatalf("归一化用户状态应为 sent，实际 %q", status)
		}

		status2, ok2 := s.PushLogStatus("2024-12-01", "wechat", "  User-Trim  ")
		if !ok2 {
			t.Fatalf("带空白用户归一化后应查到记录")
		}
		if status2 != "sent" {
			t.Fatalf("带空白用户状态应为 sent，实际 %q", status2)
		}
	})

	t.Run("无记录返回空与假", func(t *testing.T) {
		s := openPushStatusTestStore(t)

		status, ok := s.PushLogStatus("2025-01-01", "wechat", "ghost")
		if ok {
			t.Fatalf("无记录时 ok 应为 false")
		}
		if status != "" {
			t.Fatalf("无记录时 status 应为空字符串，实际 %q", status)
		}
	})

	t.Run("多记录取最新", func(t *testing.T) {
		s := openPushStatusTestStore(t)
		base := time.Date(2025, 2, 1, 10, 0, 0, 0, time.UTC)
		insertPushStatusLog(t, s, "2025-02-01", "wechat", "u-latest", "failed", base.Format(time.RFC3339))
		insertPushStatusLog(t, s, "2025-02-01", "wechat", "u-latest", "sent", base.Add(time.Hour).Format(time.RFC3339))

		status, ok := s.PushLogStatus("2025-02-01", "wechat", "u-latest")
		if !ok {
			t.Fatalf("多记录应查到记录")
		}
		if status != "sent" {
			t.Fatalf("多记录应取最新状态 sent，实际 %q", status)
		}
	})
}
