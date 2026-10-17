package store

import (
	"database/sql"
	"sentinel/internal/db"
	"strings"
	"sync"
	"testing"
	"time"
)

func openTestStore(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	sqldb, err := db.Open(dir + "/test.db")
	if err != nil {
		t.Fatalf("打开测试库失败: %v", err)
	}
	t.Cleanup(func() { sqldb.Close() })
	return New(sqldb)
}
// seedMonitors 批量创建 n 个 monitor 父行，使自增 ID 1..n 存在，
// 供投递队列测试的硬编码 monitorID 使用（webhook_deliveries.monitor_id 外键约束）。
func seedMonitors(t *testing.T, s *Store, n int) {
	t.Helper()
	for i := 0; i < n; i++ {
		_, err := s.CreateMonitor(Monitor{
			Name:           "seed",
			Kind:           "http",
			Target:         "https://example.com/seed",
			Method:         "GET",
			ExpectedStatus: 200,
			TimeoutSec:     10,
			IntervalSec:    60,
			Enabled:        1,
		})
		if err != nil {
			t.Fatalf("seed monitor %d: %v", i, err)
		}
	}
}


func TestEnqueueDeliveryEmptyAndBoundary(t *testing.T) {
	cases := []struct {
		name        string
		monitorID   int64
		url         string
		event       string
		payload     string
		maxAttempts int
		wantErr     bool
		wantMax     int
	}{
		{
			name:        "空 URL 允许写入",
			monitorID:   1,
			url:         "",
			event:       "",
			payload:     "",
			maxAttempts: 0,
			wantErr:     false,
			wantMax:     8,
		},
		{
			name:        "非法 URL 字符串照常入库",
			monitorID:   2,
			url:         "://not-a-url",
			event:       "down",
			payload:     "{}",
			maxAttempts: 3,
			wantErr:     false,
			wantMax:     3,
		},
		{
			name:        "超长 URL 一万字符",
			monitorID:   3,
			url:         "https://example.com/" + strings.Repeat("a", 10000),
			event:       "down",
			payload:     "{}",
			maxAttempts: 5,
			wantErr:     false,
			wantMax:     5,
		},
		{
			name:        "负 maxAttempts 归一到 8",
			monitorID:   4,
			url:         "https://example.com/hook",
			event:       "up",
			payload:     `{"a":1}`,
			maxAttempts: -9,
			wantErr:     false,
			wantMax:     8,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s := openTestStore(t)
			seedMonitors(t, s, 4)
			id, err := s.EnqueueDelivery(tc.monitorID, tc.url, tc.event, tc.payload, tc.maxAttempts)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("期望报错，实际成功 id=%d", id)
				}
				return
			}
			if err != nil {
				t.Fatalf("入队失败: %v", err)
			}
			if id <= 0 {
				t.Fatalf("返回 id 非法: %d", id)
			}
			got, err := s.GetDelivery(id)
			if err != nil {
				t.Fatalf("查询失败: %v", err)
			}
			if got.URL != tc.url {
				t.Fatalf("URL 不一致，期望 %q 实际 %q", tc.url, got.URL)
			}
			if got.MaxAttempts != tc.wantMax {
				t.Fatalf("MaxAttempts 期望 %d 实际 %d", tc.wantMax, got.MaxAttempts)
			}
			if got.Status != "pending" {
				t.Fatalf("初始状态期望 pending 实际 %q", got.Status)
			}
			if got.Attempt != 0 {
				t.Fatalf("初始 attempt 期望 0 实际 %d", got.Attempt)
			}
		})
	}
}

func TestEnqueueDeliveryIdempotentSameKey(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 7)
	id1, err := s.EnqueueDelivery(7, "https://example.com/hook", "down", `{"x":1}`, 8)
	if err != nil {
		t.Fatalf("首次入队失败: %v", err)
	}
	id2, err := s.EnqueueDelivery(7, "https://example.com/hook", "down", `{"x":1}`, 8)
	if err != nil {
		t.Fatalf("二次入队失败: %v", err)
	}
	if id1 != id2 {
		t.Fatalf("幂等期望同一 id，实际 %d 与 %d", id1, id2)
	}
	rows, err := s.ListDeliveries("pending", 7, 100)
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("期望只保留 1 行，实际 %d", len(rows))
	}
	counts, err := s.CountDeliveriesByStatus()
	if err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if counts["pending"] != 1 {
		t.Fatalf("pending 计数期望 1 实际 %d", counts["pending"])
	}
}

