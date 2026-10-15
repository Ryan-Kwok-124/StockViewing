"""Daily TradingView-based watchlist report -> docs/index.html (open by double-click, no server)

pip install requests vaderSentiment
python watchlist_report.py [--open] [--watchlist watchlist.txt]

Your TradingView watchlist can't be read automatically (no public API). Export it once:
TradingView > watchlist menu (...) > "Export list..." and save the file as watchlist.txt next to this script.
"""
import sys, re, json, pathlib, datetime as dt, webbrowser, requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

DEFAULT = ["NASDAQ:AAPL", "NASDAQ:LULU", "NASDAQ:TSLA", "HKEX:700", "TWSE:2330",
           "TVC:HSI", "SP:SPX", "NASDAQ:NDX", "CBOE:VIX"]
COLS = ["name", "description", "close", "change", "Recommend.All", "RSI", "MACD.macd", "MACD.signal", "Perf.1M"]
MK = {"HKEX": "hongkong", "TWSE": "taiwan", "TPEX": "taiwan", "TSE": "japan", "LSE": "uk", "SSE": "china",
      "SZSE": "china", "NASDAQ": "america", "NYSE": "america", "AMEX": "america", "NYSEARCA": "america",
      "SP": "america", "DJ": "america", "CBOE": "america"}
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
sia = SentimentIntensityAnalyzer()


def load(path):
    p = pathlib.Path(path)
    if not p.exists():
        return DEFAULT
    toks = re.split(r"[,\n]", p.read_text(encoding="utf-8", errors="ignore"))
    return [t.strip() for t in toks if ":" in t and not t.strip().startswith("#")]


def scan(tickers):
    """TradingView scanner: price + technical indicators for symbols like NASDAQ:AAPL."""
    out, by = {}, {}
    for t in tickers:
        by.setdefault(MK.get(t.split(":")[0], "global"), []).append(t)
    todo = list(by.items())
    for m, ts in todo + [("global", None)]:
        if ts is None:
            ts = [t for t in tickers if t not in out]
            if not ts:
                break
        r = S.post(f"https://scanner.tradingview.com/{m}/scan",
                   json={"symbols": {"tickers": ts}, "columns": COLS}, timeout=20)
        for d in r.json().get("data", []):
            out[d["s"]] = dict(zip(COLS, d["d"]))
    return out


def news(t):
    try:
        j = S.get("https://news-headlines.tradingview.com/v2/headlines",
                  params={"client": "web", "lang": "en", "symbol": t}, timeout=15).json()
        items = j.get("items", j) if isinstance(j, dict) else j
        return [i["title"] for i in items[:8] if i.get("title")]
    except Exception:
        return []


clip = lambda x, a=-1, b=1: max(a, min(b, x))


def score(d, sn):
    rec, rsi, c = d["Recommend.All"] or 0, d["RSI"] or 50, d["close"] or 1
    macd = clip(((d["MACD.macd"] or 0) - (d["MACD.signal"] or 0)) / c * 200)
    mom = clip((d["Perf.1M"] or 0) / 10)
    rev = -(rsi - 70) / 15 if rsi > 70 else (30 - rsi) / 15 if rsi < 30 else 0
    tech = 0.5 * rec + 0.2 * macd + 0.2 * mom + 0.1 * clip(rev)
    return tech, 0.7 * (tech + 1) / 2 + 0.3 * (sn + 1) / 2


rating = lambda s: ("STRONG BUY" if s >= .6 else "BUY" if s >= .54 else
                    "STRONG SELL" if s <= .4 else "SELL" if s <= .46 else "HOLD")


def row(t, d, hl):
    hs = [{"t": h, "s": round(sia.polarity_scores(h)["compound"], 2)} for h in hl]
    sn = sum(h["s"] for h in hs) / len(hs) if hs else 0.0
    tech, sc = score(d, sn)
    return dict(name=d["name"], desc=d["description"], symbol=t, price=d["close"], chg=round(d["change"] or 0, 2),
                rec=d["Recommend.All"] or 0, rsi=round(d["RSI"] or 50, 1), tech=round(tech, 3),
                sentiment=round(sn, 3), score=round(sc, 3), signal=rating(sc), headlines=hs[:4])


