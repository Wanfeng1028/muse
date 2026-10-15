package store

import (
	"database/sql"
	"errors"
	"os"
	"path/filepath"
	"strconv"
)

// Attachment 附件数据模型。
type Attachment struct {
	ID         int64  `json:"id"`
	NoteID     int64  `json:"noteId"`
	Filename   string `json:"filename"`
	StoredName string `json:"storedName"`
	Mime       string `json:"mime"`
	Size       int64  `json:"size"`
	SHA256     string `json:"sha256"`
	CreatedAt  string `json:"createdAt"`
}

// SetAttachDir 设置附件根目录（测试用）。
func (s *Store) SetAttachDir(dir string) {
	s.attachDir = dir
}

// AttachDir 返回附件根目录。
func (s *Store) AttachDir() string {
	return s.attachDir
}

// AttachmentPath 返回附件在磁盘上的完整路径。
func (s *Store) AttachmentPath(a Attachment) string {
	return filepath.Join(s.attachDir, strconv.FormatInt(a.NoteID, 10), a.StoredName)
}

// scanAttachment 扫描一行附件记录。
func scanAttachment(sc scanner) (Attachment, error) {
	var a Attachment
	if err := sc.Scan(
		&a.ID, &a.NoteID, &a.Filename, &a.StoredName,
		&a.Mime, &a.Size, &a.SHA256, &a.CreatedAt,
	); err != nil {
		return Attachment{}, err
	}
	return a, nil
}

// CreateAttachment 创建附件记录，先确认笔记存在。
func (s *Store) CreateAttachment(noteID int64, filename, mime string, size int64, sha256, storedName string) (Attachment, error) {
	if _, err := s.GetNote(noteID); err != nil {
		return Attachment{}, err
	}
	now := nowRFC3339()
	res, err := s.db.Exec(
		`INSERT INTO attachments(note_id, filename, stored_name, mime, size, sha256, created_at)
		 VALUES(?,?,?,?,?,?,?)`,
		noteID, filename, storedName, mime, size, sha256, now,
	)
	if err != nil {
		return Attachment{}, err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return Attachment{}, err
	}
	return Attachment{
		ID:         id,
		NoteID:     noteID,
		Filename:   filename,
		StoredName: storedName,
		Mime:       mime,
		Size:       size,
		SHA256:     sha256,
		CreatedAt:  now,
	}, nil
}

// GetAttachment 获取附件。
func (s *Store) GetAttachment(id int64) (Attachment, error) {
	row := s.db.QueryRow(
		`SELECT id, note_id, filename, stored_name, mime, size, sha256, created_at
		 FROM attachments WHERE id=?`, id,
	)
	a, err := scanAttachment(row)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Attachment{}, ErrNotFound
		}
		return Attachment{}, err
	}
	return a, nil
}

// ListAttachments 列出笔记的附件，按 id ASC。
func (s *Store) ListAttachments(noteID int64) ([]Attachment, error) {
	rows, err := s.db.Query(
		`SELECT id, note_id, filename, stored_name, mime, size, sha256, created_at
		 FROM attachments WHERE note_id=? ORDER BY id ASC`, noteID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Attachment{}
	for rows.Next() {
		a, err := scanAttachment(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// DeleteAttachment 删除附件记录及其磁盘文件。
func (s *Store) DeleteAttachment(id int64) (Attachment, error) {
	a, err := s.GetAttachment(id)
	if err != nil {
		return Attachment{}, err
	}
	path := s.AttachmentPath(a)
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return Attachment{}, err
	}
	if _, err := s.db.Exec(`DELETE FROM attachments WHERE id=?`, id); err != nil {
		return Attachment{}, err
	}
	return a, nil
}
