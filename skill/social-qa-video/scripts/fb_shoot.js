// Chup anh that cua bai dang + binh luan tu trang Facebook da luu (Ctrl+S).
// Lam mo ten that, giu nguyen nickname tu sinh.
//
// Dung: node shot/shoot.js <file.html> <targets.json> <thu-muc-xuat>
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const [FILE, TARGETS, OUTDIR] = process.argv.slice(2);

(async () => {
  const targets = JSON.parse(fs.readFileSync(TARGETS, 'utf8'));
  fs.mkdirSync(OUTDIR, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--use-gl=swiftshader', '--no-sandbox', '--allow-file-access-from-files',
           '--hide-scrollbars', '--disable-dev-shm-usage'],
    // Khung nhin rat cao: binh luan Facebook nam trong vung cuon rieng,
    // cach dau trang hang nghin px. De khung nhin du cao thi moi khoi deu
    // nam san trong tam chup, khong phai cuon -> toa do khong bi xe dich.
    defaultViewport: { width: 900, height: 18000, deviceScaleFactor: 3 },
  });
  const page = await browser.newPage();
  await page.goto('file:///' + path.resolve(FILE).replace(/\\/g, '/'),
                  { waitUntil: 'load', timeout: 120000 });
  await new Promise(r => setTimeout(r, 3000));

  // don giao dien: an popup, overlay, nut noi
  await page.addStyleTag({ content: `
    ::-webkit-scrollbar { display:none !important; }
  `});

  // phong to layout de chu trong anh chup lon hon khi dat len video doc
  const ZOOM = parseFloat(process.env.SHOT_ZOOM || '1');
  if (ZOOM !== 1) {
    await page.evaluate((z) => { document.body.style.zoom = String(z); }, ZOOM);
    await new Promise(r => setTimeout(r, 1500));
  }

  const report = [];
  for (const t of targets) {
    const handle = await page.evaluateHandle((t) => {
      const arts = [...document.querySelectorAll('div[role="article"]')];
      let el = null;

      if (t.kind === 'comment') {
        // Facebook co the render trung cung mot binh luan o 2 noi,
        // ban sao an co kich thuoc 0x0 nen phai chon ban dang hien thi.
        const matches = arts.filter(a => (a.innerText || '').includes(t.needle));
        // article long nhau: container lon chua nhieu binh luan cung khop needle,
        // nen phai chon khoi NHO NHAT (it chu nhat) ma van dang hien thi.
        matches.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
        // Chi nhan ban DANG duoc ve that va KHONG bi lop khac che.
        // Trang co the mo dialog de len feed; element phia duoi van co
        // kich thuoc nhung vung do tren man hinh lai la cua lop tren.
        for (const a of matches) {
          const r0 = a.getBoundingClientRect();
          if (r0.width < 50 || r0.height < 20) continue;
          const r = a.getBoundingClientRect();
          const cx = r.x + r.width / 2;
          const cy = r.y + Math.min(25, r.height / 2);
          const top = document.elementFromPoint(cx, cy);
          if (top && (a === top || a.contains(top))) { el = a; break; }
        }
      } else {
        // bai dang: tim node text roi di len den khoi rong ~700px
        // Duyet moi ban sao cua doan text, chi nhan ban DANG duoc ve that.
        const need = t.requireAll && t.requireAll.length ? t.requireAll : [t.needle];
        const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let n;
        while ((n = w.nextNode())) {
          if (!(n.textContent || '').includes(t.needle)) continue;
          let p = n.parentElement, cand = null;
          for (let i = 0; i < 20 && p; i++) {
            const r = p.getBoundingClientRect();
            const txt = p.textContent || '';
            if (need.every(s => txt.includes(s)) && r.width >= 300 &&
                r.height >= 60 && r.height <= 1500) { cand = p; break; }
            p = p.parentElement;
          }
          if (cand) { el = cand; break; }
        }
      }
      if (!el) return null;

      // an cac overlay noi (cua so chat, banner goc man hinh) de khong che anh chup
      for (const f of document.querySelectorAll('div,span,section')) {
        if (f.contains(el) || el.contains(f)) continue;
        const cs = getComputedStyle(f);
        if (cs.position === 'fixed' || cs.position === 'sticky') {
          const r = f.getBoundingClientRect();
          if (r.width > 40 && r.height > 40) f.style.display = 'none';
        }
      }

      // Mot so ban luu co ca nhanh bi visibility:hidden -> ep hien lai
      let anc = el;
      while (anc && anc !== document.documentElement) {
        const cs = getComputedStyle(anc);
        if (cs.visibility === 'hidden') anc.style.visibility = 'visible';
        if (cs.display === 'none') anc.style.display = 'block';
        if (parseFloat(cs.opacity) === 0) anc.style.opacity = '1';
        if (anc.hasAttribute('hidden')) anc.removeAttribute('hidden');
        if (anc.getAttribute('aria-hidden') === 'true') anc.removeAttribute('aria-hidden');
        anc = anc.parentElement;
      }

      // ep hien ca phan ben trong
      for (const d of el.querySelectorAll('*')) {
        const cs = getComputedStyle(d);
        if (cs.visibility === 'hidden') d.style.visibility = 'visible';
        if (cs.display === 'none') d.style.display = '';
        if (parseFloat(cs.opacity) === 0) d.style.opacity = '1';
        if (t.forceInk) d.style.color = '#050505';
      }
      if (t.forceInk) el.style.color = '#050505';

      // lam mo ten that neu duoc yeu cau
      if (t.blurName) {
        const links = [...el.querySelectorAll('a')];
        for (const a of links) {
          const href = a.getAttribute('href') || '';
          if (href.includes('/user/') || href.includes('/profile.php')) {
            a.style.filter = 'blur(7px)';
            a.style.opacity = '0.85';
          }
        }
        // ten dang span khong phai link (vd trong header bai dang)
        if (t.blurExtraText) {
          const w2 = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
          let m;
          while ((m = w2.nextNode())) {
            if ((m.textContent || '').trim() === t.blurExtraText && m.parentElement) {
              m.parentElement.style.filter = 'blur(7px)';
            }
          }
        }
      }

      // bo cac nut tuong tac o cuoi cho gon (Tra loi / Chia se / Gui tin nhan)
      if (t.hideActions) {
        for (const d of el.querySelectorAll('div[role="button"], span[role="button"]')) {
          const txt = (d.innerText || '').trim();
          if (/^(Trả lời|Chia sẻ|Gửi tin nhắn|Theo dõi|Thích)$/.test(txt)) {
            d.style.display = 'none';
          }
        }
      }

      // nen trang + bo goc cho hop voi video.
      // Bai dang dang "background post" co chu trang tren nen gradient:
      // ghi de nen trang se lam chu tang hinh, nen phai giu nguyen nen goc.
      if (!t.keepBackground) el.style.background = '#ffffff';
      el.style.borderRadius = '22px';
      if (!t.keepBackground) el.style.padding = '18px 20px';
      el.style.boxSizing = 'content-box';
      return el;
    }, t);

    const el = handle.asElement();
    if (!el) { console.log(`!! KHONG TIM THAY: ${t.key} (${t.needle.slice(0, 40)})`); continue; }

    // an overlay + ep hien lam layout xe dich; cuon lai va cho on dinh
    // truoc khi do toa do, neu khong anh chup se lech sang khoi khac.
    await new Promise(r => setTimeout(r, 700));

    // Lay toa do theo KHUNG NHIN roi chup khung nhin va cat theo do.
    // el.screenshot()/clip mac dinh dung toa do document, bi lech khi trang
    // co zoom hoac nhieu lop cuon -> anh ra khoi khac.
    // Facebook render kieu danh sach ao: cuon xong vi tri con dich them vai
    // nhip, nen phai doi toa do dung yen roi moi chup.
    const read = () => el.evaluate((n) => {
      const r = n.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height };
    });
    let box = await read();
    for (let k = 0; k < 10; k++) {
      await new Promise(r => setTimeout(r, 350));
      const again = await read();
      if (Math.abs(again.y - box.y) < 1 && Math.abs(again.height - box.height) < 1) {
        box = again;
        break;
      }
      box = again;
    }
    if (!box || box.width < 10 || box.height < 10) {
      console.log(`!! KICH THUOC LOI: ${t.key} ${JSON.stringify(box)}`);
      continue;
    }
    const out = path.join(OUTDIR, `${t.key}.png`);
    await page.screenshot({
      path: out,
      captureBeyondViewport: false,
      clip: { x: Math.max(0, box.x), y: Math.max(0, box.y),
              width: box.width, height: box.height },
    });
    const text = await el.evaluate(n => (n.innerText || '').slice(0, 80));
    console.log(`${t.key}: ${Math.round(box.width)}x${Math.round(box.height)} -> ${out}`);
    console.log(`       text: ${JSON.stringify(text.replace(/s+/g, " ").slice(0, 70))}`);
    report.push({ key: t.key, w: box.width, h: box.height, text });
  }

  fs.writeFileSync(path.join(OUTDIR, 'report.json'), JSON.stringify(report, null, 2));
  await browser.close();
})();