func TestEnqueueDeliveryIdempotentAfterRetryStatus(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 11)
	id, err := s.EnqueueDelivery(11, "https://example.com/hook", "down", `{"y":2}`, 4)
	if err != nil {
		t.Fatalf("入队失败: %v", err)
	}
	if err := s.MarkDeliveryAttempt(id, "2000-01-01T00:00:00Z", "timeout"); err != nil {
		t.Fatalf("标记尝试失败: %v", err)
	}
	again, err := s.EnqueueDelivery(11, "https://example.com/hook", "down", `{"y":2}`, 4)
	if err != nil {
		t.Fatalf("重试态入队失败: %v", err)
	}
	if again != id {
		t.Fatalf("retrying 状态应复用 id %d，实际 %d", id, again)
	}
	got, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if got.Status != "retrying" {
		t.Fatalf("状态期望 retrying 实际 %q", got.Status)
	}
	if got.Attempt != 1 {
		t.Fatalf("attempt 期望 1 实际 %d", got.Attempt)
	}
	if got.LastError != "timeout" {
		t.Fatalf("last_error 期望 timeout 实际 %q", got.LastError)
	}
}

func TestEnqueueDeliveryDifferentKeyInsertsNew(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 22)
	id1, err := s.EnqueueDelivery(21, "https://example.com/a", "down", `{"k":1}`, 8)
	if err != nil {
		t.Fatalf("入队 1 失败: %v", err)
	}
	id2, err := s.EnqueueDelivery(21, "https://example.com/a", "down", `{"k":2}`, 8)
	if err != nil {
		t.Fatalf("入队 2 失败: %v", err)
	}
	id3, err := s.EnqueueDelivery(22, "https://example.com/a", "down", `{"k":1}`, 8)
	if err != nil {
		t.Fatalf("入队 3 失败: %v", err)
	}
	if id1 == id2 || id1 == id3 || id2 == id3 {
		t.Fatalf("不同键应产生不同 id: %d %d %d", id1, id2, id3)
	}
	rows, err := s.ListDeliveries("", 0, 100)
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(rows) != 3 {
		t.Fatalf("期望 3 行，实际 %d", len(rows))
	}
}

func TestMarkDeliveryDoneAndNotFound(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 31)
	id, err := s.EnqueueDelivery(31, "https://example.com/done", "up", `{"z":3}`, 8)
	if err != nil {
		t.Fatalf("入队失败: %v", err)
	}
	if err := s.MarkDeliveryDone(id); err != nil {
		t.Fatalf("标记完成失败: %v", err)
	}
	got, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if got.Status != "done" {
		t.Fatalf("状态期望 done 实际 %q", got.Status)
	}
	if got.UpdatedAt == "" {
		t.Fatalf("updated_at 不应为空")
	}
	err = s.MarkDeliveryDone(999999)
	if err != sql.ErrNoRows {
		t.Fatalf("不存在的 id 期望 sql.ErrNoRows，实际 %v", err)
	}
}

