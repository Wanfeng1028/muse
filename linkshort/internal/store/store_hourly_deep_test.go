package store

import (
	"testing"
	"time"
)

func TestHourlyStats_EmptyStore(t *testing.T) {
    st := newTestStore(t)
    got, err := st.HourlyStats(0, 7)
    if err != nil {
        t.Fatalf("HourlyStats: %v", err)
    }
    if len(got.Hours) != 24 {
        t.Fatalf("Hours len = %d, want 24", len(got.Hours))
    }
    for i, v := range got.Hours {
        if v != 0 {
            t.Fatalf("Hours[%d] = %d, want 0", i, v)
        }
    }
    if len(got.Weekdays) != 7 {
        t.Fatalf("Weekdays len = %d, want 7", len(got.Weekdays))
    }
    for i, v := range got.Weekdays {
        if v != 0 {
            t.Fatalf("Weekdays[%d] = %d, want 0", i, v)
        }
    }
    if got.Total != 0 {
        t.Fatalf("Total = %d, want 0", got.Total)
    }
    if got.Days != 7 {
        t.Fatalf("Days = %d, want 7", got.Days)
    }
    if got.LinkID != 0 {
        t.Fatalf("LinkID = %d, want 0", got.LinkID)
    }
}

func TestHourlyStats_CurrentHourBucket(t *testing.T) {
    st := newTestStore(t)
    id, err := st.CreateLinkEx("cur", "https://example.com/cur", "", nil, nil, false, true)
    if err != nil {
        t.Fatalf("CreateLinkEx: %v", err)
    }
    for i := 0; i < 3; i++ {
        if err := st.RecordVisit(id, "h", "ua", ""); err != nil {
            t.Fatalf("RecordVisit: %v", err)
        }
    }
    got, err := st.HourlyStats(0, 0)
    if err != nil {
        t.Fatalf("HourlyStats: %v", err)
    }
    if got.Total != 3 {
        t.Fatalf("Total = %d, want 3", got.Total)
    }
    h := time.Now().UTC().Hour()
    if got.Hours[h] != 3 {
        t.Fatalf("Hours[%d] = %d, want 3", h, got.Hours[h])
    }
    for i, v := range got.Hours {
        if i == h {
            continue
        }
        if v != 0 {
            t.Fatalf("Hours[%d] = %d, want 0", i, v)
        }
    }
}

func TestHourlyStats_LinkFilter(t *testing.T) {
    st := newTestStore(t)
    idA, err := st.CreateLinkEx("a", "https://example.com/a", "", nil, nil, false, true)
    if err != nil {
        t.Fatalf("CreateLinkEx A: %v", err)
    }
    idB, err := st.CreateLinkEx("b", "https://example.com/b", "", nil, nil, false, true)
    if err != nil {
        t.Fatalf("CreateLinkEx B: %v", err)
    }
    for i := 0; i < 2; i++ {
        if err := st.RecordVisit(idA, "h", "ua", ""); err != nil {
            t.Fatalf("RecordVisit A: %v", err)
        }
    }
    if err := st.RecordVisit(idB, "h", "ua", ""); err != nil {
        t.Fatalf("RecordVisit B: %v", err)
    }
    gotA, err := st.HourlyStats(idA, 0)
    if err != nil {
        t.Fatalf("HourlyStats A: %v", err)
    }
    if gotA.Total != 2 {
        t.Fatalf("Total A = %d, want 2", gotA.Total)
    }
    if gotA.LinkID != idA {
        t.Fatalf("LinkID A = %d, want %d", gotA.LinkID, idA)
    }
    gotB, err := st.HourlyStats(idB, 0)
    if err != nil {
        t.Fatalf("HourlyStats B: %v", err)
    }
    if gotB.Total != 1 {
        t.Fatalf("Total B = %d, want 1", gotB.Total)
    }
}