def discover(have, n=6):
    """Screen large liquid stocks on TradingView, rank by technicals, then check news on the finalists."""
    cands = []
    for m, cap in (("america", 1e10), ("hongkong", 2e10)):
        body = {"filter": [{"left": "market_cap_basic", "operation": "greater", "right": cap},
                           {"left": "type", "operation": "equal", "right": "stock"}],
                "options": {"lang": "en"}, "markets": [m], "symbols": {"query": {"types": []}, "tickers": []},
                "columns": COLS, "sort": {"sortBy": "Recommend.All", "sortOrder": "desc"}, "range": [0, 25]}
        try:
            for d in S.post(f"https://scanner.tradingview.com/{m}/scan", json=body, timeout=20).json()["data"]:
                if d["s"] not in have:
                    x = dict(zip(COLS, d["d"]))
                    cands.append((score(x, 0)[0], d["s"], x))
        except Exception as e:
            print("discover failed for", m, e)
    cands.sort(key=lambda c: -c[0])
    ideas = [row(s, x, news(s)) for _, s, x in cands[:12]]
    return sorted(ideas, key=lambda r: -r["score"])[:n]


TEMPLATE = r"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Watchlist Outlook</title>
<style>
:root{--bg:#fff;--card:#f5f6f8;--tx:#16181d;--mu:#6b7280;--sb:#067a4c;--b:#2fb67c;--h:#8a8f98;--s:#e8707f;--ss:#c4122f}
@media(prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#1a1d24;--tx:#e8eaed;--mu:#9aa0a9}}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,sans-serif}
h1{margin:12px 0 4px}h2{margin:28px 0 4px}.mu{color:var(--mu);font-size:13px}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:14px 0}
input,select,button{font:inherit;padding:8px 12px;border-radius:8px;border:1px solid var(--mu);background:var(--card);color:var(--tx)}
input{min-width:270px}button{cursor:pointer;font-weight:600}button:disabled{opacity:.5}
#err{color:var(--ss);font-weight:600}.sum{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.pill{padding:8px 14px;border-radius:999px;background:var(--card);font-weight:600}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}
.card{background:var(--card);border-radius:12px;padding:16px;border-left:6px solid var(--h)}
.card.STRONGBUY{border-color:var(--sb)}.card.BUY{border-color:var(--b)}.card.SELL{border-color:var(--s)}.card.STRONGSELL{border-color:var(--ss)}
.top{display:flex;justify-content:space-between;align-items:center;gap:8px}.top b{cursor:pointer}
.badge{padding:2px 10px;border-radius:6px;color:#fff;font-weight:700;font-size:13px;background:var(--h)}
.badge.STRONGBUY{background:var(--sb)}.badge.BUY{background:var(--b)}.badge.SELL{background:var(--s)}.badge.STRONGSELL{background:var(--ss)}
.bar{height:6px;border-radius:3px;background:var(--ss);margin:10px 0 4px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--sb)}ul{padding-left:18px;margin:8px 0 0;font-size:13px}
.pos{color:var(--sb)}.neg{color:var(--ss)}.rm{padding:0 8px;border:0;background:none;color:var(--mu);font-size:18px}
.ch{height:200px;margin:10px 0 6px;border-radius:8px;overflow:hidden}.full{width:100%;padding:6px}
.fu{animation:fu .6s}.fd{animation:fd .6s}@keyframes fu{from{background:#0a8f5b66}}@keyframes fd{from{background:#d6334a66}}
#modal{position:fixed;inset:0;background:#000b;z-index:9;display:flex;align-items:center;justify-content:center}#modal[hidden]{display:none}
.mb{width:min(1150px,96vw);height:88vh;background:var(--bg);border-radius:12px;padding:10px;display:flex;flex-direction:column;gap:8px}#mc{flex:1}
</style>
<div id="tv"></div>
<h1>Watchlist Outlook</h1>
<div class="mu" id="upd"></div>
<div class="row"><input id="q" placeholder="Stock number or code: 700, AAPL, TWSE:2330" autocomplete="off">
 <button id="add">Add &amp; analyze</button><span id="err"></span></div>
<div class="row"><label>Live update:
 <select id="iv"><option value="0">Off</option><option value="1000">Every 1 second</option><option value="30000">Every 30 seconds</option>
 <option value="60000">Every 1 minute</option><option value="300000">Every 5 minutes</option></select></label>
 <button id="re">Re-analyze all (with news)</button><span class="mu" id="st"></span></div>
<div class="sum" id="sum"></div><div class="grid" id="grid"></div>
<h2 id="ih" hidden>Ideas to research</h2>
<div class="mu" id="ihn" hidden>Large, liquid stocks that TradingView's technicals and the latest news currently favor. Starting points for your own research, not recommendations.</div>
<div class="grid" id="ideas" style="margin-top:12px"></div>
<div class="mu" style="margin-top:20px">Not financial advice. Rating = 70% TradingView technical indicators (aggregate rating, MACD, 1-month momentum, RSI extremes) + 30% news-headline sentiment. It is a rules-based outlook, not a trained forecast. Charts and the top ticker are TradingView widgets.</div>
<div id="modal" hidden><div class="mb"><button id="mx">Close ✕</button><div id="mc"></div></div></div>
<script>
const INIT=/*INIT*/[],IDEAS=/*IDEAS*/[],STAMP=/*STAMP*/'';
const PROXY='https://corsproxy.io/?url=';   // used only if the browser blocks direct requests; '' disables
const COLS=["name","description","close","change","Recommend.All","RSI","MACD.macd","MACD.signal","Perf.1M"];
const MK={HKEX:'hongkong',TWSE:'taiwan',TPEX:'taiwan',TSE:'japan',LSE:'uk',SSE:'china',SZSE:'china',NASDAQ:'america',NYSE:'america',AMEX:'america',NYSEARCA:'america',SP:'america',DJ:'america',CBOE:'america'};
const $=id=>document.getElementById(id),fmt=p=>p.toLocaleString(undefined,{maximumFractionDigits:2});
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const theme=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
let ex=[],rm=[],timer=null,busy=false,tapeKey='';
try{ex=JSON.parse(localStorage.getItem('ex'))||[];rm=JSON.parse(localStorage.getItem('rm'))||[]}catch(e){}
const save=()=>{try{localStorage.setItem('ex',JSON.stringify(ex));localStorage.setItem('rm',JSON.stringify(rm))}catch(e){}};
let rows=INIT.filter(r=>!rm.includes(r.symbol));

/* ---- TradingView data (same scoring as the Python script) ---- */
async function req(u,body){
  for(const x of [u,...(PROXY?[PROXY+encodeURIComponent(u)]:[])]){
    try{const r=await fetch(x,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});if(r.ok)return await r.json()}catch(e){}
  }
  throw 'net';
}
async function scan(ts){
  const out={},by={},put=j=>(j.data||[]).forEach(d=>out[d.s]=Object.fromEntries(COLS.map((c,i)=>[c,d.d[i]])));
  ts.forEach(t=>(by[MK[t.split(':')[0]]||'global']??=[]).push(t));
  await Promise.all(Object.entries(by).map(async([m,l])=>put(await req(`https://scanner.tradingview.com/${m}/scan`,{symbols:{tickers:l},columns:COLS}))));
  const miss=ts.filter(t=>!out[t]);
  if(miss.length)put(await req('https://scanner.tradingview.com/global/scan',{symbols:{tickers:miss},columns:COLS}));
  return out;
}
async function news(t){try{const j=await req('https://news-headlines.tradingview.com/v2/headlines?client=web&lang=en&symbol='+encodeURIComponent(t));
  return(j.items||j).slice(0,8).map(i=>i.title).filter(Boolean)}catch(e){return[]}}
const POS=new Set("beat beats surge surges soar soars gain gains rally rallies jump jumps rise rises record growth strong upgrade upgrades profit profits bullish buy outperform boost wins win higher".split(" "));
const NEG=new Set("miss misses fall falls drop drops plunge plunges slump slumps loss losses weak downgrade downgrades lawsuit probe cut cuts bearish sell decline declines warning warns fear fears lower recall tumble tumbles crash".split(" "));
const sent=t=>{let s=0;for(const w of t.toLowerCase().match(/[a-z]+/g)||[])s+=POS.has(w)?1:NEG.has(w)?-1:0;return s/Math.sqrt(s*s+4)};
const clip=(x,a=-1,b=1)=>Math.max(a,Math.min(b,x));
const rate=s=>s>=.6?'STRONG BUY':s>=.54?'BUY':s<=.4?'STRONG SELL':s<=.46?'SELL':'HOLD';
function calc(d,sn){
  const rec=d['Recommend.All']||0,rsi=d.RSI||50,c=d.close||1,
  macd=clip(((d['MACD.macd']||0)-(d['MACD.signal']||0))/c*200),mom=clip((d['Perf.1M']||0)/10),
  rev=rsi>70?-(rsi-70)/15:rsi<30?(30-rsi)/15:0,tech=.5*rec+.2*macd+.2*mom+.1*clip(rev),score=.7*(tech+1)/2+.3*(sn+1)/2;
  return{tech,score,signal:rate(score)};
}
function mkRow(t,d,hl){
  const hs=hl.map(x=>({t:x,s:sent(x)})),sn=hs.length?hs.reduce((a,b)=>a+b.s,0)/hs.length:0;
  return{name:d.name,desc:d.description,symbol:t,price:d.close,chg:d.change||0,rec:d['Recommend.All']||0,rsi:d.RSI||50,sentiment:sn,headlines:hs.slice(0,4),...calc(d,sn)};
}
async function resolveRow(q){
  q=q.trim().toUpperCase().replace(/\s/g,'');if(!/^[A-Z0-9.:^&_-]{1,20}$/.test(q))return null;
  const c=q.includes(':')?[q]:/^\d+$/.test(q)?['HKEX:'+parseInt(q),'TWSE:'+q]:['NASDAQ:'+q,'NYSE:'+q,'AMEX:'+q];
  for(const t of c){const d=(await scan([t]))[t];if(d&&d.close!=null)return mkRow(t,d,await news(t))}
  return null;
}

/* ---- widgets ---- */
function tvw(el,n,cfg){
  el.innerHTML='';const w=document.createElement('div');w.className='tradingview-widget-container';w.style.cssText='width:100%;height:100%';
  const i=document.createElement('div');i.className='tradingview-widget-container__widget';i.style.cssText='width:100%;height:100%';w.appendChild(i);
  const s=document.createElement('script');s.src=`https://s3.tradingview.com/external-embedding/embed-widget-${n}.js`;s.async=true;
  s.innerHTML=JSON.stringify({colorTheme:theme,theme,...cfg});w.appendChild(s);el.appendChild(w);
}
function tape(){
  const k=rows.map(r=>r.symbol).join();if(k===tapeKey||!rows.length)return;tapeKey=k;
  tvw($('tv'),'ticker-tape',{symbols:rows.map(r=>({proName:r.symbol,title:r.name})),isTransparent:true,displayMode:'adaptive',locale:'en'});
  $('tv').firstChild.style.height='78px';
}
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){io.unobserve(e.target);
  tvw(e.target,'mini-symbol-overview',{symbol:e.target.dataset.tv,width:'100%',height:'100%',locale:'en',dateRange:'12M',isTransparent:true,autosize:true})}}),{rootMargin:'200px'});
