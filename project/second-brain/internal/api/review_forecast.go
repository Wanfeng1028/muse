package api

import (
	"net/http"
	"strconv"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func registerReviewForecastRoutes(mux *http.ServeMux, st *store.Store) {
	mux.HandleFunc("GET /api/review/forecast", func(w http.ResponseWriter, r *http.Request) {
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
		if days > 30 {
			days = 30
		}
		forecast, err := st.ReviewForecast(time.Now(), CurrentUser(r), days)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, forecast)
	})

	mux.HandleFunc("POST /api/review/forecast", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
	})
}
