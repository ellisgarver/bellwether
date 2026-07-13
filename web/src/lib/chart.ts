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
  line: "#e4e2db",
  paper: "#ffffff",
  paper2: "#f5f4f1",
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

  // Click-locked position lines: three gray segments from the selected node to
  // the walls, standing in for the native hover spikes (which vanish the moment
  // the pointer leaves the point and so can't persist through a selection).
  const spikeTrace = {
    type: "scatter3d",
    mode: "lines",
    x: [] as (number | null)[],
    y: [] as (number | null)[],
    z: [] as (number | null)[],
    line: { color: "rgba(111,106,96,0.6)", width: 1.5 },
    hoverinfo: "skip",
    showlegend: false,
  };
  // wall anchors for those lines: the data minima on each axis (the three
  // planes the default camera looks toward).
  const mins = [0, 1, 2].map((i) => Math.min(...pts.map((p) => xyz(p)[i])));
  const spikesFor = (cid: number) => {
    const [x, y, z] = xyz(byId[cid]);
    return {
      x: [x, mins[0], null, x, x, null, x, x],
      y: [y, y, null, y, mins[1], null, y, y],
      z: [z, z, null, z, z, null, z, mins[2]],
    };
  };

  // every out-of-scope cluster renders as an "x" (matching the map key), not
  // just JEL J; in-scope fields keep their per-field shapes.
  const symbolOf = (p: any) =>
    p.in_scope === false ? "x" : (JEL_SYMBOL[p.jel_code] ?? "circle");
  // gl3d renders each symbol as a font glyph (● ■ ◆ + ❌) whose visual extent
  // differs for the same size value. normalize every glyph to the square's box
  // so one rendered size means one article count across shapes.
  const SYMBOL_SCALE: Record<string, number> = {
    circle: 1, square: 1, diamond: 1, cross: 1.1, x: 0.6,
  };
  // stroke-only glyphs (x, cross) carry no fill mass, so at equal box size
  // they read thinner than the solid shapes; they get a self-colored outline
  // below to fatten their lines without growing their box.
  const strokeGlyph = (p: any) => {
    const s = symbolOf(p);
    return s === "x" || s === "cross";
  };
  // size tracks article count on a log scale — a linear map let the biggest
  // stories dwarf everything near the 42-article floor — with a hard visual
  // minimum so the smallest clusters stay findable after glyph normalization.
  // the exponent (< 1) bends the ramp concave: growth in size is spent early,
  // so small clusters differentiate from each other while the big ones bunch
  // up near SIZE_MAX instead of towering over the mid-field.
  const counts = pts.map((p) => Math.max(1, p.n_articles ?? 1));
  const nLo = Math.min(...counts);
  const nHi = Math.max(nLo * 1.0001, Math.max(...counts));
  const SIZE_MIN = 6;
  const SIZE_MAX = 18;
  const SIZE_FLOOR = 3;
  const SIZE_EXP = 0.67;
  const sizeOf = (p: any) => {
    const t =
      (Math.log(Math.max(1, p.n_articles ?? 1)) - Math.log(nLo)) /
      (Math.log(nHi) - Math.log(nLo));
    return Math.max(
      SIZE_FLOOR,
      (SIZE_MIN + Math.pow(t, SIZE_EXP) * (SIZE_MAX - SIZE_MIN)) *
        (SYMBOL_SCALE[symbolOf(p)] ?? 1),
    );
  };

  // gl3d accepts marker.line.width only as a per-trace scalar (border *color*
  // is per-point, width is not — a width array silently misrenders), so each
  // border class gets its own trace: solid shapes with a hairline ink border
  // so neighbors don't blend, stroke glyphs (x, +) with their self-colored
  // fattening outline, and emerging clusters with the ember ring.
  const nodeClass = (p: any) =>
    p.is_emerging ? "emerging" : strokeGlyph(p) ? "glyph" : "solid";
  const nodeTraceFor = (
    sel: any[],
    borderWidth: number,
    borderColor: (p: any) => string,
  ) => ({
    type: "scatter3d",
    mode: "markers",
    x: sel.map((p) => xyz(p)[0]),
    y: sel.map((p) => xyz(p)[1]),
    z: sel.map((p) => xyz(p)[2]),
    customdata: sel.map((p) => [p.cluster_id, p.n_articles, p.stage]),
    text: sel.map((p) => p.label_human || p.label),
    hovertemplate:
      "%{text}<br>%{customdata[1]} articles · %{customdata[2]}<extra></extra>",
    marker: {
      size: sel.map(sizeOf),
      color: sel.map((p) => STAGE_COLOR[p.stage] ?? COL.dormant),
      symbol: sel.map(symbolOf),
      opacity: 1,
      line: { width: borderWidth, color: sel.map(borderColor) },
    },
    showlegend: false,
  });
  const nodeTraces = [
    nodeTraceFor(pts.filter((p) => nodeClass(p) === "solid"), 1, () => "rgba(255,255,255,0.9)"),
    nodeTraceFor(
      pts.filter((p) => nodeClass(p) === "glyph"),
      2,
      (p) => STAGE_COLOR[p.stage] ?? COL.dormant,
    ),
    nodeTraceFor(pts.filter((p) => nodeClass(p) === "emerging"), 2.5, () => COL.ember),
  ].filter((t) => t.x.length > 0);

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

  // UMAP axes are unitless, so the display aspect is a presentation choice: a
  // landscape ratio spreads the cloud across the wide canvas instead of boxing
  // it into a cube, and the camera sits closer and lower for presence.
  const layout = baseLayout({
    margin: { l: 0, r: 0, t: 0, b: 0 },
    scene: {
      xaxis: axis, yaxis: axis, zaxis: axis,
      aspectmode: "manual",
      aspectratio: { x: 1.5, y: 1.5, z: 0.85 },
      camera: { eye: { x: 0.95, y: 0.95, z: 0.55 }, center: { x: 0, y: 0, z: -0.12 } },
    },
  });

  // Wheel zoom is handled by our own dolly (below) — plotly's built-in scroll
  // zoom clamps the camera distance and reads as "resistance" when zooming in
  // deep, so it stays off. Touch pinch keeps plotly's native handling.
  Plotly.newPlot(el, [edgeTrace, spikeTrace, ...nodeTraces], layout, {
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
  //
  // Click-lock contract:
  //  - clicking a cluster locks it: name tag + blue edges + its own gray
  //    position lines stay up, auto-rotation stays off, and other clusters
  //    produce no hover effects (no chip, no wall spikes).
  //  - the chip is hidden with CSS (.map-locked in global.css) rather than
  //    hoverinfo, because gl3d keeps drawing hovertemplate chips regardless of
  //    a restyled hoverinfo. hover *events* keep firing either way, which the
  //    click handler needs to tell "same cluster" from "anywhere else".
  //  - clicking the locked cluster or its tag keeps the lock; clicking
  //    anywhere else releases it and restores normal hover.
  let hoverCid: number | null = null;
  let selectedCid: number | null = null;
  const select = (cid: number) => {
    selectedCid = cid;
    pause();
    el.classList.add("map-locked");
    const e = edgesFor(cid);
    const s = spikesFor(cid);
    Plotly.restyle(el, { x: [e.x[0], s.x], y: [e.y[0], s.y], z: [e.z[0], s.z] }, [0, 1]);
    Plotly.relayout(el, {
      "scene.annotations": [tagFor(cid)],
      "scene.xaxis.showspikes": false,
      "scene.yaxis.showspikes": false,
      "scene.zaxis.showspikes": false,
    });
  };
  const deselect = () => {
    if (selectedCid === null) return;
    selectedCid = null;
    el.classList.remove("map-locked");
    Plotly.restyle(el, { x: [[], []], y: [[], []], z: [[], []] }, [0, 1]);
    Plotly.relayout(el, {
      "scene.annotations": [],
      "scene.xaxis.showspikes": true,
      "scene.yaxis.showspikes": true,
      "scene.zaxis.showspikes": true,
    });
    scheduleResume();
  };
  let downX = 0, downY = 0;
  el.addEventListener("pointerdown", (ev) => { downX = ev.clientX; downY = ev.clientY; }, true);
  el.addEventListener("pointerup", (ev) => {
    if (Math.hypot(ev.clientX - downX, ev.clientY - downY) > 6) return;
    // a click on the tag's link must reach the anchor, not clear the selection
    if ((ev.target as Element | null)?.closest?.("a")) return;
    if (selectedCid !== null) {
      // locked: re-clicking the same cluster keeps it; anything else releases
      if (hoverCid !== selectedCid) deselect();
      return;
    }
    if (hoverCid !== null && byId[hoverCid]) select(hoverCid);
  }, true);

  // ---- gentle auto-orbit: one persistent animation loop; `spinning` is only a
  // flag, so the loop can neither die nor double up. Interacting (drag, wheel,
  // hover) pauses it; it resumes a few seconds after the last interaction from
  // wherever the camera was left, preserving the user's zoom and tilt.
  const DEFAULT_EYE = { x: 0.95, y: 0.95, z: 0.55 };
  const DEFAULT_CENTER = { x: 0, y: 0, z: -0.12 };
  // the orbit + zoom share one camera state: the point the camera looks at
  // (which zoom-to-cursor moves) and the eye's polar offset around it.
  let orbitCenter = { ...DEFAULT_CENTER };
  let angle = Math.atan2(DEFAULT_EYE.y - DEFAULT_CENTER.y, DEFAULT_EYE.x - DEFAULT_CENTER.x);
  let radius = Math.hypot(DEFAULT_EYE.x - DEFAULT_CENTER.x, DEFAULT_EYE.y - DEFAULT_CENTER.y);
  let relZ = DEFAULT_EYE.z - DEFAULT_CENTER.z;
  let spinning = true;
  let resumeTimer: ReturnType<typeof setTimeout> | undefined;

  let lastEye: { x: number; y: number; z: number } | undefined;
  el.on("plotly_relayout", (ev: any) => {
    const cam = ev?.["scene.camera"];
    const eye = cam?.eye ?? ev?.["scene.camera.eye"];
    if (eye) lastEye = eye;
    if (cam?.center) orbitCenter = { ...cam.center };
  });

  const loop = () => {
    if (spinning) {
      angle += 0.0016;
      try {
        Plotly.relayout(el, {
          "scene.camera.eye": {
            x: orbitCenter.x + radius * Math.cos(angle),
            y: orbitCenter.y + radius * Math.sin(angle),
            z: orbitCenter.z + relZ,
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
    if (selectedCid !== null) return; // a click-lock keeps the stage still
    if (lastEye) {
      radius = Math.hypot(lastEye.x - orbitCenter.x, lastEye.y - orbitCenter.y);
      angle = Math.atan2(lastEye.y - orbitCenter.y, lastEye.x - orbitCenter.x);
      relZ = lastEye.z - orbitCenter.z;
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

  // Wheel zoom dollies toward the cursor, not the scene center: the mouse
  // position is unprojected onto the plane through the look-at point, and both
  // eye and center scale about that spot, so what's under the cursor stays
  // under the cursor. Zoom-out is capped; zoom-in is not.
  el.addEventListener(
    "wheel",
    (ev: WheelEvent) => {
      ev.preventDefault();
      pause();
      const C = orbitCenter;
      const eye = lastEye ?? {
        x: C.x + radius * Math.cos(angle),
        y: C.y + radius * Math.sin(angle),
        z: C.z + relZ,
      };
      const vx = C.x - eye.x, vy = C.y - eye.y, vz = C.z - eye.z;
      const dist = Math.hypot(vx, vy, vz) || 1e-6;
      const dx = vx / dist, dy = vy / dist, dz = vz / dist;

      // camera basis (plotly gl3d is z-up); guard the straight-down case
      let rx = dy * 1 - dz * 0, ry = dz * 0 - dx * 1, rz = dx * 0 - dy * 0;
      const rlen = Math.hypot(rx, ry, rz);
      if (rlen < 1e-6) { rx = 1; ry = 0; rz = 0; } else { rx /= rlen; ry /= rlen; rz /= rlen; }
      const ux = ry * dz - rz * dy, uy = rz * dx - rx * dz, uz = rx * dy - ry * dx;

      // cursor ray hits the center plane at T (gl3d vertical fov ~45deg)
      const rect = el.getBoundingClientRect();
      const nx = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      const ny = 1 - ((ev.clientY - rect.top) / rect.height) * 2;
      const tanV = 0.414;
      const tanH = tanV * (rect.width / Math.max(1, rect.height));
      const ox = nx * tanH * dist, oy = ny * tanV * dist;
      const T = {
        x: C.x + rx * ox + ux * oy,
        y: C.y + ry * ox + uy * oy,
        z: C.z + rz * ox + uz * oy,
      };

      const next = Math.min(4, dist * Math.exp(ev.deltaY * 0.0016));
      const s = next / dist;
      let ne = { x: T.x + (eye.x - T.x) * s, y: T.y + (eye.y - T.y) * s, z: T.z + (eye.z - T.z) * s };
      let nc = { x: T.x + (C.x - T.x) * s, y: T.y + (C.y - T.y) * s, z: T.z + (C.z - T.z) * s };

      // A proportional dolly stalls once the camera is close: each tick moves a
      // fraction of an already-tiny distance. Below a floor of absolute travel,
      // switch to flight — translate eye and center together along the cursor
      // ray, so the camera moves through the cloud instead of creeping toward a
      // point it never reaches. The flight step scales with the gesture (a
      // mouse-wheel notch is ~one deltaY of 100-240; a trackpad swipe is many
      // small deltas), so both inputs fly at the same overall pace.
      const flyStep = Math.min(0.12, Math.abs(ev.deltaY) * 0.00022);
      const travel = Math.hypot(ne.x - eye.x, ne.y - eye.y, ne.z - eye.z);
      const zoomingIn = ev.deltaY < 0;
      if (travel < flyStep && (zoomingIn || dist < 0.5)) {
        let fx = T.x - eye.x, fy = T.y - eye.y, fz = T.z - eye.z;
        const flen = Math.hypot(fx, fy, fz) || 1e-6;
        const step = zoomingIn ? flyStep : -flyStep;
        fx = (fx / flen) * step; fy = (fy / flen) * step; fz = (fz / flen) * step;
        ne = { x: eye.x + fx, y: eye.y + fy, z: eye.z + fz };
        nc = { x: C.x + fx, y: C.y + fy, z: C.z + fz };
      }
      lastEye = ne;
      orbitCenter = nc;
      try {
        Plotly.relayout(el, { "scene.camera.eye": ne, "scene.camera.center": nc });
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
    orbitCenter = { ...DEFAULT_CENTER };
    angle = Math.atan2(DEFAULT_EYE.y - DEFAULT_CENTER.y, DEFAULT_EYE.x - DEFAULT_CENTER.x);
    radius = Math.hypot(DEFAULT_EYE.x - DEFAULT_CENTER.x, DEFAULT_EYE.y - DEFAULT_CENTER.y);
    relZ = DEFAULT_EYE.z - DEFAULT_CENTER.z;
    hoverCid = null;
    deselect();
    Plotly.relayout(el, {
      "scene.camera.eye": { ...DEFAULT_EYE },
      "scene.camera.center": { ...DEFAULT_CENTER },
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
