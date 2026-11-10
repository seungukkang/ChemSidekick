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
  .bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; padding: 6px 10px;
    border-bottom: 1px solid #e5e7eb; }
  .bar label { display: inline-flex; gap: 4px; align-items: center; }
  .bar button, .bar select { font: inherit; padding: 2px 8px; border: 1px solid #d1d5db;
    border-radius: 6px; background: #fff; cursor: pointer; }
  .bar input[type=range] { width: 160px; }
  .muted { color: #6b7280; }
  #comment { flex: 1 1 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #view { position: relative; flex: 1; min-height: 240px; }
  #error { padding: 16px; color: #b91c1c; display: none; }
</style>
</head>
<body>
<div class="bar">
  <strong>__TITLE__</strong>
  <label>Style <select id="style">
    <option value="ball-and-stick">ball and stick</option>
    <option value="stick">stick</option>
    <option value="sphere">sphere</option>
  </select></label>
  <label><input type="checkbox" id="labels"> atom numbers</label>
  <button id="reset" title="Fit the molecule in view">Reset view</button>
  <span id="frames" style="display:none">
    <button id="prev" title="Previous frame">‹</button>
    <input type="range" id="slider" min="0" step="1">
    <button id="next" title="Next frame">›</button>
    <button id="play">Play</button>
    <span id="counter" class="muted"></span>
  </span>
  <span id="comment" class="muted"></span>
</div>
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
const $ = (id) => document.getElementById(id);

function xyzText(f) {
  const lines = [String(f.symbols.length), ""];
  f.symbols.forEach((s, i) => lines.push(s + " " + f.coords[i].join(" ")));
  return lines.join("\\n");
}

if (typeof $3Dmol === "undefined") {
  $("error").style.display = "block";
} else {
  const viewer = $3Dmol.createViewer($("view"), {backgroundColor: "white"});
  let current = DATA.start_frame, timer = null;

  function draw(keepView) {
    const view = keepView ? viewer.getView() : null;
    const f = DATA.frames[current];
    viewer.clear();
    viewer.addModel(xyzText(f), "xyz");
    viewer.setStyle({}, STYLES[$("style").value]);
    if ($("labels").checked) {
      f.coords.forEach((c, i) => viewer.addLabel(String(i + 1), {
        position: {x: c[0], y: c[1], z: c[2]}, fontSize: 11, fontColor: "black",
        backgroundColor: "white", backgroundOpacity: 0.7, inFront: true,
      }));
    }
    if (view) viewer.setView(view); else { viewer.zoomTo(); viewer.zoom(1.2); }
    viewer.render();
    $("comment").textContent = f.comment;
    $("comment").title = f.comment;
    if (DATA.frames.length > 1) {
      $("slider").value = current;
      $("counter").textContent = "frame " + (current + 1) + " / " + DATA.frames.length;
    }
  }

  function go(i) { current = (i + DATA.frames.length) % DATA.frames.length; draw(true); }

  $("style").value = DATA.style;
  $("labels").checked = DATA.labels;
  $("style").onchange = () => draw(true);
  $("labels").onchange = () => draw(true);
  $("reset").onclick = () => { viewer.zoomTo(); viewer.zoom(1.2); viewer.render(); };
  if (DATA.frames.length > 1) {
    $("frames").style.display = "inline-flex";
    $("frames").style.gap = "6px";
    $("frames").style.alignItems = "center";
    $("slider").max = DATA.frames.length - 1;
    $("slider").oninput = (e) => go(Number(e.target.value));
    $("prev").onclick = () => go(current - 1);
    $("next").onclick = () => go(current + 1);
    $("play").onclick = () => {
      if (timer) { clearInterval(timer); timer = null; $("play").textContent = "Play"; }
      else { timer = setInterval(() => go(current + 1), 150); $("play").textContent = "Stop"; }
    };
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
            {"symbols": f.symbols, "coords": f.coords, "comment": f.comment}
            for f in structure.frames
        ],
        "style": structure.style,
        "labels": structure.labels,
        "start_frame": structure.start_frame,
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
