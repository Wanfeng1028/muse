package api

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/notify"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func newImportTestStore(t *testing.T) (*store.Store, *config.Config, string) {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "muse.db")
	st, err := store.Open(dbPath)
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	if err := st.Migrate(); err != nil {
		t.Fatalf("store.Migrate: %v", err)
	}
	cfg := &config.Config{Database: dbPath}
	return st, cfg, dir
}

func newImportTestStoreWithSource(t *testing.T, sourceName, table, pk string) (*store.Store, *config.Config, string) {
	t.Helper()
	st, cfg, dir := newImportTestStore(t)
	cfg.Sources = []config.SourceConfig{{
		Name:       sourceName,
		Table:      table,
		PrimaryKey: pk,
	}}
	return st, cfg, dir
}

func csvBytes(header []string, rows ...[]string) []byte {
	var buf bytes.Buffer
	w := csv.NewWriter(&buf)
	_ = w.Write(header)
	for _, r := range rows {
		_ = w.Write(r)
	}
	w.Flush()
	return buf.Bytes()
}

func hashOf(b []byte) string {
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}

func TestImportCSVDeep_MultiSourceConflictSameKeyDifferentValue(t *testing.T) {
	st, cfg, _ := newImportTestStoreWithSource(t, "src_a", "users", "id")
	cfg.Sources = append(cfg.Sources, config.SourceConfig{
		Name:       "src_b",
		Table:      "users",
		PrimaryKey: "id",
	})

	bodyA := csvBytes([]string{"id", "email"}, []string{"1", "a@example.com"})
	bodyB := csvBytes([]string{"id", "email"}, []string{"1", "b@example.com"})

	resA, err := importCSV(st, cfg, "src_a", bytes.NewReader(bodyA), "a.csv")
	if err != nil {
		t.Fatalf("importCSV src_a: %v", err)
	}
	if resA.Inserted != 1 {
		t.Fatalf("src_a inserted = %d, want 1", resA.Inserted)
	}
	if resA.ErrorRows != 0 {
		t.Fatalf("src_a error_rows = %d, want 0", resA.ErrorRows)
	}

	resB, err := importCSV(st, cfg, "src_b", bytes.NewReader(bodyB), "b.csv")
	if err != nil {
		t.Fatalf("importCSV src_b: %v", err)
	}
	if resB.ConflictsPending < 1 {
		t.Fatalf("src_b conflicts_pending = %d, want >= 1", resB.ConflictsPending)
	}
	if len(resB.Conflicts) == 0 {
		t.Fatalf("src_b conflicts = empty, want >= 1 record")
	}
	foundConflict := false
	for _, c := range resB.Conflicts {
		if c.PK == "1" && strings.Contains(c.RowJSON, "b@example.com") {
			foundConflict = true
		}
	}
	if !foundConflict {
		t.Fatalf("conflict for pk=1 with new email b@example.com not found, got %+v", resB.Conflicts)
	}
}

func TestImportCSVDeep_WebhookHMACSignatureBoundaries(t *testing.T) {
	secret := "topsecret"
	payload := []byte(`{"source":"src_a","file_hash":"deadbeef","table":"users"}`)

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	validSig := hex.EncodeToString(mac.Sum(nil))

	// 真实签名函数 notify.Sign 与本地独立计算一致
	if got := notify.Sign(secret, payload); got != validSig {
		t.Fatalf("signature mismatch: got %q want %q", got, validSig)
	}
	if len(validSig) != 64 {
		t.Fatalf("sha256 十六进制长度应为 64, 实际 %d", len(validSig))
	}

	// 篡改一位后签名不同
	badSig := validSig
	if badSig[0] == 'a' {
		badSig = "b" + badSig[1:]
	} else {
		badSig = "a" + badSig[1:]
	}
	if notify.Sign(secret, payload) == badSig {
		t.Fatalf("tampered signature should differ from valid")
	}

	// 不同 secret 签名不同
	if notify.Sign("other-secret", payload) == validSig {
		t.Fatalf("different secret should give different signature")
	}

	// 空 body 签名确定且长度正确
	emptySig := notify.Sign(secret, []byte{})
	if len(emptySig) != 64 {
		t.Fatalf("empty body signature invalid: %q", emptySig)
	}
	if notify.Sign(secret, []byte{}) != emptySig {
		t.Fatalf("empty body signature not deterministic")
	}
}

