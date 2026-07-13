/// <reference path="../.astro/types.d.ts" />

// plotly.js-dist-min ships no type declarations; it is imported only from bundled
// client scripts and driven dynamically. Declare the module so the import is not an
// implicit any, and expose the event handle Plotly attaches to a rendered graph div.
declare module "plotly.js-dist-min";

interface PlotlyHTMLElement extends HTMLElement {
  on(event: string, handler: (ev: any) => void): void;
}
