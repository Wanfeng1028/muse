package store

import (
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func namedStatValue(list []model.NamedStat, name string) int64 {
	for _, s := range list {
		if s.Name == name {
			return s.Clicks
		}
	}
	return 0
}

func TestUAStatsEmpty(t *testing.T) {
	st := newTestStore(t)
	link, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	got, err := st.UAStats(link)
	if err != nil {
		t.Fatalf("UAStats: %v", err)
	}
	if got.Total != 0 {
		t.Fatalf("Total = %d, want 0", got.Total)
	}
	if got.Bots != 0 {
		t.Fatalf("Bots = %d, want 0", got.Bots)
	}
	if got.Devices == nil {
		t.Fatalf("Devices is nil, want non-nil empty slice")
	}
	if got.Browsers == nil {
		t.Fatalf("Browsers is nil, want non-nil empty slice")
	}
	if got.OSList == nil {
		t.Fatalf("OSList is nil, want non-nil empty slice")
	}
	if len(got.Devices) != 0 {
		t.Fatalf("len(Devices) = %d, want 0", len(got.Devices))
	}
	if len(got.Browsers) != 0 {
		t.Fatalf("len(Browsers) = %d, want 0", len(got.Browsers))
	}
	if len(got.OSList) != 0 {
		t.Fatalf("len(OSList) = %d, want 0", len(got.OSList))
	}
}

func TestUAStatsDesktopChromeWindows(t *testing.T) {
	st := newTestStore(t)
	link, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	ua := "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
	if err := st.RecordVisitGeo(link, "iphash1", ua, "https://ref.example", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	got, err := st.UAStats(link)
	if err != nil {
		t.Fatalf("UAStats: %v", err)
	}
	if got.Total != 1 {
		t.Fatalf("Total = %d, want 1", got.Total)
	}
	if v := namedStatValue(got.Devices, "桌面"); v != 1 {
		t.Fatalf("Devices[桌面] = %d, want 1 (devices=%+v)", v, got.Devices)
	}
	if v := namedStatValue(got.Browsers, "Chrome"); v != 1 {
		t.Fatalf("Browsers[Chrome] = %d, want 1 (browsers=%+v)", v, got.Browsers)
	}
	if v := namedStatValue(got.OSList, "Windows"); v != 1 {
		t.Fatalf("OSList[Windows] = %d, want 1 (os=%+v)", v, got.OSList)
	}
}

func TestUAStatsMobileWeChatIPhone(t *testing.T) {
	st := newTestStore(t)
	link, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	ua := "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.30(0x18001e2f) NetType/WIFI Language/zh_CN"
	if err := st.RecordVisitGeo(link, "iphash2", ua, "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	got, err := st.UAStats(link)
	if err != nil {
		t.Fatalf("UAStats: %v", err)
	}
	if got.Total != 1 {
		t.Fatalf("Total = %d, want 1", got.Total)
	}
	if v := namedStatValue(got.Devices, "手机"); v != 1 {
		t.Fatalf("Devices[手机] = %d, want 1 (devices=%+v)", v, got.Devices)
	}
	if v := namedStatValue(got.Browsers, "微信"); v != 1 {
		t.Fatalf("Browsers[微信] = %d, want 1 (browsers=%+v)", v, got.Browsers)
	}
	if v := namedStatValue(got.OSList, "iOS"); v != 1 {
		t.Fatalf("OSList[iOS] = %d, want 1 (os=%+v)", v, got.OSList)
	}
}

func TestUAStatsBotGooglebot(t *testing.T) {
	st := newTestStore(t)
	link, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	ua := "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
	if err := st.RecordVisitGeo(link, "iphash3", ua, "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	got, err := st.UAStats(link)
	if err != nil {
		t.Fatalf("UAStats: %v", err)
	}
	if got.Total != 1 {
		t.Fatalf("Total = %d, want 1", got.Total)
	}
	if got.Bots != 1 {
		t.Fatalf("Bots = %d, want 1", got.Bots)
	}
	if v := namedStatValue(got.Devices, "爬虫"); v != 1 {
		t.Fatalf("Devices[爬虫] = %d, want 1 (devices=%+v)", v, got.Devices)
	}
}

func TestUAStatsTabletIPad(t *testing.T) {
	st := newTestStore(t)
	link, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	ua := "Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
	if err := st.RecordVisitGeo(link, "iphash4", ua, "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	got, err := st.UAStats(link)
	if err != nil {
		t.Fatalf("UAStats: %v", err)
	}
	if got.Total != 1 {
		t.Fatalf("Total = %d, want 1", got.Total)
	}
	if v := namedStatValue(got.Devices, "平板"); v != 1 {
		t.Fatalf("Devices[平板] = %d, want 1 (devices=%+v)", v, got.Devices)
	}
}

func TestUAStatsAggregationThreeSameUA(t *testing.T) {
	st := newTestStore(t)
	link, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	ua := "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
	for i := 0; i < 3; i++ {
		if err := st.RecordVisitGeo(link, "iphashAgg", ua, "", "", "", "", ""); err != nil {
			t.Fatalf("RecordVisitGeo #%d: %v", i, err)
		}
	}
	got, err := st.UAStats(link)
	if err != nil {
		t.Fatalf("UAStats: %v", err)
	}
	if got.Total != 3 {
		t.Fatalf("Total = %d, want 3", got.Total)
	}
	if v := namedStatValue(got.Devices, "桌面"); v != 3 {
		t.Fatalf("Devices[桌面] = %d, want 3 (devices=%+v)", v, got.Devices)
	}
	if v := namedStatValue(got.Browsers, "Chrome"); v != 3 {
		t.Fatalf("Browsers[Chrome] = %d, want 3 (browsers=%+v)", v, got.Browsers)
	}
	if v := namedStatValue(got.OSList, "Windows"); v != 3 {
		t.Fatalf("OSList[Windows] = %d, want 3 (os=%+v)", v, got.OSList)
	}
}

func TestUAStatsLinkIsolation(t *testing.T) {
	st := newTestStore(t)
	linkA, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink A: %v", err)
	}
	linkB, err := st.CreateLink("", "https://example.com/b", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink B: %v", err)
	}
	uaA := "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
	if err := st.RecordVisitGeo(linkA, "iphashA1", uaA, "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo A1: %v", err)
	}
	if err := st.RecordVisitGeo(linkA, "iphashA2", uaA, "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo A2: %v", err)
	}
	if err := st.RecordVisitGeo(linkB, "iphashB1", uaA, "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo B1: %v", err)
	}
	gotA, err := st.UAStats(linkA)
	if err != nil {
		t.Fatalf("UAStats A: %v", err)
	}
	if gotA.Total != 2 {
		t.Fatalf("UAStats(A).Total = %d, want 2", gotA.Total)
	}
	gotB, err := st.UAStats(linkB)
	if err != nil {
		t.Fatalf("UAStats B: %v", err)
	}
	if gotB.Total != 1 {
		t.Fatalf("UAStats(B).Total = %d, want 1", gotB.Total)
	}
}

func TestUAStatsEmptyUASkipped(t *testing.T) {
	st := newTestStore(t)
	link, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	if err := st.RecordVisitGeo(link, "iphashEmpty", "", "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo empty: %v", err)
	}
	ua := "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
	if err := st.RecordVisitGeo(link, "iphashNonEmpty", ua, "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo non-empty: %v", err)
	}
	got, err := st.UAStats(link)
	if err != nil {
		t.Fatalf("UAStats: %v", err)
	}
	if got.Total != 1 {
		t.Fatalf("Total = %d, want 1 (empty UA must be skipped)", got.Total)
	}
	if v := namedStatValue(got.Devices, "桌面"); v != 1 {
		t.Fatalf("Devices[桌面] = %d, want 1 (devices=%+v)", v, got.Devices)
	}
	if v := namedStatValue(got.Browsers, "Chrome"); v != 1 {
		t.Fatalf("Browsers[Chrome] = %d, want 1 (browsers=%+v)", v, got.Browsers)
	}
}

func TestUAStatsFirefox(t *testing.T) {
	st := newTestStore(t)
	link, err := st.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	ua := "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
	if err := st.RecordVisitGeo(link, "iphashFF", ua, "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	got, err := st.UAStats(link)
	if err != nil {
		t.Fatalf("UAStats: %v", err)
	}
	if got.Total != 1 {
		t.Fatalf("Total = %d, want 1", got.Total)
	}
	if v := namedStatValue(got.Browsers, "Firefox"); v != 1 {
		t.Fatalf("Browsers[Firefox] = %d, want 1 (browsers=%+v)", v, got.Browsers)
	}
}
