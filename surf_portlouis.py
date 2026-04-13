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


# ─── Fetch Open-Meteo (tout en un) ───────────────────────────────────────────
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
    W = 3  # fenêtre de comparaison en heures
    for i in range(W, n - W):
        if any(levels[j] is None for j in range(i-W, i+W+1)):
            continue
        t_ast = utc_to_ast(datetime.fromisoformat(times[i]))
        h_dec = round(t_ast.hour + t_ast.minute / 60, 2)
        window = [levels[j] for j in range(i-W, i+W+1)]
        if levels[i] == max(window) and levels[i] > levels[i-1]:
            marees.append({"jour": t_ast.day, "h": h_dec, "m": round(levels[i], 2), "type": "H"})
        elif levels[i] == min(window) and levels[i] < levels[i-1]:
            marees.append({"jour": t_ast.day, "h": h_dec, "m": round(levels[i], 2), "type": "L"})
    print(f"Marées détectées: {len(marees)}")
    for m in marees[:8]:
        print(f"  Jour {m['jour']} {m['h']:.2f}h → {m['m']}m {'HM' if m['type']=='H' else 'BM'}")
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

        # Énergie swell (plus pertinente pour le surf)
        energie = round(sh**2 * sp * 5)

        vtype = "offshore"
        if wsd is not None:
            if 45 <= float(wsd) <= 135:   vtype = "offshore"
            elif 135 < float(wsd) <= 225: vtype = "onshore"
            else:                          vtype = "cross"

        previsions.append({
            "moment":    f"{JOURS_FR[t_ast.weekday()]} {t_ast.day} {str(h_local).zfill(2)}h",
            "jour":      t_ast.day,
            "heure":     h_local,
            "dt":        t,
            "wh":        round(wh, 2),
            "wp":        round(wp, 1),
            "wd":        deg_to_dir(wd),
            "sh":        round(sh, 2),
            "sp":        round(sp, 1),
            "sd":        deg_to_dir(sd),
            "energie":   energie,
            "vent":      round(ws),
            "vdir":      deg_to_dir(wsd),
            "vtype":     vtype,
        })

    # Meilleure session : énergie swell max parmi créneaux >= maintenant, 72h
    now_str = now_ast.strftime("%Y-%m-%dT%H:%M")
    future72 = [p for p in previsions if p["dt"] >= now_str[:16] and
                (datetime.fromisoformat(p["dt"]) - datetime.fromisoformat(now_str[:16])).total_seconds() <= 72*3600]
    best = max(future72, key=lambda x: x["energie"]) if future72 else (previsions[0] if previsions else None)

    # Créneau actuel
    current = next((p for p in previsions if p["dt"][:13] == now_str[:13]), previsions[0] if previsions else None)

    alertes = [f"⚠ Vent {p['vent']}km/h — {p['moment']}" for p in previsions[:24] if p["vent"] >= 35]

    return {
        "updated":     now_ast.strftime("%a %d %b %Y %Hh%M"),
        "alertes":     alertes,
        "bestSession": {"jour": best["jour"], "heure": best["heure"]} if best else None,
        "currentHour": {"jour": current["jour"], "heure": current["heure"]} if current else None,
        "marees":      marees,
        "previsions":  previsions,
    }


# ─── Debug terminal ───────────────────────────────────────────────────────────
def debug(surf):
    print(f"\n{'='*90}")
    print(f"Mis à jour: {surf['updated']}")
    if surf['bestSession']:
        b = surf['bestSession']
        print(f"Meilleure session: jour {b['jour']} à {b['heure']}h")
    print(f"{'─'*90}")
    print(f"{'Créneau':<14} {'Vague':>6} {'Pér':>5} {'DirV':>5} {'Swell':>6} {'Pér':>5} {'DirS':>5} {'kJ':>5} {'Vent':>6} {'VDir':>5} {'Type':<12} {'Marée'}")
    print(f"{'─'*90}")
    for p in surf["previsions"][:18]:
        t = p["jour"] * 24 + p["heure"]
        sorted_m = sorted(surf["marees"], key=lambda m: m["jour"]*24 + m["h"])
        prev_m, next_m = None, None
        for m in sorted_m:
            if m["jour"]*24 + m["h"] <= t: prev_m = m
            elif not next_m: next_m = m
        ref = next_m or prev_m
        up = next_m and next_m["type"] == "H"
        m_info = f"{'↑' if up else '↓'} {'HM' if ref['type']=='H' else 'BM'} {ref['h']:.2f}h {ref['m']}m" if ref else ""
        print(f"  {p['moment']:<12} {p['wh']:>5}m {p['wp']:>4}s {p['wd']:>5} {p['sh']:>5}m {p['sp']:>4}s {p['sd']:>5} {p['energie']:>5} {p['vent']:>5}km {p['vdir']:>5} {p['vtype']:<12} {m_info}")
    print(f"{'='*90}\n")


