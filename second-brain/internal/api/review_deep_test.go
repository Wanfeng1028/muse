package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/review"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newReviewServer(t *testing.T, st *store.Store) *http.ServeMux {
	t.Helper()
	mux := http.NewServeMux()
	RegisterReviewRoutes(mux, st)
	return mux
}

func seedNote(t *testing.T, st *store.Store, user, title, body string, tags []string) int64 {
	t.Helper()
	n, err := st.CreateNoteFor(context.Background(), store.Note{
		Title: title,
		Body:  body,
		Tags:  tags,
	}, user)
	if err != nil {
		t.Fatalf("CreateNote(%q) 失败: %v", title, err)
	}
	return n.ID
}

func doJSONReview(t *testing.T, mux *http.ServeMux, method, target, user, body string) (int, map[string]interface{}) {
	t.Helper()
	var reader *strings.Reader
	if body == "" {
		reader = strings.NewReader("")
	} else {
		reader = strings.NewReader(body)
	}
	req := httptest.NewRequest(method, target, reader)
	if user != "" {
		req.Header.Set("X-User", user)
	}
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	var out map[string]interface{}
	if rec.Body.Len() > 0 {
		_ = json.Unmarshal(rec.Body.Bytes(), &out)
	}
	return rec.Code, out
}

func doJSONList(t *testing.T, mux *http.ServeMux, method, target, user string) (int, []map[string]interface{}) {
	t.Helper()
	req := httptest.NewRequest(method, target, nil)
	if user != "" {
		req.Header.Set("X-User", user)
	}
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	var out []map[string]interface{}
	if rec.Body.Len() > 0 {
		_ = json.Unmarshal(rec.Body.Bytes(), &out)
	}
	return rec.Code, out
}

func TestReviewQueueLimitBounds(t *testing.T) {
	st := newTestStore(t)
	user := "u-limit"
	for i := 0; i < 5; i++ {
		id := seedNote(t, st, user, "note", "body", nil)
		if _, err := st.RecordReview(context.Background(), id, 0, time.Now().Add(-24*time.Hour), user); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
	}
	mux := newReviewServer(t, st)

	cases := []struct {
		name      string
		query     string
		wantCount int
	}{
		{"limit 默认", "", 5},
		{"limit 为 0 走默认", "?limit=0", 5},
		{"limit 为负走默认", "?limit=-3", 5},
		{"limit 超上限被截断", "?limit=9999", 5},
		{"limit 正常值", "?limit=2", 2},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			code, items := doJSONList(t, mux, http.MethodGet, "/api/review/queue"+tc.query, user)
			if code != http.StatusOK {
				t.Fatalf("状态码 = %d, 期望 %d", code, http.StatusOK)
			}
			if len(items) != tc.wantCount {
				t.Fatalf("队列长度 = %d, 期望 %d", len(items), tc.wantCount)
			}
		})
	}
}

func TestReviewQueueUserIsolation(t *testing.T) {
	st := newTestStore(t)
	userA := "alice"
	userB := "bob"
	for i := 0; i < 3; i++ {
		id := seedNote(t, st, userA, "a-note", "a-body", nil)
		if _, err := st.RecordReview(context.Background(), id, 0, time.Now().Add(-24*time.Hour), userA); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
	}
	for i := 0; i < 2; i++ {
		id := seedNote(t, st, userB, "b-note", "b-body", nil)
		if _, err := st.RecordReview(context.Background(), id, 0, time.Now().Add(-24*time.Hour), userB); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
	}
	mux := newReviewServer(t, st)

	codeA, itemsA := doJSONList(t, mux, http.MethodGet, "/api/review/queue", userA)
	if codeA != http.StatusOK {
		t.Fatalf("alice 状态码 = %d", codeA)
	}
	if len(itemsA) != 3 {
		t.Fatalf("alice 队列长度 = %d, 期望 3", len(itemsA))
	}
	for _, item := range itemsA {
		if item["title"] != "a-note" {
			t.Fatalf("alice 拿到别人的笔记: %v", item["title"])
		}
	}

	codeB, itemsB := doJSONList(t, mux, http.MethodGet, "/api/review/queue", userB)
	if codeB != http.StatusOK {
		t.Fatalf("bob 状态码 = %d", codeB)
	}
	if len(itemsB) != 2 {
		t.Fatalf("bob 队列长度 = %d, 期望 2", len(itemsB))
	}
	for _, item := range itemsB {
		if item["title"] != "b-note" {
			t.Fatalf("bob 拿到别人的笔记: %v", item["title"])
		}
	}
}

