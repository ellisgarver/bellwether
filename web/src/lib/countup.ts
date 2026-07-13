// count-up: tick a rendered numeric stat from 0 to its value once on load.
// the target is parsed from the element's own text, so the build-time markup
// stays the source of truth (and the final frame always matches it exactly).
export function countUp(els: Iterable<Element>, dur = 700): void {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  for (const el of els) {
    const text = el.textContent ?? "";
    const target = Number(text.replace(/,/g, ""));
    if (!isFinite(target) || target <= 0) continue;
    const grouped = text.includes(",");
    const t0 = performance.now();
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
      const v = Math.round(target * eased);
      el.textContent = grouped ? v.toLocaleString("en-US") : String(v);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}
