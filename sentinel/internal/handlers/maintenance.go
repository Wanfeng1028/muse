package handlers

import (
	"encoding/json"
	"net/http"

	"sentinel/internal/store"
)

type maintenancePayload struct {
	MonitorID int64  `json:"monitor_id"`
	Title     string `json:"title"`
	StartsAt  string `json:"starts_at"`
	EndsAt    string `json:"ends_at"`
}

type maintenanceView struct {
	ID        int64  `json:"id"`
	MonitorID int64  `json:"monitor_id"`
	Title     string `json:"title"`
	StartsAt  string `json:"starts_at"`
	EndsAt    string `json:"ends_at"`
	CreatedAt string `json:"created_at"`
}

func maintenanceToView(mw store.MaintenanceWindow) maintenanceView {
	return maintenanceView{
		ID:        mw.ID,
		MonitorID: mw.MonitorID,
		Title:     mw.Title,
		StartsAt:  mw.StartsAt,
		EndsAt:    mw.EndsAt,
		CreatedAt: mw.CreatedAt,
	}
}

func (s *Server) handleCreateMaintenanceWindow(w http.ResponseWriter, r *http.Request) {
	var p maintenancePayload
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
	id, err := s.store.CreateMaintenanceWindow(store.MaintenanceWindow{
		MonitorID: p.MonitorID,
		Title:     p.Title,
		StartsAt:  p.StartsAt,
		EndsAt:    p.EndsAt,
	})
	if err != nil {
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"id":         id,
		"monitor_id": p.MonitorID,
		"title":      p.Title,
		"starts_at":  p.StartsAt,
		"ends_at":    p.EndsAt,
	})
}

func (s *Server) handleListMaintenanceWindows(w http.ResponseWriter, r *http.Request) {
	list, err := s.store.ListMaintenanceWindows()
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "读取维护窗口列表失败")
		return
	}
	items := make([]maintenanceView, 0, len(list))
	for _, mw := range list {
		items = append(items, maintenanceToView(mw))
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) handleDeleteMaintenanceWindow(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	if err := s.store.DeleteMaintenanceWindow(id); err != nil {
		writeErr(w, http.StatusInternalServerError, "删除维护窗口失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}
func (s *Server) handleMaintenancePage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "maintenance.html", "text/html; charset=utf-8")
}