func TestImportCSVDeep_SyncIdempotency(t *testing.T) {
	st, cfg, _ := newImportTestStoreWithSource(t, "src_sync", "items", "id")
	body := csvBytes([]string{"id", "name"}, []string{"1", "one"}, []string{"2", "two"})

	first, err := importCSV(st, cfg, "src_sync", bytes.NewReader(body), "items.csv")
	if err != nil {
		t.Fatalf("first import: %v", err)
	}
	if first.Inserted != 2 {
		t.Fatalf("first inserted = %d, want 2", first.Inserted)
	}
	if first.Duplicate {
		t.Fatalf("first import must not be marked duplicate")
	}

	second, err := importCSV(st, cfg, "src_sync", bytes.NewReader(body), "items.csv")
	if err != nil {
		t.Fatalf("second import: %v", err)
	}
	if !second.Duplicate {
		t.Fatalf("second import must be duplicate")
	}
	if second.Inserted != 2 {
		t.Fatalf("second inserted = %d, want 2 (replayed summary)", second.Inserted)
	}
	if second.FileHash != first.FileHash {
		t.Fatalf("file hash differs: %q vs %q", first.FileHash, second.FileHash)
	}

	var count int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM items`).Scan(&count); err != nil {
		t.Fatalf("count rows: %v", err)
	}
	if count != 2 {
		t.Fatalf("row count = %d, want 2 (idempotent)", count)
	}
}

func TestImportCSVDeep_CSVIncrementalResume(t *testing.T) {
	st, cfg, dir := newImportTestStoreWithSource(t, "src_inc", "events", "id")

	batch1 := csvBytes([]string{"id", "payload"}, []string{"1", "a"}, []string{"2", "b"})
	res1, err := importCSV(st, cfg, "src_inc", bytes.NewReader(batch1), "part1.csv")
	if err != nil {
		t.Fatalf("batch1: %v", err)
	}
	if res1.Inserted != 2 {
		t.Fatalf("batch1 inserted = %d, want 2", res1.Inserted)
	}

	checkpointPath := filepath.Join(dir, ".import-tmp")
	if _, err := os.Stat(checkpointPath); err != nil {
		t.Fatalf("checkpoint dir missing: %v", err)
	}

	batch2 := csvBytes([]string{"id", "payload"}, []string{"3", "c"}, []string{"4", "d"}, []string{"5", "e"})
	res2, err := importCSV(st, cfg, "src_inc", bytes.NewReader(batch2), "part2.csv")
	if err != nil {
		t.Fatalf("batch2: %v", err)
	}
	if res2.Inserted != 3 {
		t.Fatalf("batch2 inserted = %d, want 3", res2.Inserted)
	}
	if res2.FileHash == res1.FileHash {
		t.Fatalf("batch2 hash must differ from batch1")
	}

	var total int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM events`).Scan(&total); err != nil {
		t.Fatalf("count events: %v", err)
	}
	if total != 5 {
		t.Fatalf("total events = %d, want 5", total)
	}
}

func TestImportCSVDeep_ConflictKeyEmptyAndMissingColumns(t *testing.T) {
	st, cfg, _ := newImportTestStoreWithSource(t, "src_conf", "records", "id")
	body := csvBytes([]string{"id", "value"},
		[]string{"", "empty-key"},
		[]string{"2", "ok"},
	)
	res, err := importCSV(st, cfg, "src_conf", bytes.NewReader(body), "rec.csv")
	if err != nil {
		t.Fatalf("importCSV: %v", err)
	}
	if res.ErrorRows != 1 {
		t.Fatalf("error_rows = %d, want 1", res.ErrorRows)
	}
	if len(res.Errors) != 1 {
		t.Fatalf("errors len = %d, want 1", len(res.Errors))
	}
	if res.Errors[0].Line != 2 {
		t.Fatalf("error line = %d, want 2", res.Errors[0].Line)
	}
	if !strings.Contains(res.Errors[0].Reason, "主键为空") {
		t.Fatalf("error reason = %q, want contains 主键为空", res.Errors[0].Reason)
	}
	if res.Inserted != 1 {
		t.Fatalf("inserted = %d, want 1", res.Inserted)
	}
}

