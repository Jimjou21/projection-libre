#!/usr/bin/env python3
"""
Projection libre - programme local.

Lance l'outil dans ton navigateur et va chercher lui-même les résultats
sur les sites que tu as ajoutés (section « Mes sites »).

Utilisation : double-clic sur « Lancer Projection libre.bat »
ou, dans un terminal :  python projection_libre.py

Aucune installation de module : uniquement la bibliothèque standard Python 3.8+.
Sur ton PC, le programme n'écoute que sur ton ordinateur (127.0.0.1).

En ligne (Render ou autre hébergeur), variables d'environnement :
  PORT       fournie par l'hébergeur
  CODE_ACCES code à saisir dans l'outil pour l'utiliser (fortement conseillé)
  TMDB_KEY   clé TMDB, pour ne pas avoir à la saisir sur chaque appareil
"""
import base64
import ipaddress
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import socket
import sys
import threading
import unicodedata
import webbrowser
from html import unescape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

PORT = 8765
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
STOP = {"le", "la", "les", "l", "de", "du", "des", "d", "un", "une", "et", "a",
        "au", "aux", "the", "of", "and", "an", "en"}

CODE = os.environ.get("CODE_ACCES", "").strip()
TMDB_KEY = os.environ.get("TMDB_KEY", "").strip()
CLOUD = "PORT" in os.environ
TMDB_PATHS = re.compile(r"^/(search/movie|discover/movie|movie/\d+/watch/providers)$")

MANIFEST = json.dumps({
    "name": "Projection libre", "short_name": "Projection", "start_url": "/",
    "display": "standalone", "background_color": "#eef0f2", "theme_color": "#a8322b",
    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
})
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        '<rect width="512" height="512" rx="96" fill="#a8322b"/>'
        '<circle cx="256" cy="256" r="150" fill="none" stroke="#fff" stroke-width="28"/>'
        '<circle cx="256" cy="256" r="26" fill="#fff"/>'
        '<circle cx="256" cy="166" r="34" fill="#fff"/><circle cx="256" cy="346" r="34" fill="#fff"/>'
        '<circle cx="166" cy="256" r="34" fill="#fff"/><circle cx="346" cy="256" r="34" fill="#fff"/></svg>')

PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Projection libre</title>
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#a8322b">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Projection libre">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;800&family=Source+Sans+3:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --bg:#eef0f2;--surface:#fff;--ink:#16202a;--muted:#5b6670;--line:#d5dade;
  --accent:#a8322b;--accent-ink:#fff;--accent-soft:#f6e3e1;
  --free:#2e6a5f;--free-soft:#dfeeea;--ads:#8a6a1e;--ads-soft:#f3ecd9;--pd:#3b5b8f;--pd-soft:#e1e8f4;
  --ok:#2e6a5f;--bad:#a8322b;
  --f-display:"Big Shoulders Display","Arial Narrow",Impact,sans-serif;
  --f-body:"Source Sans 3",system-ui,-apple-system,"Segoe UI",sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#12171c;--surface:#1b2229;--ink:#e8ecef;--muted:#9aa5ae;--line:#2c353d;
  --accent:#e0665d;--accent-ink:#1b0e0c;--accent-soft:#3a2220;
  --free:#7cc4b5;--free-soft:#1d332e;--ads:#dcbd6c;--ads-soft:#352d17;--pd:#9bb6e6;--pd-soft:#1f2a3d;
  --ok:#7cc4b5;--bad:#e0665d;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 var(--f-body);padding:20px 16px 48px}
