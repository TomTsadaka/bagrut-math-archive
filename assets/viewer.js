const el = id => document.getElementById(id);
function esc(s){const d=document.createElement('div');d.textContent=s??'';return d.innerHTML}

const B = String.fromCharCode(92); // תו לוכסן אחורי, בלי בעיות escaping
const SYM = {
  'cdot':'·','times':'×','div':'÷','leq':'≤','le':'≤','geq':'≥','ge':'≥',
  'neq':'≠','ne':'≠','pm':'±','infty':'∞','alpha':'α','beta':'β','gamma':'γ',
  'theta':'θ','pi':'π','lambda':'λ','mu':'μ','Delta':'Δ','angle':'∠','perp':'⊥',
  'parallel':'∥','in':'∈','to':'→','Rightarrow':'⇒','approx':'≈','cdots':'⋯',
  'sin':'sin','cos':'cos','tan':'tan','log':'log','ln':'ln','left':'','right':''
};

// ממיר LaTeX נפוץ בשאלוני בגרות ל-HTML קריא
function tex(t){
  let x = esc(t);
  const fracRe = new RegExp(B+B+'frac\\s*\\{([^{}]*)\\}\\s*\\{([^{}]*)\\}','g');
  const sqrtRe = new RegExp(B+B+'sqrt\\s*\\{([^{}]*)\\}','g');
  x = x.replace(fracRe, (m,a,b) =>
    '<span class="frac"><span class="num">'+a+'</span><span class="den">'+b+'</span></span>');
  x = x.replace(sqrtRe, (m,a) => '√<span class="sqrt">'+a+'</span>');
  // סמלים — הארוכים קודם, כדי ש-leq לא ייבלע בתוך le
  Object.keys(SYM).sort((a,b)=>b.length-a.length).forEach(k=>{
    x = x.split(B+k).join(SYM[k]);
  });
  x = x.replace(/\^\{([^{}]*)\}/g,'<sup>$1</sup>').replace(/\^(\w)/g,'<sup>$1</sup>');
  x = x.replace(/_\{([^{}]*)\}/g,'<sub>$1</sub>').replace(/_(\w)/g,'<sub>$1</sub>');
  x = x.split('{').join('').split('}').join('');
  return '<span class="mth">'+x+'</span>';
}

// עברית נשארת טקסט; כל $...$ עובר רינדור מתמטי
function md(s){
  if(!s) return '';
  return String(s).split(/(\$[^$]*\$)/g).map(p =>
    (p.startsWith('$') && p.endsWith('$') && p.length>2)
      ? tex(p.slice(1,-1))
      : esc(p).replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>')
  ).join('');
}

function card(x){
  const parts = (x.parts||[]).map(p =>
    '<div class="part"><b>סעיף '+esc(p.letter)+'</b>'+
    (p.topic ? ' <span class="chip">'+esc(p.topic)+'</span>' : '')+
    (p.difficulty ? ' <span class="chip">קושי '+p.difficulty+'</span>' : '')+
    '<div class="body">'+md(p.body)+'</div></div>').join('');
  return '<div class="q"><div class="meta">'+
    '<span class="chip t">'+esc(x.topic||'—')+'</span>'+
    '<span class="chip d">קושי '+(x.difficulty??'—')+'</span>'+
    '<span class="chip">'+x.year+'</span>'+
    '<span class="chip">שאלון '+esc(x.code)+'</span>'+
    '<span class="chip">'+(x.units||'?')+' יח"ל</span>'+
    '<span class="chip">'+esc(x.moed||'')+'</span>'+
    (x.points ? '<span class="chip">'+x.points+' נק\'</span>' : '')+
    (x.est_minutes ? '<span class="chip">~'+x.est_minutes+' דק\'</span>' : '')+
    (x.has_figure ? '<span class="chip">כולל שרטוט</span>' : '')+
    '</div>'+
    ((x.figures||[]).length ? '<div class="figs">'+(x.figures||[]).map(f=>
        '<img class="fig" src="'+f+'" alt="שרטוט מתוך השאלה" loading="lazy">').join('')+'</div>' : '')+
    '<div class="body">'+md(x.body)+'</div>'+
    (parts ? '<div class="parts">'+parts+'</div>' : '')+
    ((x.skills||[]).length ? '<div class="skills">מיומנויות: '+
        esc((x.skills||[]).join(' · '))+'</div>' : '')+
    '</div>';
}

function render(){
  const q=el('q').value.trim(), u=el('units').value, t=el('topic').value,
        d=el('diff').value, y=el('year').value;
  const out = DATA.filter(x =>
      (!q || (x.body||'').includes(q) || (x.skills||[]).join(' ').includes(q)
           || (x.parts||[]).some(p=>(p.body||'').includes(q))) &&
      (!u || String(x.units)===u) && (!t || x.topic===t) &&
      (!d || String(x.difficulty)===d) && (!y || String(x.year)===y));
  el('count').textContent = out.length + ' שאלות';
  el('list').innerHTML = out.length ? out.map(card).join('')
      : '<div class="empty">לא נמצאו שאלות מתאימות</div>';
}

['q','units','topic','diff','year'].forEach(i=>{
  el(i).addEventListener('input',render);
  el(i).addEventListener('change',render);
});
render();
