package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"sentinel/internal/store"
)

// GenerateAndStoreSnapshot 生成状态页快照并存入归档
func (s *Server) GenerateAndStoreSnapshot(pageID int64, generator string) (int64, error) {
	page, err := s.store.GetStatusPage(pageID)
	if err != nil {
		return 0, fmt.Errorf("获取状态页失败: %w", err)
	}
	monitors, err := s.store.ListPageMonitors(pageID)
	if err != nil {
		return 0, fmt.Errorf("获取监控列表失败: %w", err)
	}
	items := buildPublishItems(s.store, monitors)
	html := renderSnapshotHTML(page, items)
	id, err := s.store.CreateStatusSnapshot(pageID, generator, page.Theme, html)
	if err != nil {
		return 0, fmt.Errorf("创建快照失败: %w", err)
	}
	return id, nil
}

// handleCreateSnapshot 处理 POST /api/status-pages/{id}/snapshots，生成并归档快照
func (s *Server) handleCreateSnapshot(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	if _, err := s.store.GetStatusPage(id); err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	snapID, err := s.GenerateAndStoreSnapshot(id, "manual")
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成快照失败")
		return
	}
	snap, err := s.store.GetStatusSnapshot(snapID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成快照失败")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]interface{}{
		"id":         snap.ID,
		"created_at": snap.CreatedAt,
		"size_bytes": snap.SizeBytes,
	})
}

// handleListSnapshots 处理 GET /api/status-pages/{id}/snapshots，返回快照归档列表
func (s *Server) handleListSnapshots(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	_, err := s.store.GetStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		n, e := strconv.Atoi(v)
		if e != nil || n < 1 || n > 200 {
			writeErr(w, http.StatusBadRequest, "limit 参数非法")
			return
		}
		limit = n
	}
	snaps, err := s.store.ListStatusSnapshots(id, limit)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "获取快照列表失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"items": snaps,
		"total": len(snaps),
	})
}

// handleGetSnapshot 处理 GET /api/status-pages/{id}/snapshots/{sid}，下载指定归档快照
func (s *Server) handleGetSnapshot(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	sid, ok := parsePathID(r, "sid")
	if !ok {
		return
	}
	snap, err := s.store.GetStatusSnapshot(sid)
	if err != nil {
		writeErr(w, http.StatusNotFound, "快照不存在")
		return
	}
	if snap.PageID != id {
		writeErr(w, http.StatusNotFound, "快照不存在")
		return
	}
	dateStr := time.Now().UTC().Format("20060102")
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="snapshot-%d-%d-%s.html"`, id, sid, dateStr))
	w.Write([]byte(snap.HTML))
}

// handleDeleteSnapshot 处理 DELETE /api/status-pages/{id}/snapshots/{sid}，删除归档快照
func (s *Server) handleDeleteSnapshot(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	sid, ok := parsePathID(r, "sid")
	if !ok {
		return
	}
	snap, err := s.store.GetStatusSnapshot(sid)
	if err != nil {
		writeErr(w, http.StatusNotFound, "快照不存在")
		return
	}
	if snap.PageID != id {
		writeErr(w, http.StatusNotFound, "快照不存在")
		return
	}
	if err := s.store.DeleteStatusSnapshot(sid); err != nil {
		writeErr(w, http.StatusInternalServerError, "删除快照失败")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// handleUpdateSnapshotSchedule 处理 PUT /api/status-pages/{id}/snapshot-schedule，设置快照定时计划
func (s *Server) handleUpdateSnapshotSchedule(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	_, err := s.store.GetStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	var body struct {
		Schedule string `json:"schedule"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "请求体非法")
		return
	}
	if !store.ValidSnapshotSchedule(body.Schedule) {
		writeErr(w, http.StatusBadRequest, "schedule 非法，仅支持 off/daily/hourly")
		return
	}
	if err := s.store.UpdateStatusPageSnapshotSchedule(id, body.Schedule); err != nil {
		writeErr(w, http.StatusInternalServerError, "更新快照计划失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"snapshot_schedule": body.Schedule,
	})
}
