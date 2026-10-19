package handlers

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"sentinel/internal/store"
)

type publishManifest struct {
	Slug         string `json:"slug"`
	Version      string `json:"version"`
	PublishedAt  string `json:"published_at"`
	MonitorCount int    `json:"monitor_count"`
}

func (s *Server) SetPublishDir(dir string) {
	s.publishDir = strings.TrimSpace(dir)
}

func (s *Server) publishRoot() string {
	if s.publishDir != "" {
		return s.publishDir
	}
	return "data/published"
}

func buildPublishItems(st *store.Store, monitors []store.Monitor) []snapshotItem {
	items := make([]snapshotItem, 0, len(monitors))
	for _, m := range monitors {
		it := snapshotItem{
			Name:        m.Name,
			Status:      "unknown",
			LastChecked: "无数据",
			LatencyMs:   0,
		}
		if lc, err := st.LastCheck(m.ID); err == nil && lc != nil {
			if lc.Ok == 1 {
				it.Status = "up"
			} else {
				it.Status = "down"
			}
			it.LastChecked = lc.CheckedAt
			it.LatencyMs = lc.LatencyMs
		}
		if up, _, _, _, err := st.MonitorStats(m.ID, 30); err == nil {
			it.Uptime30 = up
		} else {
			it.Uptime30 = 100
		}
		if daily, err := st.DailyBreakdown(m.ID, 90); err == nil {
			it.Daily = daily
		}
		items = append(items, it)
	}
	return items
}

func (s *Server) PublishStatusPage(pageID int64) (string, error) {
	page, err := s.store.GetStatusPage(pageID)
	if err != nil {
		return "", err
	}
	monitors, err := s.store.ListPageMonitors(pageID)
	if err != nil {
		return "", err
	}
	items := buildPublishItems(s.store, monitors)
	html := renderSnapshotHTML(page, items)

	dir := filepath.Join(s.publishRoot(), page.Slug)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	histDir := filepath.Join(dir, "history")
	if err := os.MkdirAll(histDir, 0o755); err != nil {
		return "", err
	}

	prevVersion := "prev"
	if b, err := os.ReadFile(filepath.Join(dir, "manifest.json")); err == nil {
		var prev publishManifest
		if json.Unmarshal(b, &prev) == nil && prev.Version != "" {
			prevVersion = prev.Version
		}
	}

	indexPath := filepath.Join(dir, "index.html")
	if _, err := os.Stat(indexPath); err == nil {
		if b, err := os.ReadFile(indexPath); err == nil {
			archive := filepath.Join(histDir, "index-"+prevVersion+".html")
			if err := os.WriteFile(archive, b, 0o644); err != nil {
				return "", err
			}
		}
		if err := pruneHistory(histDir, 10); err != nil {
			return "", err
		}
	}

	tmp, err := os.CreateTemp(dir, "index-*.tmp")
	if err != nil {
		return "", err
	}
	tmpName := tmp.Name()
	if _, err := tmp.WriteString(html); err != nil {
		tmp.Close()
		os.Remove(tmpName)
		return "", err
	}
	if err := tmp.Close(); err != nil {
		os.Remove(tmpName)
		return "", err
	}
	if err := os.Chmod(tmpName, 0o644); err != nil {
		os.Remove(tmpName)
		return "", err
	}
	if err := os.Rename(tmpName, indexPath); err != nil {
		os.Remove(tmpName)
		return "", err
	}

	now := time.Now().UTC()
	version := now.Format("20060102T150405")
	manifest := publishManifest{
		Slug:         page.Slug,
		Version:      version,
		PublishedAt:  now.Format(time.RFC3339),
		MonitorCount: len(monitors),
	}
	mb, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), mb, 0o644); err != nil {
		return "", err
	}
	return version, nil
}