function openChart(s){$('modal').hidden=false;tvw($('mc'),'advanced-chart',{autosize:true,symbol:s,interval:'D',timezone:'Asia/Hong_Kong',style:'1',locale:'en',allow_symbol_change:true,support_host:'https://www.tradingview.com'})}
const closeChart=()=>{$('modal').hidden=true;$('mc').innerHTML=''};
$('mx').onclick=closeChart;$('modal').onclick=e=>{if(e.target.id==='modal')closeChart()};document.onkeydown=e=>{if(e.key==='Escape')closeChart()};

/* ---- rendering ---- */
const recLbl=x=>x>=.5?'Strong Buy':x>=.1?'Buy':x>-.1?'Neutral':x>-.5?'Sell':'Strong Sell';
const metrics=r=>`Score ${r.score.toFixed(2)} · TradingView technicals: ${recLbl(r.rec)} · RSI ${Math.round(r.rsi)} · News ${r.sentiment>=0?'+':''}${r.sentiment.toFixed(2)}`;
function card(r,idea){
  const k=r.signal.replace(' ',''),h=r.headlines.map(x=>`<li class="${x.s>.05?'pos':x.s<-.05?'neg':''}">${esc(x.t)}</li>`).join('')||'<li>No recent news</li>',S=esc(r.symbol);
  return `<div class="card ${k}" data-s="${S}"><div class="top"><b data-full="${S}" title="Open full chart">${esc(r.name)} <span class="mu">${S}</span></b>
  <span><span class="badge bdg ${k}">${r.signal}</span>${idea?`<button class="rm" data-watch="${S}" title="Add to watchlist" style="font-size:13px;border:1px solid var(--mu);border-radius:6px">+ Watch</button>`:`<button class="rm" data-rm="${S}" title="Remove">×</button>`}</span></div>
  <div class="mu">${esc(r.desc||'')}</div><div><span class="px">${fmt(r.price)}</span> <span class="chg ${r.chg>=0?'pos':'neg'}">${r.chg>=0?'+':''}${r.chg.toFixed(2)}%</span></div>
  <div class="bar"><i style="width:${r.score*100}%"></i></div><div class="mu sc">${metrics(r)}</div>
  <div class="ch" data-tv="${S}"></div><button class="full" data-full="${S}">📈 Full price history chart</button><ul>${h}</ul></div>`;
}
function sum(){
  $('sum').innerHTML=['STRONG BUY','BUY','HOLD','SELL','STRONG SELL'].map(l=>{const n=rows.filter(r=>r.signal===l).map(r=>esc(r.name)).join(', ');
    return n?`<span class="pill"><span class="badge ${l.replace(' ','')}">${l}</span> ${n}</span>`:''}).join('');
}
function render(){
  sum();$('grid').innerHTML=rows.map(r=>card(r,0)).join('');
  const id=IDEAS.filter(r=>!rows.some(x=>x.symbol===r.symbol));
  $('ih').hidden=$('ihn').hidden=!id.length;$('ideas').innerHTML=id.map(r=>card(r,1)).join('');
  document.querySelectorAll('.ch').forEach(e=>io.observe(e));tape();
}
const sortRender=()=>{rows.sort((a,b)=>b.score-a.score);render()};
function upd(r,old){
  const c=document.querySelector(`.card[data-s="${CSS.escape(r.symbol)}"]`);if(!c)return;const k=r.signal.replace(' ','');
  c.className='card '+k;c.querySelector('.px').textContent=fmt(r.price);
  const g=c.querySelector('.chg');g.textContent=(r.chg>=0?'+':'')+r.chg.toFixed(2)+'%';g.className='chg '+(r.chg>=0?'pos':'neg');
  const b=c.querySelector('.bdg');b.className='badge bdg '+k;b.textContent=r.signal;c.querySelector('.bar i').style.width=r.score*100+'%';c.querySelector('.sc').textContent=metrics(r);
  if(old!=null&&old!==r.price){const e=c.querySelector('.px').parentElement;e.classList.remove('fu','fd');void e.offsetWidth;e.classList.add(r.price>old?'fu':'fd')}
}

