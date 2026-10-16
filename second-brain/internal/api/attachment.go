package api

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// attachAllowedExt 附件允许的扩展名白名单（小写）。
var attachAllowedExt = map[string]bool{
	".png":  true,
	".jpg":  true,
	".jpeg": true,
	".gif":  true,
	".webp": true,
	".pdf":  true,
	".md":   true,
	".txt":  true,
	".csv":  true,
	".mp3":  true,
	".wav":  true,
	".m4a":  true,
}

// attachImageExt 图片类扩展名，需要与嗅探结果一致。
var attachImageExt = map[string]bool{
	".png":  true,
	".jpg":  true,
	".jpeg": true,
	".gif":  true,
	".webp": true,
}

// attachMaxBytes 返回上传大小硬上限（字节）。
func attachMaxBytes() int64 {
	mb := int64(10)
	if v := strings.TrimSpace(os.Getenv("SB_ATTACH_MAX_MB")); v != "" {
		if n, err := strconv.ParseInt(v, 10, 64); err == nil && n > 0 {
			mb = n
		}
	}
	return mb << 20
}

// sanitizeFilename 消毒客户端文件名，防路径穿越。
func sanitizeFilename(name string) string {
	name = filepath.Base(name)
	name = strings.TrimSpace(name)
	var b strings.Builder
	for _, r := range name {
		if r < 0x20 || r == 0x7f {
			continue
		}
		switch r {
		case '/', '\\', ':', '*', '?', '"', '<', '>', '|':
			continue
		}
		b.WriteRune(r)
	}
	out := strings.Trim(b.String(), ". ")
	if out == "" {
		out = "file"
	}
	runes := []rune(out)
	if len(runes) > 120 {
		out = string(runes[:120])
	}
	return out
}

// RegisterAttachmentRoutes 注册附件相关路由。
func RegisterAttachmentRoutes(mux *http.ServeMux, st *store.Store) {
	maxBytes := attachMaxBytes()
	maxMB := maxBytes >> 20
	tooLargeMsg := fmt.Sprintf("附件超过大小限制（%d MB）", maxMB)

	// 上传附件
	mux.HandleFunc("POST /api/notes/{id}/attachments", func(w http.ResponseWriter, r *http.Request) {
		noteID, ok := parseID(w, r)
		if !ok {
			return
		}
		if _, err := st.GetNote(noteID); err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}

		r.Body = http.MaxBytesReader(w, r.Body, maxBytes+(1<<20))
		if err := r.ParseMultipartForm(maxBytes + (1 << 20)); err != nil {
			var mbe *http.MaxBytesError
			if errors.As(err, &mbe) {
				writeError(w, r, http.StatusRequestEntityTooLarge, tooLargeMsg)
				return
			}
			writeError(w, r, http.StatusBadRequest, "invalid multipart form")
			return
		}

		file, header, err := r.FormFile("file")
		if err != nil {
			writeError(w, r, http.StatusBadRequest, "缺少 file 字段")
			return
		}
		defer file.Close()

		data, err := io.ReadAll(io.LimitReader(file, maxBytes+1))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		if int64(len(data)) > maxBytes {
			writeError(w, r, http.StatusRequestEntityTooLarge, tooLargeMsg)
			return
		}

		filename := sanitizeFilename(header.Filename)
		ext := strings.ToLower(filepath.Ext(filename))
		if !attachAllowedExt[ext] {
			writeError(w, r, http.StatusUnsupportedMediaType, "不支持的文件类型："+ext)
			return
		}

		sniffed := http.DetectContentType(data)
		if attachImageExt[ext] && !strings.HasPrefix(sniffed, "image/") {
			writeError(w, r, http.StatusUnsupportedMediaType, "文件内容与扩展名不符")
			return
		}

		sum := sha256.Sum256(data)
		shaHex := hex.EncodeToString(sum[:])

		var rnd [8]byte
		if _, err := rand.Read(rnd[:]); err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		storedName := hex.EncodeToString(rnd[:]) + ext

		dir := filepath.Join(st.AttachDir(), strconv.FormatInt(noteID, 10))
		if err := os.MkdirAll(dir, 0o755); err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		fullPath := filepath.Join(dir, storedName)
		if err := os.WriteFile(fullPath, data, 0o644); err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}

		a, err := st.CreateAttachment(noteID, filename, sniffed, int64(len(data)), shaHex, storedName)
		if err != nil {
			_ = os.Remove(fullPath)
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusCreated, a)
	})

	// 列出笔记附件
	mux.HandleFunc("GET /api/notes/{id}/attachments", func(w http.ResponseWriter, r *http.Request) {
		noteID, ok := parseID(w, r)
		if !ok {
			return
		}
		if _, err := st.GetNote(noteID); err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		list, err := st.ListAttachments(noteID)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		if list == nil {
			list = []store.Attachment{}
		}
		writeJSON(w, http.StatusOK, list)
	})

	// 下载附件
	mux.HandleFunc("GET /api/attachments/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		a, err := st.GetAttachment(id)
		if err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "attachment not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		fullPath := st.AttachmentPath(a)
		f, err := os.Open(fullPath)
		if err != nil {
			if os.IsNotExist(err) {
				writeError(w, r, http.StatusInternalServerError, "附件文件丢失")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		defer f.Close()
		info, err := f.Stat()
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		dispName := strings.ReplaceAll(sanitizeFilename(a.Filename), `"`, "_")
		w.Header().Set("Content-Type", a.Mime)
		w.Header().Set("Content-Disposition", `inline; filename="`+dispName+`"`)
		http.ServeContent(w, r, a.Filename, info.ModTime(), f)
	})

	// 删除附件
	mux.HandleFunc("DELETE /api/attachments/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		if _, err := st.DeleteAttachment(id); err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "attachment not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})
}
