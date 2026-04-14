#!/usr/bin/env python3
"""Surf Dashboard — Port-Louis (Guadeloupe) + Tartane (Martinique).
Usage: python3 surf_antilles.py"""

import json, os
from datetime import datetime, timezone, timedelta
import requests

SPOTS_CFG = [
    {"nom": "Port-Louis · Guadeloupe", "lat": 16.43,  "lng": -61.54, "tz": "America/Guadeloupe"},
    {"nom": "Tartane · Martinique",    "lat": 14.745, "lng": -60.895, "tz": "America/Martinique"},
]

AST      = timedelta(hours=-4)
DIRS     = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
JOURS_FR = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
CRENEAUX = {5, 8, 11, 14, 17, 20}

def deg_to_dir(deg):
    if deg is None: return "—"
    return DIRS[round(float(deg) / 22.5) % 16]

def utc_to_ast(t):
    return t + AST


# ─── Fetch un spot ────────────────────────────────────────────────────────────
def fetch_spot(lat, lng, tz, nom):
    print(f"Fetching Marine — {nom}...")
    om = requests.get("https://marine-api.open-meteo.com/v1/marine", params={
        "latitude": lat, "longitude": lng,
        "hourly": "sea_level_height_msl,wave_height,wave_direction,wave_period,swell_wave_height,swell_wave_direction,swell_wave_period",
        "forecast_days": 16,
        "timezone": tz,
    }, timeout=15).json()

    print(f"Fetching Vent — {nom}...")
    ow = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lng,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": 16,
        "timezone": tz,
        "wind_speed_unit": "kmh",
    }, timeout=15).json()

    print(f"  OK — {len(om['hourly']['time'])} heures")
    return om, ow


# ─── Détecter HM/BM ──────────────────────────────────────────────────────────
def detect_marees(times, levels):
    marees = []
    n = len(levels)
    i = 1
    while i < n - 1:
        if levels[i] is None or levels[i-1] is None:
            i += 1; continue
        j = i
        while j + 1 < n and levels[j+1] is not None and levels[j+1] == levels[i]:
            j += 1
        if j + 1 >= n or levels[j+1] is None:
            break
        after, before = levels[j+1], levels[i-1]
        t_loc = datetime.fromisoformat(times[i])
        h_dec = round(t_loc.hour + t_loc.minute / 60, 2)
        if levels[i] > before and levels[i] > after:
            marees.append({"jour": t_loc.day, "mois": t_loc.month, "h": h_dec, "m": round(levels[i], 2), "type": "H"})
        elif levels[i] < before and levels[i] < after:
            marees.append({"jour": t_loc.day, "mois": t_loc.month, "h": h_dec, "m": round(levels[i], 2), "type": "L"})
        i = j + 1
    print(f"  Marées: {len(marees)}")
    return marees


# ─── Process un spot ──────────────────────────────────────────────────────────
def process_spot(om, ow, nom):
    times  = om["hourly"]["time"]
    levels = om["hourly"]["sea_level_height_msl"]
    marees = detect_marees(times, levels)

    previsions = []
    now_ast    = utc_to_ast(datetime.now(timezone.utc))

    for i, t in enumerate(times):
        t_ast   = datetime.fromisoformat(t)
        h_local = t_ast.hour
        if h_local not in CRENEAUX:
            continue

        wh  = om["hourly"]["wave_height"][i]          or 0
        wp  = om["hourly"]["wave_period"][i]           or 0
        wd  = om["hourly"]["wave_direction"][i]
        sh  = om["hourly"]["swell_wave_height"][i]     or 0
        sp  = om["hourly"]["swell_wave_period"][i]     or 0
        sd  = om["hourly"]["swell_wave_direction"][i]
        ws  = ow["hourly"]["wind_speed_10m"][i]        or 0
        wsd = ow["hourly"]["wind_direction_10m"][i]

        energie = round(wh**2 * wp**2 * 2)

        previsions.append({
            "label":   f"{JOURS_FR[t_ast.weekday()]} {t_ast.day}",
            "jour":    t_ast.day,
            "mois":    t_ast.month,
            "heure":   h_local,
            "dt":      t,
            "wh":      round(wh, 1),
            "wp":      round(wp, 1),
            "wd":      deg_to_dir(wd),
            "sh":      round(sh, 1),
            "sp":      round(sp, 1),
            "sd":      deg_to_dir(sd),
            "energie": energie,
            "vent":    round(ws),
            "vdir":    deg_to_dir(wsd),
        })

    alertes = [f"⚠ Vent {p['vent']}km/h — {p['label']} {p['heure']:02d}h"
               for p in previsions[:24] if p["vent"] >= 35]

    return {
        "nom":        nom,
        "updated":    now_ast.strftime("%a %d %b %Y %Hh%M"),
        "alertes":    alertes,
        "marees":     marees,
        "previsions": previsions,
    }