# ─── JS ───────────────────────────────────────────────────────────────────────
JS = r"""
const DIR={N:"↓",NNE:"↙",NE:"↙",ENE:"↙",E:"←",ESE:"↖",SE:"↖",SSE:"↑",S:"↑",SSW:"↗",SW:"↗",WSW:"→",W:"→",WNW:"↘",NW:"↘",NNW:"↘"};
const hCol=h=>h>=0.8?"#2a7a5a":h>=0.5?"#4a6a5a":"#aaa";
const wCol=v=>v>=30?"#aa4a4a":v>=25?"#8a6a2a":"#2a6a5a";
const eCol=e=>e>=80?"#2a6a4a":e>=40?"#5a7a4a":"#bbb";
const vCol=t=>t==="offshore"?"#2a6a5a":t==="cross"?"#8a6a2a":"#aa4a4a";
const vIcon=t=>t==="offshore"?"⬢":t==="cross"?"◈":"⬡";

function verdict(p,now){
  const fut=p.filter(x=>x.dt>=now).slice(0,24);
  if(!fut.length)return{v:"—",c:"#999"};
  const best=Math.max(...fut.map(x=>x.energie));
  if(best>=120)return{v:"GO",c:"#2a7a5a"};
  if(best>=60) return{v:"BORDERLINE",c:"#8a6a2a"};
  return          {v:"NO-GO",c:"#aa4a4a"};
}

function tideCell(marees,jour,heure){
  if(!marees||!marees.length)return"—";
  const t=jour*24+heure;
  const sorted=[...marees].sort((a,b)=>(a.jour*24+a.h)-(b.jour*24+b.h));
  let prev=null,next=null;
  for(const m of sorted){
    if(m.jour*24+m.h<=t)prev=m;
    else if(!next)next=m;
  }
  function fmt(m){
    if(!m)return"—";
    const h=Math.floor(m.h),min=Math.round((m.h-h)*60);
    const hStr=String(h).padStart(2,"0")+"h"+(min>0?String(min).padStart(2,"0"):"");
    const col=m.type==="H"?"#2a5a8a":"#7a5a2a";
    const label=m.type==="H"?"HM":"BM";
    return`<span style="color:${col}">${label} ${hStr} <span style="opacity:.7">${m.m.toFixed(2)}m</span></span>`;
  }
  const arrow=next&&next.type==="H"?"↑":"↓";
  const col=next&&next.type==="H"?"#2a5a8a":"#7a5a2a";
  return`${fmt(prev)} <span style="color:${col}">${arrow}</span> ${fmt(next)}`;
}

function render(){
  const S=window.SURF_DATA;
  if(!S||!S.previsions||!S.previsions.length)return;

  const nowStr=new Date().toISOString().slice(0,13);
  const vd=verdict(S.previsions,nowStr);
  const cur=S.currentHour;
  const curP=S.previsions.find(p=>cur&&p.jour===cur.jour&&p.heure===cur.heure)||S.previsions[0];
  const B=S.bestSession;

  // Verdict simple dans le titre
  document.getElementById("verdict").textContent=vd.v;
  document.getElementById("verdict").style.color=vd.c;
  document.getElementById("updated").textContent=S.updated;

  if(S.alertes&&S.alertes.length){
    const al=document.getElementById("alerts");
    al.textContent=S.alertes.join("  ·  ");
    al.style.display="block";
  }

  document.getElementById("tbody").innerHTML=S.previsions.map(r=>{
    const isCurrent=cur&&r.jour===cur.jour&&r.heure===cur.heure;
    const isBest=B&&r.jour===B.jour&&r.heure===B.heure;
    const bg=isCurrent?"#e8f2ec":isBest?"#f0f5e8":"transparent";
    const bl=isCurrent?"3px solid #2a7a5a":isBest?"3px solid #8a9a5a":"3px solid transparent";
    const ew=Math.min(r.energie/150*100,100);
    const tide=tideCell(S.marees,r.jour,r.heure);
    return`<tr style="background:${bg};border-left:${bl}">
<td style="color:${isCurrent?"#2a7a5a":isBest?"#6a7a3a":"#777"};white-space:nowrap;font-size:0.58rem;font-weight:${isCurrent||isBest?500:300}">${r.moment}${isCurrent?' ◀':''}</td>
<td style="white-space:nowrap">
  <span style="color:${hCol(r.wh)};font-size:12px">${DIR[r.wd]||"•"}</span>
  <span style="color:${hCol(r.wh)};font-weight:${r.wh>=0.7?500:300}"> ${r.wh}m</span>
  <span style="color:#999;font-size:0.52rem"> ${r.wp}s ${r.wd}</span>
</td>
<td style="white-space:nowrap;color:#3a6a8a">
  <span style="font-size:12px">${DIR[r.sd]||"•"}</span>
  <span style="font-weight:${r.sh>=0.5?500:300}"> ${r.sh}m</span>
  <span style="font-size:0.52rem;color:#999"> ${r.sp}s ${r.sd}</span>
</td>
<td>
  <div style="display:flex;align-items:center;gap:3px">
    <div style="flex:1;height:2px;background:#e0ddd8;position:relative;min-width:28px">
      <div style="position:absolute;left:0;top:0;height:100%;width:${ew}%;background:${eCol(r.energie)}"></div>
    </div>
    <span style="font-size:0.52rem;color:${eCol(r.energie)};min-width:20px;text-align:right">${r.energie}</span>
  </div>
</td>
<td style="white-space:nowrap">
  <span style="font-size:12px;color:${wCol(r.vent)}">${DIR[r.vdir]||"•"}</span>
  <span style="color:${wCol(r.vent)}"> ${r.vent}</span>
  <span style="color:#999;font-size:0.52rem"> ${r.vdir}</span>
</td>
<td style="font-size:0.52rem;color:${vCol(r.vtype)};text-align:center">${vIcon(r.vtype)} ${r.vtype}</td>
<td style="font-size:0.52rem;white-space:nowrap">${tide}</td>
</tr>`;
  }).join("");

  document.getElementById("foot").textContent="Open-Meteo · "+S.updated+" · Vague=vague totale | Swell=houle longue distance | kJ=énergie swell";
}

document.addEventListener("DOMContentLoaded",render);
"""

