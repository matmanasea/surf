#!/usr/bin/env python3
"""Surf Dashboard — Port-Louis, Guadeloupe. Usage: python3 surf_portlouis.py"""

import json, os
from datetime import datetime, timezone, timedelta
import requests

SG_KEY   = os.environ.get("SG_KEY", "")
LAT, LNG = 16.43, -61.54
AST      = timedelta(hours=-4)
DIRS     = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
JOURS_FR = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]

def deg_to_dir(deg):
    if deg is None: return "—"
    return DIRS[round(float(deg) / 22.5) % 16]

def utc_to_ast(t):
    return t + AST


# ─── Open-Meteo ───────────────────────────────────────────────────────────────
def fetch_open_meteo():
    print("Fetching Open-Meteo Marine...")
    om = requests.get("https://marine-api.open-meteo.com/v1/marine", params={
        "latitude": LAT, "longitude": LNG,
        "hourly": "wave_height,wave_period,wave_direction,swell_wave_height,swell_wave_period,swell_wave_direction",
        "forecast_days": 7,
        "timezone": "America/Guadeloupe"
    }, timeout=15).json()

    print("Fetching Open-Meteo Vent...")
    ow = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LNG,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": 7,
        "timezone": "America/Guadeloupe",
        "wind_speed_unit": "kmh"
    }, timeout=15).json()

    print(f"OK — {len(om['hourly']['time'])} heures")
    return om, ow


# ─── Stormglass marées ────────────────────────────────────────────────────────
# ─── Marées tide-forecast.com ────────────────────────────────────────────────
def fetch_marees():
    print("Fetching marées tide-forecast.com...")
    try:
        r = requests.get(
            "https://www.tide-forecast.com/locations/Port-Louis-1/tides/latest",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=15
        )
        r.raise_for_status()

        import re
        marees = []

        # Le HTML contient des lignes comme :
        # | High Tide | **2:35 AM**(Mon 13 April) | **1.05 ft** (0.32 m) |
        # On cherche ce pattern dans le texte brut
        # Parser en deux passes : d'abord les types+heures+jours, puis les hauteurs
        types_heures = re.findall(
            r'(High Tide|Low Tide)</td><td><b>\s*(\d{1,2}:\d{2}\s*[AP]M)</b><span[^>]*>\((?:\w+\s+)(\d{1,2})\s+\w+\)',
            r.text
        )
        hauteurs = re.findall(
            r'<b class="js-two-units-length-value__primary">([-\d.]+)\s*m</b>',
            r.text
        )

        for i, (tide_type, time_str, jour_str) in enumerate(types_heures):
            t = datetime.strptime(time_str.strip(), "%I:%M %p")
            hm = float(hauteurs[i]) if i < len(hauteurs) else 0.0
            marees.append({
                "jour": int(jour_str),
                "h":    round(t.hour + t.minute / 60, 2),
                "m":    hm,
                "type": "H" if "High" in tide_type else "L",
            })

        print(f"OK — {len(marees)} points marées")
        for m in marees[:8]:
            print(f"    Jour {m['jour']} {m['h']:.2f}h → {m['m']}m {'HM' if m['type']=='H' else 'BM'}")
        return marees

    except Exception as e:
        print(f"  ⚠ Marées indisponibles: {e}")
        return []


# ─── Process ──────────────────────────────────────────────────────────────────
def process(om, ow, marees):
    previsions = []
    CRENEAUX   = {2, 8, 11, 14, 17, 20}

    for i, t in enumerate(om["hourly"]["time"]):
        h = int(t[11:13])
        if h not in CRENEAUX:
            continue

        wh  = om["hourly"]["wave_height"][i]
        wp  = om["hourly"]["wave_period"][i]
        wd  = om["hourly"]["wave_direction"][i]
        sh  = om["hourly"]["swell_wave_height"][i]
        sp  = om["hourly"]["swell_wave_period"][i]
        sd  = om["hourly"]["swell_wave_direction"][i]
        ws  = ow["hourly"]["wind_speed_10m"][i]
        wsd = ow["hourly"]["wind_direction_10m"][i]

        wh  = wh  or 0
        wp  = wp  or 0
        ws  = ws  or 0

        energie  = round(wh**2 * wp * 0.5 * 10)
        vdir     = deg_to_dir(wsd)
        vtype    = "offshore"
        if wsd is not None:
            if 45 <= float(wsd) <= 135:    vtype = "offshore"
            elif 135 < float(wsd) <= 225:  vtype = "onshore"
            else:                          vtype = "cross-offshore"

        t_ast    = datetime.fromisoformat(t)
        jour_num = t_ast.day
        jour_nom = JOURS_FR[t_ast.weekday()]
        moment   = f"{jour_nom} {jour_num} {str(h).zfill(2)}h"

        previsions.append({
            "moment":       moment,
            "jour":         jour_num,
            "heure":        h,
            "houle":        round(wh, 2),
            "periode":      round(wp, 1),
            "dir":          deg_to_dir(wd),
            "swell":        round(sh, 2) if sh else 0,
            "swellPeriode": round(sp, 1) if sp else 0,
            "swellDir":     deg_to_dir(sd),
            "energie":      energie,
            "vent":         round(ws),
            "vdir":         vdir,
            "vtype":        vtype,
            "note":         1 if wh >= 0.6 and energie >= 50 else 0,
        })

    first72  = previsions[:24]
    best     = max(first72, key=lambda x: x["energie"]) if first72 else previsions[0]
    alertes  = [f"⚠ Vent fort {p['vent']}km/h — {p['moment']}" for p in previsions[:24] if p["vent"] >= 35]

    return {
        "updated":     datetime.now().strftime("%a %d %b %Y %Hh%M"),
        "tempEau":     26.5,
        "alertes":     alertes,
        "bestSession": {"jour": best["jour"], "heure": best["heure"]},
        "marees":      marees,
        "previsions":  previsions,
    }