func (s *Server) RollbackStatusPage(pageID int64) (string, error) {
	page, err := s.store.GetStatusPage(pageID)
	if err != nil {
		return "", err
	}
	dir := filepath.Join(s.publishRoot(), page.Slug)
	histDir := filepath.Join(dir, "history")

	entries, err := os.ReadDir(histDir)
	if err != nil {
		return "", errors.New("无可回滚版本")
	}
	var versions []string
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasPrefix(name, "index-") || !strings.HasSuffix(name, ".html") {
			continue
		}
		v := strings.TrimSuffix(strings.TrimPrefix(name, "index-"), ".html")
		if v == "" {
			continue
		}
		versions = append(versions, v)
	}
	if len(versions) == 0 {
		return "", errors.New("无可回滚版本")
	}
	sort.Strings(versions)
	restored := versions[len(versions)-1]

	src := filepath.Join(histDir, "index-"+restored+".html")
	b, err := os.ReadFile(src)
	if err != nil {
		return "", err
	}

	tmp, err := os.CreateTemp(dir, "index-*.tmp")
	if err != nil {
		return "", err
	}
	tmpName := tmp.Name()
	if _, err := tmp.Write(b); err != nil {
		tmp.Close()
		os.Remove(tmpName)
		return "", err
	}
	if err := tmp.Close(); err != nil {
		os.Remove(tmpName)
		return "", err
	}
	if err := os.Chmod(tmpName, 0o644); err != nil {
		os.Remove(tmpName)
		return "", err
	}
	if err := os.Rename(tmpName, filepath.Join(dir, "index.html")); err != nil {
		os.Remove(tmpName)
		return "", err
	}

	monitors, err := s.store.ListPageMonitors(pageID)
	if err != nil {
		return "", err
	}
	now := time.Now().UTC()
	manifest := publishManifest{
		Slug:         page.Slug,
		Version:      restored + "-rollback",
		PublishedAt:  now.Format(time.RFC3339),
		MonitorCount: len(monitors),
	}
	mb, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), mb, 0o644); err != nil {
		return "", err
	}
	return restored, nil
}

func pruneHistory(histDir string, keep int) error {
	entries, err := os.ReadDir(histDir)
	if err != nil {
		return err
	}
	var versions []string
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasPrefix(name, "index-") || !strings.HasSuffix(name, ".html") {
			continue
		}
		v := strings.TrimSuffix(strings.TrimPrefix(name, "index-"), ".html")
		if v == "" {
			continue
		}
		versions = append(versions, v)
	}
	if len(versions) <= keep {
		return nil
	}
	sort.Strings(versions)
	for _, v := range versions[:len(versions)-keep] {
		if err := os.Remove(filepath.Join(histDir, "index-"+v+".html")); err != nil {
			return err
		}
	}
	return nil
}

func (s *Server) handlePublishStatusPage(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	if _, err := s.store.GetStatusPage(id); err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	version, err := s.PublishStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err.Error())
		return
	}
	page, err := s.store.GetStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err.Error())
		return
	}
	dir := filepath.Join(s.publishRoot(), page.Slug)
	abs, err := filepath.Abs(dir)
	if err != nil {
		abs = dir
	}
	monitors, _ := s.store.ListPageMonitors(id)
	writeJSON(w, http.StatusOK, map[string]any{
		"slug":          page.Slug,
		"version":       version,
		"path":          abs,
		"monitor_count": len(monitors),
	})
}

func (s *Server) handlePublishRollback(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	page, err := s.store.GetStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	restored, err := s.RollbackStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusNotFound, "无可回滚版本")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"slug":             page.Slug,
		"restored_version": restored,
	})
}

func (s *Server) handlePublishInfo(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	page, err := s.store.GetStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	dir := filepath.Join(s.publishRoot(), page.Slug)
	b, err := os.ReadFile(filepath.Join(dir, "manifest.json"))
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"published": false,
			"slug":      page.Slug,
		})
		return
	}
	var m publishManifest
	if json.Unmarshal(b, &m) != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"published": false,
			"slug":      page.Slug,
		})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"published":     true,
		"slug":          page.Slug,
		"version":       m.Version,
		"published_at":  m.PublishedAt,
		"monitor_count": m.MonitorCount,
	})
}
