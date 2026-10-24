package api

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// streakResponse 连续复习接口响应结构
type streakResponse struct {
	CurrentStreak    int    `json:"currentStreak"`
	LongestStreak    int    `json:"longestStreak"`
	TotalDays        int    `json:"totalDays"`
	LastReviewedDate string `json:"lastReviewedDate"`
}

func TestReviewStreakAPI_Empty(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/streak", nil)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望 200，得到 %d", resp.StatusCode)
	}

	var got streakResponse
	decodeReviewJSON(t, resp, &got)

	if got.CurrentStreak != 0 || got.LongestStreak != 0 || got.TotalDays != 0 {
		t.Errorf("期望全 0，得到 %+v", got)
	}
	if got.LastReviewedDate != "" {
		t.Errorf("期望空字符串，得到 %s", got.LastReviewedDate)
	}
}

func TestReviewStreakAPI_Data(t *testing.T) {
	srv, st := newReviewTestServer(t)
	today := time.Now()
	dates := []time.Time{
		today.AddDate(0, 0, -2),
		today.AddDate(0, 0, -1),
		today,
	}

	// 建3个笔记并在不同日期评分
	for _, d := range dates {
		note, err := st.CreateNote(store.Note{Title: "X", Body: "x"})
		if err != nil {
			t.Fatalf("创建笔记失败: %v", err)
		}
		if _, err := st.RecordReview(context.Background(), note.ID, 4, d, store.DefaultUser); err != nil {
			t.Fatalf("记录复习失败: %v", err)
		}
	}

	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/streak", nil)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望 200，得到 %d", resp.StatusCode)
	}

	var got streakResponse
	decodeReviewJSON(t, resp, &got)

	if got.TotalDays != 3 || got.LongestStreak != 3 || got.CurrentStreak != 3 {
		t.Errorf("期望 totalDays=3, longestStreak=3, currentStreak=3，得到 %+v", got)
	}

	if got.LastReviewedDate == "" {
		t.Fatal("lastReviewedDate 不应为空")
	}

	// 防跨日 flaky：允许今天或昨天 UTC
	todayUTC := today.UTC().Format("2006-01-02")
	yesterdayUTC := today.AddDate(0, 0, -1).UTC().Format("2006-01-02")
	if got.LastReviewedDate != todayUTC && got.LastReviewedDate != yesterdayUTC {
		t.Errorf("lastReviewedDate 期望为今天或昨天 UTC，得到 %s", got.LastReviewedDate)
	}
}

func TestReviewStreakAPI_MethodNotAllowed(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	resp := doReviewJSON(t, http.MethodPost, srv.URL+"/api/review/streak", nil)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("期望 405，得到 %d", resp.StatusCode)
	}
}
