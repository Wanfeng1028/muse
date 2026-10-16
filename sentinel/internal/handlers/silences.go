package handlers

import (
	"encoding/json"
	"net/http"

	"sentinel/internal/store"
)

type silencePayload struct {
	MonitorID int64  `json:"monitor_id"`
	NameMatch string `json:"name_match"`
	StartsAt  string `json:"starts_at"`
	EndsAt    string `json:"ends_at"`
	Reason    string `json:"reason"`
}

type silenceView struct {
	ID        int64  `json:"id"`
	MonitorID int64  `json:"monitor_id"`
	NameMatch string `json:"name_match"`
	StartsAt  string `json:"starts_at"`
	EndsAt    string `json:"ends_at"`
	Reason    string `json:"reason"`
	CreatedAt string `json:"created_at"`
}

func silenceToView(sl store.Silence) silenceView {
	return silenceView{
		ID:        sl.ID,
		MonitorID: sl.MonitorID,
		NameMatch: sl.NameMatch,
		StartsAt:  sl.StartsAt,
		EndsAt:    sl.EndsAt,
		Reason:    sl.Reason,
		CreatedAt: sl.CreatedAt,
	}
}

func (s *Server) handleCreateSilence(w http.ResponseWriter, r *http.Request) {
	var p silencePayload
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		writeErr(w, http.StatusBadRequest, "请求体不是合法 JSON")
		return
	}
	if p.MonitorID > 0 {
		if _, err := s.store.GetMonitor(p.MonitorID); err != nil {
			writeErr(w, http.StatusBadRequest, "监控目标不存在")
			return
		}
	}
	id, err := s.store.CreateSilence(store.Silence{
		MonitorID: p.MonitorID,
		NameMatch: p.NameMatch,
		StartsAt:  p.StartsAt,
		EndsAt:    p.EndsAt,
		Reason:    p.Reason,
	})
	if err != nil {
		logErr(r, "handleCreateSilence", err)
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	sl, err := s.store.GetSilence(id)
	if err != nil {
		logErr(r, "handleCreateSilence", err)
		writeErr(w, http.StatusInternalServerError, "创建静默失败")
		return
	}
	writeJSON(w, http.StatusCreated, silenceToView(sl))
}

func (s *Server) handleListSilences(w http.ResponseWriter, r *http.Request) {
	list, err := s.store.ListSilences()
	if err != nil {
		logErr(r, "handleListSilences", err)
		writeErr(w, http.StatusInternalServerError, "读取静默列表失败")
		return
	}
	items := make([]silenceView, 0, len(list))
	for _, sl := range list {
		items = append(items, silenceToView(sl))
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) handleDeleteSilence(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	if _, err := s.store.GetSilence(id); err != nil {
		writeErr(w, http.StatusNotFound, "静默不存在")
		return
	}
	if err := s.store.DeleteSilence(id); err != nil {
		logErr(r, "handleDeleteSilence", err)
		writeErr(w, http.StatusInternalServerError, "删除静默失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}
