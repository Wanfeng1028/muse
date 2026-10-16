package backupscript_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

// repoRoot 通过测试文件位置定位仓库根目录。
func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller 失败，无法定位测试文件")
	}
	// 测试文件位于 internal/backupscript/，仓库根在其上两级。
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", ".."))
}

// scriptPath 返回 scripts/backup.sh 的绝对路径。
func scriptPath(t *testing.T) string {
	t.Helper()
	return filepath.Join(repoRoot(t), "scripts", "backup.sh")
}

// requireTool 检查外部命令可用，不可用则跳过。
func requireTool(t *testing.T, name, skipMsg string) {
	t.Helper()
	if _, err := exec.LookPath(name); err != nil {
		t.Skip(skipMsg)
	}
}

// makeRealDB 造一个真实 sqlite 数据库文件，返回其路径。
func makeRealDB(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "linkshort.db")

	database, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("db.Open(%q) 失败: %v", dbPath, err)
	}
	st := store.New(database)
	if _, err := st.CreateLinkEx("", "https://example.com/a", "t", nil, nil, false); err != nil {
		database.Close()
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}
	if err := database.Close(); err != nil {
		t.Fatalf("关闭数据库失败: %v", err)
	}
	return dbPath
}

// sidecar 对应 last-backup.json 的严格结构。
type sidecar struct {
	OK             bool   `json:"ok"`
	File           string `json:"file"`
	FinishedAt     string `json:"finished_at"`
	IntegrityCheck string `json:"integrity_check"`
	SizeBytes      int64  `json:"size_bytes"`
	Error          string `json:"error"`
}

// readSidecar 读取并解析 last-backup.json。
func readSidecar(t *testing.T, dir string) sidecar {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join(dir, "last-backup.json"))
	if err != nil {
		t.Fatalf("读取 last-backup.json 失败: %v", err)
	}
	var sc sidecar
	if err := json.Unmarshal(raw, &sc); err != nil {
		t.Fatalf("解析 last-backup.json 失败: %v; 原始内容: %s", err, string(raw))
	}
	return sc
}

// runScript 在受控环境下执行备份脚本。
func runScript(t *testing.T, env []string, dbArg string) (exitCode int, output string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "bash", scriptPath(t), dbArg)
	cmd.Dir = repoRoot(t)
	cmd.Env = env
	out, err := cmd.CombinedOutput()

	code := 0
	if err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			code = ee.ExitCode()
		} else {
			t.Fatalf("执行脚本失败: %v; 输出: %s", err, string(out))
		}
	}
	return code, string(out)
}

// fakeWebhook 记录收到的请求体。
type fakeWebhook struct {
	mu    sync.Mutex
	bodys []string
}

func (f *fakeWebhook) add(body string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.bodys = append(f.bodys, body)
}

func (f *fakeWebhook) count() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.bodys)
}

func (f *fakeWebhook) at(i int) string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.bodys[i]
}