CSS = """
* {box-sizing:border-box;margin:0;padding:0}
body {background:#f5f3f0;color:#2a2a2a;font-family:'IBM Plex Mono',monospace;min-height:100vh}
.header {padding:1rem 1.4rem;border-bottom:1px solid #ddd;display:flex;justify-content:space-between;align-items:center}
.title-row {display:flex;align-items:baseline;gap:1rem}
.title {font-size:0.9rem;letter-spacing:5px;color:#555;text-transform:uppercase;font-weight:300}
.verdict {font-size:1.4rem;letter-spacing:4px;font-weight:300}
.updated {font-size:0.46rem;color:#bbb;letter-spacing:1px}
.btn {background:transparent;border:1px solid #ccc;color:#666;padding:0.35rem 0.8rem;font-family:inherit;font-size:0.56rem;letter-spacing:2px;text-transform:uppercase;cursor:pointer}
.btn:hover {border-color:#999;color:#333}
.alerts {padding:0.5rem 1.4rem;border-bottom:1px solid #ddd;font-size:0.58rem;color:#b07a3a}
.table-wrap {overflow-x:auto}
table {width:100%;border-collapse:collapse;font-size:0.62rem;min-width:520px}
th {padding:0.3rem 0.6rem;color:#bbb;font-weight:300;font-size:0.46rem;letter-spacing:1px;text-align:left;border-bottom:1px solid #e0ddd8;white-space:nowrap}
td {padding:0.35rem 0.6rem;border-bottom:1px solid #eae7e2;vertical-align:middle}
.foot {padding:0.6rem 1.4rem;font-size:0.44rem;color:#bbb;border-top:1px solid #e0ddd8;font-style:italic}
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
        '<div class="table-wrap"><table>'
        '<thead><tr>'
        '<th>Créneau</th><th>Vague</th><th>Swell</th>'
        '<th>kJ</th><th>Vent</th><th>Conditions</th><th>Marée</th>'
        '</tr></thead>'
        '<tbody id="tbody"></tbody></table></div>'
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
