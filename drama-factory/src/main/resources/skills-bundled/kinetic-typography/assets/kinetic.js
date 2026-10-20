// Kinetic typography helpers.
//
// splitWords(): split each headline line into per-word spans so words can cascade in
// one after another. Preserves inline child elements (e.g. a colored/gradient word, or a
// .crackword) as single word units, and sets a per-headline word index `--wi` used by the
// CSS stagger (see kinetic.css @keyframes wordrise).
//
// Expected markup:  <div class="head"><span class="ln"><span>Find the <span class="grad">cracks</span></span></span>...</div>
// After split:      each .ln contains <span class="wd" style="--wi:N">word</span> ... (inline children kept whole)
function splitWords(root=document){
  root.querySelectorAll('.head').forEach(head=>{ let wi=0;
    head.querySelectorAll('.ln').forEach(line=>{
      const src = line.querySelector(':scope > span') || line;
      const frag = document.createDocumentFragment();
      const addWord = child => { const w=document.createElement('span'); w.className='wd'; w.style.setProperty('--wi', wi++); w.appendChild(child); frag.appendChild(w); };
      [...src.childNodes].forEach(n=>{
        if (n.nodeType===3){ // text node → split on whitespace, keep real spaces between words
          n.textContent.split(/(\s+)/).forEach(p=>{ if(!p) return; if(/^\s+$/.test(p)) frag.appendChild(document.createTextNode(' ')); else addWord(document.createTextNode(p)); });
        } else addWord(n.cloneNode(true)); // element (colored word, .crackword, …) → one unit
      });
      line.innerHTML=''; line.appendChild(frag);
    });
  });
}

// Optional: drive the fracture of a .crackword in logical time (0 = solid, 1 = fully cracked).
// Call from your frame loop: setCrack(el, clamp((t - startSec) / durSec, 0, 1)).
function setCrack(el, p){ if(el) el.style.setProperty('--ck', Math.max(0, Math.min(1, p)).toFixed(3)); }

if (typeof window !== 'undefined'){ window.splitWords = splitWords; window.setCrack = setCrack; }
