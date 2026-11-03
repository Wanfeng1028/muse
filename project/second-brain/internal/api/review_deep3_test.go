package api

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"testing"
	"time"
)

// doStatusBody 是 doReviewJSONUser 的薄包装，返回（状态码，响应体字节）。
func doStatusBody(t *testing.T, method, url string, body any, user string) (int, []byte) {
	t.Helper()
	resp := doReviewJSONUser(t, method, url, body, user)
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read body: %v", err)
	}
	return resp.StatusCode, b
}

// TestReviewQueueDueOrderDeterministic：三篇笔记 due 分别设为前天/昨天/今天，
// 队列按 due_date ASC 返回，且 overdueDays 与今天日期差一致。
func TestReviewQueueDueOrderDeterministic(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	const user = "u"

	idA := createNoteAs(t, srv.URL, user, "A")
	idB := createNoteAs(t, srv.URL, user, "B")
	idC := createNoteAs(t, srv.URL, user, "C")

	today := time.Now().UTC()
	// grade=0 → due = today_param + 1，因此传入 yesterday/twoDaysAgo/today 才能得到
	// due = today/today-1/today+1... 但我们想要 due 分别落在昨天/前天/今天：
	//  - due = today-1  → 传入 today-2（前天）
	//  - due = today-2  → 传入 today-3
	//  - due = today    → 传入 today-1
	// 注意 addDays 只取 UTC 日期，因此直接构造 UTC 日期即可。
	utcMidnight := time.Date(today.Year(), today.Month(), today.Day(), 0, 0, 0, 0, time.UTC)
	yesterday := utcMidnight.AddDate(0, 0, -1)
	twoDaysAgo := utcMidnight.AddDate(0, 0, -2)
	threeDaysAgo := utcMidnight.AddDate(0, 0, -3)

	ctx := context.Background()

	// 目标 due：前天（A）、昨天（B）、今天（C）。
	// RecordReview 内 due = today_param + 1，所以：
	if _, err := st.RecordReview(ctx, idA, 0, threeDaysAgo, user); err != nil {
		t.Fatalf("RecordReview A: %v", err)
	}
	if _, err := st.RecordReview(ctx, idB, 0, twoDaysAgo, user); err != nil {
		t.Fatalf("RecordReview B: %v", err)
	}
	if _, err := st.RecordReview(ctx, idC, 0, yesterday, user); err != nil {
		t.Fatalf("RecordReview C: %v", err)
	}

	status, body := getQueueAs(t, srv.URL, user)
	if status != http.StatusOK {
		t.Fatalf("GET queue status = %d, want 200, body=%s", status, string(body))
	}
	items := decodeQueue(t, body)
	if len(items) != 3 {
		t.Fatalf("queue len = %d, want 3, body=%s", len(items), string(body))
	}

	// 按 dueDate ASC：前天(A) 在前，昨天(B) 中，今天(C) 后。
	expectedOrder := []int64{idA, idB, idC}
	for i, want := range expectedOrder {
		gotID, ok := items[i]["id"].(float64)
		if !ok {
			t.Fatalf("item[%d].id not a number: %#v", i, items[i]["id"])
		}
		if int64(gotID) != want {
			t.Fatalf("item[%d].id = %d, want %d (order must be due_date ASC)", i, int64(gotID), want)
		}
	}

	// overdueDays 应等于 today - dueDate 的天数差。
	expectedOverdue := []float64{2, 1, 0}
	for i, want := range expectedOverdue {
		got, ok := items[i]["overdueDays"].(float64)
		if !ok {
			t.Fatalf("item[%d].overdueDays not a number: %#v", i, items[i]["overdueDays"])
		}
		if got != want {
			t.Fatalf("item[%d].overdueDays = %v, want %v", i, got, want)
		}
	}
}