func TestMarkDeliveryAttemptAndFailed(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 41)
	id, err := s.EnqueueDelivery(41, "https://example.com/fail", "down", `{"q":4}`, 3)
	if err != nil {
		t.Fatalf("入队失败: %v", err)
	}
	if err := s.MarkDeliveryAttempt(id, "2000-01-01T00:00:00Z", "connection refused"); err != nil {
		t.Fatalf("标记尝试失败: %v", err)
	}
	mid, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if mid.Attempt != 1 {
		t.Fatalf("attempt 期望 1 实际 %d", mid.Attempt)
	}
	if mid.Status != "retrying" {
		t.Fatalf("状态期望 retrying 实际 %q", mid.Status)
	}
	if mid.LastError != "connection refused" {
		t.Fatalf("last_error 期望 connection refused 实际 %q", mid.LastError)
	}
	if !mid.NextRetryAt.Valid || mid.NextRetryAt.String != "2000-01-01T00:00:00Z" {
		t.Fatalf("next_retry_at 期望 2000-01-01T00:00:00Z 实际 %+v", mid.NextRetryAt)
	}

	if err := s.MarkDeliveryFailed(id, "no route to host"); err != nil {
		t.Fatalf("标记最终失败失败: %v", err)
	}
	fin, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if fin.Status != "failed" {
		t.Fatalf("状态期望 failed 实际 %q", fin.Status)
	}
	if fin.Attempt != 2 {
		t.Fatalf("最终失败后 attempt 期望 2 实际 %d", fin.Attempt)
	}
	if fin.LastError != "no route to host" {
		t.Fatalf("last_error 期望 no route to host 实际 %q", fin.LastError)
	}

	if err := s.MarkDeliveryFailed(888888, "x"); err != sql.ErrNoRows {
		t.Fatalf("不存在 id 期望 sql.ErrNoRows，实际 %v", err)
	}
	if err := s.MarkDeliveryAttempt(888888, "now", "x"); err != sql.ErrNoRows {
		t.Fatalf("不存在 id 期望 sql.ErrNoRows，实际 %v", err)
	}
}

func TestRetryDeliveryStatusRules(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 51)
	id, err := s.EnqueueDelivery(51, "https://example.com/retry", "down", `{"r":5}`, 3)
	if err != nil {
		t.Fatalf("入队失败: %v", err)
	}
	err = s.RetryDelivery(id)
	if err != errInvalidDeliveryStatus {
		t.Fatalf("pending 状态手动重试期望 errInvalidDeliveryStatus，实际 %v", err)
	}

	if err := s.MarkDeliveryAttempt(id, "2000-01-01T00:00:00Z", "boom"); err != nil {
		t.Fatalf("标记尝试失败: %v", err)
	}
	if err := s.RetryDelivery(id); err != nil {
		t.Fatalf("retrying 状态重试失败: %v", err)
	}
	got, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if got.Status != "pending" {
		t.Fatalf("状态期望 pending 实际 %q", got.Status)
	}
	if got.Attempt != 0 {
		t.Fatalf("attempt 期望重置 0 实际 %d", got.Attempt)
	}
	if got.LastError != "" {
		t.Fatalf("last_error 期望清空 实际 %q", got.LastError)
	}

	if err := s.MarkDeliveryFailed(id, "dead"); err != nil {
		t.Fatalf("标记失败失败: %v", err)
	}
	if err := s.RetryDelivery(id); err != nil {
		t.Fatalf("failed 状态重试失败: %v", err)
	}
	again, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if again.Status != "pending" {
		t.Fatalf("状态期望 pending 实际 %q", again.Status)
	}
	if again.Attempt != 0 {
		t.Fatalf("attempt 期望 0 实际 %d", again.Attempt)
	}
	if err := s.RetryDelivery(777777); err != sql.ErrNoRows {
		t.Fatalf("不存在 id 期望 sql.ErrNoRows，实际 %v", err)
	}
}