# ─── Debug ────────────────────────────────────────────────────────────────────
def debug(surf):
    print(f"\n{'='*75}")
    print(f"Mis à jour: {surf['updated']} | Best: jour {surf['bestSession']['jour']} {surf['bestSession']['heure']}h")
    print(f"{'─'*75}")
    print(f"{'Créneau':<16} {'Houle':>6} {'Pér':>5} {'Dir':>5} {'Swell':>6} {'SwPér':>6} {'kJ':>5} {'Vent':>6} {'VDir':>5}")
    print(f"{'─'*75}")
    for p in surf["previsions"][:12]:
        print(f"  {p['moment']:<14} {p['houle']:>5}m {p['periode']:>4}s {p['dir']:>5} {p['swell']:>5}m {p['swellPeriode']:>5}s {p['energie']:>5} {p['vent']:>5}km {p['vdir']:>5}")
    print(f"{'='*75}\n")


# ─── JS ───────────────────────────────────────────────────────────────────────
JS = r"""
const C = {
  houleHigh: "#2a7a5a", houleMid: "#4a6a5a", houleLow: "#aaa",
  ventFort:  "#aa4a4a", ventMed:  "#8a6a2a", ventLex:  "#2a6a5a",
  energyH:   "#2a6a4a", energyM:  "#5a7a4a", energyL:  "#bbb",
  best:      "#2a6a4a", star:     "#7a5a1a",
  hmColor:   "#2a5a8a", bmColor:  "#7a5a2a",
  up:        "#2a7a5a", down:     "#8a3a3a",
};

const hCol = h => h >= 0.8 ? C.houleHigh : h >= 0.5 ? C.houleMid : C.houleLow;
const wCol = v => v >= 30 ? C.ventFort : v >= 25 ? C.ventMed : C.ventLex;
const eCol = e => e >= 80 ? C.energyH : e >= 40 ? C.energyM : C.energyL;

const DIR = {
  N:"↓",NNE:"↙",NE:"↙",ENE:"↙",E:"←",ESE:"↖",SE:"↖",SSE:"↑",
  S:"↑",SSW:"↗",SW:"↗",WSW:"→",W:"→",WNW:"↘",NW:"↘",NNW:"↘",
};

function verdict(p) {
  const b = Math.max(...p.map(x => x.houle));
  const n = Math.max(...p.map(x => x.note));
  if (b >= 1.2 || n >= 4) return {v:"GO",        c:"#2a7a5a", ph:"La mer a décidé de coopérer. Rare."};
  if (b >= 0.65|| n >= 1) return {v:"BORDERLINE", c:"#8a6a2a", ph:"Surfable pour qui sait chercher. Les autres rentrent bredouilles."};
  return                         {v:"NO-GO",       c:"#8a3a3a", ph:"La mer a pris un jour de congé. Sans culpabilité."};
}

function tideInfo(marees, jour, heure) {
  if (!marees || !marees.length) return {sens:"—", prochain:null};
  const t = jour * 24 + heure;
  const sorted = [...marees].sort((a,b) => (a.jour*24+a.h)-(b.jour*24+b.h));
  let prev = null, next = null;
  for (const m of sorted) {
    if (m.jour*24+m.h <= t) prev = m;
    else if (!next) next = m;
  }
  if (!prev && next) return {sens:"montant", prochain:next};
  if (!next)         return {sens:"descendant", prochain:null};
  return {sens: next.type==="H" ? "montant" : "descendant", prochain:next};
}

function fmtH(m) {
  if (!m) return "—";
  const h = Math.floor(m.h), min = Math.round((m.h-h)*60);
  return String(h).padStart(2,"0")+"h"+(min>0?String(min).padStart(2,"0"):"");
}

function render() {
  const S = window.SURF_DATA;
  if (!S || !S.previsions || !S.previsions.length) return;
  const vd = verdict(S.previsions), now = S.previsions[0];

  document.getElementById("verdict").style.color   = vd.c;
  document.getElementById("verdict").textContent   = vd.v;
  document.getElementById("phrase").textContent    = '"' + vd.ph + '"';
  document.getElementById("now-label").textContent = "Maintenant · " + now.moment;

  document.getElementById("ngrid").innerHTML = [
    ["Houle",   now.houle+"m",             hCol(now.houle)],
    ["Période", now.periode+"s",           "#555"],
    ["Dir.",    now.dir,                   "#4a4a4a"],
    ["Swell",   now.swell+"m "+now.swellPeriode+"s", "#3a6a8a"],
    ["Vent",    now.vent+"km/h "+now.vdir, wCol(now.vent)],
    ["Eau",     S.tempEau+"°C",            "#2a6a7a"],
  ].map(([l,v,c]) =>
    `<div class="ncell"><div class="nlabel">${l}</div><div class="nval" style="color:${c}">${v}</div></div>`
  ).join("");

  if (S.alertes && S.alertes.length) {
    const al = document.getElementById("alerts");
    al.textContent = S.alertes.join("  ·  ");
    al.style.display = "block";
  }

  const B = S.bestSession;
  document.getElementById("tbody").innerHTML = S.previsions.map(r => {
    const best = B && r.jour===B.jour && r.heure===B.heure;
    const {sens, prochain} = tideInfo(S.marees, r.jour, r.heure);
    const up   = sens === "montant";
    const bg   = best ? "#e8f2ec" : r.note>=1 ? "#f0f5f0" : "transparent";
    const bl   = best ? `2px solid ${C.best}` : "2px solid transparent";
    const badge = best
      ? `<span style="color:${C.best};font-size:0.65rem">▶</span>`
      : r.note>=2 ? `<span style="color:${C.star};font-size:0.6rem">★</span>` : "";
    const ew   = Math.min(r.energie/120*100, 100);
    const mCol = prochain ? (prochain.type==="H" ? C.hmColor : C.bmColor) : "#bbb";
    const mLabel = prochain
      ? `${prochain.type==="H"?"HM":"BM"} ${fmtH(prochain)} ${prochain.m>0?"+":""}${prochain.m}m`
      : "—";

    return `<tr style="background:${bg};border-left:${bl}">
<td style="width:14px;padding-left:0.7rem">${badge}</td>
<td style="color:${best?"#2a6a4a":r.note>=1?"#3a4a3a":"#555"};white-space:nowrap;font-size:0.58rem;font-weight:${best?400:300}">${r.moment}</td>
<td><div style="display:flex;align-items:center;gap:3px">
  <span style="font-size:13px;color:${hCol(r.houle)}">${DIR[r.dir]||"•"}</span>
  <span style="color:${hCol(r.houle)};font-weight:${r.houle>=0.7?400:300}">${r.houle}m</span>
</div></td>
<td style="color:#666">${r.periode}s</td>
<td style="color:#3a6a8a;font-size:0.58rem;white-space:nowrap">${r.swell}m ${r.swellPeriode}s <span style="color:#aaa">${r.swellDir}</span></td>
<td><div style="display:flex;align-items:center;gap:4px">
  <div style="flex:1;height:2px;background:#ddd;position:relative;min-width:32px">
    <div style="position:absolute;left:0;top:0;height:100%;width:${ew}%;background:${eCol(r.energie)}"></div>
  </div>
  <span style="font-size:0.54rem;color:${eCol(r.energie)};min-width:22px;text-align:right">${r.energie}</span>
</div></td>
<td><div style="display:flex;align-items:center;gap:3px">
  <span style="font-size:13px;color:${wCol(r.vent)}">${DIR[r.vdir]||"•"}</span>
  <span style="color:${wCol(r.vent)}">${r.vent}</span>
  <span style="color:#999;font-size:0.52rem">${r.vdir}</span>
</div></td>
<td><div style="display:flex;align-items:center;gap:4px">
  <span style="font-size:0.85rem;color:${up?C.up:C.down};line-height:1">${up?"↑":"↓"}</span>
  <span style="font-size:0.5rem;color:${mCol}">${mLabel}</span>
</div></td>
</tr>`;
  }).join("");

  document.getElementById("foot").textContent =
    "Open-Meteo · Stormglass · " + S.updated + " · Houle=vague totale | Swell=houle longue distance";
}

document.addEventListener("DOMContentLoaded", render);
"""

