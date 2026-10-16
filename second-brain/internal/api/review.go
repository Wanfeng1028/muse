package api

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/review"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// RegisterReviewRoutes 注册复习相关的路由。
func RegisterReviewRoutes(mux *http.ServeMux, st *store.Store) {
	// 获取待复习队列
	mux.HandleFunc("GET /api/review/queue", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		limit := parseIntDefault(r.URL.Query().Get("limit"), 20)
		if limit <= 0 {
			limit = 20
		}
		if limit > 200 {
			limit = 200
		}
		dues, err := st.ListDueReviews(time.Now(), limit, CurrentUser(r))
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		type queueItem struct {
			ID           int64    `json:"id"`
			Title        string   `json:"title"`
			Body         string   `json:"body"`
			Snippet      string   `json:"snippet"`
			Tags         []string `json:"tags"`
			DueDate      string   `json:"dueDate"`
			OverdueDays  int      `json:"overdueDays"`
			EF           float64  `json:"ef"`
			IntervalDays int      `json:"intervalDays"`
			Repetitions  int      `json:"repetitions"`
		}
		items := make([]queueItem, 0, len(dues))
		for _, d := range dues {
			items = append(items, queueItem{
				ID:           d.Note.ID,
				Title:        d.Note.Title,
				Body:         d.Note.Body,
				Snippet:      snippetOf(d.Note.Body, 120),
				Tags:         d.Note.Tags,
				DueDate:      d.DueDate,
				OverdueDays:  d.OverdueDays,
				EF:           d.EF,
				IntervalDays: d.IntervalDays,
				Repetitions:  d.Repetitions,
			})
		}
		writeJSON(w, http.StatusOK, items)
	})

	// 提交一次复习评分
	mux.HandleFunc("POST /api/review/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		var req struct {
			Grade *int `json:"grade"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid body")
			return
		}
		if req.Grade == nil || *req.Grade < 0 || *req.Grade > 5 {
			writeError(w, http.StatusBadRequest, "invalid grade")
			return
		}
		state, err := st.RecordReview(id, *req.Grade, time.Now(), CurrentUser(r))
		if err != nil {
			if err == store.ErrNotFound {
				writeError(w, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		resp := map[string]interface{}{
			"ef":            state.EF,
			"intervalDays":  state.IntervalDays,
			"repetitions":   state.Repetitions,
			"dueDate":       state.DueDate,
			"reviewedCount": 1,
		}
		// 尝试从 GetReviewState 中补充额外信息（此处 reviewedCount 以 1 表示本次）
		if s, err := st.GetReviewState(id, CurrentUser(r)); err == nil {
			_ = s
		}
		writeJSON(w, http.StatusOK, resp)
	})

	// 复习统计
	mux.HandleFunc("GET /api/review/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		stats, err := st.ReviewStats(time.Now(), CurrentUser(r))
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, stats)
	})

	// 今日摘要
	mux.HandleFunc("GET /api/review/digest", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		n := parseIntDefault(r.URL.Query().Get("n"), 5)
		notes, err := st.DigestNotes(time.Now(), n, CurrentUser(r))
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		type digestItem struct {
			ID      int64    `json:"id"`
			Title   string   `json:"title"`
			Snippet string   `json:"snippet"`
			Tags    []string `json:"tags"`
			DueDate string   `json:"dueDate"`
		}
		items := make([]digestItem, 0, len(notes))
		for _, note := range notes {
			dueDate := ""
			if s, err := st.GetReviewState(note.ID, CurrentUser(r)); err == nil {
				dueDate = s.DueDate
			}
			items = append(items, digestItem{
				ID:      note.ID,
				Title:   note.Title,
				Snippet: snippetOf(note.Body, 120),
				Tags:    note.Tags,
				DueDate: dueDate,
			})
		}

		writeJSON(w, http.StatusOK, map[string]interface{}{"notes": items})
	})

	// 按用户摘要（v0.9）：与 /api/review/digest 同数据源，显式返回 user 与 date
	mux.HandleFunc("GET /api/digest", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		user := CurrentUser(r)
		n := parseIntDefault(r.URL.Query().Get("n"), 5)
		if n <= 0 {
			n = 5
		}
		if n > 200 {
			n = 200
		}
		notes, err := st.DigestNotes(time.Now(), n, user)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		type digestItem struct {
			ID      int64    `json:"id"`
			Title   string   `json:"title"`
			Snippet string   `json:"snippet"`
			Tags    []string `json:"tags"`
			DueDate string   `json:"dueDate"`
		}
		items := make([]digestItem, 0, len(notes))
		for _, note := range notes {
			dueDate := ""
			if s, err := st.GetReviewState(note.ID, user); err == nil {
				dueDate = s.DueDate
			}
			items = append(items, digestItem{
				ID:      note.ID,
				Title:   note.Title,
				Snippet: snippetOf(note.Body, 120),
				Tags:    note.Tags,
				DueDate: dueDate,
			})
		}
		if items == nil {
			items = []digestItem{}
		}
		writeJSON(w, http.StatusOK, map[string]interface{}{
			"user":  user,
			"date":  time.Now().Format("2006-01-02"),
			"notes": items,
		})
	})
}

// snippetOf 按 rune 截取正文前 n 个字符。
func snippetOf(body string, n int) string {
	if n <= 0 {
		return ""
	}
	runes := []rune(body)
	if len(runes) <= n {
		return body
	}
	return string(runes[:n])
}

// 避免未使用 review 包导入
var _ = review.GradeForgot
