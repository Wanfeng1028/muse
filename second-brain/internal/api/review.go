package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"time"

	logpkg "github.com/Wanfeng1028/muse/second-brain/internal/log"
	"github.com/Wanfeng1028/muse/second-brain/internal/metrics"
	"github.com/Wanfeng1028/muse/second-brain/internal/review"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// RegisterReviewRoutes 注册复习相关的路由。
func RegisterReviewRoutes(mux *http.ServeMux, st *store.Store) {
	registerReviewHealthRoutes(mux, st)
	registerReviewStreakRoutes(mux, st)
	registerReviewForecastRoutes(mux, st)
	registerReviewOverdueRoutes(mux, st)

	// 获取待复习队列
	mux.HandleFunc("GET /api/review/queue", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		rawLimit := r.URL.Query().Get("limit")
		limit := 20
		if rawLimit != "" {
			parsed, err := strconv.Atoi(rawLimit)
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "limit 参数非法")
				return
			}
			limit = parsed
		}
		if limit <= 0 {
			limit = 20
		}
		if limit > 200 {
			limit = 200
		}
		dues, err := st.ListDueReviews(time.Now(), limit, CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
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
			Hard         bool     `json:"hard"`
		}
		// 批量查询困难标记；查询失败则降级为全部 hard=false，不阻断队列返回。
		ids := make([]int64, 0, len(dues))
		for _, d := range dues {
			ids = append(ids, d.Note.ID)
		}
		hardMap, hardErr := st.HardMarkMap(ids, CurrentUser(r))
		if hardErr != nil {
			hardMap = nil
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
				Hard:         hardMap[d.Note.ID],
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
			writeError(w, r, http.StatusBadRequest, "invalid body")
			return
		}
		if req.Grade == nil || *req.Grade < 0 || *req.Grade > 5 {
			writeError(w, r, http.StatusBadRequest, "invalid grade")
			return
		}
		state, err := st.RecordReview(r.Context(), id, *req.Grade, time.Now(), CurrentUser(r))
		if err != nil {
			if err == store.ErrNotFound {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		// 按 grade 维度记录复习评分计数
		metrics.Default().IncReviewGraded(*req.Grade)
		logpkg.RequestLogger(r.Context()).Info("review.graded",
			"note_id", id, "grade", *req.Grade, "user", CurrentUser(r),
			"next_due", state.DueDate)
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

	// 标记/取消标记困难卡片
	// 路由说明：Go 1.22+ ServeMux 中 "POST /api/review/{id}/hard" 比 "POST /api/review/{id}" 更具体，
	// 优先匹配，二者无冲突。
	mux.HandleFunc("POST /api/review/{id}/hard", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		var req struct {
			Hard *bool `json:"hard"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, r, http.StatusBadRequest, "invalid body")
			return
		}
		if req.Hard == nil {
			writeError(w, r, http.StatusBadRequest, "invalid body")
			return
		}
		if err := st.SetHardMark(id, CurrentUser(r), *req.Hard); err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, "internal error")
			return
		}
		writeJSON(w, http.StatusOK, map[string]interface{}{
			"id":   id,
			"hard": *req.Hard,
		})
	})

	// 复习统计
	mux.HandleFunc("GET /api/review/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		stats, err := st.ReviewStats(time.Now(), CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, stats)
	})

	// 复习趋势（最近 days 天，默认 7，上限 60）
	mux.HandleFunc("GET /api/review/trend", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		rawDays := r.URL.Query().Get("days")
		days := 7
		if rawDays != "" {
			parsed, err := strconv.Atoi(rawDays)
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "days 参数非法")
				return
			}
			days = parsed
		}
		if days <= 0 {
			days = 7
		}
		if days > 60 {
			days = 60
		}
		trend, err := st.ReviewTrend(time.Now(), CurrentUser(r), days)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"days":  days,
			"trend": trend,
		})
	})

	// 复习热力图（年度贡献图数据源，默认 365 天、上限 366 天）
	mux.HandleFunc("GET /api/review/heatmap", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		rawDays := r.URL.Query().Get("days")
		days := 365
		if rawDays != "" {
			parsedDays, err := strconv.Atoi(rawDays)
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "days 参数非法")
				return
			}
			days = parsedDays
		}
		if days <= 0 {
			days = 365
		}
		if days > 366 {
			days = 366
		}
		heatmap, err := st.ReviewHeatmap(time.Now(), CurrentUser(r), days)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"days":    days,
			"heatmap": heatmap,
		})
	})

	// 各科掌握度（按标签聚合）
	mux.HandleFunc("GET /api/review/mastery", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		mastery, err := st.ReviewMastery(time.Now(), CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"mastery": mastery,
		})
	})

	// 今日摘要
	mux.HandleFunc("GET /api/review/digest", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		n := 5
		if s := r.URL.Query().Get("n"); s != "" {
			v, err := strconv.Atoi(s)
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "n 参数非法")
				return
			}
			n = v
		}
		if n <= 0 {
			n = 5
		} else if n > 200 {
			n = 200
		}
		notes, err := st.DigestNotes(time.Now(), n, CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
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
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		user := CurrentUser(r)
		n := 5
		if rawN := r.URL.Query().Get("n"); rawN != "" {
			parsedN, err := strconv.Atoi(rawN)
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "n 参数非法")
				return
			}
			n = parsedN
		}
		if n <= 0 {
			n = 5
		}
		if n > 200 {
			n = 200
		}
		notes, err := st.DigestNotes(time.Now(), n, user)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
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