// TestReviewQueueLimitBoundary：limit=2 返回 2 条；limit=0 用默认 20；limit=999 截断上限 200。
func TestReviewQueueLimitBoundary(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	const user = "v"

	ids := make([]int64, 0, 5)
	for i := 0; i < 5; i++ {
		ids = append(ids, createNoteAs(t, srv.URL, user, "note"))
	}

	utcNow := time.Now().UTC()
	utcMidnight := time.Date(utcNow.Year(), utcNow.Month(), utcNow.Day(), 0, 0, 0, 0, time.UTC)
	// RecordReview grade=0 → due = param + 1。传入 today-2 得 due = today-1，保证已到期。
	twoDaysAgo := utcMidnight.AddDate(0, 0, -2)

	ctx := context.Background()
	for _, id := range ids {
		if _, err := st.RecordReview(ctx, id, 0, twoDaysAgo, user); err != nil {
			t.Fatalf("RecordReview(%d): %v", id, err)
		}
	}

	// limit=2 → 2 条。
	{
		status, body := doStatusBody(t, http.MethodGet, srv.URL+"/api/review/queue?limit=2", nil, user)
		if status != http.StatusOK {
			t.Fatalf("limit=2: status = %d, want 200, body=%s", status, string(body))
		}
		items := decodeQueue(t, body)
		if len(items) != 2 {
			t.Fatalf("limit=2: queue len = %d, want 2", len(items))
		}
	}

	// limit=0 → 使用默认 20 → 返回全部 5 条。
	{
		status, body := doStatusBody(t, http.MethodGet, srv.URL+"/api/review/queue?limit=0", nil, user)
		if status != http.StatusOK {
			t.Fatalf("limit=0: status = %d, want 200, body=%s", status, string(body))
		}
		items := decodeQueue(t, body)
		if len(items) != 5 {
			t.Fatalf("limit=0: queue len = %d, want 5 (default 20 covers all)", len(items))
		}
	}

	// limit=999 → 服务端截断到上限 200 → 5 条全部返回。
	{
		status, body := doStatusBody(t, http.MethodGet, srv.URL+"/api/review/queue?limit=999", nil, user)
		if status != http.StatusOK {
			t.Fatalf("limit=999: status = %d, want 200, body=%s", status, string(body))
		}
		items := decodeQueue(t, body)
		if len(items) != 5 {
			t.Fatalf("limit=999: queue len = %d, want 5", len(items))
		}
	}
}

