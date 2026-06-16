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
  accent: "#3a5a93",
  accentBright: "#4a7ac4",
  ember: "#c2410c",
  growth: "#1f9d6b",
  decay: "#d1495b",
  dormant: "#9a958a",
};

export const STAGE_COLOR: Record<string, string> = {
  growth: COL.growth,
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

export function baseLayout(extra: Record<string, any> = {}): Record<string, any> {
  return {
    font: { family: FONT, color: COL.ink, size: 13 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 48, r: 16, t: 12, b: 40 },
    // dark chip that reads as intentional against the warm paper (a near-white
    // box looked out of place); left-aligned so single-line counts sit cleanly.
    hoverlabel: {
      bgcolor: COL.ink,
      bordercolor: COL.ink,
      font: { family: FONT, color: COL.paper, size: 13 },
      align: "left",
    },
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

  // de-duplicated undirected edges → one line trace with null breaks
  const seen = new Set<string>();
  const ex: (number | null)[] = [];
  const ey: (number | null)[] = [];
  const ez: (number | null)[] = [];
  for (const p of pts) {
    for (const [nbr] of p.similar_edges ?? []) {
      const key = [p.cluster_id, nbr].sort((a: number, b: number) => a - b).join("-");
      if (seen.has(key) || !byId[nbr]) continue;
      seen.add(key);
      const a = xyz(p);
      const b = xyz(byId[nbr]);
      ex.push(a[0], b[0], null);
      ey.push(a[1], b[1], null);
      ez.push(a[2], b[2], null);
    }
  }

  const edgeTrace = {
    type: "scatter3d",
    mode: "lines",
    x: ex, y: ey, z: ez,
    line: { color: "rgba(111,106,96,0.22)", width: 1.5 },
    hoverinfo: "skip",
    showlegend: false,
  };

  const nodeTrace = {
    type: "scatter3d",
    mode: "markers",
    x: pts.map((p) => xyz(p)[0]),
    y: pts.map((p) => xyz(p)[1]),
    z: pts.map((p) => xyz(p)[2]),
    customdata: pts.map((p) => p.cluster_id),
    text: pts.map((p) => p.label),
    hovertemplate: "%{text}<extra></extra>",
    marker: {
      size: pts.map((p) => 3 + Math.sqrt(p.n_articles) * 0.5),
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
    gridcolor: "rgba(226,220,207,0.55)",
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
      camera: { eye: { x: 1.2, y: 1.2, z: 0.8 }, center: { x: 0, y: 0, z: -0.12 } },
    },
  });

  // scrollZoom ON: wheel dollies the 3-D camera. The map is now text-width with
  // page margins on either side, so the wheel-over-map case is intentional zoom,
  // not a scroll-trap.
  Plotly.newPlot(el, [edgeTrace, nodeTrace], layout, {
    displayModeBar: false, responsive: true, scrollZoom: true,
  });

  el.on("plotly_click", (ev: any) => {
    const cd = ev.points?.[0]?.customdata;
    if (cd !== undefined) window.location.href = `${base}/narratives/${cd}`;
  });

  // gentle auto-orbit. Any interaction (drag/scroll/touch) pauses it; it resumes
  // ~10s after the last interaction, picking up from wherever the user left the
  // camera — so their zoom (radius) and tilt (eye.z) are preserved, only motion
  // is restored.
  let angle = Math.atan2(1.2, 1.2);
  let radius = Math.hypot(1.2, 1.2);
  let z = 0.8;
  let spinning = true;
  let resumeTimer: ReturnType<typeof setTimeout> | undefined;

  const tick = () => {
    if (!spinning) return;
    angle += 0.0016;
    Plotly.relayout(el, {
      "scene.camera.eye": {
        x: radius * Math.cos(angle),
        y: radius * Math.sin(angle),
        z,
      },
    });
    requestAnimationFrame(tick);
  };

  // user drags/zooms emit plotly_relayout with the live camera; cache its eye so
  // resume() can pick up from exactly where they left it (preserving zoom + tilt).
  let lastEye: { x: number; y: number; z: number } | undefined;
  el.on("plotly_relayout", (ev: any) => {
    const eye = ev?.["scene.camera"]?.eye ?? ev?.["scene.camera.eye"];
    if (eye) lastEye = eye;
  });

  const resume = () => {
    if (lastEye) {
      radius = Math.hypot(lastEye.x, lastEye.y);
      angle = Math.atan2(lastEye.y, lastEye.x);
      z = lastEye.z;
    }
    spinning = true;
    requestAnimationFrame(tick);
  };

  const pause = () => {
    spinning = false;
    if (resumeTimer) clearTimeout(resumeTimer);
  };
  const scheduleResume = () => {
    if (resumeTimer) clearTimeout(resumeTimer);
    resumeTimer = setTimeout(resume, 10000);
  };

  el.addEventListener("mousedown", pause);
  el.addEventListener("touchstart", pause, { passive: true });
  el.addEventListener("wheel", () => { pause(); scheduleResume(); }, { passive: true });
  el.addEventListener("mouseup", scheduleResume);
  el.addEventListener("touchend", scheduleResume);

  requestAnimationFrame(tick);
}
