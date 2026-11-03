package handlers

import (
	"encoding/json"
	"net/http"

	"sentinel/internal/store"
)

type groupPayload struct {
	Name string `json:"name"`
}

type groupView struct {
	ID           int64  `json:"id"`
	Name         string `json:"name"`
	CreatedAt    string `json:"created_at"`
	MonitorCount int    `json:"monitor_count"`
}

func groupToView(g store.MonitorGroup) groupView {
	return groupView{
		ID:           g.ID,
		Name:         g.Name,
		CreatedAt:    g.CreatedAt,
		MonitorCount: g.MonitorCount,
	}
}

func (s *Server) handleCreateGroup(w http.ResponseWriter, r *http.Request) {
	var p groupPayload
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		writeErr(w, http.StatusBadRequest, "请求体不是合法 JSON")
		return
	}

	id, err := s.store.CreateGroup(p.Name)
	if err != nil {
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "name": p.Name})
}

func (s *Server) handleListGroups(w http.ResponseWriter, r *http.Request) {
	list, err := s.store.ListGroups()
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "读取分组列表失败")
		return
	}
	items := make([]groupView, 0, len(list))
	for _, g := range list {
		items = append(items, groupToView(g))
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) handleDeleteGroup(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	if err := s.store.DeleteGroup(id); err != nil {
		writeErr(w, http.StatusInternalServerError, "删除分组失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (s *Server) handleAddGroupMonitor(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	var body struct {
		MonitorID int64 `json:"monitor_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "请求体不是合法 JSON")
		return
	}
	if err := s.store.AddMonitorToGroup(id, body.MonitorID); err != nil {
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (s *Server) handleRemoveGroupMonitor(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	mid, ok2 := parsePathID(r, "mid")
	if !ok2 {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	if err := s.store.RemoveMonitorFromGroup(id, mid); err != nil {
		writeErr(w, http.StatusInternalServerError, "移出分组失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (s *Server) handleListGroupMonitors(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	list, err := s.store.ListGroupMonitors(id)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "读取分组监控失败")
		return
	}
	items := make([]map[string]any, 0, len(list))
	for _, m := range list {
		items = append(items, map[string]any{
			"id":     m.ID,
			"name":   m.Name,
			"target": m.Target,
			"kind":   m.Kind,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) handleGroupsPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "groups.html", "text/html; charset=utf-8")
}