func TestHourlyStats_DaysFilter(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("slug-daysfilter", "https://example.com/x", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	now := time.Now().UTC()
	tenDaysAgo := now.AddDate(0, 0, -10)
	if _, err := st.db.Exec(`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city) VALUES (?,?,?,?,?,?,?,?,?)`, id, formatTime(now), "h", "ua", "", "", "", "", ""); err != nil {
		t.Fatalf("insert now: %v", err)
	}
	if _, err := st.db.Exec(`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city) VALUES (?,?,?,?,?,?,?,?,?)`, id, formatTime(tenDaysAgo), "h", "ua", "", "", "", "", ""); err != nil {
		t.Fatalf("insert ten days ago: %v", err)
	}
	got, err := st.HourlyStats(0, 7)
	if err != nil {
		t.Fatalf("HourlyStats: %v", err)
	}
	if got.Total != 1 {
		t.Errorf("HourlyStats(0,7).Total = %d, want 1", got)
	}
	got30, err := st.HourlyStats(0, 30)
	if err != nil {
		t.Fatalf("HourlyStats 30: %v", err)
	}
	if got30.Total != 2 {
		t.Errorf("HourlyStats(0,30).Total = %d, want 2", got)
	}
	got0, err := st.HourlyStats(0, 0)
	if err != nil {
		t.Fatalf("HourlyStats 0: %v", err)
	}
	if got0.Total != 2 {
		t.Errorf("HourlyStats(0,0).Total = %d, want 2", got)
	}
}

func TestHourlyStats_WeekdayBucket(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("slug-weekdaybucket", "https://example.com/x", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	d := time.Now().UTC()
	for d.Weekday() != time.Wednesday {
		d = d.AddDate(0, 0, -1)
	}
	ts := time.Date(d.Year(), d.Month(), d.Day(), 12, 0, 0, 0, time.UTC)
	if _, err := st.db.Exec(`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city) VALUES (?,?,?,?,?,?,?,?,?)`, id, formatTime(ts), "h", "ua", "", "", "", "", ""); err != nil {
		t.Fatalf("insert: %v", err)
	}
	gotW, err := st.HourlyStats(0, 0)
	if err != nil {
		t.Fatalf("HourlyStats: %v", err)
	}
	if gotW.Weekdays[3] != 1 {
		t.Errorf("Weekdays[3] = %d, want 1", gotW.Weekdays[3])
	}
}

func TestHourlyStats_HourBucket(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("slug-hourbucket", "https://example.com/x", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	d := time.Now().UTC()
	ts := time.Date(d.Year(), d.Month(), d.Day(), 5, 30, 0, 0, time.UTC)
	if _, err := st.db.Exec(`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city) VALUES (?,?,?,?,?,?,?,?,?)`, id, formatTime(ts), "h", "ua", "", "", "", "", ""); err != nil {
		t.Fatalf("insert: %v", err)
	}
	gotH, err := st.HourlyStats(0, 0)
	if err != nil {
		t.Fatalf("HourlyStats: %v", err)
	}
	if gotH.Hours[5] != 1 {
		t.Errorf("Hours[5] = %d, want 1", gotH.Hours[5])
	}
}

func TestHourlyStats_SumConsistency(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("slug-sumconsistency", "https://example.com/x", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	base := time.Now().UTC()
	for i := 0; i < 5; i++ {
		ts := base.Add(time.Duration(i) * time.Hour)
		if _, err := st.db.Exec(`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city) VALUES (?,?,?,?,?,?,?,?,?)`, id, formatTime(ts), "h", "ua", "", "", "", "", ""); err != nil {
			t.Fatalf("insert %d: %v", i, err)
		}
	}
	stats, err := st.HourlyStats(0, 0)
	if err != nil {
		t.Fatalf("HourlyStats: %v", err)
	}
	var sumHours, sumWeekdays int64
	for _, v := range stats.Hours {
		sumHours += v
	}
	for _, v := range stats.Weekdays {
		sumWeekdays += v
	}
	if sumHours != stats.Total {
		t.Errorf("sum(Hours) = %d, want %d", sumHours, stats.Total)
	}
	if sumWeekdays != stats.Total {
		t.Errorf("sum(Weekdays) = %d, want %d", sumWeekdays, stats.Total)
	}
}
func TestHourlyStats_NonexistentLink(t *testing.T) {
    st := newTestStore(t)
    got, err := st.HourlyStats(999999, 7)
    if err != nil {
        t.Fatalf("HourlyStats: %v", err)
    }
    if got.Total != 0 {
        t.Fatalf("Total = %d, want 0", got.Total)
    }
}
