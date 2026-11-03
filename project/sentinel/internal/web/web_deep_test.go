
package web

import (
	"errors"
	"io/fs"
	"strings"
	"sync"
	"testing"
)

func TestWebFS_ExpectedFilesPresent(t *testing.T) {
	expected := []string{
		"app.js",
		"deliveries.html",
		"incidents.html",
		"index.html",
		"monitors.html",
		"profile.html",
		"sms_log.html",
		"status.html",
		"style.css",
	}

	entries, err := fs.ReadDir(FS, "static")
	if err != nil {
		t.Fatalf("读取 static 目录失败: %v", err)
	}

	present := make(map[string]bool, len(entries))
	for _, e := range entries {
		present[e.Name()] = true
	}

	if len(expected) != 9 {
		t.Fatalf("期望文件列表应含 9 项, 实际 %d", len(expected))
	}

	for _, name := range expected {
		if !present[name] {
			t.Errorf("期望文件缺失: %s", name)
			continue
		}
		info, err := fs.Stat(FS, "static/"+name)
		if err != nil {
			t.Errorf("Stat %s 失败: %v", name, err)
			continue
		}
		if info.Size() <= 0 {
			t.Errorf("文件 %s 大小应为正数, 实际 %d", name, info.Size())
		}
	}
}

func TestWebFS_IndexStructure(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/index.html")
	if err != nil {
		t.Fatalf("读取 static/index.html 失败: %v", err)
	}
	if len(data) == 0 {
		t.Fatalf("static/index.html 内容为空")
	}
	lower := strings.ToLower(string(data))
	if !strings.Contains(lower, "<!doctype html>") {
		t.Errorf("index.html 应包含 <!DOCTYPE html>")
	}
	if !strings.Contains(lower, "</html>") {
		t.Errorf("index.html 应包含 </html>")
	}
}

func TestWebFS_ConcurrentRead(t *testing.T) {
	files := []string{
		"static/app.js",
		"static/deliveries.html",
		"static/incidents.html",
		"static/index.html",
		"static/monitors.html",
		"static/profile.html",
		"static/sms_log.html",
		"static/status.html",
		"static/style.css",
	}

	const workers = 16
	var wg sync.WaitGroup
	wg.Add(workers)
	for i := 0; i < workers; i++ {
		go func() {
			defer wg.Done()
			for _, f := range files {
				data, err := fs.ReadFile(FS, f)
				if err != nil {
					t.Errorf("并发读取 %s 失败: %v", f, err)
					continue
				}
				if len(data) == 0 {
					t.Errorf("并发读取 %s 内容为空", f)
				}
			}
		}()
	}
	wg.Wait()
}

func TestWebFS_MissingFile(t *testing.T) {
	_, err := fs.ReadFile(FS, "static/not-exist-12345.html")
	if err == nil {
		t.Fatalf("读取不存在的文件应返回错误")
	}
	if !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("错误应为 fs.ErrNotExist, 实际 %v", err)
	}
}
