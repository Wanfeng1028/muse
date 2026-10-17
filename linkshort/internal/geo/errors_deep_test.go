package geo

import (
	"errors"
	"strings"
	"testing"
)

// geoProbeError 是专用于 errors.As 靶子测试的自定义错误类型。
type geoProbeError struct{ msg string }

func (e *geoProbeError) Error() string { return e.msg }

func TestErrEmptyPathIsExportedPackageVar(t *testing.T) {
	if errEmptyPath == nil {
		t.Fatal("errEmptyPath 不能是 nil")
	}
	msg := errEmptyPath.Error()
	if msg != "mmdb 路径为空" {
		t.Fatalf("错误文案不对，拿到的是 %q", msg)
	}
	if strings.TrimSpace(msg) == "" {
		t.Fatal("错误文案不能是空白")
	}
}

func TestErrEmptyPathIdentityStable(t *testing.T) {
	a := errEmptyPath
	b := errEmptyPath
	if a != b {
		t.Fatal("同一次进程里 errEmptyPath 应该是同一个实例")
	}
	if !errors.Is(a, b) {
		t.Fatal("errors.Is 对同一个 error 实例应该返回 true")
	}
}

func TestErrEmptyPathIsNotNilWhenComparedWithNil(t *testing.T) {
	var wrapped error = errEmptyPath
	if wrapped == nil {
		t.Fatal("把 errEmptyPath 装进 error 接口后不应该变成 nil")
	}
	if wrapped.Error() != "mmdb 路径为空" {
		t.Fatalf("装进接口后文案变了，拿到的是 %q", wrapped.Error())
	}
}

func TestErrEmptyPathCanBeMatchedByErrorsIs(t *testing.T) {
	got := error(errEmptyPath)
	if !errors.Is(got, errEmptyPath) {
		t.Fatal("errors.Is 应该能匹配到 errEmptyPath 本身")
	}
	if errors.Is(got, errors.New("mmdb 路径为空")) {
		t.Fatal("errors.Is 不应该把新建的同文案错误当成 errEmptyPath")
	}
}

func TestErrEmptyPathUnwrapReturnsNil(t *testing.T) {
	if errors.Unwrap(errEmptyPath) != nil {
		t.Fatal("errEmptyPath 是叶子错误，Unwrap 应该返回 nil")
	}
}

func TestErrEmptyPathAsTargetOfErrorsAs(t *testing.T) {
	var target *geoProbeError
	wrapped := error(errEmptyPath)
	if errors.As(wrapped, &target) {
		t.Fatal("errEmptyPath 不是 geoProbeError 类型，errors.As 不应该命中")
	}
	if !errors.Is(wrapped, errEmptyPath) {
		t.Fatal("errors.As 没命中时，errors.Is 仍然应该命中")
	}
}

func TestErrEmptyPathMessageIsStableAcrossCalls(t *testing.T) {
	first := errEmptyPath.Error()
	for i := 0; i < 100; i++ {
		if errEmptyPath.Error() != first {
			t.Fatalf("第 %d 次调用文案变了，第一次是 %q，这次是 %q", i, first, errEmptyPath.Error())
		}
	}
	if first != "mmdb 路径为空" {
		t.Fatalf("文案应该固定是 mmdb 路径为空，实际是 %q", first)
	}
}

func TestErrEmptyPathConcurrentReadIsRaceFree(t *testing.T) {
	const workers = 16
	const loops = 200
	done := make(chan string, workers)
	for w := 0; w < workers; w++ {
		go func() {
			for i := 0; i < loops; i++ {
				if errEmptyPath.Error() != "mmdb 路径为空" {
					done <- "文案在并发读时被改了"
					return
				}
				if !errors.Is(errEmptyPath, errEmptyPath) {
					done <- "并发读时 errors.Is 没命中"
					return
				}
			}
			done <- ""
		}()
	}
	for w := 0; w < workers; w++ {
		if msg := <-done; msg != "" {
			t.Fatal(msg)
		}
	}
}

func TestErrEmptyPathWrappedKeepsOriginalReachable(t *testing.T) {
	wrapped := errors.Join(errEmptyPath, errors.New("附带信息"))
	if !errors.Is(wrapped, errEmptyPath) {
		t.Fatal("Join 之后 errors.Is 应该还能找到 errEmptyPath")
	}
	if wrapped.Error() == errEmptyPath.Error() {
		t.Fatal("Join 之后的整体文案应该包含额外信息，不该和原始文案完全相同")
	}
}

func TestErrEmptyPathFormattingContainsMessage(t *testing.T) {
	got := errEmptyPath.Error()
	if !strings.Contains(got, "mmdb") {
		t.Fatalf("文案里应该提到 mmdb，实际是 %q", got)
	}
	if !strings.Contains(got, "路径为空") {
		t.Fatalf("文案里应该提到路径为空，实际是 %q", got)
	}
}

func TestErrEmptyPathIsDistinctFromOtherErrors(t *testing.T) {
	other := errors.New("mmdb 路径为空")
	if errors.Is(other, errEmptyPath) {
		t.Fatal("随便 new 出来的错误不该和包级 errEmptyPath 相等")
	}
	if other == error(errEmptyPath) {
		t.Fatal("随便 new 出来的错误不该和包级 errEmptyPath 是同一个值")
	}
}
