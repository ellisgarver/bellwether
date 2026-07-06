// Shared client-side chart theme so every Plotly island uses the same typeface
// and palette as the rest of the site (single-font requirement). Imported only
// from bundled <script> tags — Vite resolves the bare plotly import there.
import Plotly from "plotly.js-dist-min";

export const FONT =
  '"Space Grotesk Variable","Space Grotesk",system-ui,-apple-system,sans-serif';

export const COL = {
  ink: "#16140f",
  muted: "#6f6a60",
  faint: "#908a7e",
  line: "#e2dccf",
  paper: "#edece8",
  paper2: "#e6e4de",
  accent: "#3a5a93",
  accentBright: "#4a7ac4",
  ember: "#c2410c",
  growth: "#1f9d6b",
  decay: "#d1495b",
  dormant: "#9a958a",
};

export const STAGE_COLOR: Record<string, string> = {
  growth: COL.growth,
  stable: COL.accent,
  decay: COL.decay,
  dormant: COL.dormant,
};

// scatter3d only supports a small symbol set; map JEL fields onto it.
export const JEL_SYMBOL: Record<string, string> = {
  E: "circle",
  F: "square",
  G: "diamond",
  H: "cross",
  J: "x",
};

// on-palette hover chip: a soft paper surface with a hairline border, not the
// stark white default nor a hard black box. Exported so per-trace overrides can
// reuse it — Plotly otherwise lets a translucent trace color leak into the chip.
export const HOVER_LABEL = {
  bgcolor: COL.paper2,
  bordercolor: COL.line,
  font: { family: FONT, color: COL.ink, size: 13 },
  align: "left" as const,
};

export function baseLayout(extra: Record<string, any> = {}): Record<string, any> {
  return {
    font: { family: FONT, color: COL.ink, size: 13 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 48, r: 16, t: 12, b: 40 },
    hoverlabel: HOVER_LABEL,
    colorway: [COL.accent, COL.ember, COL.growth, COL.decay, COL.dormant],
    ...extra,
  };
}

export const CONFIG = { displayModeBar: false, responsive: true } as const;

// 2-D charts: smooth scroll-to-zoom + drag-to-pan, double-click resets. No box.
export const CHART_CONFIG = {
  displayModeBar: false,
  responsive: true,
  scrollZoom: true,
  doubleClick: "reset" as const,
};

// pretty-print a FRED series label (vix -> VIX, 10y_yield -> 10-year yield)
export function seriesLabel(s: string | null | undefined): string {
  if (!s) return "market";
  const map: Record<string, string> = {
    vix: "VIX",
    "10y_yield": "10-year yield",
    yield_spread: "yield spread (10y–2y)",
  };
  return map[s] ?? s.replace(/_/g, " ");
}

export { Plotly };