// newFakeWebhook 启动捕获告警的假 webhook 服务。
func newFakeWebhook(t *testing.T) (*httptest.Server, *fakeWebhook) {
	t.Helper()
	fw := &fakeWebhook{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		var sb strings.Builder
		buf := make([]byte, 4096)
		for {
			n, err := r.Body.Read(buf)
			if n > 0 {
				sb.Write(buf[:n])
			}
			if err != nil {
				break
			}
		}
		fw.add(sb.String())
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	return srv, fw
}

func TestBackupScript_Success(t *testing.T) {
	requireTool(t, "sqlite3", "sqlite3 CLI 不可用，跳过脚本测试")
	requireTool(t, "bash", "bash 不可用，跳过脚本测试")

	dbPath := makeRealDB(t)
	backupDir := t.TempDir()

	srv, fw := newFakeWebhook(t)

	env := append(os.Environ(),
		"LINKSHORT_BACKUP_DIR="+backupDir,
		"LINKSHORT_ALERT_WEBHOOK_URL="+srv.URL,
	)

	code, output := runScript(t, env, dbPath)
	if code != 0 {
		t.Fatalf("期望脚本退出码 0，实际 %d; 输出: %s", code, output)
	}

	// 断言备份目录下有且仅有一个 linkshort-*.db
	entries, err := os.ReadDir(backupDir)
	if err != nil {
		t.Fatalf("读取备份目录失败: %v", err)
	}
	var dbFiles []string
	for _, e := range entries {
		name := e.Name()
		if !e.IsDir() && strings.HasPrefix(name, "linkshort-") && strings.HasSuffix(name, ".db") {
			dbFiles = append(dbFiles, name)
		}
	}
	if len(dbFiles) != 1 {
		t.Fatalf("期望恰好 1 个 linkshort-*.db 备份，实际 %d 个: %v", len(dbFiles), dbFiles)
	}

	sc := readSidecar(t, backupDir)
	if !sc.OK {
		t.Errorf("期望 sidecar ok==true，实际 false; error=%q", sc.Error)
	}
	if sc.IntegrityCheck != "ok" {
		t.Errorf("期望 integrity_check==\"ok\"，实际 %q", sc.IntegrityCheck)
	}
	if !strings.HasPrefix(sc.File, "linkshort-") {
		t.Errorf("期望 file 以 linkshort- 开头，实际 %q", sc.File)
	}
	if _, err := time.Parse(time.RFC3339, sc.FinishedAt); err != nil {
		t.Errorf("期望 finished_at 可被 RFC3339 解析，实际 %q: %v", sc.FinishedAt, err)
	}
	if sc.SizeBytes <= 0 {
		t.Errorf("期望 size_bytes>0，实际 %d", sc.SizeBytes)
	}

	if n := fw.count(); n != 0 {
		t.Errorf("成功备份不应触发告警，实际收到 %d 个请求; body[0]=%q", n, fw.at(0))
	}
}

func TestBackupScript_Failure(t *testing.T) {
	requireTool(t, "sqlite3", "sqlite3 CLI 不可用，跳过脚本测试")
	requireTool(t, "bash", "bash 不可用，跳过脚本测试")

	backupDir := t.TempDir()
	missingDB := filepath.Join(t.TempDir(), "does-not-exist.db")

	srv, fw := newFakeWebhook(t)

	env := append(os.Environ(),
		"LINKSHORT_BACKUP_DIR="+backupDir,
		"LINKSHORT_ALERT_WEBHOOK_URL="+srv.URL,
	)

	code, output := runScript(t, env, missingDB)
	if code == 0 {
		t.Fatalf("期望脚本退出码非 0，实际 0; 输出: %s", output)
	}

	sc := readSidecar(t, backupDir)
	if sc.OK {
		t.Errorf("期望 sidecar ok==false，实际 true")
	}
	if sc.Error == "" {
		t.Errorf("期望 sidecar error 非空，实际为空")
	}

	if n := fw.count(); n != 1 {
		t.Fatalf("期望恰好 1 个告警请求，实际 %d 个", n)
	}
	var payload struct {
		Source string `json:"source"`
		Event  string `json:"event"`
		Error  string `json:"error"`
	}
	if err := json.Unmarshal([]byte(fw.at(0)), &payload); err != nil {
		t.Fatalf("解析告警 body 失败: %v; 原始内容: %s", err, fw.at(0))
	}
	if payload.Event != "backup_failed" {
		t.Errorf("期望 event==\"backup_failed\"，实际 %q", payload.Event)
	}
	if payload.Source != "linkshort" {
		t.Errorf("期望 source==\"linkshort\"，实际 %q", payload.Source)
	}
	if payload.Error == "" {
		t.Errorf("期望告警 error 非空，实际为空")
	}
}

func TestBackupScript_FailureNoWebhook(t *testing.T) {
	requireTool(t, "sqlite3", "sqlite3 CLI 不可用，跳过脚本测试")
	requireTool(t, "bash", "bash 不可用，跳过脚本测试")

	backupDir := t.TempDir()
	missingDB := filepath.Join(t.TempDir(), "does-not-exist.db")

	env := append(os.Environ(),
		"LINKSHORT_BACKUP_DIR="+backupDir,
		"LINKSHORT_ALERT_WEBHOOK_URL=",
	)

	code, output := runScript(t, env, missingDB)
	if code == 0 {
		t.Fatalf("期望脚本退出码非 0，实际 0; 输出: %s", output)
	}

	sc := readSidecar(t, backupDir)
	if sc.OK {
		t.Errorf("期望 sidecar ok==false，实际 true")
	}
}
