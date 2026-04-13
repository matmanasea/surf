#!/usr/bin/env python3
"""Surf Dashboard — Port-Louis, Guadeloupe. Usage: python3 surf_portlouis.py"""

import json, os
from datetime import datetime, timezone, timedelta
import requests

LAT, LNG = 16.43, -61.54
AST      = timedelta(hours=-4)
DIRS     = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
JOURS_FR = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
CRENEAUX = {5, 8, 11, 14, 17, 20}

def deg_to_dir(deg):
    if deg is None: return "—"
    return DIRS[round(float(deg) / 22.5) % 16]

def utc_to_ast(t):
    return t + AST


# ─── Fetch Open-Meteo ────────────────────────────────────────────────────────
def fetch_all():
    print("Fetching Open-Meteo Marine...")
    om = requests.get("https://marine-api.open-meteo.com/v1/marine", params={
        "latitude": LAT, "longitude": LNG,
        "hourly": "sea_level_height_msl,wave_height,wave_direction,wave_period,swell_wave_height,swell_wave_direction,swell_wave_period",
        "forecast_days": 16,
        "timezone": "America/Guadeloupe"
    }, timeout=15).json()

    print("Fetching Open-Meteo Vent...")
    ow = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LNG,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": 16,
        "timezone": "America/Guadeloupe",
        "wind_speed_unit": "kmh"
    }, timeout=15).json()

    print(f"OK — {len(om['hourly']['time'])} heures")
    return om, ow


# ─── Détecter HM/BM depuis sea_level_height_msl ──────────────────────────────
def detect_marees(times, levels):
    marees = []
    n = len(levels)
    i = 1
    while i < n - 1:
        if levels[i] is None or levels[i-1] is None:
            i += 1
            continue
        j = i
        while j + 1 < n and levels[j+1] is not None and levels[j+1] == levels[i]:
            j += 1
        if j + 1 >= n or levels[j+1] is None:
            break
        after = levels[j+1]
        before = levels[i-1]
        t_loc = datetime.fromisoformat(times[i])
        h_dec = round(t_loc.hour + t_loc.minute / 60, 2)
        if levels[i] > before and levels[i] > after:
            marees.append({"jour": t_loc.day, "mois": t_loc.month, "h": h_dec, "m": round(levels[i], 2), "type": "H"})
        elif levels[i] < before and levels[i] < after:
            marees.append({"jour": t_loc.day, "mois": t_loc.month, "h": h_dec, "m": round(levels[i], 2), "type": "L"})
        i = j + 1

    print(f"Marées détectées: {len(marees)}")
    for m in marees[:8]:
        t = "HM" if m['type'] == "H" else "BM"
        print(f"  Jour {m['jour']} {m['h']:.2f}h -> {m['m']}m {t}")
    return marees


# ─── Process ──────────────────────────────────────────────────────────────────
def process(om, ow):
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

        energie = round(sh**2 * sp * 5)

        vtype = "offshore"
        if wsd is not None:
            if 45 <= float(wsd) <= 135:   vtype = "offshore"
            elif 135 < float(wsd) <= 225: vtype = "onshore"
            else:                          vtype = "cross"

        previsions.append({
            "label":   f"{JOURS_FR[t_ast.weekday()]} {t_ast.day}",
            "jour":    t_ast.day,
            "mois":    t_ast.month,
            "heure":   h_local,
            "dt":      t,
            "wh":      round(wh, 2),
            "wp":      round(wp, 1),
            "wd":      deg_to_dir(wd),
            "sh":      round(sh, 2),
            "sp":      round(sp, 1),
            "sd":      deg_to_dir(sd),
            "energie": energie,
            "vent":    round(ws),
            "vdir":    deg_to_dir(wsd),
            "vtype":   vtype,
        })

    alertes = [f"⚠ Vent {p['vent']}km/h — {p['label']} {p['heure']:02d}h" for p in previsions[:24] if p["vent"] >= 35]

    return {
        "updated":    now_ast.strftime("%a %d %b %Y %Hh%M"),
        "alertes":    alertes,
        "marees":     marees,
        "previsions": previsions,
    }


# ─── Debug terminal ───────────────────────────────────────────────────────────
def debug(surf):
    print(f"\n{'='*80}")
    print(f"Mis à jour: {surf['updated']}")
    print(f"{'─'*80}")
    for p in surf["previsions"][:18]:
        print(f"  {p['label']} {p['heure']:02d}h  sh={p['sh']}m sp={p['sp']}s  e={p['energie']}  vent={p['vent']}km {p['vtype']}")
    print(f"{'='*80}\n")