CSS = """
* { box-sizing:border-box; margin:0; padding:0; }
body { background:#f5f3f0; color:#2a2a2a; font-family:'IBM Plex Mono',monospace; min-height:100vh; }
.header { padding:1.4rem 1.4rem 0; border-bottom:1px solid #ddd; display:flex; justify-content:space-between; align-items:flex-start; }
.title { font-size:0.95rem; letter-spacing:6px; color:#555; text-transform:uppercase; font-weight:300; }
.coords { font-size:0.54rem; color:#aaa; letter-spacing:2px; margin-top:0.2rem; padding-bottom:1rem; }
.btn { background:transparent; border:1px solid #ccc; color:#666; padding:0.4rem 0.9rem; font-family:inherit; font-size:0.6rem; letter-spacing:2px; text-transform:uppercase; cursor:pointer; }
.btn:hover { border-color:#999; color:#333; }
.vbox { padding:1.2rem 1.4rem; border-bottom:1px solid #ddd; }
.verdict { font-size:1.8rem; letter-spacing:7px; font-weight:300; margin-bottom:0.2rem; }
.phrase { font-size:0.66rem; color:#999; font-style:italic; margin-bottom:0.8rem; }
.now-label { font-size:0.5rem; color:#bbb; letter-spacing:2px; margin-bottom:0.4rem; text-transform:uppercase; }
.ngrid { display:grid; grid-template-columns:repeat(3,1fr); gap:1px; background:#e8e5e0; margin-top:0.8rem; }
.ncell { background:#f5f3f0; padding:0.8rem; }
.nlabel { font-size:0.48rem; color:#bbb; letter-spacing:2px; text-transform:uppercase; margin-bottom:0.25rem; }
.nval { font-size:1rem; font-weight:300; }
.alerts { padding:0.6rem 1.4rem; border-bottom:1px solid #ddd; font-size:0.6rem; color:#b07a3a; }
.legend { padding:0.35rem 1.4rem; font-size:0.48rem; color:#bbb; border-bottom:1px solid #e0ddd8; display:flex; gap:1rem; }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:0.62rem; min-width:560px; }
th { padding:0.28rem 0.5rem; color:#bbb; font-weight:300; font-size:0.48rem; letter-spacing:1px; text-align:left; border-bottom:1px solid #e0ddd8; }
td { padding:0.32rem 0.5rem; border-bottom:1px solid #eae7e2; vertical-align:middle; }
.foot { padding:0.8rem 1.4rem; font-size:0.44rem; color:#bbb; border-top:1px solid #e0ddd8; font-style:italic; }
"""