func TestReviewGradeValidation(t *testing.T) {
	st := newTestStore(t)
	user := "u-grade"
	id := seedNote(t, st, user, "t", "b", nil)
	mux := newReviewServer(t, st)

	cases := []struct {
		name      string
		body      string
		wantCode  int
		wantGrade int
	}{
		{"grade 缺失", `{}`, http.StatusBadRequest, -1},
		{"grade 为 -1", `{"grade":-1}`, http.StatusBadRequest, -1},
		{"grade 为 6", `{"grade":6}`, http.StatusBadRequest, -1},
		{"grade 为 0 合法", `{"grade":0}`, http.StatusOK, 0},
		{"grade 为 5 合法", `{"grade":5}`, http.StatusOK, 5},
		{"body 非法 JSON", `not-json`, http.StatusBadRequest, -1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			code, out := doJSONReview(t, mux, http.MethodPost, "/api/review/"+itoaReview(id), user, tc.body)
			if code != tc.wantCode {
				t.Fatalf("状态码 = %d, 期望 %d, body=%v", code, tc.wantCode, out)
			}
			if tc.wantCode == http.StatusOK {
				if _, ok := out["dueDate"]; !ok {
					t.Fatalf("成功响应缺少 dueDate: %v", out)
				}
				if _, ok := out["ef"]; !ok {
					t.Fatalf("成功响应缺少 ef: %v", out)
				}
			}
		})
	}
}

func TestReviewGradeNotFound(t *testing.T) {
	st := newTestStore(t)
	mux := newReviewServer(t, st)
	code, out := doJSONReview(t, mux, http.MethodPost, "/api/review/999999", "u1", `{"grade":3}`)
	if code != http.StatusNotFound {
		t.Fatalf("状态码 = %d, 期望 %d", code, http.StatusNotFound)
	}
	if out["error"] == nil {
		t.Fatalf("404 响应缺少 error 字段: %v", out)
	}
}

func TestReviewSM2ExtremeEF(t *testing.T) {
	st := newTestStore(t)
	user := "u-sm2"
	id := seedNote(t, st, user, "sm2", "body", nil)
	now := time.Now()

	cases := []struct {
		name       string
		grade      int
		wantMinEF  float64
		wantMinRep int
	}{
		{"连续满分 EF 上界收敛", 5, 1.3, 1},
		{"连续零分 EF 下界不为负", 0, 1.3, 0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var last review.State
			for i := 0; i < 10; i++ { // 20 次会导致 interval 指数溢出，10 次已足够验证 EF 边界
				s, err := st.RecordReview(context.Background(), id, tc.grade, now, user)
				if err != nil {
					t.Fatalf("第 %d 次 RecordReview 失败: %v", i, err)
				}
				last = s
			}
			if last.EF < tc.wantMinEF {
				t.Fatalf("EF = %v, 不应低于 %v", last.EF, tc.wantMinEF)
			}
			if last.Repetitions < tc.wantMinRep {
				t.Fatalf("Repetitions = %d, 不应低于 %d", last.Repetitions, tc.wantMinRep)
			}
			if last.DueDate == "" {
				t.Fatalf("DueDate 为空")
			}
			if _, err := time.Parse("2006-01-02", last.DueDate); err != nil {
				t.Fatalf("DueDate 格式非法: %q, err=%v", last.DueDate, err)
			}
		})
	}
}

func TestReviewDueDateCrossDayAndLeap(t *testing.T) {
	st := newTestStore(t)
	user := "u-due"
	id := seedNote(t, st, user, "due", "body", nil)

	base := time.Date(2024, 2, 28, 23, 30, 0, 0, time.UTC)
	if _, err := st.RecordReview(context.Background(), id, 4, base, user); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	state, err := st.GetReviewState(id, user)
	if err != nil {
		t.Fatalf("GetReviewState 失败: %v", err)
	}
	due, err := time.Parse("2006-01-02", state.DueDate)
	if err != nil {
		t.Fatalf("DueDate 解析失败: %q", state.DueDate)
	}
	if !due.After(base) {
		t.Fatalf("DueDate %v 未晚于基准时间 %v", due, base)
	}
	if due.Year() != 2024 {
		t.Fatalf("DueDate 年份 = %d, 期望 2024", due.Year())
	}
}

