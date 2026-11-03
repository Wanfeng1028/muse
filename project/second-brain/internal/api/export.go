package api

import (
	"archive/zip"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode"

	logpkg "github.com/Wanfeng1028/muse/second-brain/internal/log"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// exportPageSize 是导出时分页拉取笔记的每页大小。
const exportPageSize = 500

// sanitizeZipName 将字符串消毒为可安全用作 zip 条目名的片段：
// 只保留 unicode 字母与数字，其他字符转为 '-'，连续 '-' 合并，
// 去掉首尾 '-'，按 rune 截断到 60，为空返回 "note"。
func sanitizeZipName(s string) string {
	var b strings.Builder
	prevDash := false
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			b.WriteRune(r)
			prevDash = false
			continue
		}
		if !prevDash {
			b.WriteRune('-')
			prevDash = true
		}
	}
	out := strings.Trim(b.String(), "-")
	runes := []rune(out)
	if len(runes) > 60 {
		runes = runes[:60]
	}
	out = string(runes)
	out = strings.Trim(out, "-")
	if out == "" {
		return "note"
	}
	return out
}

// yamlQuote 用双引号包裹字符串，并转义其中的反斜杠与双引号。
func yamlQuote(s string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '\\':
			b.WriteString(`\\`)
		case '"':
			b.WriteString(`\"`)
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte('"')
	return b.String()
}

// exportFileName 生成带时间戳的导出文件名。
func exportFileName(base, ext string) string {
	return "second-brain-export-" + time.Now().Format("20060102T150405") + ext
}

// attachmentRefRe 匹配正文中的 attachment:123 引用。
var attachmentRefRe = regexp.MustCompile(`attachment:(\d+)`)

// exportNote 是 JSON 导出中单条笔记的结构。
type exportNote struct {
	ID          int64              `json:"id"`
	Title       string             `json:"title"`
	Body        string             `json:"body"`
	Tags        []string           `json:"tags"`
	Pinned      bool               `json:"pinned"`
	CreatedAt   string             `json:"createdAt"`
	UpdatedAt   string             `json:"updatedAt"`
	Attachments []store.Attachment `json:"attachments"`
}

// exportDoc 是 JSON 导出的顶层结构。
type exportDoc struct {
	Version    string       `json:"version"`
	ExportedAt string       `json:"exportedAt"`
	Notes      []exportNote `json:"notes"`
}

// handleExportJSON 处理 GET /api/export/json。
func handleExportJSON(st *store.Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		notes, err := collectAllNotes(st)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}

		doc := exportDoc{
			Version:    "0.3.0",
			ExportedAt: time.Now().Format(time.RFC3339),
			Notes:      notes,
		}

		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, exportFileName("", ".json")))
		w.WriteHeader(http.StatusOK)
		enc := json.NewEncoder(w)
		if err := enc.Encode(doc); err != nil {
			logpkg.RequestLogger(r.Context()).Error("export.json.encode_failed", "error", err)
		}
	}
}

// collectAllNotes 分页拉取全部笔记，并附上附件元数据。
func collectAllNotes(st *store.Store) ([]exportNote, error) {
	var out []exportNote
	offset := 0
	for {
		page, err := st.ListNotes("", exportPageSize, offset)
		if err != nil {
			return nil, err
		}
		for _, n := range page {
			atts, err := st.ListAttachments(n.ID)
			if err != nil {
				return nil, err
			}
			if atts == nil {
				atts = []store.Attachment{}
			}
			tags := n.Tags
			if tags == nil {
				tags = []string{}
			}
			out = append(out, exportNote{
				ID:          n.ID,
				Title:       n.Title,
				Body:        n.Body,
				Tags:        tags,
				Pinned:      n.Pinned,
				CreatedAt:   n.CreatedAt,
				UpdatedAt:   n.UpdatedAt,
				Attachments: atts,
			})
		}
		if len(page) < exportPageSize {
			break
		}
		offset += exportPageSize
	}
	if out == nil {
		out = []exportNote{}
	}
	return out, nil
}