# ─── Debug ────────────────────────────────────────────────────────────────────
def debug(spots):
    for s in spots:
        print(f"\n{'='*70}")
        print(f"{s['nom']} — {s['updated']}")
        print(f"{'─'*70}")
        for p in s["previsions"][:6]:
            print(f"  {p['label']} {p['heure']:02d}h  sh={p['sh']}m sp={p['sp']}s e={p['energie']}  vent={p['vent']}km")
    print(f"{'='*70}\n")


# ─── CSS ─────────────────────────────────────────────────────────────────────
CSS = """
:root {
  --bg:   #f4f2ef;
  --bg2:  #eceae6;
  --card: #ffffff;
  --bdr:  #dedad4;
  --sep:  #c8c4bc;
  --txt:  #1a1a1a;
  --mut:  #888;
  --fnt:  #bbb;
  --lw:   68px;
  --cw:   52px;
  --gh:   38px;  /* gauge cell height */
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--txt); font-family: 'IBM Plex Mono', monospace; font-size: 11px; min-height: 100vh; }

.ghdr { padding: 10px 14px; border-bottom: 1px solid var(--bdr); display: flex; justify-content: space-between; align-items: center; background: var(--card); position: sticky; top: 0; z-index: 200; }
.ghdr-l { display: flex; align-items: baseline; gap: 10px; }
.gtitle { font-size: 9px; letter-spacing: 5px; color: var(--mut); text-transform: uppercase; font-weight: 300; }
#upd    { font-size: 8px; color: var(--fnt); letter-spacing: 1px; margin-top: 2px; }
.btn    { background: transparent; border: 1px solid var(--bdr); color: var(--mut); padding: 4px 11px; font-family: inherit; font-size: 9px; letter-spacing: 2px; text-transform: uppercase; cursor: pointer; }
.btn:hover { border-color: #999; color: var(--txt); }

.spot-hdr { padding: 8px 14px; background: var(--bg2); border-top: 2px solid var(--sep); border-bottom: 1px solid var(--bdr); display: flex; align-items: baseline; gap: 10px; }
.spot-name    { font-size: 9px; letter-spacing: 4px; text-transform: uppercase; color: var(--mut); font-weight: 300; }
.spot-verdict { font-size: 15px; letter-spacing: 3px; font-weight: 300; }
.spot-upd     { font-size: 8px; color: var(--fnt); margin-left: auto; }
.alerts { padding: 5px 14px; background: #fdf5e8; border-bottom: 1px solid #e8d8a0; font-size: 9px; color: #8a6020; }

.wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.tbl  { border-collapse: collapse; table-layout: fixed; }

.lbl {
  position: sticky; left: 0; z-index: 10;
  width: var(--lw); min-width: var(--lw); max-width: var(--lw);
  background: var(--bg); border-right: 1px solid var(--sep); border-bottom: 1px solid var(--bdr);
  text-align: right; padding: 0 7px; font-size: 8px; letter-spacing: 1px; color: var(--fnt);
  font-weight: 300; text-transform: uppercase; white-space: nowrap; vertical-align: middle;
}
.lbl.sect { background: var(--bg2); color: var(--mut); font-size: 7.5px; border-bottom: 1px solid var(--sep); font-weight: 400; }

.dc {
  width: var(--cw); min-width: var(--cw); max-width: var(--cw);
  border-bottom: 1px solid var(--bdr); border-right: 1px solid #ebe8e3;
  text-align: center; vertical-align: middle; white-space: nowrap; position: relative;
  padding: 0;
}
.dc.sep { border-left: 2px solid var(--sep); }

/* Row heights */
tr.r-day  td { height: 22px; background: var(--bg2); border-bottom: 1px solid var(--sep); }
tr.r-time td { height: 26px; background: var(--card); }
tr.r-sect td { height: 11px; background: var(--bg2); border-bottom: 1px solid var(--sep); }
tr.r-vdir td { height: 26px; background: #fafaf8; }
tr.r-vkmh td { height: var(--gh); background: var(--card); }
tr.r-wdir td { height: 26px; background: #fafaf8; }
tr.r-wh   td { height: var(--gh); background: var(--card); }
tr.r-wp   td { height: var(--gh); background: #fafaf8; }
tr.r-wkj  td { height: var(--gh); background: var(--card); }
tr.r-marr td { height: 26px; background: #fafaf8; }
tr.r-mhbm td { height: 26px; background: var(--card); }
tr.r-mm   td { height: 26px; background: #fafaf8; }

/* Sticky label bg */
tr.r-day  .lbl { background: var(--bg2); }
tr.r-time .lbl { background: var(--bg); }
tr.r-sect .lbl { background: var(--bg2); }
tr.r-vdir .lbl { background: #f5f3f0; }
tr.r-vkmh .lbl { background: var(--bg); }
tr.r-wdir .lbl { background: #f5f3f0; }
tr.r-wh   .lbl { background: var(--bg); }
tr.r-wp   .lbl { background: #f5f3f0; }
tr.r-wkj  .lbl { background: var(--bg); }
tr.r-marr .lbl { background: #f5f3f0; }
tr.r-mhbm .lbl { background: var(--bg); }
tr.r-mm   .lbl { background: #f5f3f0; }

.day-cell  { font-size: 8.5px; letter-spacing: 2px; text-transform: uppercase; color: var(--mut); font-weight: 400; padding: 0 4px; }
.day-cell.today { color: #2d7a52; font-weight: 500; }
.time-cell { font-size: 10px; color: var(--mut); font-weight: 300; }
.time-cell.is-now  { color: #2d7a52; font-weight: 600; background: #e8f2ec; }
.time-cell.is-best { color: #8a6e2a; font-weight: 500; background: #f5f2ea; }

/* ── GAUGE ── */
.gauge-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: var(--gh);
  padding: 0 0 2px;
  gap: 1px;
}
.gauge-track {
  width: 100%;
  height: 24px;
  background: #eae7e2;
  position: relative;
  overflow: hidden;
  flex-shrink: 0;
}
.gauge-fill {
  position: absolute;
  bottom: 0; left: 0; right: 0;
}
.gauge-val {
  font-size: 9px;
  line-height: 1;
  font-weight: 400;
  color: var(--mut);
}

.foot { padding: 7px 14px; font-size: 8px; color: var(--fnt); border-top: 1px solid var(--bdr); font-style: italic; }
"""

