// Client-side catalog controller shared by the narratives and emerging pages.
// Applies the page's filter predicate to the pre-rendered cards, then windows
// the matches into fixed-size pages with a compact pager (prev/next plus
// condensed page numbers). Everything stays static: the cards are all in the
// HTML; this only toggles visibility.

export interface CatalogOptions {
  cards: HTMLElement[];
  empty?: HTMLElement | null;
  pager?: HTMLElement | null;
  /** element scrolled back into view on a page change */
  scrollTo?: HTMLElement | null;
  pageSize?: number;
  matches?: (card: HTMLElement) => boolean;
}

export interface Catalog {
  /** re-apply the filter and jump back to the first page */
  refresh(): void;
}

export function setupCatalog(opts: CatalogOptions): Catalog {
  const pageSize = opts.pageSize ?? 20;
  const matches = opts.matches ?? (() => true);
  let page = 0;

  function render(scroll = false): void {
    const hits = opts.cards.filter(matches);
    const pages = Math.max(1, Math.ceil(hits.length / pageSize));
    page = Math.min(Math.max(0, page), pages - 1);
    const shown = new Set(hits.slice(page * pageSize, (page + 1) * pageSize));
    for (const c of opts.cards) c.classList.toggle("hidden", !shown.has(c));
    opts.empty?.classList.toggle("hidden", hits.length !== 0);
    renderPager(hits.length, pages);
    if (scroll) opts.scrollTo?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderPager(total: number, pages: number): void {
    const el = opts.pager;
    if (!el) return;
    el.innerHTML = "";
    el.classList.toggle("hidden", pages <= 1);
    if (pages <= 1) return;

    const btn = (label: string, disabled: boolean, go: number): HTMLButtonElement => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "page-btn";
      b.textContent = label;
      b.disabled = disabled;
      if (!disabled) {
        b.addEventListener("click", () => {
          page = go;
          render(true);
        });
      }
      return b;
    };

    el.appendChild(btn("← prev", page === 0, page - 1));

    // condensed numbers: first, last, and the neighborhood of the current page
    const want = new Set([0, page - 1, page, page + 1, pages - 1]);
    let prev = -1;
    for (let i = 0; i < pages; i++) {
      if (!want.has(i)) continue;
      if (prev !== -1 && i - prev > 1) {
        const gap = document.createElement("span");
        gap.className = "page-gap";
        gap.textContent = "…";
        el.appendChild(gap);
      }
      const b = btn(String(i + 1), false, i);
      if (i === page) b.classList.add("active");
      el.appendChild(b);
      prev = i;
    }

    el.appendChild(btn("next →", page === pages - 1, page + 1));

    const info = document.createElement("span");
    info.className = "page-info";
    info.textContent = `${total.toLocaleString("en-US")} narratives`;
    el.appendChild(info);
  }

  render();
  return {
    refresh() {
      page = 0;
      render();
    },
  };
}