// handleExportMarkdown 处理 GET /api/export/markdown，以流式方式输出 zip。
//
// 注意：由于响应是边生成边写出的，一旦开始写 body 就无法再改变状态码。
// 若中途读库或读文件失败，只能记录日志并中断写出，已发送的部分无法撤回。
func handleExportMarkdown(st *store.Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		notes, err := collectAllNotes(st)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}

		w.Header().Set("Content-Type", "application/zip")
		w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, exportFileName("", ".zip")))
		w.WriteHeader(http.StatusOK)

		zw := zip.NewWriter(w)
		now := time.Now()

		// index.md
		var idx strings.Builder
		idx.WriteString("# 第二大脑导出\n\n")
		idx.WriteString("导出时间：" + now.Format(time.RFC3339) + "\n\n")
		for i, n := range notes {
			entry := noteEntryName(i+1, n.ID, n.Title)
			idx.WriteString(fmt.Sprintf("- [%s](notes/%s)\n", n.Title, entry))
		}
		if err := writeZipEntry(zw, "index.md", []byte(idx.String()), now); err != nil {
			logpkg.RequestLogger(r.Context()).Error("export.markdown.write_index_failed", "error", err)
			return
		}

		for i, n := range notes {
			entry := noteEntryName(i+1, n.ID, n.Title)
			zipPath := "notes/" + entry

			// 建立 attachmentID -> zip 条目名 映射，同时写出附件。
			attMap := map[int64]string{}
			for _, a := range n.Attachments {
				storedName := filepath.Base(a.StoredName)
				attEntry := fmt.Sprintf("attachments/%d-%s", n.ID, storedName)
				attMap[a.ID] = attEntry

				full := st.AttachmentPath(a)
				data, rerr := os.ReadFile(full)
				if rerr != nil {
					logpkg.RequestLogger(r.Context()).Error("export.markdown.read_attachment_failed", "attachment_id", a.ID, "error", rerr)
					continue
				}
				if err := writeZipEntry(zw, attEntry, data, now); err != nil {
					logpkg.RequestLogger(r.Context()).Error("export.markdown.write_attachment_failed", "entry", attEntry, "error", err)
					return
				}
			}

			body := rewriteAttachmentRefs(n.Body, attMap)
			content := buildNoteMarkdown(n, body)
			if err := writeZipEntry(zw, zipPath, []byte(content), now); err != nil {
				logpkg.RequestLogger(r.Context()).Error("export.markdown.write_note_failed", "entry", zipPath, "error", err)
				return
			}
		}

		if err := zw.Close(); err != nil {
			logpkg.RequestLogger(r.Context()).Error("export.markdown.close_zip_failed", "error", err)
		}
	}
}

// noteEntryName 构造笔记在 zip 中的条目名（不含 notes/ 前缀）。
func noteEntryName(seq int, id int64, title string) string {
	return fmt.Sprintf("%04d-%d-%s.md", seq, id, sanitizeZipName(title))
}

// buildNoteMarkdown 组装单条笔记的 Markdown 内容。
func buildNoteMarkdown(n exportNote, body string) string {
	var b strings.Builder
	b.WriteString("---\n")
	b.WriteString("title: " + yamlQuote(n.Title) + "\n")
	if len(n.Tags) == 0 {
		b.WriteString("tags: []\n")
	} else {
		quoted := make([]string, 0, len(n.Tags))
		for _, t := range n.Tags {
			quoted = append(quoted, yamlQuote(t))
		}
		b.WriteString("tags: [" + strings.Join(quoted, ", ") + "]\n")
	}
	b.WriteString("created: " + yamlQuote(n.CreatedAt) + "\n")
	b.WriteString("updated: " + yamlQuote(n.UpdatedAt) + "\n")
	b.WriteString("---\n\n")
	b.WriteString(body)
	return b.String()
}

// rewriteAttachmentRefs 将正文中的 attachment:ID 引用改写为相对 notes/ 目录的路径。
// 找不到映射的引用保持原样。
func rewriteAttachmentRefs(body string, attMap map[int64]string) string {
	return attachmentRefRe.ReplaceAllStringFunc(body, func(m string) string {
		sub := attachmentRefRe.FindStringSubmatch(m)
		if len(sub) != 2 {
			return m
		}
		id, err := strconv.ParseInt(sub[1], 10, 64)
		if err != nil {
			return m
		}
		entry, ok := attMap[id]
		if !ok {
			return m
		}
		return "../" + entry
	})
}

// writeZipEntry 写出一个 zip 条目；条目名包含 ".." 时跳过并记录日志。
func writeZipEntry(zw *zip.Writer, name string, data []byte, mod time.Time) error {
	if strings.Contains(name, "..") || filepath.IsAbs(name) {
		slog.Warn("export.markdown.skip_unsafe_entry", "entry", name)
		return nil
	}
	hdr := &zip.FileHeader{
		Name:     name,
		Method:   zip.Deflate,
		Modified: mod,
	}
	fw, err := zw.CreateHeader(hdr)
	if err != nil {
		return err
	}
	_, err = fw.Write(data)
	return err
}

// RegisterExportRoutes 注册导出相关路由。
func RegisterExportRoutes(mux *http.ServeMux, st *store.Store) {
	mux.HandleFunc("GET /api/export/json", handleExportJSON(st))
	mux.HandleFunc("GET /api/export/markdown", handleExportMarkdown(st))
}