func TestClaimDueDeliveriesBoundaryAndOrder(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 99)
	base := "2020-01-01T00:00:00Z"
	later := "2030-01-01T00:00:00Z"
	ids := make([]int64, 0, 3)
	for i := 0; i < 3; i++ {
		id, err := s.EnqueueDelivery(int64(60+i), "https://example.com/c", "down", `{"i":`+string(rune('0'+i))+`}`, 3)
		if err != nil {
			t.Fatalf("入队失败: %v", err)
		}
		if err := s.MarkDeliveryAttempt(id, base, "e"); err != nil {
			t.Fatalf("标记尝试失败: %v", err)
		}
		ids = append(ids, id)
	}
	future, err := s.EnqueueDelivery(99, "https://example.com/future", "down", `{"f":1}`, 3)
	if err != nil {
		t.Fatalf("入队失败: %v", err)
	}
	if err := s.MarkDeliveryAttempt(future, later, "e"); err != nil {
		t.Fatalf("标记尝试失败: %v", err)
	}

	got, err := s.ClaimDueDeliveries("2021-01-01T00:00:00Z", 0)
	if err != nil {
		t.Fatalf("捞取失败: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("limit<=0 应钳到 1，期望 1 行，实际 %d", len(got))
	}
	if got[0].NextRetryAt.String > "2021-01-01T00:00:00Z" {
		t.Fatalf("不应捞到未到期记录: %+v", got[0])
	}

	all, err := s.ClaimDueDeliveries("2031-01-01T00:00:00Z", 5000)
	if err != nil {
		t.Fatalf("捞取失败: %v", err)
	}
	if len(all) != 4 {
		t.Fatalf("期望 4 行，实际 %d", len(all))
	}
	for i := 1; i < len(all); i++ {
		if all[i-1].NextRetryAt.String > all[i].NextRetryAt.String {
			t.Fatalf("未按 next_retry_at 升序: %q > %q", all[i-1].NextRetryAt.String, all[i].NextRetryAt.String)
		}
	}
}

func TestListDeliveriesFilterAndClamp(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 80)
	for i := 0; i < 5; i++ {
		if _, err := s.EnqueueDelivery(int64(70+i), "https://example.com/l", "down", `{"n":`+string(rune('0'+i))+`}`, 3); err != nil {
			t.Fatalf("入队失败: %v", err)
		}
	}
	done, err := s.EnqueueDelivery(80, "https://example.com/l", "up", `{"d":1}`, 3)
	if err != nil {
		t.Fatalf("入队失败: %v", err)
	}
	if err := s.MarkDeliveryDone(done); err != nil {
		t.Fatalf("标记完成失败: %v", err)
	}

	zero, err := s.ListDeliveries("", 0, 0)
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(zero) != 1 {
		t.Fatalf("limit<=0 应钳到 1，实际 %d", len(zero))
	}

	pending, err := s.ListDeliveries("pending", 0, 100)
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(pending) != 5 {
		t.Fatalf("pending 期望 5 行，实际 %d", len(pending))
	}
	for i := 1; i < len(pending); i++ {
		if pending[i-1].ID < pending[i].ID {
			t.Fatalf("未按 id 降序: %d < %d", pending[i-1].ID, pending[i].ID)
		}
	}

	one, err := s.ListDeliveries("", 71, 100)
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(one) != 1 {
		t.Fatalf("按 monitor 过滤期望 1 行，实际 %d", len(one))
	}
	if one[0].MonitorID != 71 {
		t.Fatalf("monitor_id 期望 71 实际 %d", one[0].MonitorID)
	}

	doneList, err := s.ListDeliveries("done", 0, 100)
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(doneList) != 1 {
		t.Fatalf("done 期望 1 行，实际 %d", len(doneList))
	}
	if doneList[0].ID != done {
		t.Fatalf("done 行 id 期望 %d 实际 %d", done, doneList[0].ID)
	}
}


func TestEnqueueDeliveryConcurrentSameKey(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 101)
	const goroutines = 16
	var wg sync.WaitGroup
	ids := make([]int64, goroutines)
	errs := make([]error, goroutines)
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func(idx int) {
			defer wg.Done()
			id, err := s.EnqueueDelivery(101, "https://example.com/concurrent", "down", `{"same":true}`, 5)
			ids[idx] = id
			errs[idx] = err
		}(i)
	}
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Fatalf("goroutine %d 入队失败: %v", i, err)
		}
		if ids[i] <= 0 {
			t.Fatalf("goroutine %d 返回非法 id: %d", i, ids[i])
		}
		if ids[i] != ids[0] {
			t.Fatalf("并发幂等期望同一 id，实际 %d 与 %d", ids[0], ids[i])
		}
	}
	rows, err := s.ListDeliveries("pending", 101, 100)
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("并发同键期望 1 行，实际 %d", len(rows))
	}
}

