// Helpers for the liquid-glass card model (pair with glass.css).

// Lay out a cardstage's .lcard children in a rows×cols grid (positions in % of the stage).
// gap/pad are in %. Cards keep these base positions; raise() temporarily overrides via .up.
function placeGrid(stage, cols, rows, {gap=4, padX=2, padY=8} = {}){
  const cards = [...stage.querySelectorAll('.lcard')];
  const w = (100 - padX*2 - gap*(cols-1)) / cols;
  const h = (100 - padY*2 - gap*(rows-1)) / rows;
  cards.forEach((c,i)=>{ const r=Math.floor(i/cols), col=i%cols;
    c.style.left = (padX + col*(w+gap)) + '%'; c.style.top = (padY + r*(h+gap)) + '%';
    c.style.width = w + '%'; c.style.height = h + '%';
  });
}

// Zoom one card forward to demo; dim the rest. Call with a different key/index to make the
// current one FALL BACK and the next rise. Pass null to drop everything back to the grid.
function raise(stage, keyOrIndex){
  const cards = [...stage.querySelectorAll('.lcard')];
  cards.forEach((c,i)=>{
    const on = keyOrIndex!=null && (c.dataset.k===keyOrIndex || i===keyOrIndex);
    c.classList.toggle('up', on);
    c.classList.toggle('dim', keyOrIndex!=null && !on);
  });
}

// Reveal the cards (triggers the staggered cardIn entrance). Add .cardsin to the scene/stage.
function revealCards(el){ el.classList.add('cardsin'); }

// Camera: gentle zoom-in on enter, then settle. Give .world a slight scale, then after a beat
// set it back to 1.0 — the CSS transition (1.6s) does the move. estHold scales with __RATE so it
// renders correctly under the smooth-render slow clock.
function applyCam(world, scale){ world.style.transform = `scale(${scale})`; }
function enterScene(world, { from=1.06, to=1.0, holdMs=300 } = {}){
  applyCam(world, from);
  setTimeout(()=>applyCam(world, to), holdMs / (window.__RATE||1));
}

if (typeof window !== 'undefined') Object.assign(window, { placeGrid, raise, revealCards, applyCam, enterScene });