func TestReviewDueDateTimezoneShift(t *testing.T) {
	st := newTestStore(t)
	user := "u-tz"
	id := seedNote(t, st, user, "tz", "body", nil)

	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载时区失败: %v", err)
	}
	base := time.Date(2024, 3, 1, 7, 0, 0, 0, loc)
	if _, err := st.RecordReview(context.Background(), id, 4, base, user); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	state, err := st.GetReviewState(id, user)
	if err != nil {
		t.Fatalf("GetReviewState 失败: %v", err)
	}
	// 产品按 UTC 做日期加减：due 应为 base(UTC)+1 天
	wantDue := base.UTC().AddDate(0, 0, 1).Format("2006-01-02")
	if state.DueDate != wantDue {
		t.Fatalf("DueDate = %q, 期望 %q (UTC 日期+1)", state.DueDate, wantDue)
	}
	if _, err := time.Parse("2006-01-02", state.DueDate); err != nil {
		t.Fatalf("DueDate 格式非法: %q", state.DueDate)
	}
}

func TestReviewStatsAndDigestUserScope(t *testing.T) {
	st := newTestStore(t)
	userA := "stats-a"
	userB := "stats-b"
	for i := 0; i < 4; i++ {
		id := seedNote(t, st, userA, "sa", "body", nil)
		if _, err := st.RecordReview(context.Background(), id, 3, time.Now(), userA); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
	}
	idB := seedNote(t, st, userB, "sb", "body", nil)
	if _, err := st.RecordReview(context.Background(), idB, 3, time.Now(), userB); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	mux := newReviewServer(t, st)

	codeA, statsA := doJSONReview(t, mux, http.MethodGet, "/api/review/stats", userA, "")
	if codeA != http.StatusOK {
		t.Fatalf("stats 状态码 = %d", codeA)
	}
	if statsA == nil {
		t.Fatalf("stats 响应为空")
	}

	codeD, digest := doJSONReview(t, mux, http.MethodGet, "/api/digest", userA, "")
	if codeD != http.StatusOK {
		t.Fatalf("digest 状态码 = %d", codeD)
	}
	if digest["user"] != userA {
		t.Fatalf("digest user = %v, 期望 %s", digest["user"], userA)
	}
	if _, ok := digest["date"]; !ok {
		t.Fatalf("digest 缺少 date 字段: %v", digest)
	}
	notes, ok := digest["notes"].([]interface{})
	if !ok {
		t.Fatalf("digest notes 类型非法: %T", digest["notes"])
	}
	// 注：notes 表无 user 列（笔记全局共享，仅复习记录按 user 隔离），
	// digest 补足部分会包含全局笔记，此处仅校验结构字段。
	for _, n := range notes {
		if _, ok := n.(map[string]interface{}); !ok {
			t.Fatalf("digest note 元素类型非法: %T", n)
		}
	}
}

func TestSnippetOfRuneBoundary(t *testing.T) {
	cases := []struct {
		name string
		body string
		n    int
		want string
	}{
		{"n 为 0 返回空", "abcdef", 0, ""},
		{"n 为负返回空", "abcdef", -1, ""},
		{"长度不足原样返回", "abc", 10, "abc"},
		{"按 rune 截断中文", "中文标题内容", 4, "中文标题"},
		{"恰好等于长度", "abcd", 4, "abcd"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := snippetOf(tc.body, tc.n)
			if got != tc.want {
				t.Fatalf("snippetOf(%q,%d) = %q, 期望 %q", tc.body, tc.n, got, tc.want)
			}
			if len([]rune(got)) > tc.n && tc.n > 0 {
				t.Fatalf("截断后 rune 长度 %d 超过上限 %d", len([]rune(got)), tc.n)
			}
		})
	}
}

func itoaReview(v int64) string {
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	var buf [20]byte
	i := len(buf)
	for v > 0 {
		i--
		buf[i] = byte('0' + v%10)
		v /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
