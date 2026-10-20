// Capture real product screens at crisp 2x from a logged-in session, headful, saved to ./screens/.
// Pair with seed_capture_profile.sh (seeds .capdir with the user's auth). See CAPTURE_REAL_DASHBOARD.md.
//
//   node scripts/capture.js          # runs the STEPS below
//
// Why a seeded clean profile + pipe transport: launching the user's REAL Chrome profile makes
// puppeteer hang on "Target.setDiscoverTargets timed out" (too many tabs/extensions/targets).
// A clean .capdir + pipe:true + browser.newPage() launches reliably and stays logged in.
const puppeteer = require('puppeteer-core');
const fs = require('fs'), path = require('path');

// ---------------- CONFIG (edit me) ----------------
const CHROME  = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const WORK    = __dirname.replace(/\/scripts$/, '');     // project dir (parent of scripts/)
const USER_DATA_DIR = path.join(WORK, '.capdir');        // seeded by seed_capture_profile.sh
const BASE    = 'https://YOUR-DASHBOARD.example.com';    // <- set
const OUT     = path.join(WORK, 'screens');
const LOGGED_IN_TEXT = 'YOUR_HOME_TEXT';                 // <- a string only present once logged in
const VIEW    = { width: 1280, height: 720, deviceScaleFactor: 2 };  // 2x → 2560x1440 PNGs
const LOG     = path.join(WORK, 'capture.log');
// --------------------------------------------------

fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const w = s => { try { fs.appendFileSync(LOG, '['+new Date().toISOString()+'] '+s+'\n'); } catch(_){} };
process.on('unhandledRejection', e => { w('UNHANDLED '+(e&&e.stack||e)); process.exit(3); });
process.on('uncaughtException',  e => { w('UNCAUGHT '+(e&&e.stack||e)); process.exit(4); });
fs.writeFileSync(LOG, 'start '+new Date().toISOString()+'\n');

// ---- toolkit ----
async function goto(p, u){ w('goto '+u); await p.goto(BASE+u, {waitUntil:'networkidle2', timeout:60000}).catch(e=>w('navwarn '+e.message)); await sleep(3500); }
async function shot(p, name, full){ await p.screenshot({path:path.join(OUT, name+'.png'), fullPage:!!full}).catch(e=>w('shotfail '+name+' '+e.message)); w('shot '+name+(full?' (full)':'')); }
async function scrollTo(p, y){ await p.evaluate(yy=>window.scrollTo({top:yy, behavior:'instant'}), y); await sleep(700); }
// REAL pointer click (in-page el.click() does NOT open Radix/custom comboboxes or some React buttons)
async function clickByText(p, txt, {exact=false, tag=null, notRole=null}={}){
  const found = await p.evaluate((txt,exact,tag,notRole)=>{
    const els=[...document.querySelectorAll(tag||'button,[role=button],[role=tab],[role=option],[role=combobox],a,div,span,li')].filter(e=>e.offsetParent!==null);
    let m=els.filter(e=>{const t=(e.innerText||'').trim(); const ok=exact?t===txt:t.includes(txt); if(!ok)return false; if(notRole&&e.getAttribute('role')===notRole)return false; return true;});
    m.sort((a,b)=>(a.innerText||'').length-(b.innerText||'').length);
    if(!m[0])return false; m[0].setAttribute('data-capx','1'); return true;
  }, txt, exact, tag, notRole);
  if(!found){ w('NOTFOUND "'+txt+'"'); return false; }
  await p.click('[data-capx="1"]').catch(e=>w('clickerr "'+txt+'" '+e.message));
  await p.evaluate(()=>{const e=document.querySelector('[data-capx]'); if(e)e.removeAttribute('data-capx');}).catch(()=>{});
  w('clicked "'+txt+'"'); return true;
}
// type via REAL keystrokes (setting .value often doesn't update React state)
async function typeInto(p, selectorOrBiggestTextarea, text){
  let sel = selectorOrBiggestTextarea;
  if(sel === '@biggest-textarea'){
    const ok = await p.evaluate(()=>{ const t=[...document.querySelectorAll('textarea')].filter(x=>x.offsetParent!==null).sort((a,b)=>b.clientWidth*b.clientHeight-a.clientWidth*a.clientHeight)[0]; if(!t)return false; t.setAttribute('data-capx','1'); return true; });
    if(!ok){ w('no textarea'); return false; } sel='[data-capx="1"]';
  }
  await p.click(sel, {clickCount:3}).catch(e=>w('focuserr '+e.message)); await sleep(120);
  await p.keyboard.press('Backspace'); await sleep(80);
  await p.keyboard.type(text, {delay:6});
  await p.evaluate(()=>{const e=document.querySelector('[data-capx]'); if(e)e.removeAttribute('data-capx');}).catch(()=>{});
  w('typed '+text.length+' chars'); return true;
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: false, userDataDir: USER_DATA_DIR, pipe: true,
    timeout: 120000, protocolTimeout: 180000,
    args: ['--no-first-run','--no-default-browser-check','--restore-last-session=false','--hide-crash-restore-bubble'],
    defaultViewport: VIEW, ignoreDefaultArgs: ['--enable-automation'],
  });
  const page = await browser.newPage();
  await page.setViewport(VIEW);

  // ---- patient login wait (DON'T re-navigate every tick — that interrupts SSO redirects) ----
  await goto(page, '/');
  let ok = await page.evaluate(t => document.body.innerText.includes(t), LOGGED_IN_TEXT).catch(()=>false);
  if(!ok){
    w('not logged in — sign in IN THIS WINDOW (up to 240s)');
    for(let i=0;i<80;i++){ await sleep(3000);
      ok = await page.evaluate(t => document.body.innerText.includes(t), LOGGED_IN_TEXT).catch(()=>false);
      if(ok) break;
      if(i>0 && i%10===0){ await page.goto(BASE+'/', {waitUntil:'networkidle2', timeout:60000}).catch(()=>{}); } // gentle nudge only
    }
  }
  w('logged in: '+ok);
  if(!ok){ w('aborting — not authenticated'); await browser.close(); process.exit(2); }

  // ================= STEPS (edit me) =================
  try {
    await goto(page, '/home');                 await shot(page, '01_home');
    // dropdown that lists everything (real click to open, screenshot while open):
    // await clickByText(page, 'FHE Inference (Tool Router)');  await sleep(900); await shot(page, '02_scenarios_open');
    // interactive before/after:
    // await typeInto(page, '@biggest-textarea', 'User is requesting a refund...');  await shot(page, '03_before');
    // await clickByText(page, 'Run', {exact:true, tag:'button'});  await sleep(9000); await shot(page, '04_after');
    // tall page: await scrollTo(page, 650); await shot(page, '05_scrolled'); await scrollTo(page, 0);
  } catch(e){ w('ERROR '+e.message); }
  // ===================================================

  w('DONE'); await browser.close();
})();