# ─── JS ──────────────────────────────────────────────────────────────────────
JS = r"""
const PROP_DEG={N:180,NNE:202,NE:225,ENE:247,E:270,ESE:292,SE:315,SSE:337,S:0,SSW:22,SW:45,WSW:67,W:90,WNW:112,NW:135,NNW:157};

const arr=(dir,col,sz=13)=>`<span style="display:inline-block;transform:rotate(${PROP_DEG[dir]||0}deg);color:${col};font-size:${sz}px;line-height:1">↑</span>`;
const wCol=v=>v>=30?'#a03030':v>=20?'#8a6e2a':'#2d7a52';
const hCol=h=>h>=1.5?'#1e6a42':h>=0.8?'#3a8a62':h>=0.4?'#5aaa82':'#aaa';
const pCol=p=>p>=12?'#1e5f8a':p>=9?'#3a7aaa':p>=7?'#6a9aba':'#aaa';
const eCol=e=>e>=150?'#2a6a44':e>=50?'#5a7a44':'#bbb';

// Gauge cell HTML
// val=value, max=scale max, col=fill color, label=display string
function gauge(val, max, col, label) {
  const pct = Math.min(val / max * 100, 100);
  return `<div class="gauge-cell">
    <div class="gauge-track">
      <div class="gauge-fill" style="height:${pct}%;background:${col}"></div>
    </div>
    <span class="gauge-val" style="color:${col}">${label}</span>
  </div>`;
}

function verdict(prev,now){
  const fut=prev.filter(x=>new Date(x.dt)>=now).slice(0,24);
  if(!fut.length)return{v:'—',c:'#999'};
  const b=Math.max(...fut.map(x=>x.energie));
  return b>=150?{v:'GO',c:'#2d7a52'}:b>=50?{v:'BORDERLINE',c:'#8a6e2a'}:{v:'NO-GO',c:'#a03030'};
}
function verdictJour(slots){
  const b=Math.max(...slots.map(x=>x.energie));
  return b>=150?{v:'GO',c:'#2d7a52'}:b>=50?{v:'BORDERLINE',c:'#8a6e2a'}:{v:'NO-GO',c:'#a03030'};
}
function nextTide(marees,jour,mois,heure){
  if(!marees||!marees.length)return null;
  const s=[...marees].sort((a,b)=>(a.jour*10000+a.mois*100+a.h)-(b.jour*10000+b.mois*100+b.h));
  for(const m of s) if(m.jour*10000+m.mois*100+m.h>jour*10000+mois*100+heure)return m;
  return null;
}
function tHStr(m){
  const h=Math.floor(m.h),mn=Math.round((m.h-h)*60);
  return String(h).padStart(2,'0')+'h'+(mn>0?String(mn).padStart(2,'0'):'');
}

function buildTable(S,now){
  const nowMs=now.getTime(),ms72=72*3600*1000;
  let curKey=null,minDiff=Infinity;
  for(const p of S.previsions){const d=Math.abs(new Date(p.dt).getTime()-nowMs);if(d<minDiff){minDiff=d;curKey=p.dt;}}
  const fut72=S.previsions.filter(p=>new Date(p.dt)>=now&&new Date(p.dt).getTime()-nowMs<=ms72);
  const bestKey=fut72.length?fut72.reduce((a,b)=>b.energie>a.energie?b:a).dt:null;

  const days=[];let cd=null;
  for(const p of S.previsions){if(!cd||cd.label!==p.label){cd={label:p.label,slots:[]};days.push(cd);}cd.slots.push(p);}

  const P=S.previsions;
  const R={day:[],time:[],vdir:[],vkmh:[],wdir:[],wh:[],wp:[],wkj:[],marr:[],mhbm:[],mm:[]};

  days.forEach((day,di)=>{
    const vj=verdictJour(day.slots);
    day.slots.forEach((s,si)=>{
      const isFirst=si===0,isSep=isFirst&&di>0,sc=isSep?' sep':'';
      const isNow=s.dt===curKey,isBest=s.dt===bestKey;
      const tide=nextTide(S.marees,s.jour,s.mois,s.heure);
      const tc=tide?(tide.type==='H'?'#2a5a8a':'#8a6a2a'):'#bbb';
      const badge=isNow?' <span style="font-size:8px;color:#2d7a52">◀</span>':isBest?' <span style="font-size:8px;color:#8a6e2a">★</span>':'';

      if(isFirst) R.day.push(`<td class="dc day-cell${sc}${di===0?' today':''}" colspan="${day.slots.length}" style="color:${vj.c}">${day.label}&nbsp;<span style="font-size:7px;opacity:.6">${vj.v}</span></td>`);

      R.time.push(`<td class="dc time-cell${sc}${isNow?' is-now':isBest?' is-best':''}">${String(s.heure).padStart(2,'0')}h${badge}</td>`);

      // Vent dir
      R.vdir.push(`<td class="dc${sc}">${arr(s.vdir,wCol(s.vent))}</td>`);
      // Vent km/h — jauge
      R.vkmh.push(`<td class="dc${sc}">${gauge(s.vent, 50, '#7aaa88', s.vent)}</td>`);

      // Vague dir
      R.wdir.push(`<td class="dc${sc}">${arr(s.wd,hCol(s.wh))}</td>`);
      // Vague m — jauge
      R.wh.push(`<td class="dc${sc}">${gauge(s.wh, 3, '#6a9aba', s.wh+'m')}</td>`);
      // Vague s — jauge
      R.wp.push(`<td class="dc${sc}">${gauge(s.wp, 15, '#4a7aaa', s.wp+'s')}</td>`);
      // kJ — jauge
      R.wkj.push(`<td class="dc${sc}">${gauge(s.energie, 400, '#2a5a8a', s.energie)}</td>`);

      // Marée
      R.marr.push(`<td class="dc${sc}"><span style="color:${tc};font-size:14px">${tide?(tide.type==='H'?'↑':'↓'):'—'}</span></td>`);
      R.mhbm.push(`<td class="dc${sc}"><span style="color:${tc};font-size:9px">${tide?(tide.type==='H'?'HM':'BM')+' '+tHStr(tide):'—'}</span></td>`);
      R.mm.push(`<td class="dc${sc}"><span style="color:${tc}">${tide?tide.m.toFixed(2)+'m':'—'}</span></td>`);
    });
  });

  const sect=l=>`<tr class="r-sect"><td class="lbl sect">${l}</td>${P.map((p,i)=>{const f=i===0||P[i-1].label!==p.label,s=f&&i>0;return`<td class="dc${s?' sep':''}"></td>`;}).join('')}</tr>`;
  const curIdx=P.findIndex(p=>p.dt===curKey);

  return{
    curIdx, vd:verdict(S.previsions,now),
    html:`<colgroup><col style="width:var(--lw)">${P.map(()=>`<col style="width:var(--cw)">`).join('')}</colgroup>
    <tbody>
      <tr class="r-day"> <td class="lbl sect"></td>${R.day.join('')}</tr>
      <tr class="r-time"><td class="lbl">h</td>${R.time.join('')}</tr>
      ${sect('Vent km/h')}
      <tr class="r-vdir"><td class="lbl">dir</td>${R.vdir.join('')}</tr>
      <tr class="r-vkmh"><td class="lbl">km/h</td>${R.vkmh.join('')}</tr>
      ${sect('Vague')}
      <tr class="r-wdir"><td class="lbl">dir</td>${R.wdir.join('')}</tr>
      <tr class="r-wh">  <td class="lbl">m</td>${R.wh.join('')}</tr>
      <tr class="r-wp">  <td class="lbl">s</td>${R.wp.join('')}</tr>
      <tr class="r-wkj"> <td class="lbl">kJ</td>${R.wkj.join('')}</tr>
      ${sect('Marée m')}
      <tr class="r-marr"><td class="lbl">↑↓</td>${R.marr.join('')}</tr>
      <tr class="r-mhbm"><td class="lbl">HM/BM</td>${R.mhbm.join('')}</tr>
      <tr class="r-mm">  <td class="lbl">m</td>${R.mm.join('')}</tr>
    </tbody>`
  };
}

function render(){
  const spots=window.SURF_SPOTS;
  if(!spots||!spots.length)return;
  const now=new Date();
  document.getElementById('upd').textContent=spots[0].updated;
  const container=document.getElementById('spots');
  container.innerHTML='';
  spots.forEach((S,si)=>{
    const{vd,html,curIdx}=buildTable(S,now);
    const alertHTML=S.alertes&&S.alertes.length?`<div class="alerts">${S.alertes.join('  ·  ')}</div>`:'';
    const div=document.createElement('div');
    div.innerHTML=`
      <div class="spot-hdr">
        <span class="spot-name">${S.nom}</span>
        <span class="spot-verdict" style="color:${vd.c}">${vd.v}</span>
        <span class="spot-upd">${S.updated}</span>
      </div>
      ${alertHTML}
      <div class="wrap" id="w${si}"><table class="tbl">${html}</table></div>`;
    container.appendChild(div);
    if(curIdx>=0) setTimeout(()=>{const w=document.getElementById(`w${si}`);if(w)w.scrollLeft=Math.max(0,curIdx*52-52);},80+si*30);
  });
  document.getElementById('foot').textContent='Open-Meteo · '+spots[0].updated+' · kJ=énergie vague (H²×T²×2) · ◀=maintenant · ★=meilleure 72h';
}
document.addEventListener('DOMContentLoaded',render);

"""