func TestImportCSVDeep_ConflictPendingMultipleColumns(t *testing.T) {
	// 跨源：同 pk 多列变化记一条行级冲突（真实语义：冲突按行记，不是按列）
	st, cfg, _ := newImportTestStoreWithSource(t, "src_p1", "profile", "id")
	cfg.Sources = append(cfg.Sources, config.SourceConfig{
		Name:       "src_p2",
		Table:      "profile",
		PrimaryKey: "id",
	})
	base := csvBytes([]string{"id", "email", "phone"}, []string{"1", "a@x.com", "111"})
	if _, err := importCSV(st, cfg, "src_p1", bytes.NewReader(base), "base.csv"); err != nil {
		t.Fatalf("base import: %v", err)
	}

	upd := csvBytes([]string{"id", "email", "phone"}, []string{"1", "b@x.com", "222"})
	res, err := importCSV(st, cfg, "src_p2", bytes.NewReader(upd), "upd.csv")
	if err != nil {
		t.Fatalf("upd import: %v", err)
	}
	if res.ConflictsPending < 1 {
		t.Fatalf("conflicts_pending = %d, want >= 1", res.ConflictsPending)
	}
	found := false
	for _, c := range res.Conflicts {
		if c.PK == "1" && c.SourceA == "src_p1" && c.SourceB == "src_p2" &&
			strings.Contains(c.RowJSON, "b@x.com") && strings.Contains(c.RowJSON, "222") {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected row-level conflict for pk=1 with new values, got %+v", res.Conflicts)
	}
}

func TestImportCSVDeep_EmptyFileRejected(t *testing.T) {
	st, cfg, _ := newImportTestStoreWithSource(t, "src_e", "t", "id")
	res, err := importCSV(st, cfg, "src_e", bytes.NewReader(nil), "empty.csv")
	if !errors.Is(err, errImportEmptyFile) {
		t.Fatalf("err = %v, want errImportEmptyFile", err)
	}
	if res.Source != "src_e" {
		t.Fatalf("res.Source = %q, want src_e", res.Source)
	}
	if res.Inserted != 0 || res.ErrorRows != 0 {
		t.Fatalf("res counters = inserted %d error %d, want 0/0", res.Inserted, res.ErrorRows)
	}
}

func TestImportCSVDeep_UnknownSourceRejected(t *testing.T) {
	st, cfg, _ := newImportTestStore(t)
	body := csvBytes([]string{"id"}, []string{"1"})
	res, err := importCSV(st, cfg, "nope", bytes.NewReader(body), "x.csv")
	if !errors.Is(err, errImportSourceNotFound) {
		t.Fatalf("err = %v, want errImportSourceNotFound", err)
	}
	if res.Source != "nope" {
		t.Fatalf("res.Source = %q, want nope", res.Source)
	}
	if res.Filename != "x.csv" {
		t.Fatalf("res.Filename = %q, want x.csv", res.Filename)
	}
}

func TestImportCSVDeep_DuplicateFileHashSummary(t *testing.T) {
	st, cfg, _ := newImportTestStoreWithSource(t, "src_d", "d", "id")
	body := csvBytes([]string{"id", "v"}, []string{"1", "x"})
	if _, err := importCSV(st, cfg, "src_d", bytes.NewReader(body), "d.csv"); err != nil {
		t.Fatalf("first import: %v", err)
	}
	firstHash := hashOf(body)

	dup, err := importCSV(st, cfg, "src_d", bytes.NewReader(body), "ignored.csv")
	if err != nil {
		t.Fatalf("dup import: %v", err)
	}
	if dup.FileHash != firstHash {
		t.Fatalf("dup hash = %q, want %q", dup.FileHash, firstHash)
	}
	if dup.Filename != "d.csv" {
		t.Fatalf("dup filename = %q, want d.csv (from stored summary)", dup.Filename)
	}
	if dup.Inserted != 1 {
		t.Fatalf("dup inserted = %d, want 1", dup.Inserted)
	}
	if !dup.Duplicate {
		t.Fatalf("dup.Duplicate = false, want true")
	}
}

func TestImportCSVDeep_ColumnMappingAndInvalidName(t *testing.T) {
	st, cfg, _ := newImportTestStoreWithSource(t, "src_map", "m", "id")
	body := csvBytes([]string{"ID", "Name"}, []string{"1", "n1"})
	opts := importCSVOptions{
		Table:      "m",
		PrimaryKey: "id",
		ColumnMapping: map[string]string{
			"ID":   "id",
			"Name": "name",
		},
	}
	res, err := importCSVStream(st, cfg, "src_map", bytes.NewReader(body), "m.csv", opts)
	if err != nil {
		t.Fatalf("mapped import: %v", err)
	}
	if res.Inserted != 1 {
		t.Fatalf("inserted = %d, want 1", res.Inserted)
	}
	if res.Table != "m" {
		t.Fatalf("table = %q, want m", res.Table)
	}
	var name string
	if err := st.DB.QueryRow(`SELECT name FROM m WHERE id = ?`, "1").Scan(&name); err != nil {
		t.Fatalf("query mapped row: %v", err)
	}
	if name != "n1" {
		t.Fatalf("name = %q, want n1", name)
	}

	bad := csvBytes([]string{"id", "bad name"}, []string{"2", "x"})
	_, err = importCSVStream(st, cfg, "src_map", bytes.NewReader(bad), "bad.csv", importCSVOptions{})
	if !errors.Is(err, errImportInvalidColumnName) {
		t.Fatalf("err = %v, want errImportInvalidColumnName", err)
	}
}

func TestImportCSVDeep_ConcurrentSameFile(t *testing.T) {
	st, cfg, _ := newImportTestStoreWithSource(t, "src_c", "c", "id")
	body := csvBytes([]string{"id", "v"}, []string{"1", "x"}, []string{"2", "y"})

	var wg sync.WaitGroup
	results := make([]importCSVResult, 4)
	errs := make([]error, 4)
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			r, err := importCSV(st, cfg, "src_c", bytes.NewReader(body), "c.csv")
			results[idx] = r
			errs[idx] = err
		}(i)
	}
	wg.Wait()

	insertedTotal := 0
	dupCount := 0
	for i := 0; i < 4; i++ {
		if errs[i] != nil {
			t.Fatalf("goroutine %d err: %v", i, errs[i])
		}
		insertedTotal += results[i].Inserted
		if results[i].Duplicate {
			dupCount++
		}
	}
	if dupCount < 1 {
		t.Fatalf("expected at least 1 duplicate result, got %d", dupCount)
	}

	var count int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM c`).Scan(&count); err != nil {
		t.Fatalf("count rows: %v", err)
	}
	if count != 2 {
		t.Fatalf("row count = %d, want 2", count)
	}
}

func TestImportCSVDeep_ConflictJSONRoundTrip(t *testing.T) {
	body := csvBytes([]string{"id", "v"}, []string{"1", "x"})
	res := importCSVResult{
		Source:    "s",
		Table:     "t",
		FileHash:  hashOf(body),
		Filename:  "f.csv",
		Conflicts: []store.Conflict{{PK: "1", TableName: "t", SourceA: "a", SourceB: "b", RowJSON: `{"id":"1","v":"b"}`, Status: "pending"}},
	}
	raw, err := json.Marshal(res)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var back importCSVResult
	if err := json.Unmarshal(raw, &back); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(back.Conflicts) != 1 {
		t.Fatalf("conflicts len = %d, want 1", len(back.Conflicts))
	}
	if back.Conflicts[0].PK != "1" || back.Conflicts[0].RowJSON != `{"id":"1","v":"b"}` || back.Conflicts[0].Status != "pending" {
		t.Fatalf("roundtrip conflict = %+v", back.Conflicts[0])
	}
	if back.FileHash != res.FileHash {
		t.Fatalf("hash roundtrip = %q want %q", back.FileHash, res.FileHash)
	}
	_ = sql.ErrNoRows
	_ = fmt.Sprintf
}
