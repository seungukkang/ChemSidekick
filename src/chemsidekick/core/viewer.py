"""A self-contained HTML page that shows a Structure3D with 3Dmol.js.

The same page is used everywhere: the CLI saves it and opens it in the
browser, and the Streamlit app embeds it. 3Dmol.js is loaded from a CDN, so
the 3D view needs an internet connection (plan 003, risks).

Bonds are drawn by 3Dmol.js from interatomic distances only; they are not
chemical bond assignments.
"""

import html
import json

from chemsidekick.core.schemas import Structure3D

THREEDMOL_URL = "https://cdn.jsdelivr.net/npm/3dmol@2.4.2/build/3Dmol-min.js"

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<script src="__LIB__"></script>
<style>
  html, body { margin: 0; height: 100%; font: 13px/1.4 -apple-system, system-ui, sans-serif;
    color: #1f2937; background: #fff; }
  body { display: flex; flex-direction: column; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 7px 10px;
    border-bottom: 1px solid #e5e7eb; }
  .bar .title { font-weight: 600; margin-right: 6px; }
  .bar label { display: inline-flex; gap: 6px; align-items: center; color: #4b5563; }
  button, select { font: inherit; padding: 3px 10px; border: 1px solid #d1d5db;
    border-radius: 999px; background: #fff; color: #1f2937; cursor: pointer; }
  button:hover { background: #f3f4f6; }
  button.toggle[aria-pressed="true"] { background: #1f2937; border-color: #1f2937; color: #fff; }
  .spacer { flex: 1; }
  .nav { gap: 6px; }
  .pages { display: inline-flex; gap: 4px; flex-wrap: wrap; }
  .pages button { min-width: 30px; padding: 3px 8px; }
  .pages button.current { background: #1f2937; border-color: #1f2937; color: #fff; }
  .arrow { font-size: 15px; line-height: 1; padding: 3px 11px; }
  .muted { color: #6b7280; }
  .caption { font-weight: 600; }
  input[type=range] { width: 180px; }
  #comment { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
  #legend { display: none; gap: 12px; font-size: 12px; color: #4b5563; }
  #legend span { display: inline-flex; align-items: center; gap: 5px; }
  #legend i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  #view { position: relative; flex: 1; min-height: 240px; }
  #error { padding: 16px; color: #b91c1c; display: none; }
</style>
</head>
<body>
<div class="bar">
  <span class="title">__TITLE__</span>
  <label>Style <select id="style">
    <option value="ball-and-stick">ball and stick</option>
    <option value="stick">stick</option>
    <option value="sphere">sphere</option>
  </select></label>
  <button class="toggle" id="numbers" aria-pressed="false"></button>
  <button class="toggle" id="marks" aria-pressed="false" style="display:none">Stereocenters</button>
  <button id="reset" title="Fit the molecule in view">Reset view</button>
  <span class="spacer"></span>
  <span id="legend">
    <span><i style="background:#7c3aed"></i>R/S center</span>
    <span><i style="background:#0d9488"></i>r/s pseudoasymmetric</span>
    <span><i style="background:#ea580c"></i>E/Z double bond</span>
  </span>
</div>
<div class="bar nav" id="nav" style="display:none">
  <button class="arrow" id="prev" title="Previous (←)">‹</button>
  <span class="pages" id="pages"></span>
  <input type="range" id="slider" min="0" step="1" style="display:none">
  <button class="arrow" id="next" title="Next (→)">›</button>
  <button id="play" style="display:none">Play</button>
  <span id="counter" class="muted"></span>
  <span id="comment" class="caption"></span>
</div>
<div class="bar" id="single" style="display:none"><span id="comment1" class="muted"></span></div>
<div id="error">The 3D viewer could not be loaded. It needs an internet connection
  to download 3Dmol.js.</div>
<div id="view"></div>
<script>
const DATA = __DATA__;
const STYLES = {
  "ball-and-stick": {stick: {radius: 0.14, colorscheme: "Jmol"},
                     sphere: {scale: 0.28, colorscheme: "Jmol"}},
  "stick": {stick: {radius: 0.18, colorscheme: "Jmol"}},
  "sphere": {sphere: {colorscheme: "Jmol"}},
};
const FONT = "-apple-system, system-ui, sans-serif";
const $ = (id) => document.getElementById(id);
const N = DATA.frames.length;
const PAGES = DATA.navigation === "pages";
const MAX_PAGE_BUTTONS = 15;

function xyzText(f) {
  const lines = [String(f.symbols.length), ""];
  f.symbols.forEach((s, i) => lines.push(s + " " + f.coords[i].join(" ")));
  return lines.join("\\n");
}
function markColor(label) {
  if (/^[RS]$/.test(label)) return "#7c3aed";
  if (/^[rs]$/.test(label)) return "#0d9488";
  if (/^[EZ]$/.test(label)) return "#ea580c";
  return "#4b5563";
}
function pt(c) { return {x: c[0], y: c[1], z: c[2]}; }
function add(a, b, k) { return [a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2]]; }
// A point next to the stereo element, pointing away from its bonded neighbors,
// so that its label does not cover the atom number.
function outside(f, atoms) {
  const c = atoms.map((i) => f.coords[i]);
  const at = c.length === 1 ? c[0] : add(c[0], add(c[1], c[0], -1), 0.5);
  let d = [0, 0, 0];
  f.coords.forEach((p, j) => {
    if (atoms.includes(j)) return;
    for (const q of c) {
      const v = add(q, p, -1), r = Math.hypot(...v);
      if (r > 0.1 && r < 1.75) d = add(d, v, 1 / r);
    }
  });
  const n = Math.hypot(...d);
  return n > 1e-6 ? add(at, d, 1.0 / n) : add(at, [0, 1, 0], 1.0);
}
function setPressed(el, on) { el.setAttribute("aria-pressed", on ? "true" : "false"); }
function pressed(el) { return el.getAttribute("aria-pressed") === "true"; }

const hasMarks = DATA.frames.some((f) => f.marks.length > 0);

if (typeof $3Dmol === "undefined") {
  $("error").style.display = "block";
} else {
  const viewer = $3Dmol.createViewer($("view"), {backgroundColor: "white"});
  let current = DATA.start_frame, timer = null;

  function drawNumbers(f) {
    f.coords.forEach((c, i) => {
      const text = f.numbers.length ? f.numbers[i] : String(i + 1);
      if (!text) return;
      viewer.addLabel(text, {
        position: pt(c), alignment: "center", font: FONT, fontSize: 13,
        fontColor: "#111827", backgroundColor: "#ffffff", backgroundOpacity: 0.95,
        borderThickness: 1, borderColor: "#94a3b8", padding: 3, inFront: true,
      });
    });
  }

  function drawMarks(f) {
    f.marks.forEach((m) => {
      const color = markColor(m.label);
      const a = f.coords[m.atoms[0]];
      if (m.atoms.length === 2) {
        const b = f.coords[m.atoms[1]];
        viewer.addCylinder({start: pt(a), end: pt(b), radius: 0.32, color: color,
                            opacity: 0.35, fromCap: 1, toCap: 1});
      } else {
        viewer.addSphere({center: pt(a), radius: 0.7, color: color, opacity: 0.3});
      }
      viewer.addLabel(m.label, {
        position: pt(outside(f, m.atoms)), alignment: "center", font: FONT, fontSize: 15,
        bold: true, fontColor: "#ffffff", backgroundColor: color, backgroundOpacity: 0.95,
        padding: 4, inFront: true,
      });
    });
  }

  function draw(keepView) {
    const view = keepView ? viewer.getView() : null;
    const f = DATA.frames[current];
    viewer.clear();
    viewer.removeAllShapes();
    viewer.removeAllLabels();
    viewer.addModel(xyzText(f), "xyz");
    viewer.setStyle({}, STYLES[$("style").value]);
    if (pressed($("numbers"))) drawNumbers(f);
    const showMarks = hasMarks && pressed($("marks"));
    if (showMarks) drawMarks(f);
    $("legend").style.display = showMarks ? "inline-flex" : "none";
    if (view) viewer.setView(view); else { viewer.zoomTo(); viewer.zoom(1.4); }
    viewer.render();
    updateNav(f);
  }

  function updateNav(f) {
    if (N === 1) { $("comment1").textContent = f.comment; return; }
    $("comment").textContent = f.comment;
    $("comment").title = f.comment;
    if (PAGES) {
      if (N <= MAX_PAGE_BUTTONS) {
        [...$("pages").children].forEach((b, i) => b.classList.toggle("current", i === current));
        $("counter").textContent = "";
      } else {
        $("counter").textContent = DATA.page_name + " " + (current + 1) + " / " + N;
      }
    } else {
      $("slider").value = current;
      $("counter").textContent = DATA.page_name.toLowerCase() + " " + (current + 1) + " / " + N;
    }
  }

  function go(i) { current = (i + N) % N; draw(true); }

  $("style").value = DATA.style;
  $("numbers").textContent = DATA.numbers_name;
  setPressed($("numbers"), DATA.labels);
  if (hasMarks) { $("marks").style.display = ""; setPressed($("marks"), DATA.marks_shown); }
  $("style").onchange = () => draw(true);
  [$("numbers"), $("marks")].forEach((b) => {
    b.onclick = () => { setPressed(b, !pressed(b)); draw(true); };
  });
  $("reset").onclick = () => { viewer.zoomTo(); viewer.zoom(1.4); viewer.render(); };

  if (N > 1) {
    $("nav").style.display = "flex";
    $("prev").onclick = () => go(current - 1);
    $("next").onclick = () => go(current + 1);
    if (PAGES) {
      if (N <= MAX_PAGE_BUTTONS) {
        for (let i = 0; i < N; i++) {
          const b = document.createElement("button");
          b.textContent = String(i + 1);
          b.title = DATA.page_name + " " + (i + 1);
          b.onclick = () => go(i);
          $("pages").appendChild(b);
        }
      }
      document.addEventListener("keydown", (e) => {
        if (e.key === "ArrowLeft") go(current - 1);
        if (e.key === "ArrowRight") go(current + 1);
      });
    } else {
      $("slider").style.display = "";
      $("play").style.display = "";
      $("slider").max = N - 1;
      $("slider").oninput = (e) => go(Number(e.target.value));
      $("play").onclick = () => {
        if (timer) { clearInterval(timer); timer = null; $("play").textContent = "Play"; }
        else { timer = setInterval(() => go(current + 1), 150); $("play").textContent = "Stop"; }
      };
    }
  } else if (DATA.frames[0].comment) {
    $("single").style.display = "flex";
  }
  window.addEventListener("resize", () => viewer.resize());
  draw(false);
}
</script>
</body>
</html>
"""


def viewer_html(structure: Structure3D) -> str:
    """A complete HTML page showing the structure (all frames)."""
    data = {
        "frames": [
            {
                "symbols": f.symbols,
                "coords": f.coords,
                "comment": f.comment,
                "numbers": f.numbers,
                "marks": [{"atoms": m.atoms, "label": m.label} for m in f.marks],
            }
            for f in structure.frames
        ],
        "style": structure.style,
        "labels": structure.labels,
        "marks_shown": structure.marks_shown,
        "start_frame": structure.start_frame,
        "navigation": structure.navigation,
        "page_name": structure.page_name,
        "numbers_name": structure.numbers_name,
    }
    # "</" inside a <script> block would end it early; JSON allows the escaped form.
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    title = html.escape(structure.title or "3D structure")
    return (
        _PAGE.replace("__TITLE__", title)
        .replace("__LIB__", THREEDMOL_URL)
        # Last, so that text inside the data can never be mistaken for a placeholder.
        .replace("__DATA__", payload)
    )
