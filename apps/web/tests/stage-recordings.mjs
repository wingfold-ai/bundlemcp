// Stage a recorded e2e run into a durable, browsable gallery.
//
// Playwright wipes `test-results/` at the start of every run, so recordings made
// with `PW_VIDEO=1 npx playwright test` are copied out to `e2e-recordings/`.
// Each file is named `E2E-NN__<primary-spec>__<slug>.webm`, so the recording
// name maps straight to the spec that codes it. The video->scenario mapping is
// read from the per-test output directory, whose name always begins with the
// E2E-NN token (Playwright truncates the middle of long titles, never the
// leading token), and every requirement's text comes verbatim from /spec.
//
// Usage, from apps/web:  PW_VIDEO=1 npx playwright test && node tests/stage-recordings.mjs

import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadRequirements, loadScenarios, primarySpec, videoName } from "./spec-map.mjs";

const WEB = dirname(dirname(fileURLToPath(import.meta.url)));
const SRC = join(WEB, "test-results");
const OUT = join(WEB, "e2e-recordings");

if (!existsSync(SRC)) {
  throw new Error(`no ${SRC} — run with recording first: PW_VIDEO=1 npx playwright test`);
}

const requirements = loadRequirements();
const scenarios = loadScenarios();
const byId = new Map(scenarios.map((s) => [s.id, s]));

// Map each E2E-NN scenario to its recorded video via the output directory name.
const videos = new Map();
for (const dir of readdirSync(SRC, { withFileTypes: true })) {
  if (!dir.isDirectory()) continue;
  const idMatch = dir.name.match(/\bE2E-\d+\b/);
  const video = join(SRC, dir.name, "video.webm");
  if (idMatch && existsSync(video)) videos.set(idMatch[0], video);
}

if (existsSync(OUT)) rmSync(OUT, { recursive: true });
mkdirSync(OUT, { recursive: true });

const staged = [];
for (const s of scenarios) {
  const src = videos.get(s.id);
  if (!src || !existsSync(src)) {
    console.warn(`  no recording for ${s.id} (${s.title})`);
    continue;
  }
  const name = videoName(s.id, requirements, byId);
  copyFileSync(src, join(OUT, name));
  staged.push({
    id: s.id,
    file: name,
    title: s.title,
    testFile: s.testFile,
    spec: primarySpec(s.id, requirements, byId),
    new: s.new === true,
    reqs: s.requirements.map((id) => ({ id, ...requirements.get(id) })),
  });
}

function renderIndex(items) {
  return INDEX_TEMPLATE.replace("__ITEMS__", JSON.stringify(items));
}

const INDEX_TEMPLATE = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>bundlemcp - e2e run</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;font:14px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
 background:#0d1117;color:#e6edf3;display:grid;grid-template-columns:360px 1fr;min-height:100vh}
aside{border-right:1px solid #30363d;padding:16px;overflow-y:auto}
h1{font-size:15px;margin:0 0 4px}.sub{color:#8b949e;font-size:12px;margin-bottom:14px}
ol{list-style:none;margin:0;padding:0}
li{padding:8px 10px;border-radius:6px;cursor:pointer;margin-bottom:2px}
li:hover{background:#161b22}li.active{background:#1f6feb33;outline:1px solid #1f6feb}
.rowtop{display:flex;gap:8px;align-items:baseline}
.eid{color:#58a6ff;font-weight:700;font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
.new{color:#3fb950;font-weight:600;font-size:10px;letter-spacing:.04em}
.lfile{color:#8b949e;font-size:11px;margin-top:2px;margin-left:2px}
main{padding:20px;display:flex;flex-direction:column;gap:14px;min-width:0}
video{width:100%;max-height:60vh;background:#000;border-radius:8px}
.bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
button{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:6px;
 padding:6px 12px;cursor:pointer;font:inherit}button:hover{background:#30363d}
#title{font-weight:600}.eidbig{color:#58a6ff;font-weight:700}
label{color:#8b949e;display:flex;align-items:center;gap:6px}
.meta{color:#8b949e;font-size:12px;font-family:ui-monospace,monospace}
.reqs{display:flex;flex-direction:column;gap:10px;border-top:1px solid #30363d;padding-top:12px}
.req{display:flex;gap:12px;align-items:flex-start}
.badge{background:#1f6feb;color:#fff;padding:2px 9px;border-radius:5px;font-weight:700;
 font-size:12px;white-space:nowrap}
.rspec{color:#8b949e;font-size:11px}.rtext{font-size:13px;color:#c9d1d9}
@media(max-width:900px){body{grid-template-columns:1fr}}
</style></head><body>
<aside><h1>bundlemcp e2e run</h1>
<div class="sub">all tests passed &middot; each clip opens with the spec requirement it verifies</div>
<ol id="list"></ol></aside>
<main>
 <div class="bar"><button id="prev">&larr; Prev</button><button id="next">Next &rarr;</button>
  <span id="title"></span>
  <label style="margin-left:auto"><input type="checkbox" id="auto" checked/> autoplay next</label></div>
 <video id="player" controls autoplay muted playsinline></video>
 <div class="meta" id="meta"></div>
 <div class="reqs" id="reqs"></div>
</main>
<script>
const items = __ITEMS__;
const listEl=document.getElementById("list"),player=document.getElementById("player"),
 titleEl=document.getElementById("title"),metaEl=document.getElementById("meta"),
 autoEl=document.getElementById("auto"),reqsEl=document.getElementById("reqs");
let current=0;
const esc=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
items.forEach((it,i)=>{const li=document.createElement("li");
 li.innerHTML='<div class="rowtop"><span class="eid">'+it.id+'</span><span>'+esc(it.title)+
  (it.new?' <span class="new">NEW</span>':'')+'</span></div>'+
  '<div class="lfile">'+esc(it.file)+'</div>';
 li.addEventListener("click",()=>play(i));listEl.appendChild(li);});
function play(i){current=(i+items.length)%items.length;const it=items[current];
 player.src=it.file;player.play().catch(()=>{});
 titleEl.innerHTML='<span class="eidbig">'+it.id+'</span> &middot; '+esc(it.title);
 metaEl.innerHTML='spec/'+esc(it.spec)+'  &middot;  tests/'+esc(it.testFile)+'  &middot;  '+esc(it.file);
 reqsEl.innerHTML=it.reqs.map(r=>'<div class="req"><span class="badge">'+esc(r.id)+
  '</span><div><div class="rspec">spec/'+esc(r.spec)+(r.title?' &middot; '+esc(r.title):'')+
  '</div><div class="rtext">'+esc(r.text)+'</div></div></div>').join("");
 [...listEl.children].forEach((el,n)=>el.classList.toggle("active",n===current));
 listEl.children[current].scrollIntoView({block:"nearest"});}
player.addEventListener("ended",()=>{if(autoEl.checked)play(current+1);});
document.getElementById("prev").addEventListener("click",()=>play(current-1));
document.getElementById("next").addEventListener("click",()=>play(current+1));
document.addEventListener("keydown",e=>{
 if(e.key==="ArrowRight")play(current+1);if(e.key==="ArrowLeft")play(current-1);});
play(0);
</script></body></html>
`;

writeFileSync(join(OUT, "index.html"), renderIndex(staged));
console.log(`staged ${staged.length} recordings -> ${OUT}`);
