package api

import (
	"net/http"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

type overdueReviewItem struct {
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

func registerReviewOverdueRoutes(mux *http.ServeMux, st *store.Store) {
	mux.HandleFunc("GET /api/review/overdue", func(w http.ResponseWriter, r *http.Request) {
		limit := parseIntDefault(r.URL.Query().Get("limit"), 50)
		if limit <= 0 {
			limit = 50
		}
		if limit > 200 {
			limit = 200
		}
		reviews, err := st.ListOverdueReviews(time.Now(), limit, CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		ids := make([]int64, 0, len(reviews))
		for _, it := range reviews {
			ids = append(ids, it.Note.ID)
		}
		hard := map[int64]bool{}
		if marks, err := st.HardMarkMap(ids, CurrentUser(r)); err == nil {
			hard = marks
		}
		items := make([]overdueReviewItem, 0, len(reviews))
		for _, it := range reviews {
			items = append(items, overdueReviewItem{
				ID:           it.Note.ID,
				Title:        it.Note.Title,
				Body:         it.Note.Body,
				Snippet:      snippetOf(it.Note.Body, 120),
				Tags:         it.Note.Tags,
				DueDate:      it.DueDate,
				OverdueDays:  it.OverdueDays,
				EF:           it.EF,
				IntervalDays: it.IntervalDays,
				Repetitions:  it.Repetitions,
				Hard:         hard[it.Note.ID],
			})
		}
		writeJSON(w, http.StatusOK, items)
	})

	mux.HandleFunc("POST /api/review/overdue", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
	})
}
