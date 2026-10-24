package api

import (
	"net/http"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func registerReviewForecastRoutes(mux *http.ServeMux, st *store.Store) {
	mux.HandleFunc("GET /api/review/forecast", func(w http.ResponseWriter, r *http.Request) {
		days := parseIntDefault(r.URL.Query().Get("days"), 7)
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