# ─── Generate HTML ────────────────────────────────────────────────────────────
def generate_html(spots):
    data_json = json.dumps(spots, ensure_ascii=False)
    return (
        '<!DOCTYPE html><html lang="fr"><head>'
        '<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="refresh" content="3600">'
        '<title>Surf · Antilles</title>'
        '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">'
        f'<style>{CSS}</style>'
        '</head><body>'
        f'<script>window.SURF_SPOTS={data_json};</script>'
        '<div class="ghdr">'
          '<div>'
            '<div class="ghdr-l"><span class="gtitle">Surf · Antilles</span></div>'
            '<div id="upd">chargement…</div>'
          '</div>'
          '<button class="btn" onclick="location.reload()">↺ Actualiser</button>'
        '</div>'
        '<div id="spots"></div>'
        '<div class="foot" id="foot"></div>'
        f'<script>{JS}</script>'
        '</body></html>'
    )


def main():
    spots = []
    for cfg in SPOTS_CFG:
        om, ow = fetch_spot(cfg["lat"], cfg["lng"], cfg["tz"], cfg["nom"])
        spot   = process_spot(om, ow, cfg["nom"])
        spots.append(spot)

    debug(spots)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(generate_html(spots))
    print(f"Dashboard: {out}")

if __name__ == "__main__":
    main()