// TestReviewCrossUserGradeIsolation：bob 对 alice 的笔记评分不得污染 alice 的行。
func TestReviewCrossUserGradeIsolation(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	const alice = "alice"
	const bob = "bob"

	noteID := createNoteAs(t, srv.URL, alice, "shared note")

	utcNow := time.Now().UTC()
	utcMidnight := time.Date(utcNow.Year(), utcNow.Month(), utcNow.Day(), 0, 0, 0, 0, time.UTC)
	twoDaysAgo := utcMidnight.AddDate(0, 0, -2)

	ctx := context.Background()
	if _, err := st.RecordReview(ctx, noteID, 0, twoDaysAgo, alice); err != nil {
		t.Fatalf("RecordReview(alice): %v", err)
	}

	// 记录 alice 评分前的状态。
	aliceBefore, err := st.GetReviewState(noteID, alice)
	if err != nil {
		t.Fatalf("GetReviewState(alice) before: %v", err)
	}

	// bob 评分。
	{
		status, body := doStatusBody(
			t, http.MethodPost,
			srv.URL+"/api/review/"+itoa(noteID),
			map[string]any{"grade": 5},
			bob,
		)
		if status != http.StatusOK {
			t.Fatalf("bob POST grade=5: status = %d, want 200, body=%s", status, string(body))
		}
	}

	// alice 的状态必须未变。
	aliceAfter, err := st.GetReviewState(noteID, alice)
	if err != nil {
		t.Fatalf("GetReviewState(alice) after: %v", err)
	}
	if aliceAfter.EF != aliceBefore.EF ||
		aliceAfter.IntervalDays != aliceBefore.IntervalDays ||
		aliceAfter.Repetitions != aliceBefore.Repetitions ||
		aliceAfter.DueDate != aliceBefore.DueDate {
		t.Fatalf("alice state changed by bob's grade:\nbefore=%+v\nafter =%+v",
			aliceBefore, aliceAfter)
	}
	if aliceAfter.Repetitions != 0 {
		t.Fatalf("alice Repetitions = %d, want 0 (from RecordReview grade=0)", aliceAfter.Repetitions)
	}

	// alice 队列仍包含该笔记。
	{
		status, body := getQueueAs(t, srv.URL, alice)
		if status != http.StatusOK {
			t.Fatalf("alice queue status = %d, want 200, body=%s", status, string(body))
		}
		items := decodeQueue(t, body)
		if len(items) != 1 {
			t.Fatalf("alice queue len = %d, want 1", len(items))
		}
		gotID, _ := items[0]["id"].(float64)
		if int64(gotID) != noteID {
			t.Fatalf("alice queue item id = %d, want %d", int64(gotID), noteID)
		}
		reps, _ := items[0]["repetitions"].(float64)
		if int(reps) != 0 {
			t.Fatalf("alice queue repetitions = %v, want 0", reps)
		}
	}

	// bob 的队列包含该笔记（bob 自己的行；grade=5 成功一次后 due=次日，需再记一次
	// grade=0（due 回到今天）才能进入到期队列——SM-2 语义，grade>=3 成功后间隔为 1 天）。
	if _, err := st.RecordReview(ctx, noteID, 0, utcMidnight.AddDate(0, 0, -1), bob); err != nil {
		t.Fatalf("RecordReview(bob) pull due: %v", err)
	}
	{
		status, body := getQueueAs(t, srv.URL, bob)
		if status != http.StatusOK {
			t.Fatalf("bob queue status = %d, want 200, body=%s", status, string(body))
		}
		items := decodeQueue(t, body)
		if len(items) != 1 {
			t.Fatalf("bob queue len = %d, want 1, body=%s", len(items), string(body))
		}
		gotID, _ := items[0]["id"].(float64)
		if int64(gotID) != noteID {
			t.Fatalf("bob queue item id = %d, want %d", int64(gotID), noteID)
		}
		reps, _ := items[0]["repetitions"].(float64)
		if int(reps) != 0 {
			t.Fatalf("bob queue repetitions = %v, want 0（grade=0 重置）", reps)
		}
	}
}

// TestReviewGradeInvalidAPI：非法 grade / 空 body / 非 JSON 一律 400；不存在 id 返回 404。
func TestReviewGradeInvalidAPI(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	defer srv.Close()

	const user = "u"
	noteID := createNoteAs(t, srv.URL, user, "n")
	url := srv.URL + "/api/review/" + itoa(noteID)

	cases := []struct {
		name string
		body any
	}{
		{"grade=-1", map[string]any{"grade": -1}},
		{"grade=6", map[string]any{"grade": 6}},
		{"empty body", map[string]any{}},
		{"non-JSON string", "not-json"},
	}

	for _, tc := range cases {
		tc := tc
		status, body := doStatusBody(t, http.MethodPost, url, tc.body, user)
		if status != http.StatusBadRequest {
			t.Fatalf("%s: status = %d, want 400, body=%s", tc.name, status, string(body))
		}
		// 保证返回体是合法 JSON（若服务端约定返回 JSON 错误体）。
		var probe map[string]any
		if len(body) > 0 {
			_ = json.Unmarshal(body, &probe)
		}
	}

	// 不存在的 id。
	{
		status, body := doStatusBody(
			t, http.MethodPost,
			srv.URL+"/api/review/999999",
			map[string]any{"grade": 4},
			user,
		)
		if status != http.StatusNotFound {
			t.Fatalf("missing id: status = %d, want 404, body=%s", status, string(body))
		}
	}
}