.wrap{max-width:1000px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
a{color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.eyebrow{font:500 12px var(--f-mono);letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
h1{font:800 clamp(44px,10vw,72px)/.9 var(--f-display);text-transform:uppercase;margin:4px 0 0}
.lede{color:var(--muted);margin:6px 0 0;max-width:65ch}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input[type=text],input[type=password],input[type=url]{flex:1 1 220px;min-width:0;font:16px var(--f-body);color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
#q{font-size:17px}
.btn{font:700 15px var(--f-body);border-radius:8px;padding:10px 16px;cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--ink)}
.btn-primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.btn-small{font-size:13px;padding:6px 10px}
.btn:disabled{opacity:.5;cursor:wait}
.toggles{display:flex;gap:6px;flex-wrap:wrap}
.toggle{display:inline-flex;align-items:center;gap:6px;font-size:14px;border:1px solid var(--line);border-radius:999px;padding:5px 11px;cursor:pointer;user-select:none}
.toggle input{accent-color:var(--accent)}
.status{display:flex;gap:8px;flex-wrap:wrap;font:13px var(--f-mono);color:var(--muted)}
.status span{border:1px solid var(--line);border-radius:4px;padding:2px 8px}
.status .ok{color:var(--ok)} .status .bad{color:var(--bad)}
.results-head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}
h2{font:600 28px var(--f-display);text-transform:uppercase;margin:0}
.count{font:13px var(--f-mono);color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.card .body{padding:12px 14px 14px;display:flex;flex-direction:column;gap:8px;flex:1}
.card img{width:100%;aspect-ratio:16/9;object-fit:cover;background:var(--bg);display:block}
.card h3{font:800 22px/1.05 var(--f-display);text-transform:uppercase;margin:0;overflow-wrap:anywhere}
.meta{font:12.5px var(--f-mono);color:var(--muted)}
.overview{font-size:14px;color:var(--muted);margin:0;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.plats{display:flex;gap:6px;flex-wrap:wrap;margin-top:auto}
.plat{font:600 13px var(--f-body);text-decoration:none;border-radius:6px;padding:5px 9px}
.k-free{background:var(--free-soft);color:var(--free)}
.k-ads{background:var(--ads-soft);color:var(--ads)}
.k-pd{background:var(--pd-soft);color:var(--pd)}
.plat small{font-weight:400;opacity:.8}
.empty{color:var(--muted);border:1px dashed var(--line);border-radius:10px;padding:18px;background:var(--surface)}
.extra{display:flex;gap:6px;flex-wrap:wrap}
.extra a{font:600 13.5px var(--f-body);text-decoration:none;border:1px solid var(--line);border-radius:6px;padding:6px 10px;background:var(--surface)}
details.panel summary{cursor:pointer;font-weight:700}
.settings{display:flex;flex-direction:column;gap:16px;margin-top:12px}
.settings h3{font:500 12px var(--f-mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0}
.settings p{margin:0;font-size:14px;color:var(--muted)}
.linklist{display:flex;flex-direction:column;gap:6px}
.linkitem{display:flex;gap:8px;align-items:center;font-size:14px;flex-wrap:wrap}
.linkitem code{font:12px var(--f-mono);color:var(--muted);overflow-wrap:anywhere;flex:1;min-width:0}
.extra a.all{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.site-chips{display:flex;gap:6px;flex-wrap:wrap}
.site-chip{display:inline-flex;align-items:center;gap:6px;font-size:14px;font-weight:600;border:1px solid var(--line);border-radius:999px;padding:3px 4px 3px 12px;background:var(--bg)}
.site-chip small{font:400 11px var(--f-mono);color:var(--muted)}
.site-chip .x{border:0;background:transparent;color:var(--muted);font-size:18px;line-height:1;width:26px;height:26px;border-radius:50%;cursor:pointer}
.site-chip .x:hover{background:var(--accent-soft);color:var(--accent)}
.site-msg{margin:0;font-size:14px;min-height:1em}
.site-msg.ok{color:var(--ok)} .site-msg.bad{color:var(--bad)}
.site-groups{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.sg{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:8px;min-width:0}
.sg-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.sg-head strong{font:800 20px var(--f-display);text-transform:uppercase}
.sg-head span{font:12px var(--f-mono);color:var(--muted)}
.sg ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.sg li a{font-weight:600;text-decoration-color:var(--line);text-underline-offset:3px;overflow-wrap:anywhere}
.sg li a:hover{text-decoration-color:var(--accent)}
.sg li p{margin:2px 0 0;font-size:13.5px;color:var(--muted);overflow-wrap:anywhere}
.sg li small{font:11.5px var(--f-mono);color:var(--muted);overflow-wrap:anywhere}
.sg .none{font-size:14px;color:var(--muted);margin:0}
.diag{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.diag p{margin:0;font-size:14px}
.diag-row{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;font-size:14px}
.diag-row span{font:500 12px var(--f-mono);border-radius:4px;padding:1px 6px;border:1px solid currentColor}
.diag-row small{color:var(--muted);font:12px var(--f-mono);overflow-wrap:anywhere;flex-basis:100%}
.diag .ok{color:var(--ok)} .diag .bad{color:var(--bad)}
.server-note{font-size:14px;color:var(--muted);margin:0}
footer{font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="eyebrow">Gratuit · Légal · France</span>
    <h1>Projection libre</h1>
    <p class="lede">Moteur de recherche autonome : il interroge directement des bases ouvertes pour trouver les films visibles gratuitement et légalement. Aucune IA, aucun compte Claude.</p>
  </header>

  <form class="panel" id="form" autocomplete="off">
    <div class="row">
      <input id="q" type="text" placeholder="Titre, réalisateur, mot-clé… (vide = tout le gratuit du moment)">
      <button class="btn btn-primary" id="go" type="submit">Chercher</button>
      <button class="btn" id="discover" type="button">Découvrir le gratuit</button>
    </div>
    <div class="toggles" id="srcToggles"></div>
    <div class="toggles">
      <label class="toggle"><input type="checkbox" id="optVF"> VF / films français en priorité</label>
      <label class="toggle"><input type="checkbox" id="optLoose"> Montrer aussi les titres approchants</label>
    </div>
    <div class="status" id="status" aria-live="polite"></div>
  </form>

  <section style="display:flex;flex-direction:column;gap:12px">
    <div class="results-head"><h2>Résultats</h2><span class="count" id="count"></span></div>
    <div class="grid" id="grid"></div>
  </section>

  <section style="display:flex;flex-direction:column;gap:12px" id="siteResWrap" hidden>
    <div class="results-head"><h2>Sur mes sites</h2><span class="count" id="siteCount"></span></div>
    <div class="site-groups" id="siteRes"></div>
  </section>

  <section class="panel" aria-labelledby="sites-h">
    <h2 id="sites-h" style="font-size:22px">Mes sites</h2>
    <div class="extra" id="extra"></div>
    <p class="meta" id="extraHint" style="margin:0">Lance une recherche de titre : un lien par site apparaîtra ici.</p>
    <div class="row">
      <input id="newSite" type="text" inputmode="url" placeholder="Colle l'adresse d'un site, ex. arte.tv">
      <button class="btn btn-primary btn-small" type="button" id="addSite">Ajouter</button>
    </div>
    <p class="site-msg" id="siteMsg" aria-live="polite"></p>
    <div class="site-chips" id="siteChips"></div>
    <p class="meta" style="margin:0">Astuce pour une recherche directe sur le site : cherche le mot <strong>TEST</strong> sur ce site, puis colle ici l'adresse de la page de résultats.</p>
    <button class="btn btn-small" type="button" id="resetLinks" style="align-self:flex-start">Rétablir les sites par défaut</button>
  </section>

  <details class="panel" id="settingsPanel">
    <summary>Réglages et sources</summary>
    <div class="settings">
      <div>
        <h3>Diagnostic</h3>
        <p>Teste chaque source depuis le serveur et affiche ce qui fonctionne.</p>
        <button class="btn btn-small" type="button" id="diagBtn" style="margin-top:8px">Tester les sources</button>
        <div class="diag" id="diagOut"></div>
      </div>
      <div>
        <h3>Code d'accès</h3>
        <p>Le code choisi lors de la mise en ligne. À saisir une fois par appareil.</p>
        <div class="row" style="margin-top:8px">
          <input id="accessCode" type="password" placeholder="Code d'accès">
          <button class="btn btn-small" type="button" id="saveCode">Enregistrer</button>
        </div>
      </div>
      <div id="tmdbBlock">
        <h3>Clé TMDB (plateformes françaises)</h3>
        <p>Débloque Arte, france.tv, TF1+, M6+, Pluto TV, Rakuten TV gratuit, Plex… Clé gratuite : crée un compte sur themoviedb.org, puis Paramètres › API. La clé reste dans ton navigateur.</p>
        <div class="row" style="margin-top:8px">
          <input id="tmdbKey" type="password" placeholder="Clé API (v3) ou jeton d'accès (v4)">
          <button class="btn btn-small" type="button" id="saveKey">Enregistrer</button>
        </div>
      </div>
    </div>
  </details>

  <footer>Sources interrogées : TMDB (données de disponibilité JustWatch), Wikidata (films libres référencés, base de WikiFlix), Internet Archive (collections de films du domaine public). Les catalogues gratuits changent souvent.</footer>
</div>

<script>
/* =====================================================================
   AJOUTER UNE SOURCE INTERROGÉE AUTOMATIQUEMENT
   Ajoute un objet dans SOURCES :
   {
     id: "monsite", name: "Mon site", on: true,
     search: async (q, opts) => [ RESULTAT, ... ],   // q peut être vide
   }
   RESULTAT = { title, year, overview, image, platforms: [{name, kind, url}] }
   kind : "free" (gratuit), "ads" (gratuit avec pub), "pd" (domaine public)
   L'API du site doit autoriser les appels depuis un navigateur (CORS).
   ===================================================================== */

const store = {
  get(k, d){ try { const v = localStorage.getItem("pl_"+k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v){ try { localStorage.setItem("pl_"+k, JSON.stringify(v)); } catch {} }
};

/* Serveur Projection libre (PC ou en ligne) : null si la page est ouverte comme simple fichier */
const serverInfo = location.protocol.startsWith("http")
  ? fetch("/api/ping").then(r => r.ok ? r.json() : null).catch(() => null)
  : Promise.resolve(null);
function authHeaders(){ const c = (store.get("code","") || "").trim(); return c ? { "X-Code": c } : {}; }

async function getJSON(url, init){
  const info = await serverInfo;
  const host = new URL(url).hostname;
  if (info && (host === "query.wikidata.org" || host === "archive.org")) {
    url = "/api/fetch?u=" + encodeURIComponent(url); init = { headers: authHeaders() };
  }
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 25000);
  try {
    const r = await fetch(url, { ...(init||{}), signal: ctl.signal });
    if (r.status === 401) throw new Error("code d'accès requis");
    if (!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

/* ---------- TMDB : disponibilité gratuite / avec pub en France ---------- */
async function tmdbFetch(path, params){
  const info = await serverInfo;
  if (info && info.tmdb) {
    const u = new URLSearchParams({ p: path, ...(params||{}) });
    const r = await fetch("/api/tmdb?" + u.toString(), { headers: authHeaders() });
    if (r.status === 401) throw new Error("code d'accès requis");
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }
  const key = (store.get("tmdb","") || "").trim();
  if (!key) throw new Error("clé TMDB manquante");
  const u = new URL("https://api.themoviedb.org/3" + path);
  Object.entries(params||{}).forEach(([k,v]) => u.searchParams.set(k, v));
  const init = {};
  if (key.length > 60) init.headers = { Authorization: "Bearer " + key };
  else u.searchParams.set("api_key", key);
  return getJSON(u.toString(), init);
}
async function tmdbSearch(q, opts){
  let movies;
  if (q){
    const d = await tmdbFetch("/search/movie", { query: q, language: "fr-FR", region: "FR", include_adult: "false" });
    movies = d.results.slice(0, 15);
  } else {
    const p = { watch_region: "FR", with_watch_monetization_types: "free|ads", language: "fr-FR", sort_by: "popularity.desc", include_adult: "false" };
    if (opts.vf) p.with_original_language = "fr";
    const [a, b] = await Promise.all([tmdbFetch("/discover/movie", {...p, page: 1}), tmdbFetch("/discover/movie", {...p, page: 2})]);
    movies = a.results.concat(b.results);
  }
  const out = await Promise.all(movies.map(async m => {
    try {
      const w = await tmdbFetch("/movie/" + m.id + "/watch/providers");
      const fr = w.results && w.results.FR; if (!fr) return null;
      const plats = [];
      (fr.free||[]).forEach(p => plats.push({ name: p.provider_name, kind: "free", url: fr.link }));
      (fr.ads||[]).forEach(p => plats.push({ name: p.provider_name, kind: "ads", url: fr.link }));
      if (!plats.length) return null;
      return { title: m.title, alt: m.original_title, year: (m.release_date||"").slice(0,4), overview: m.overview,
        image: m.backdrop_path ? "https://image.tmdb.org/t/p/w500" + m.backdrop_path : null,
        lang: m.original_language, platforms: plats };
    } catch { return null; }
  }));
  return out.filter(Boolean);
}

/* ---------- Wikidata : films libres avec vidéo référencée ---------- */
async function wikidataSearch(q, opts){
  const esc = s => s.replace(/\\/g,"\\\\").replace(/"/g,'\\"');
  const finder = q
    ? `SERVICE wikibase:mwapi { bd:serviceParam wikibase:endpoint "www.wikidata.org"; wikibase:api "EntitySearch"; mwapi:search "${esc(q)}"; mwapi:language "fr"; wikibase:limit 50 . ?film wikibase:apiOutputItem mwapi:item . }`
    : `?film wdt:P10 ?commons0 .`;
  const sparql = `SELECT ?film ?filmLabel (SAMPLE(?y) AS ?year) (SAMPLE(?c) AS ?commons) (SAMPLE(?ia) AS ?iaid) (SAMPLE(?yt) AS ?ytid) WHERE {
    ${finder}
    ?film wdt:P31 ?type . VALUES ?type { wd:Q11424 wd:Q24869 wd:Q202866 wd:Q506240 wd:Q24862 wd:Q93204 }
    ${opts.vf ? "?film wdt:P364 wd:Q150 ." : ""}
    OPTIONAL { ?film wdt:P10 ?c } OPTIONAL { ?film wdt:P724 ?ia } OPTIONAL { ?film wdt:P1651 ?yt }
    FILTER(BOUND(?c) || BOUND(?ia) || BOUND(?yt))
    OPTIONAL { ?film wdt:P577 ?d . BIND(YEAR(?d) AS ?y) }
    SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en". }
  } GROUP BY ?film ?filmLabel LIMIT ${q ? 40 : 60}`;
  const d = await getJSON("https://query.wikidata.org/sparql?format=json&query=" + encodeURIComponent(sparql), { headers: { Accept: "application/sparql-results+json" } });
  return d.results.bindings.map(b => {
    const plats = [];
    if (b.commons) plats.push({ name: "Wikimedia Commons", kind: "pd", url: b.commons.value });
    if (b.iaid) plats.push({ name: "Internet Archive", kind: "pd", url: "https://archive.org/details/" + b.iaid.value });
    if (b.ytid) plats.push({ name: "YouTube", kind: "pd", url: "https://www.youtube.com/watch?v=" + b.ytid.value });
    return { title: b.filmLabel.value, year: b.year ? b.year.value : "", overview: "", image: null, platforms: plats };
  });
}

/* ---------- Internet Archive : collection Feature Films ---------- */
async function archiveSearch(q, opts){
  let query = "mediatype:(movies) AND collection:(feature_films OR silent_films)";
  if (q) {
    const words = q.replace(/[^\p{L}\p{N}\s]/gu, " ").split(/\s+/).filter(Boolean);
    if (words.length) query += " AND title:(" + words.join(" AND ") + ")";
  }
  if (opts.vf) query += " AND language:(French OR fre OR fra OR fr)";
  const u = "https://archive.org/advancedsearch.php?q=" + encodeURIComponent(query)
    + "&fl[]=identifier&fl[]=title&fl[]=year&fl[]=description&rows=40&output=json"
    + (q ? "" : "&sort[]=downloads+desc");
  const d = await getJSON(u);
  return d.response.docs.map(x => ({
    title: Array.isArray(x.title) ? x.title[0] : x.title, year: x.year ? String(x.year).slice(0,4) : "",
    overview: (Array.isArray(x.description) ? x.description[0] : (x.description||"")).replace(/<[^>]+>/g," ").slice(0,300),
    image: "https://archive.org/services/img/" + x.identifier,
    platforms: [{ name: "Internet Archive", kind: "pd", url: "https://archive.org/details/" + x.identifier }]
  }));
}

const SOURCES = [
  { id: "tmdb", name: "Plateformes FR (TMDB)", on: true, search: tmdbSearch },
  { id: "wikidata", name: "Wikidata / WikiFlix", on: true, search: wikidataSearch },
  { id: "archive", name: "Internet Archive", on: true, search: archiveSearch }
];

/* Un site = { name, host, url }. url contient {q} (recherche directe) ; sinon recherche Google limitée au site. */
const DEFAULT_LINKS = [
  { name: "JustWatch", host: "justwatch.com", url: "https://www.justwatch.com/fr/recherche?q={q}" },
  { name: "Arte.tv", host: "arte.tv", url: "https://www.arte.tv/fr/search/?q={q}" },
  { name: "YouTube", host: "youtube.com", url: "https://www.youtube.com/results?search_query={q}+film+complet" },
  { name: "france.tv", host: "france.tv", url: "" },
  { name: "TF1+", host: "tf1.fr", url: "" },
  { name: "M6+", host: "m6.fr", url: "" },
  { name: "70millimètres", host: "70millimetres.fr", url: "" }
];

/* Transforme ce que la personne colle en site exploitable */
function makeLink(raw){
  let s = raw.trim(); if (!s) return null;
  if (!/^https?:\/\//i.test(s)) s = "https://" + s;
  let u; try { u = new URL(s); } catch { return null; }
  const host = u.hostname.replace(/^www\./, "");
  if (!host.includes(".")) return null;
  let url = "";
  if (s.includes("{q}")) url = s;
  else if (/TEST/.test(s) && (u.search || u.pathname.length > 1)) url = s.replace(/TEST/g, "{q}");
  const name = host.split(".").slice(0, -1).join(".") || host;
  return { name: name.charAt(0).toUpperCase() + name.slice(1), host, url };
}
function linkFor(l, q){
  if (l.url) return l.url.replace(/\{q\}/g, encodeURIComponent(q));
  return "https://www.google.com/search?q=" + encodeURIComponent('"' + q + '" site:' + l.host);
}

/* ---------- Interface ---------- */
const $ = id => document.getElementById(id);
const el = (t, c, txt) => { const n = document.createElement(t); if (c) n.className = c; if (txt != null) n.textContent = txt; return n; };
const KIND = { free: "Gratuit", ads: "Gratuit avec pub", pd: "Domaine public" };

const enabled = store.get("enabled", {});
SOURCES.forEach(s => { if (s.id in enabled) s.on = enabled[s.id]; });
SOURCES.forEach(s => {
  const l = el("label", "toggle"); const c = el("input"); c.type = "checkbox"; c.checked = s.on; c.id = "src-" + s.id;
  c.onchange = () => { s.on = c.checked; enabled[s.id] = c.checked; store.set("enabled", enabled); };
  l.append(c, document.createTextNode(s.name)); $("srcToggles").append(l);
});
$("optVF").checked = store.get("vf", false);
$("optVF").onchange = () => store.set("vf", $("optVF").checked);
$("tmdbKey").value = store.get("tmdb", "");
$("saveKey").onclick = () => { store.set("tmdb", $("tmdbKey").value.trim()); $("saveKey").textContent = "Enregistrée"; setTimeout(() => $("saveKey").textContent = "Enregistrer", 1500); };

let links = store.get("links2", null) || DEFAULT_LINKS.slice();
function saveLinks(){ store.set("links2", links); }
function renderLinks(){
  const box = $("siteChips"); box.replaceChildren();
  links.forEach((l, i) => {
    const chip = el("span", "site-chip");
    chip.append(el("span", null, l.name), el("small", null, l.url ? "direct" : "via moteur"));
    const b = el("button", "x", "×"); b.type = "button"; b.title = "Retirer " + l.name; b.setAttribute("aria-label", "Retirer " + l.name);
    b.onclick = () => { links.splice(i, 1); saveLinks(); renderLinks(); renderExtra(); };
    chip.append(b); box.append(chip);
  });
}
function addSite(){
  const inp = $("newSite"), msg = $("siteMsg");
  const l = makeLink(inp.value);
  if (!l) { msg.textContent = "Adresse non reconnue. Exemple : arte.tv ou https://www.arte.tv"; msg.className = "site-msg bad"; inp.focus(); return; }
  const dup = links.findIndex(x => x.host === l.host);
  if (dup >= 0 && !l.url) {
    msg.textContent = links[dup].name + " est déjà dans tes sites (" + l.host + ").";
    msg.className = "site-msg ok"; inp.value = ""; return;
  }
  if (dup >= 0) { l.name = links[dup].name; links[dup] = l; } else links.push(l);
  saveLinks(); renderLinks(); renderExtra();
  msg.textContent = (dup >= 0 ? l.name + " mis à jour" : l.name + " ajouté") + (l.url ? " : recherche directe sur le site." : " : recherche via moteur, limitée à ce site.");
  msg.className = "site-msg ok"; inp.value = "";
  if (lastQuery) runSites(lastQuery);
}
$("addSite").onclick = addSite;
$("newSite").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); addSite(); } });
$("resetLinks").onclick = () => { links = DEFAULT_LINKS.slice(); saveLinks(); renderLinks(); renderExtra(); };
renderLinks();

let lastQuery = "";
function renderExtra(){
  const ex = $("extra"); ex.replaceChildren();
  const q = lastQuery;
  $("extraHint").hidden = !!q;
  if (!q) return;
  links.forEach(l => { const a = el("a", null, l.name); a.href = linkFor(l, q); a.target = "_blank"; a.rel = "noopener noreferrer"; ex.append(a); });
  const google = links.filter(l => l.host);
  if (google.length > 1){
    const a = el("a", "all", "Tous mes sites en une recherche");
    a.href = "https://www.google.com/search?q=" + encodeURIComponent('"' + q + '" (' + google.map(l => "site:" + l.host).join(" OR ") + ")");
    a.target = "_blank"; a.rel = "noopener noreferrer"; ex.prepend(a);
  }
}

/* ---------- Résultats de mes sites (via le programme local) ---------- */
const serverReady = serverInfo.then(i => !!i);

async function runSites(q){
  const wrap = $("siteResWrap"), box = $("siteRes");
  if (!q || !links.length) { wrap.hidden = true; return; }
  wrap.hidden = false; box.replaceChildren();
  if (!(await serverReady)) {
    $("siteCount").textContent = "";
    box.append(el("p", "server-note", "Pour voir ici les résultats de tes sites, ouvre l'outil avec « Lancer Projection libre » (programme local). En attendant, utilise les boutons de la section Mes sites."));
    return;
  }
  let total = 0, done = 0;
  $("siteCount").textContent = "recherche sur " + links.length + " sites…";
  await Promise.all(links.map(async l => {
    const g = el("div", "sg"); const head = el("div", "sg-head");
    const st = el("span", null, "recherche…");
    head.append(el("strong", null, l.name), st); g.append(head); box.append(g);
    try {
      const u = "/api/site?q=" + encodeURIComponent(q) + "&host=" + encodeURIComponent(l.host || "") + "&url=" + encodeURIComponent(l.url || "");
      const r = await fetch(u, { headers: authHeaders() });
      if (r.status === 401) { $("settingsPanel").open = true; throw new Error("code d'accès requis, voir Réglages"); }
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      let items = d.results || [];
      const loose = $("optLoose").checked;
      items = items.map(x => ({ ...x, _s: score({ title: x.title }, q) })).filter(x => loose ? true : x._s >= 65).sort((a, b) => b._s - a._s);
      st.textContent = items.length + " résultat" + (items.length > 1 ? "s" : "") + (d.method === "site" ? " · sur le site" : " · via moteur");
      total += items.length;
      if (!items.length) { g.append(el("p", "none", "Rien qui corresponde à « " + q + " ».")); return; }
      const ul = el("ul");
      items.slice(0, 8).forEach(x => {
        const li = el("li"); const a = el("a", null, x.title); a.href = x.url; a.target = "_blank"; a.rel = "noopener noreferrer";
        li.append(a);
        if (x.snippet) li.append(el("p", null, x.snippet));
        li.append(el("small", null, x.url.replace(/^https?:\/\/(www\.)?/, "").slice(0, 80)));
        ul.append(li);
      });
      g.append(ul);
    } catch (e) {
      st.textContent = "erreur";
      g.append(el("p", "none", "Site injoignable pour le moment (" + (e.message || "erreur") + ")."));
    } finally {
      done++; $("siteCount").textContent = done < links.length ? "recherche… " + done + "/" + links.length : total + " résultat" + (total > 1 ? "s" : "");
    }
  }));
}

/* Pertinence : le titre doit vraiment correspondre à la recherche */
const STOP = new Set(["le","la","les","l","de","du","des","d","un","une","et","a","au","aux","the","of","and","an","en"]);
function tokens(s){ return norm(s).split(" ").filter(w => w && !STOP.has(w)); }
function score(r, q){
  const nq = norm(q); if (!nq) return 1;
  let best = 0;
  [r.title, r.alt].filter(Boolean).forEach(t => {
    const nt = norm(t);
    let s = 0;
    if (nt === nq) s = 100;
    else if ((" " + nt + " ").includes(" " + nq + " ")) s = 85;
    else {
      const qt = tokens(q), tt = new Set(tokens(t));
      if (qt.length) {
        const hit = qt.filter(w => tt.has(w) || [...tt].some(x => x.length > 4 && w.length > 4 && (x.startsWith(w) || w.startsWith(x)))).length;
        if (hit === qt.length) s = 65; else if (qt.length >= 3 && hit / qt.length >= 0.75) s = 40;
      }
    }
    best = Math.max(best, s);
  });
  return best;
}

function norm(s){ return (s||"").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"").replace(/[^a-z0-9]+/g," ").trim(); }
function merge(all){
  const map = new Map();
  all.forEach(r => {
    if (!r || !r.title) return;
    const k = norm(r.title) + "|" + (r.year || "");
    const cur = map.get(k);
    if (!cur) { map.set(k, { ...r, platforms: r.platforms.slice() }); return; }
    r.platforms.forEach(p => { if (!cur.platforms.some(x => x.name === p.name)) cur.platforms.push(p); });
    if (!cur.image && r.image) cur.image = r.image;
    if (!cur.overview && r.overview) cur.overview = r.overview;
  });
  return [...map.values()];
}

function card(r){
  const c = el("article", "card");
  if (r.image){ const img = el("img"); img.src = r.image; img.alt = ""; img.loading = "lazy"; img.onerror = () => img.remove(); c.append(img); }
  const b = el("div", "body");
  b.append(el("h3", null, r.title));
  if (r.year) b.append(el("div", "meta", r.year));
  if (r.overview) b.append(el("p", "overview", r.overview));
  const p = el("div", "plats");
  r.platforms.forEach(x => {
    const a = el("a", "plat k-" + x.kind); a.href = x.url; a.target = "_blank"; a.rel = "noopener noreferrer";
    a.append(document.createTextNode(x.name + " "), el("small", null, "· " + KIND[x.kind]));
    p.append(a);
  });
  b.append(p); c.append(b); return c;
}

let running = false;
async function run(q){
  if (running) return; running = true;
  $("go").disabled = $("discover").disabled = true;
  const opts = { vf: $("optVF").checked };
  const active = SOURCES.filter(s => s.on);
  const st = $("status"); st.replaceChildren();
  const tags = {};
  active.forEach(s => { tags[s.id] = el("span", null, s.name + " : recherche…"); st.append(tags[s.id]); });
  $("grid").replaceChildren(el("div", "empty", "Recherche en cours…"));
  const results = await Promise.all(active.map(async s => {
    try { const r = await s.search(q, opts); tags[s.id].className = "ok"; tags[s.id].textContent = s.name + " : " + r.length; return r; }
    catch (e) { tags[s.id].className = "bad"; tags[s.id].textContent = s.name + " : " + (e.message.includes("clé") ? "clé manquante (Réglages)" : e.message.includes("code") ? "code d'accès requis (Réglages)" : "indisponible"); return []; }
  }));
  let merged = merge(results.flat());
  let hidden = 0;
  if (q) {
    merged.forEach(r => r._s = score(r, q));
    const kept = merged.filter(r => r._s >= 65);
    hidden = merged.length - kept.length;
    merged = $("optLoose").checked ? merged.filter(r => r._s > 0) : kept;
    merged.sort((a, b) => b._s - a._s || (b.platforms.length - a.platforms.length));
  }
  if (opts.vf) merged.sort((a, b) => (b.lang === "fr") - (a.lang === "fr"));
  const g = $("grid"); g.replaceChildren();
  if (!merged.length) g.append(el("div", "empty", q
    ? "« " + q + " » n'est disponible gratuitement dans aucune des bases interrogées. Vérifie sur tes sites ci-dessous."
    : "Aucun film gratuit trouvé dans ces sources."));
  merged.forEach(r => g.append(card(r)));
  $("count").textContent = merged.length + " film" + (merged.length > 1 ? "s" : "") + (hidden && !$("optLoose").checked ? " · " + hidden + " sans rapport masqué" + (hidden > 1 ? "s" : "") : "");
  lastQuery = q; renderExtra();
  runSites(q);
  $("go").disabled = $("discover").disabled = false; running = false;
}

$("diagBtn").onclick = async () => {
  const out = $("diagOut"); out.replaceChildren(el("p", null, "Test en cours (jusqu'à 30 s)…"));
  $("diagBtn").disabled = true;
  try {
    const info = await serverInfo;
    if (!info) { out.replaceChildren(el("p", "bad", "Serveur introuvable : la page est ouverte comme simple fichier.")); return; }
    const r = await fetch("/api/diag", { headers: authHeaders() });
    if (r.status === 401) { out.replaceChildren(el("p", "bad", "Code d'accès manquant ou incorrect : saisis-le ci-dessous puis réessaie.")); return; }
    const d = await r.json(); out.replaceChildren();
    d.tests.forEach(t => {
      const row = el("div", "diag-row");
      row.append(el("span", t.ok ? "ok" : "bad", t.ok ? "OK" : "ÉCHEC"), el("strong", null, t.name), el("small", null, t.detail));
      out.append(row);
    });
  } catch (e) { out.replaceChildren(el("p", "bad", "Le test a échoué : " + e.message)); }
  finally { $("diagBtn").disabled = false; }
};

$("accessCode").value = store.get("code", "");
$("saveCode").onclick = () => { store.set("code", $("accessCode").value.trim()); $("saveCode").textContent = "Enregistré"; setTimeout(() => $("saveCode").textContent = "Enregistrer", 1500); };

$("form").addEventListener("submit", e => { e.preventDefault(); run($("q").value.trim()); });
$("discover").onclick = () => { $("q").value = ""; run(""); };
serverInfo.then(info => {
  if (info && info.tmdb) $("tmdbBlock").hidden = true;
  const needKey = !(info && info.tmdb) && !store.get("tmdb", "");
  const needCode = info && info.code && !store.get("code", "");
  if (needKey || needCode) $("settingsPanel").open = true;
  run("");
});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- outils texte
def norm(s):
    s = unicodedata.normalize("NFD", s or "").lower()
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def tokens(s):
    return [w for w in norm(s).split() if w and w not in STOP]


def matches(text, q):
    """Vrai si tous les mots importants de la recherche sont dans le texte."""
    qt = tokens(q)
    if not qt:
        return True
    tt = set(tokens(text))
    return all(w in tt or any(len(w) > 4 and len(x) > 4 and (x.startswith(w) or w.startswith(x)) for x in tt) for w in qt)


def clean(s):
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


# ---------------------------------------------------------------- réseau
def fetch(url, data=None, timeout=15):
    headers = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, data=data, headers=headers)
    with urlopen(req, timeout=timeout) as r:
        raw = r.read(4_000_000)
        cs = r.headers.get_content_charset() or "utf-8"
        return raw.decode(cs, "replace"), r.geturl()


# ---------------------------------------------------------------- moteurs de recherche (relais)
class SerpParser(HTMLParser):
    """Lit une page de résultats : titres dans h2/h3 (ou lien result__a), extrait qui suit."""

    def __init__(self):
        super().__init__()
        self.results, self._h, self._a, self._snip, self._skip = [], 0, None, None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            return
        if tag in ("h2", "h3"):
            self._h += 1
        if tag == "a" and (self._h or "result__a" in cls) and self._a is None:
            self._a = {"href": a.get("href", ""), "title": "", "snippet": ""}
            self.results.append(self._a)
            return
        if self.results and self._snip is None and self._a is None and (
                tag == "p" or "snippet" in cls or "b_caption" in cls or cls == "s"):
            self._snip = tag

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("h2", "h3"):
            self._h = max(0, self._h - 1)
        elif tag == "a" and self._a is not None:
            self._a = None
        elif tag == self._snip:
            self._snip = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._a is not None:
            self._a["title"] += data
        elif self._snip and len(self.results[-1]["snippet"]) < 300:
            self.results[-1]["snippet"] += data


def real_url(href):
    if href.startswith("//"):
        href = "https:" + href
    p = urlparse(href)
    if "duckduckgo.com" in p.netloc:
        target = parse_qs(p.query).get("uddg")
        return unquote(target[0]) if target else None
    if "bing.com" in p.netloc and p.path.startswith("/ck/"):
        u = (parse_qs(p.query).get("u") or [""])[0]
        if u.startswith("a1"):
            s = u[2:] + "=" * (-len(u[2:]) % 4)
            try:
                return base64.urlsafe_b64decode(s).decode("utf-8", "replace")
            except ValueError:
                return None
        return None
    return href if p.scheme in ("http", "https") else None


ENGINE_HOSTS = ("duckduckgo.com", "bing.com", "microsoft.com", "mojeek.com", "msn.com")
ENGINES = [
    ("DuckDuckGo", lambda q: ("https://html.duckduckgo.com/html/", urlencode({"q": q, "kl": "fr-fr"}).encode())),
    ("Bing", lambda q: ("https://www.bing.com/search?" + urlencode({"q": q, "setlang": "fr", "cc": "FR"}), None)),
    ("Mojeek", lambda q: ("https://www.mojeek.com/search?" + urlencode({"q": q, "lb": "fr"}), None)),
]


def parse_serp(page, host):
    p = SerpParser()
    p.feed(page)
    out, seen = [], set()
    for r in p.results:
        url = real_url(r["href"])
        title = clean(r["title"])
        if not url or not title or url in seen:
            continue
        h = urlparse(url).netloc.lower()
        if any(h == e or h.endswith("." + e) for e in ENGINE_HOSTS):
            continue
        if host and not (h == host or h.endswith("." + host)):
            continue
        seen.add(url)
        out.append({"title": title, "url": url, "snippet": clean(r["snippet"])[:240]})
    return out


def search_engine(q, host):
    """Essaie chaque moteur à tour de rôle jusqu'à obtenir des résultats."""
    query = f'"{q}" site:{host}' if host else q
    errors, tried = [], 0
    for name, build in ENGINES:
        try:
            url, data = build(query)
            page, _ = fetch(url, data)
            tried += 1
            res = parse_serp(page, host)
            if res:
                return res, name
        except Exception as e:  # moteur bloqué ou injoignable : on passe au suivant
            errors.append(f"{name}: {str(e)[:60]}")
    if not tried:
        raise RuntimeError(" ; ".join(errors))
    return [], "moteurs"



# ---------------------------------------------------------------- sources ouvertes (via le serveur)
OPEN_SOURCES = {"query.wikidata.org", "archive.org"}
WIKI_UA = "ProjectionLibre/1.0 (outil personnel de recherche de films libres)"


def fetch_open(url, timeout=25):
    host = urlparse(url).hostname
    headers = {"User-Agent": WIKI_UA if host == "query.wikidata.org" else UA,
               "Accept": "application/sparql-results+json, application/json;q=0.9"}
    with urlopen(Request(url, headers=headers), timeout=timeout) as r:
        return r.read(8_000_000).decode("utf-8", "replace")


def diagnose():
    def t_wikidata():
        q = 'SELECT ?f WHERE { ?f wdt:P31 wd:Q11424 ; wdt:P724 ?ia } LIMIT 3'
        d = json.loads(fetch_open("https://query.wikidata.org/sparql?format=json&query=" + quote(q)))
        return f'{len(d["results"]["bindings"])} films libres lus'

    def t_archive():
        d = json.loads(fetch_open("https://archive.org/advancedsearch.php?q=collection%3A(feature_films)"
                                  "&fl[]=identifier&rows=3&output=json"))
        return f'{d["response"]["numFound"]} films dans la collection'

    def t_tmdb():
        if not TMDB_KEY:
            return None
        headers = {"Accept": "application/json", "User-Agent": UA}
        url = "https://api.themoviedb.org/3/search/movie?query=Nosferatu&language=fr-FR"
        if len(TMDB_KEY) > 60:
            headers["Authorization"] = "Bearer " + TMDB_KEY
        else:
            url += "&api_key=" + quote(TMDB_KEY)
        with urlopen(Request(url, headers=headers), timeout=15) as r:
            return f'{json.loads(r.read())["total_results"]} résultats pour « Nosferatu »'

    def engine(name, build):
        def run():
            url, data = build('"Nosferatu" site:archive.org')
            page, _ = fetch(url, data)
            n = len(parse_serp(page, "archive.org"))
            if not n:
                raise RuntimeError("page reçue mais aucun résultat lisible (blocage probable)")
            return f"{n} résultats"
        return run

    tests = [("Wikidata / WikiFlix", t_wikidata), ("Internet Archive", t_archive), ("TMDB (clé du serveur)", t_tmdb)]
    tests += [(f"Moteur {n} (pour Mes sites)", engine(n, b)) for n, b in ENGINES]

    def run(item):
        name, fn = item
        try:
            detail = fn()
            if detail is None:
                return {"name": name, "ok": False, "detail": "TMDB_KEY non définie sur Render (la clé saisie dans Réglages reste utilisable)"}
            return {"name": name, "ok": True, "detail": detail}
        except HTTPError as e:
            return {"name": name, "ok": False, "detail": f"refusé : HTTP {e.code}"}
        except Exception as e:
            return {"name": name, "ok": False, "detail": str(e)[:140]}

    with ThreadPoolExecutor(max_workers=len(tests)) as ex:
        return list(ex.map(run, tests))


# ---------------------------------------------------------------- recherche directe sur le site
class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._stack = [], []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            a = dict(attrs)
            self._stack.append({"href": a.get("href") or "", "text": "",
                                "title": a.get("title") or a.get("aria-label") or ""})
        elif tag == "img" and self._stack:
            alt = dict(attrs).get("alt")
            if alt:
                self._stack[-1]["text"] += " " + alt

    def handle_endtag(self, tag):
        if tag == "a" and self._stack:
            self.links.append(self._stack.pop())

    def handle_data(self, data):
        if self._stack:
            self._stack[-1]["text"] += data


def public_url(url):
    """Refuse les adresses internes (sécurité quand le serveur est en ligne)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def search_site(q, template):
    url = template.replace("{q}", quote(q))
    if not public_url(url):
        raise ValueError("adresse non autorisée")
    page, final = fetch(url)
    p = LinkParser()
    p.feed(page)
    out, seen = [], set()
    for l in p.links:
        text, title = clean(l["text"]), clean(l["title"])
        if not matches(text + " " + title, q):
            continue
        label = text if (text and matches(text, q)) else (title or text)
        if not label or len(label) > 200:
            continue
        href = urljoin(final, l["href"])
        if not href.startswith("http") or href in seen or href.split("#")[0] == final.split("#")[0]:
            continue
        seen.add(href)
        out.append({"title": label, "url": href, "snippet": ""})
    return out[:15]


def search(q, host, template):
    errors = []
    if template:
        try:
            res = search_site(q, template)
            if res:
                return {"results": res, "method": "site"}
        except Exception as e:
            errors.append(str(e))
    if host:
        try:
            res, name = search_engine(q, host)
            return {"results": res, "method": "moteur", "engine": name}
        except Exception as e:
            errors.append(str(e))
    if errors:
        return {"error": errors[-1][:120]}
    return {"results": [], "method": "site"}


# ---------------------------------------------------------------- serveur local
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        return not CODE or self.headers.get("X-Code", "") == CODE

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self.send(200, PAGE, "text/html")
        if u.path == "/manifest.webmanifest":
            return self.send(200, MANIFEST, "application/manifest+json")
        if u.path == "/icon.svg":
            return self.send(200, ICON, "image/svg+xml")
        if u.path == "/api/ping":
            return self.send(200, json.dumps({"ok": True, "tmdb": bool(TMDB_KEY), "code": bool(CODE)}), "application/json")
        if u.path.startswith("/api/") and not self.authorized():
            return self.send(401, '{"error":"code d\'accès requis"}', "application/json")
        if u.path == "/api/tmdb":
            qs = parse_qs(u.query)
            path = (qs.pop("p", [""]))[0]
            if not TMDB_KEY or not TMDB_PATHS.match(path):
                return self.send(400, '{"error":"requête TMDB refusée"}', "application/json")
            params = {k: v[0] for k, v in qs.items() if k != "api_key"}
            headers = {"Accept": "application/json", "User-Agent": UA}
            if len(TMDB_KEY) > 60:
                headers["Authorization"] = "Bearer " + TMDB_KEY
            else:
                params["api_key"] = TMDB_KEY
            try:
                req = Request("https://api.themoviedb.org/3" + path + "?" + urlencode(params), headers=headers)
                with urlopen(req, timeout=15) as r:
                    return self.send(200, r.read().decode("utf-8"), "application/json")
            except HTTPError as e:
                return self.send(e.code, '{"error":"TMDB a refusé la requête"}', "application/json")
            except (URLError, socket.timeout) as e:
                return self.send(502, json.dumps({"error": str(e)[:120]}), "application/json")
        if u.path == "/api/fetch":
            target = (parse_qs(u.query).get("u") or [""])[0]
            t = urlparse(target)
            if t.scheme != "https" or t.hostname not in OPEN_SOURCES:
                return self.send(400, '{"error":"source non autorisée"}', "application/json")
            try:
                body = fetch_open(target)
                return self.send(200, body, "application/json")
            except HTTPError as e:
                return self.send(502, json.dumps({"error": f"{t.hostname} a répondu {e.code}"}), "application/json")
            except Exception as e:
                return self.send(502, json.dumps({"error": str(e)[:120]}), "application/json")
        if u.path == "/api/diag":
            return self.send(200, json.dumps({"tests": diagnose()}, ensure_ascii=False), "application/json")
        if u.path == "/api/site":
            qs = parse_qs(u.query)
            q = (qs.get("q") or [""])[0].strip()[:200]
            host = (qs.get("host") or [""])[0].strip().lower()
            template = (qs.get("url") or [""])[0].strip()
            if template and not template.startswith(("http://", "https://")):
                template = ""
            if not q:
                return self.send(400, '{"error":"recherche vide"}', "application/json")
            try:
                res = search(q, host, template)
            except Exception as e:  # ne jamais faire tomber le serveur
                res = {"error": str(e)[:120]}
            return self.send(200, json.dumps(res, ensure_ascii=False), "application/json")
        self.send(404, "Introuvable", "text/plain")


def main():
    if CLOUD:
        port = int(os.environ["PORT"])
        server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        print(f"Projection libre en ligne sur le port {port}"
              + ("" if CODE else " - ATTENTION : aucun CODE_ACCES défini"), flush=True)
        server.serve_forever()
        return
    port = PORT
    for _ in range(20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            port += 1
    else:
        print("Impossible de trouver un port libre.")
        sys.exit(1)
    url = f"http://127.0.0.1:{port}/"
    print("Projection libre est lancé :", url)
    print("Laisse cette fenêtre ouverte pendant que tu utilises l'outil. Ferme-la pour arrêter.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