/** Mount the interactive 3-D narrative landscape (ADR-044, pair-code style). */
export function mountMap3d(
  el: HTMLElement,
  pts: any[],
  base: string,
): void {
  const byId: Record<number, any> = Object.fromEntries(
    pts.map((p) => [p.cluster_id, p]),
  );
  const xyz = (p: any) => p.umap_xyz ?? [...(p.umap_xy ?? [0, 0]), 0];

  // Focus-lit edges (ADR-044): hovering a node lights up only its incident
  // edges, so the map never renders the full static hairball. Build an
  // undirected adjacency (union of each node's top-3 and any node that lists
  // it), de-duplicated so a reciprocal pair isn't stored twice.
  const adj: Record<number, number[]> = {};
  const linked = new Set<string>();
  const link = (a: number, b: number) => {
    (adj[a] ??= []).push(b);
  };
  for (const p of pts) {
    for (const [nbr] of p.similar_edges ?? []) {
      if (!byId[nbr]) continue;
      const key = [p.cluster_id, nbr].sort((a: number, b: number) => a - b).join("-");
      if (linked.has(key)) continue;
      linked.add(key);
      link(p.cluster_id, nbr);
      link(nbr, p.cluster_id);
    }
  }

  // Edge trace starts empty; plotly_hover fills it with the focused node's
  // incident segments (accent blue, intentionally visible), unhover clears it.
  const edgeTrace = {
    type: "scatter3d",
    mode: "lines",
    x: [] as (number | null)[],
    y: [] as (number | null)[],
    z: [] as (number | null)[],
    line: { color: "rgba(58,90,147,0.55)", width: 2 },
    hoverinfo: "skip",
    showlegend: false,
  };

  const nodeTrace = {
    type: "scatter3d",
    mode: "markers",
    x: pts.map((p) => xyz(p)[0]),
    y: pts.map((p) => xyz(p)[1]),
    z: pts.map((p) => xyz(p)[2]),
    customdata: pts.map((p) => [p.cluster_id, p.n_articles, p.stage]),
    text: pts.map((p) => p.label_human || p.label),
    hovertemplate:
      "%{text}<br>%{customdata[1]} articles · %{customdata[2]}<extra></extra>",
    marker: {
      size: pts.map((p) => 4 + Math.sqrt(p.n_articles) * 0.55),
      color: pts.map((p) => STAGE_COLOR[p.stage] ?? COL.dormant),
      symbol: pts.map((p) => JEL_SYMBOL[p.jel_code] ?? "circle"),
      opacity: 0.95,
      line: {
        width: pts.map((p) => (p.is_emerging ? 2.5 : 0.5)),
        color: pts.map((p) => (p.is_emerging ? COL.ember : "rgba(255,255,255,0.85)")),
      },
    },
    showlegend: false,
  };

  const axis = {
    showgrid: true,
    gridcolor: "#dcd7ca",
    zeroline: false,
    showticklabels: false,
    title: "",
    showbackground: false,
    // hover drops dashed spike lines to the cube walls; match the muted
    // subtitle gray instead of Plotly's default near-black.
    spikecolor: COL.muted,
    spikethickness: 1,
  };

  const layout = baseLayout({
    margin: { l: 0, r: 0, t: 0, b: 0 },
    scene: {
      xaxis: axis, yaxis: axis, zaxis: axis,
      aspectmode: "cube",
      camera: { eye: { x: 0.95, y: 0.95, z: 0.62 }, center: { x: 0, y: 0, z: -0.12 } },
    },
  });

  // Wheel zoom is handled by our own dolly (below) — plotly's built-in scroll
  // zoom clamps the camera distance and reads as "resistance" when zooming in
  // deep, so it stays off. Touch pinch keeps plotly's native handling.
  Plotly.newPlot(el, [edgeTrace, nodeTrace], layout, {
    displayModeBar: false, responsive: true, scrollZoom: false,
  });

  // ---- selection: hover is passive (tooltip only); a click pins a name tag
  // to the cluster and lights its edges. The tag's link opens the narrative.
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const edgesFor = (cid: number) => {
    const a = xyz(byId[cid]);
    const hx: (number | null)[] = [];
    const hy: (number | null)[] = [];
    const hz: (number | null)[] = [];
    for (const nbr of adj[cid] ?? []) {
      const b = xyz(byId[nbr]);
      hx.push(a[0], b[0], null);
      hy.push(a[1], b[1], null);
      hz.push(a[2], b[2], null);
    }
    return { x: [hx], y: [hy], z: [hz] };
  };

  const tagFor = (cid: number) => {
    const p = byId[cid];
    const [x, y, z] = xyz(p);
    return {
      x, y, z,
      text: `<a href="${base}/narratives/${cid}">${esc(p.label_human || p.label)} ↗</a>`,
      bgcolor: COL.paper2,
      bordercolor: COL.line,
      borderwidth: 1,
      borderpad: 6,
      font: { family: FONT, size: 13, color: COL.accent },
      arrowcolor: COL.muted,
      arrowwidth: 1.2,
      arrowhead: 6,
      ax: 0,
      ay: -44,
      captureevents: false, // clicks reach the anchor inside the tag
    };
  };

  // Selection keys off the hover pick (gl3d's one reliable picking signal): a
  // pointerup with minimal travel selects whatever point is under the cursor.
  // Travel gating means an orbit-drag release never selects.
  let hoverCid: number | null = null;
  const select = (cid: number) => {
    Plotly.restyle(el, edgesFor(cid), [0]);
    Plotly.relayout(el, { "scene.annotations": [tagFor(cid)] });
  };
  let downX = 0, downY = 0;
  el.addEventListener("pointerdown", (ev) => { downX = ev.clientX; downY = ev.clientY; }, true);
  el.addEventListener("pointerup", (ev) => {
    if (Math.hypot(ev.clientX - downX, ev.clientY - downY) > 6) return;
    if (hoverCid !== null && byId[hoverCid]) select(hoverCid);
  }, true);

  // ---- gentle auto-orbit: one persistent animation loop; `spinning` is only a
  // flag, so the loop can neither die nor double up. Interacting (drag, wheel,
  // hover) pauses it; it resumes a few seconds after the last interaction from
  // wherever the camera was left, preserving the user's zoom and tilt.
  let angle = Math.atan2(0.95, 0.95);
  let radius = Math.hypot(0.95, 0.95);
  let camZ = 0.62;
  let spinning = true;
  let resumeTimer: ReturnType<typeof setTimeout> | undefined;

  let lastEye: { x: number; y: number; z: number } | undefined;
  el.on("plotly_relayout", (ev: any) => {
    const eye = ev?.["scene.camera"]?.eye ?? ev?.["scene.camera.eye"];
    if (eye) lastEye = eye;
  });

  const loop = () => {
    if (spinning) {
      angle += 0.0016;
      try {
        Plotly.relayout(el, {
          "scene.camera.eye": {
            x: radius * Math.cos(angle),
            y: radius * Math.sin(angle),
            z: camZ,
          },
        });
      } catch {
        // plot mid-redraw; skip this frame and keep the loop alive
      }
    }
    requestAnimationFrame(loop);
  };

  const pause = () => {
    spinning = false;
    if (resumeTimer) clearTimeout(resumeTimer);
  };
  const resume = () => {
    if (lastEye) {
      radius = Math.hypot(lastEye.x, lastEye.y);
      angle = Math.atan2(lastEye.y, lastEye.x);
      camZ = lastEye.z;
    }
    spinning = true;
  };
  const scheduleResume = () => {
    if (resumeTimer) clearTimeout(resumeTimer);
    resumeTimer = setTimeout(resume, 6000);
  };

  // pause starts on the map, but the release often lands outside the plot, so
  // the resume is scheduled from the window. Hovering pauses too, so a point
  // never drifts away while the reader aims at it.
  el.addEventListener("pointerdown", pause);
  window.addEventListener("pointerup", scheduleResume);
  window.addEventListener("pointercancel", scheduleResume);

  // Custom wheel dolly: scale the eye→center distance exponentially with no
  // hard floor in reach, so deep zooms keep responding instead of hitting
  // plotly's internal distance clamp.
  const DEFAULT_EYE = { x: 0.95, y: 0.95, z: 0.62 };
  const CENTER = { x: 0, y: 0, z: -0.12 };
  el.addEventListener(
    "wheel",
    (ev: WheelEvent) => {
      ev.preventDefault();
      pause();
      const eye = lastEye ?? {
        x: radius * Math.cos(angle),
        y: radius * Math.sin(angle),
        z: camZ,
      };
      const dx = eye.x - CENTER.x, dy = eye.y - CENTER.y, dz = eye.z - CENTER.z;
      const dist = Math.hypot(dx, dy, dz) || 1e-6;
      // zoom-out is capped so the map can't shrink to a speck; zoom-in is not.
      const next = Math.min(4, dist * Math.exp(ev.deltaY * 0.0016));
      const s = next / dist;
      const ne = { x: CENTER.x + dx * s, y: CENTER.y + dy * s, z: CENTER.z + dz * s };
      lastEye = ne;
      try {
        Plotly.relayout(el, { "scene.camera.eye": ne });
      } catch { /* mid-redraw; the next tick lands it */ }
      scheduleResume();
    },
    { passive: false },
  );

  // Reset control (top right of the plot): camera, spin, and selection back to
  // the defaults without reloading the page.
  const resetBtn = document.createElement("button");
  resetBtn.type = "button";
  resetBtn.className = "map-reset";
  resetBtn.textContent = "⟲ reset view";
  resetBtn.setAttribute("aria-label", "reset the map view");
  resetBtn.addEventListener("click", () => {
    lastEye = undefined;
    angle = Math.atan2(DEFAULT_EYE.x, DEFAULT_EYE.y);
    radius = Math.hypot(DEFAULT_EYE.x, DEFAULT_EYE.y);
    camZ = DEFAULT_EYE.z;
    hoverCid = null;
    Plotly.restyle(el, { x: [[]], y: [[]], z: [[]] }, [0]);
    Plotly.relayout(el, {
      "scene.camera.eye": { ...DEFAULT_EYE },
      "scene.camera.center": { ...CENTER },
      "scene.annotations": [],
    });
    spinning = true;
  });
  if (getComputedStyle(el).position === "static") el.style.position = "relative";
  el.appendChild(resetBtn);
  el.on("plotly_hover", (ev: any) => {
    const cd = ev.points?.[0]?.customdata;
    hoverCid = Array.isArray(cd) ? cd[0] : (cd ?? null);
    pause();
  });
  el.on("plotly_unhover", () => {
    hoverCid = null;
    scheduleResume();
  });
  el.addEventListener("mouseleave", scheduleResume);

  requestAnimationFrame(loop);
}