func TestMarkDeliveryAttemptConcurrentDistinctRows(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 212)
	const rows = 12
	ids := make([]int64, rows)
	for i := 0; i < rows; i++ {
		id, err := s.EnqueueDelivery(int64(200+i), "https://example.com/multi", "down", `{"m":`+string(rune('0'+i%10))+string(rune('a'+i/10))+`}`, 4)
		if err != nil {
			t.Fatalf("入队失败: %v", err)
		}
		ids[i] = id
	}

	var wg sync.WaitGroup
	errs := make([]error, rows)
	wg.Add(rows)
	for i := 0; i < rows; i++ {
		go func(idx int) {
			defer wg.Done()
			errs[idx] = s.MarkDeliveryAttempt(ids[idx], "2000-01-01T00:00:00Z", "concurrent")
		}(i)
	}
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Fatalf("goroutine %d 标记失败: %v", i, err)
		}
	}
	for i := 0; i < rows; i++ {
		got, err := s.GetDelivery(ids[i])
		if err != nil {
			t.Fatalf("查询 %d 失败: %v", ids[i], err)
		}
		if got.Attempt != 1 {
			t.Fatalf("行 %d attempt 期望 1 实际 %d", ids[i], got.Attempt)
		}
		if got.Status != "retrying" {
			t.Fatalf("行 %d 状态期望 retrying 实际 %q", ids[i], got.Status)
		}
		if got.LastError != "concurrent" {
			t.Fatalf("行 %d last_error 期望 concurrent 实际 %q", ids[i], got.LastError)
		}
	}
	counts, err := s.CountDeliveriesByStatus()
	if err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if counts["retrying"] != rows {
		t.Fatalf("retrying 期望 %d 实际 %d", rows, counts["retrying"])
	}
	if counts["pending"] != 0 {
		t.Fatalf("pending 期望 0 实际 %d", counts["pending"])
	}
}

func TestClaimDueDeliveriesConcurrentNoDuplicateOverlap(t *testing.T) {
	s := openTestStore(t)

	seedMonitors(t, s, 320)
	const total = 20
	for i := 0; i < total; i++ {
		id, err := s.EnqueueDelivery(int64(300+i), "https://example.com/claim", "down", `{"c":`+string(rune('a'+i%26))+string(rune('0'+i/26))+`}`, 3)
		if err != nil {
			t.Fatalf("入队失败: %v", err)
		}
		if err := s.MarkDeliveryAttempt(id, "2000-01-01T00:00:00Z", "e"); err != nil {
			t.Fatalf("标记尝试失败: %v", err)
		}
	}

	var wg sync.WaitGroup
	mu := sync.Mutex{}
	seen := make(map[int64]int)
	workerCount := 4
	wg.Add(workerCount)
	for w := 0; w < workerCount; w++ {
		go func() {
			defer wg.Done()
			got, err := s.ClaimDueDeliveries("2001-01-01T00:00:00Z", 1000)
			if err != nil {
				t.Errorf("捞取失败: %v", err)
				return
			}
			mu.Lock()
			for _, d := range got {
				seen[d.ID]++
			}
			mu.Unlock()
		}()
	}
	wg.Wait()

	if len(seen) != total {
		t.Fatalf("期望看到 %d 个不同 id，实际 %d", total, len(seen))
	}
	for id, n := range seen {
		if n != workerCount {
			t.Fatalf("id %d 应被每个 worker 看到一次，实际 %d", id, n)
		}
	}
	again, err := s.ClaimDueDeliveries("2001-01-01T00:00:00Z", 1000)
	if err != nil {
		t.Fatalf("再次捞取失败: %v", err)
	}
	if len(again) != total {
		t.Fatalf("再次捞取期望 %d 行，实际 %d", total, len(again))
	}
	start := time.Now()
	if time.Since(start) > 5*time.Second {
		t.Fatalf("捞取耗时过长")
	}
}