# ─── JS ──────────────────────────────────────────────────────────────────────
JS = r"""
const PROP_DEG={N:180,NNE:202,NE:225,ENE:247,E:270,ESE:292,SE:315,SSE:337,S:0,SSW:22,SW:45,WSW:67,W:90,WNW:112,NW:135,NNW:157};
const CRENEAUX=[5,8,11,14,17,20];

function propArrow(dir,col,sz){
  const d=PROP_DEG[dir]||0;
  return`<span style="display:inline-block;transform:rotate(${d}deg);color:${col};font-size:${sz||11}px;line-height:1">↑</span>`;
}
const hCol=h=>h>=0.8?"#2a7a5a":h>=0.5?"#4a6a5a":"#aaa";
const wCol=v=>v>=30?"#aa4a4a":v>=25?"#8a6a2a":"#2a6a5a";
const eCol=e=>e>=80?"#2a6a4a":e>=40?"#5a7a4a":"#ccc";

// Verdict global 24h
function verdictGlobal(previsions, nowDt){
  const fut=previsions.filter(x=>new Date(x.dt)>=nowDt).slice(0,24);
  if(!fut.length)return{v:"—",c:"#999"};
  const best=Math.max(...fut.map(x=>x.energie));
  if(best>=120)return{v:"GO",c:"#2a7a5a"};
  if(best>=60) return{v:"BORDERLINE",c:"#8a6a2a"};
  return          {v:"NO-GO",c:"#aa4a4a"};
}

// Verdict d'un jour (énergie max des créneaux du jour)
function verdictJour(slots){
  const best=Math.max(...slots.map(x=>x.energie));
  if(best>=120)return{v:"GO",c:"#2a7a5a"};
  if(best>=60) return{v:"BORDERLINE",c:"#8a6a2a"};
  return          {v:"NO-GO",c:"#aa4a4a"};
}

// Prochain extrême de marée après un créneau donné
function nextTide(marees, jour, mois, heure){
  if(!marees||!marees.length) return null;
  const t = jour*10000 + mois*100 + heure; // clé de tri approximative
  const sorted=[...marees].sort((a,b)=>{
    const ka=a.jour*10000+a.mois*100+a.h;
    const kb=b.jour*10000+b.mois*100+b.h;
    return ka-kb;
  });
  // chercher le premier extrême strictement après l'heure du créneau
  for(const m of sorted){
    const km=m.jour*10000+m.mois*100+m.h;
    const kc=jour*10000+mois*100+heure;
    if(km>kc) return m;
  }
  return null;
}

function fmtTide(m){
  if(!m)return"—";
  const h=Math.floor(m.h), min=Math.round((m.h-h)*60);
  const hStr=String(h).padStart(2,"0")+"h"+(min>0?String(min).padStart(2,"0"):"");
  const col=m.type==="H"?"#3a6a9a":"#9a7a3a";
  const arrow=m.type==="H"?"↑":"↓";
  return`<span style="color:${col}">${arrow}${m.type==="H"?"HM":"BM"} ${hStr}<br>${m.m.toFixed(2)}m</span>`;
}

// Calculer créneau actuel (index dans CRENEAUX) et best 72h
function computeHighlights(previsions, nowDt){
  const nowMs=nowDt.getTime();
  const ms72=72*3600*1000;

  // créneau actuel = créneau dont dt est le plus proche de maintenant (passé ou futur dans ±3h)
  let curKey=null, minDiff=Infinity;
  for(const p of previsions){
    const diff=Math.abs(new Date(p.dt).getTime()-nowMs);
    if(diff<minDiff){minDiff=diff;curKey=p.dt;}
  }

  // meilleure session dans les 72h à venir
  const future=previsions.filter(p=>new Date(p.dt)>=nowDt && new Date(p.dt).getTime()-nowMs<=ms72);
  let bestKey=null;
  if(future.length){
    const bst=future.reduce((a,b)=>b.energie>a.energie?b:a);
    bestKey=bst.dt;
  }

  return{curKey, bestKey};
}

function render(){
  const S=window.SURF_DATA;
  if(!S||!S.previsions||!S.previsions.length)return;

  const nowDt=new Date();
  // Ajuster en AST (UTC-4) pour comparer avec les dt locaux
  // Les dt dans les données sont en heure locale Guadeloupe (AST)
  // new Date() est UTC — on crée une string locale AST pour comparer
  const nowAST=new Date(nowDt.getTime()-4*3600*1000);
  const nowASTStr=nowAST.toISOString().slice(0,16).replace("T"," "); // "2026-04-13 11:00"

  const {curKey,bestKey}=computeHighlights(S.previsions, nowDt);

  const vd=verdictGlobal(S.previsions, nowDt);
  document.getElementById("verdict").textContent=vd.v;
  document.getElementById("verdict").style.color=vd.c;
  document.getElementById("updated").textContent=S.updated;

  if(S.alertes&&S.alertes.length){
    const al=document.getElementById("alerts");
    al.textContent=S.alertes.join("  ·  ");
    al.style.display="block";
  }

  // Grouper par jour (label = "Lun 14")
  const days=[];
  let cur=null;
  for(const p of S.previsions){
    if(!cur||cur.label!==p.label){
      cur={label:p.label,slots:[]};
      days.push(cur);
    }
    cur.slots.push(p);
  }

  const container=document.getElementById("cards");
  container.innerHTML=days.map(day=>{
    const vj=verdictJour(day.slots);
    const slotMap={};
    for(const s of day.slots) slotMap[s.heure]=s;

    function cs(h){
      const s=slotMap[h];
      if(!s)return`style="border-top:3px solid transparent"`;
      if(s.dt===curKey) return`style="border-top:3px solid #2a7a5a"`;
      if(s.dt===bestKey)return`style="border-top:3px solid #8a9a5a"`;
      return`style="border-top:3px solid transparent"`;
    }
    function bdg(h){
      const s=slotMap[h];
      if(!s)return"";
      if(s.dt===curKey) return'<span class="badge cur">◀</span>';
      if(s.dt===bestKey)return'<span class="badge best">★</span>';
      return"";
    }

    const hRow=CRENEAUX.map(h=>`<th ${cs(h)}>${String(h).padStart(2,"0")}h${bdg(h)}</th>`).join("");

    const swellRow=CRENEAUX.map(h=>{
      const s=slotMap[h];
      if(!s)return`<td ${cs(h)}>—</td>`;
      return`<td ${cs(h)}>${propArrow(s.sd,"#3a6a8a")}<span style="color:#3a6a8a;font-weight:${s.sh>=0.5?500:300}">${s.sh}m</span><span class="sub"> ${s.sp}s ${s.sd}</span></td>`;
    }).join("");

    const vagueRow=CRENEAUX.map(h=>{
      const s=slotMap[h];
      if(!s)return`<td ${cs(h)}>—</td>`;
      return`<td ${cs(h)}>${propArrow(s.wd,hCol(s.wh))}<span style="color:${hCol(s.wh)};font-weight:${s.wh>=0.7?500:300}">${s.wh}m</span><span class="sub"> ${s.wp}s ${s.wd}</span></td>`;
    }).join("");

    const kjRow=CRENEAUX.map(h=>{
      const s=slotMap[h];
      if(!s)return`<td ${cs(h)}>—</td>`;
      const ew=Math.min(s.energie/150*100,100);
      return`<td ${cs(h)}><div style="display:flex;align-items:center;gap:3px"><div class="ebar"><div class="efill" style="width:${ew}%;background:${eCol(s.energie)}"></div></div><span style="color:${eCol(s.energie)};font-size:0.5rem">${s.energie}</span></div></td>`;
    }).join("");

    const ventRow=CRENEAUX.map(h=>{
      const s=slotMap[h];
      if(!s)return`<td ${cs(h)}>—</td>`;
      return`<td ${cs(h)}>${propArrow(s.vdir,wCol(s.vent))}<span style="color:${wCol(s.vent)}">${s.vent}</span><span class="sub"> ${s.vdir}</span></td>`;
    }).join("");

    const mareeRow=CRENEAUX.map(h=>{
      const s=slotMap[h];
      if(!s)return`<td ${cs(h)}>—</td>`;
      return`<td ${cs(h)}>${fmtTide(nextTide(S.marees,s.jour,s.mois,s.heure))}</td>`;
    }).join("");

    return`<div class="card">
  <div class="card-header">
    <span class="card-day">${day.label}</span>
    <span class="card-verdict" style="color:${vj.c}">${vj.v}</span>
  </div>
  <div class="card-scroll">
    <table class="day-table">
      <thead><tr><th class="row-label"></th>${hRow}</tr></thead>
      <tbody>
        <tr><td class="row-label sub">Swell</td>${swellRow}</tr>
        <tr><td class="row-label sub">kJ</td>${kjRow}</tr>
        <tr><td class="row-label sub">Vague</td>${vagueRow}</tr>
        <tr><td class="row-label sub">Vent</td>${ventRow}</tr>
        <tr><td class="row-label sub">Marée</td>${mareeRow}</tr>
      </tbody>
    </table>
  </div>
</div>`;
  }).join("");

  document.getElementById("foot").textContent="Open-Meteo · "+S.updated+" · Swell=houle longue distance · kJ=énergie swell · ◀=maintenant · ★=meilleure 72h";
}

document.addEventListener("DOMContentLoaded",render);
"""

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f5f3f0;color:#2a2a2a;font-family:'IBM Plex Mono',monospace;min-height:100vh}
.header{padding:0.9rem 1.2rem;border-bottom:1px solid #ddd;display:flex;justify-content:space-between;align-items:center}
.title-row{display:flex;align-items:baseline;gap:0.8rem}
.title{font-size:0.82rem;letter-spacing:4px;color:#555;text-transform:uppercase;font-weight:300}
.verdict{font-size:1.3rem;letter-spacing:3px;font-weight:300}
.updated{font-size:0.44rem;color:#bbb;letter-spacing:1px;margin-top:2px}
.btn{background:transparent;border:1px solid #ccc;color:#666;padding:0.3rem 0.7rem;font-family:inherit;font-size:0.52rem;letter-spacing:2px;text-transform:uppercase;cursor:pointer}
.btn:hover{border-color:#999;color:#333}
.alerts{padding:0.45rem 1.2rem;border-bottom:1px solid #ddd;font-size:0.54rem;color:#b07a3a}
#cards{padding:0.6rem 0.8rem;display:flex;flex-direction:column;gap:0.8rem}
.card{border:1px solid #e0ddd8;background:#fff;border-radius:2px}
.card-header{display:flex;align-items:baseline;gap:0.6rem;padding:0.4rem 0.7rem;border-bottom:1px solid #eae7e2}
.card-day{font-size:0.72rem;letter-spacing:2px;color:#555;font-weight:400;text-transform:uppercase}
.card-verdict{font-size:0.62rem;letter-spacing:2px;font-weight:300}
.card-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.day-table{border-collapse:collapse;font-size:0.7rem;white-space:nowrap;min-width:360px;width:100%}
.day-table th{padding:0.3rem 0.6rem;color:#999;font-weight:400;font-size:0.62rem;letter-spacing:1px;text-align:left;border-bottom:1px solid #eae7e2}
.day-table td{padding:0.35rem 0.6rem;border-bottom:1px solid #f0ede8;vertical-align:middle}
.row-label{color:#bbb;font-size:0.54rem;letter-spacing:1px;font-weight:300;white-space:nowrap;padding-right:0.4rem;min-width:40px}
.sub{color:#999;font-size:0.56rem}
.badge{font-size:0.6rem;margin-left:3px}
.badge.cur{color:#2a7a5a}
.badge.best{color:#8a9a5a}
.ebar{width:28px;height:2px;background:#e0ddd8;position:relative;display:inline-block;vertical-align:middle}
.efill{position:absolute;left:0;top:0;height:100%}
.foot{padding:0.5rem 1.2rem;font-size:0.42rem;color:#bbb;border-top:1px solid #e0ddd8;font-style:italic}
"""

def generate_html(surf):
    data_json = json.dumps(surf, ensure_ascii=False)
    return (
        '<!DOCTYPE html><html lang="fr"><head>'
        '<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="refresh" content="3600">'
        '<title>Port-Louis · Surf</title>'
        '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&display=swap" rel="stylesheet">'
        f'<style>{CSS}</style></head><body>'
        f'<script>window.SURF_DATA={data_json};</script>'
        '<div class="header">'
        '<div>'
        '<div class="title-row">'
        '<div class="title">Port-Louis · Surf</div>'
        '<div class="verdict" id="verdict"></div>'
        '</div>'
        '<div class="updated" id="updated"></div>'
        '</div>'
        '<button class="btn" onclick="location.reload()">↺ Actualiser</button>'
        '</div>'
        '<div class="alerts" id="alerts" style="display:none"></div>'
        '<div id="cards"></div>'
        '<div class="foot" id="foot"></div>'
        f'<script>{JS}</script>'
        '</body></html>'
    )

def main():
    om, ow = fetch_all()
    surf   = process(om, ow)
    debug(surf)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(generate_html(surf))
    print(f"Dashboard: {out}")

if __name__ == "__main__":
    main()