/* ---- actions ---- */
async function tick(){
  if(busy||!rows.length)return;busy=true;
  try{const d=await scan(rows.map(r=>r.symbol));
    for(const r of rows){const x=d[r.symbol];if(!x)continue;const old=r.price;
      Object.assign(r,{price:x.close,chg:x.change||0,rec:x['Recommend.All']||0,rsi:x.RSI||50},calc(x,r.sentiment));upd(r,old)}
    sum();$('st').textContent='Last tick '+new Date().toLocaleTimeString()}
  catch(e){$('st').textContent='Live update failed (offline or blocked)'}
  busy=false;
}
$('iv').onchange=()=>{clearInterval(timer);const ms=+$('iv').value;if(ms){tick();timer=setInterval(tick,ms)}else $('st').textContent='Live update off'};
async function analyzeAll(){
  $('re').disabled=true;$('upd').textContent='Analyzing…';
  try{const d=await scan(rows.map(r=>r.symbol));
    rows=await Promise.all(rows.map(async r=>d[r.symbol]?mkRow(r.symbol,d[r.symbol],await news(r.symbol)):r));
    sortRender();$('upd').textContent='Ratings updated '+new Date().toLocaleString()}
  catch(e){$('upd').textContent='Ratings from Python run: '+STAMP;$('err').textContent='⚠ Could not reach TradingView data from the browser (see notes).'}
  $('re').disabled=false;
}
function addRow(r){rows.push(r);if(!INIT.some(x=>x.symbol===r.symbol)&&!ex.includes(r.symbol))ex.push(r.symbol);rm=rm.filter(x=>x!==r.symbol);save();sortRender()}
async function add(){
  const v=$('q').value.trim();if(!v)return;$('err').textContent='';$('add').disabled=true;$('add').textContent='Analyzing…';
  try{const r=await resolveRow(v);
    if(!r)$('err').textContent=`⚠ '${v}' not found on TradingView. Check the number, or type the full code, e.g. HKEX:700, TWSE:2330, NASDAQ:AAPL.`;
    else if(rows.some(x=>x.symbol===r.symbol))$('err').textContent=`⚠ ${r.symbol} is already in your list.`;
    else{addRow(r);$('q').value=''}}
  catch(e){$('err').textContent='⚠ Could not reach TradingView data (blocked by the browser or offline). Try again.'}
  if($('err').textContent)$('q').focus();$('add').disabled=false;$('add').textContent='Add & analyze';
}
$('add').onclick=add;$('q').onkeydown=e=>{if(e.key==='Enter')add()};$('re').onclick=analyzeAll;
document.body.onclick=e=>{const t=e.target,d=t.dataset;
  if(d.full)openChart(d.full);
  else if(d.rm){rows=rows.filter(r=>r.symbol!==d.rm);ex=ex.filter(x=>x!==d.rm);if(INIT.some(r=>r.symbol===d.rm)&&!rm.includes(d.rm))rm.push(d.rm);save();render()}
  else if(d.watch){const r=IDEAS.find(x=>x.symbol===d.watch);if(r)addRow({...r})}};
(async()=>{
  render();$('upd').textContent='Ratings from Python run: '+STAMP;
  const m=ex.filter(s=>!rows.some(r=>r.symbol===s));
  if(m.length)try{const d=await scan(m);for(const s of m)if(d[s])rows.push(mkRow(s,d[s],await news(s)));sortRender()}catch(e){}
})();
</script>"""


def main():
    path = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--watchlist"), "watchlist.txt")
    syms = load(path)
    data = scan(syms)
    rows = []
    for t in syms:
        if t in data:
            rows.append(row(t, data[t], news(t)))
            print("ok  ", t)
        else:
            print("not found on TradingView:", t)
    rows.sort(key=lambda r: -r["score"])
    ideas = discover(set(syms))
    safe = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    page = (TEMPLATE.replace("/*INIT*/[]", safe(rows)).replace("/*IDEAS*/[]", safe(ideas))
            .replace("/*STAMP*/''", safe(dt.datetime.now().strftime("%Y-%m-%d %H:%M"))))
    out = pathlib.Path("docs")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    p = (out / "index.html").resolve()
    print("Wrote", p)
    if "--open" in sys.argv:
        webbrowser.open(p.as_uri())


if __name__ == "__main__":
    main()