def generate_html(surf):
    data_json = json.dumps(surf, ensure_ascii=False)
    return (
        '<!DOCTYPE html><html lang="fr"><head>'
        '<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Port-Louis · Surf</title>'
        '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400&display=swap" rel="stylesheet">'
        f'<style>{CSS}</style></head><body>'
        f'<script>window.SURF_DATA={data_json};</script>'
        '<div class="header"><div>'
        '<div class="title">Port-Louis · Surf</div>'
        '<div class="coords">Grande-Terre · Guadeloupe · 16.43°N 61.54°W</div>'
        '</div><button class="btn" onclick="location.reload()">↺ Actualiser</button></div>'
        '<div class="vbox">'
        '<div class="verdict" id="verdict"></div>'
        '<div class="phrase" id="phrase"></div>'
        '<div class="now-label" id="now-label"></div>'
        '<div class="ngrid" id="ngrid"></div>'
        '</div>'
        '<div class="alerts" id="alerts" style="display:none"></div>'
        '<div class="legend">'
        '<span style="color:#4a6a5a">▶ meilleure session 72h</span>'
        '<span style="color:#6a5a3a">★ note ≥ 2</span>'
        '</div>'
        '<div class="table-wrap"><table>'
        '<thead><tr>'
        '<th></th><th>Créneau</th><th>Houle</th><th>Pér.</th>'
        '<th>Swell</th><th>Énergie</th><th>Vent</th><th>Marée</th>'
        '</tr></thead>'
        '<tbody id="tbody"></tbody></table></div>'
        '<div class="foot" id="foot"></div>'
        f'<script>{JS}</script>'
        '</body></html>'
    )


def main():
    om, ow = fetch_open_meteo()
    marees = fetch_marees()
    surf   = process(om, ow, marees)
    debug(surf)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(generate_html(surf))
    print(f"Dashboard: {out}")

if __name__ == "__main__":
    main()
