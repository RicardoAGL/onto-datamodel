"""Generate a self-contained HTML status report of the current ontology.

Dogfoods the toolkit design note's own principle (Sec 11.2): the
monolithic human-readable view should be a *generated rollup* over
structured, per-entity sources -- never hand-edited. This script is that
generator. Re-run it any time the ontology changes; never edit the HTML
output directly.

Usage: python3 render_ontology.py [output_path]
"""
import html
import json
import sys
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import Graph

from generate_customers_entity import customers
from generate_erd import generate_mermaid_erd
from generate_metrics import ALL_METRICS
from generate_orders_entity import orders
from generate_owl import build_graph
from generate_remaining_entities import ALL_REMAINING
from review_signoffs import is_signed_off, load_signoffs
from suggest_fixes import suggest_description_fixes
from validate_coverage import find_coverage_gaps
from validate_grounding import validate_entity
from validate_metrics import validate_metric

ALL_ENTITIES = [customers, orders] + ALL_REMAINING


def e(s: str) -> str:
    return html.escape(s, quote=True)


def build():
    with open("structural_facts.json") as f:
        facts = json.load(f)
    signoffs = load_signoffs()
    entities_by_name = {ent.name: ent for ent in ALL_ENTITIES}

    entity_results = []
    for ent in ALL_ENTITIES:
        failures, review = validate_entity(ent, facts)
        pending = [r for r in review if not is_signed_off(r, signoffs)]
        signed = [r for r in review if is_signed_off(r, signoffs)]
        entity_results.append(dict(entity=ent, failures=failures, review=review, pending=pending, signed=signed))

    metric_results = []
    for m in ALL_METRICS:
        failures, review = validate_metric(m, entities_by_name)
        pending = [r for r in review if not is_signed_off(r, signoffs)]
        metric_results.append(dict(metric=m, failures=failures, review=review, pending=pending))

    coverage_gaps = find_coverage_gaps(ALL_ENTITIES, facts)
    suggested_fixes = []
    for ent in ALL_ENTITIES:
        suggested_fixes.extend(suggest_description_fixes(ent, facts))

    # Same "live, never read from a stale file" discipline as the Mermaid
    # ERD above: rebuild the OWL graph in-memory from the same entities
    # everything else on this page is generated from, rather than reading
    # a possibly-stale ontology.ttl off disk.
    owl_graph = build_graph(ALL_ENTITIES)
    owl_ttl = owl_graph.serialize(format="turtle")
    shapes_graph = Graph().parse("shapes.ttl", format="turtle")
    owl_conforms, _, owl_shacl_report = shacl_validate(owl_graph, shacl_graph=shapes_graph, inference="none")

    totals = dict(
        n_entities=len(ALL_ENTITIES),
        n_metrics=len(ALL_METRICS),
        n_relationships=sum(len(ent.relationships) for ent in ALL_ENTITIES),
        n_failures=sum(len(r["failures"]) for r in entity_results) + sum(len(r["failures"]) for r in metric_results),
        n_review=sum(len(r["review"]) for r in entity_results) + sum(len(r["review"]) for r in metric_results),
        n_pending=sum(len(r["pending"]) for r in entity_results) + sum(len(r["pending"]) for r in metric_results),
        n_coverage_gaps=len(coverage_gaps),
        n_owl_triples=len(owl_graph),
        owl_conforms=owl_conforms,
    )
    return entity_results, metric_results, totals, coverage_gaps, suggested_fixes, owl_ttl, owl_shacl_report


def entity_card(res) -> str:
    ent = res["entity"]
    pk = next((c.name for c in ent.columns if c.role == "primary_key"), "—")
    status = "clean" if not res["pending"] else f"{len(res['pending'])} pending"
    status_class = "ok" if not res["pending"] else "warn"
    return f"""
    <div class="ecard">
      <div class="ecard-head">
        <span class="ecard-name">{e(ent.name)}</span>
        <span class="chip chip-{status_class}">{e(status)}</span>
      </div>
      <p class="ecard-grain">{e(ent.grain)}</p>
      <div class="ecard-meta">
        <span><b>{len(ent.columns)}</b> cols</span>
        <span><b>{len(ent.relationships)}</b> rels</span>
        <span class="mono">pk: {e(pk)}</span>
      </div>
    </div>"""


def metric_card(res) -> str:
    m = res["metric"]
    status = "clean" if not res["pending"] and not res["failures"] else (f"{len(res['failures'])} failed" if res["failures"] else f"{len(res['pending'])} pending")
    status_class = "fail" if res["failures"] else ("warn" if res["pending"] else "ok")
    return f"""
    <div class="mcard">
      <div class="mcard-head">
        <span class="mcard-name">{e(m.name)}</span>
        <span class="chip chip-{status_class}">{e(status)}</span>
      </div>
      <p class="mono formula">{e(m.formula)}</p>
      <p class="mcard-rationale">{e(m.rationale)}</p>
      <p class="mcard-caveat"><b>Caveat —</b> {e(m.caveats)}</p>
    </div>"""


def review_row(item: dict, reviewer_placeholder: str = "your name") -> str:
    cmd = f'python3 scripts/review_signoffs.py sign {item["key"]} "{reviewer_placeholder}"'
    return f"""
    <div class="rrow">
      <div class="rrow-key mono">{e(item['key'])}</div>
      <p class="rrow-text">{e(item['text'])}</p>
      <div class="rrow-cmd">
        <code class="mono">{e(cmd)}</code>
        <button class="copy-btn" onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent); this.textContent='copied'; setTimeout(() => this.textContent='copy', 1500)">copy</button>
      </div>
    </div>"""


def gap_row(g: dict) -> str:
    label = f"{g['model']}" if g["column"] is None else f"{g['model']}.{g['column']}"
    return f"""<li><span class="mono">{e(label)}</span> — {e(g['note'])}</li>"""


def fix_row(s: dict) -> str:
    return f"""
    <div class="fixrow">
      <div class="rrow-key mono">{e(s['entity'])}.{e(s['column'])} <span class="muted-inline">in {e(s['file'])}</span></div>
      <div class="diff-line diff-old"><span class="mono">- {e(s['current'])}</span></div>
      <div class="diff-line diff-new"><span class="mono">+ {e(s['suggested'])}</span></div>
    </div>"""


def render(entity_results, metric_results, totals, coverage_gaps, suggested_fixes, owl_ttl, owl_shacl_report) -> str:
    cards = "\n".join(entity_card(r) for r in entity_results)
    mcards = "\n".join(metric_card(r) for r in metric_results)
    signed_pct = round(100 * (totals["n_review"] - totals["n_pending"]) / totals["n_review"]) if totals["n_review"] else 100

    pending_by_entity = []
    for r in entity_results:
        if r["pending"]:
            rows = "\n".join(review_row(item) for item in r["pending"])
            pending_by_entity.append(f"""
      <div class="pending-group">
        <h3 class="pending-entity mono">{e(r['entity'].name)}</h3>
        {rows}
      </div>""")
    pending_html = "\n".join(pending_by_entity) if pending_by_entity else "<p class='muted-inline'>Nothing pending — every review item has a human signoff on file.</p>"

    gaps_html = "\n".join(gap_row(g) for g in coverage_gaps) if coverage_gaps else "<li>none — every real column in every modeled entity is documented</li>"

    erd_source = generate_mermaid_erd([r["entity"] for r in entity_results])

    fixes_html = "\n".join(fix_row(s) for s in suggested_fixes) if suggested_fixes else "<p class='muted-inline'>None right now — every manifest-sourced description matches exactly. This section exists for when one doesn't.</p>"

    return f"""<!doctype html>
<meta charset="utf-8">
<title>Ontology Status Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {{
  --paper: #F5F7F6;
  --surface: #FFFFFF;
  --ink: #151A18;
  --muted: #5C6D68;
  --accent: #1E6B5A;
  --accent-soft: #E3EEEA;
  --ok: #2F7D4F;
  --ok-soft: #E4F1E8;
  --warn: #A6741E;
  --warn-soft: #F5ECDA;
  --fail: #B33F3F;
  --fail-soft: #F6E4E1;
  --border: #DCE3E0;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper: #101513; --surface: #161C1A; --ink: #E7ECE9; --muted: #8B9C96;
    --accent: #4FB596; --accent-soft: #1B2C27;
    --ok: #4FA86B; --ok-soft: #16281D; --warn: #D0973B; --warn-soft: #2B2213;
    --fail: #D86B5C; --fail-soft: #2D1917; --border: #283330;
  }}
}}
:root[data-theme="dark"] {{
  --paper: #101513; --surface: #161C1A; --ink: #E7ECE9; --muted: #8B9C96;
  --accent: #4FB596; --accent-soft: #1B2C27;
  --ok: #4FA86B; --ok-soft: #16281D; --warn: #D0973B; --warn-soft: #2B2213;
  --fail: #D86B5C; --fail-soft: #2D1917; --border: #283330;
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
  line-height: 1.55;
}}
.wrap {{ max-width: 880px; margin: 0 auto; padding: 3rem 1.5rem 5rem; }}
h1, h2, h3 {{ font-family: 'Fraunces', Georgia, serif; text-wrap: balance; margin: 0; }}
h1 {{ font-size: 2.1rem; font-weight: 700; }}
h2 {{ font-size: 1.4rem; font-weight: 600; margin: 3rem 0 1rem; }}
.mono {{ font-family: 'IBM Plex Mono', monospace; }}
.lede {{ color: var(--muted); font-size: 1.05rem; max-width: 60ch; margin-top: 0.6rem; }}

.stat-strip {{ display: flex; gap: 1px; margin-top: 2rem; background: var(--border); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
.stat {{ flex: 1; background: var(--surface); padding: 1rem 1.2rem; }}
.stat-n {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.6rem; font-weight: 500; font-variant-numeric: tabular-nums; }}
.stat-l {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 0.2rem; }}

.chip {{ font-size: 0.72rem; font-family: 'IBM Plex Mono', monospace; padding: 0.15rem 0.55rem; border-radius: 999px; white-space: nowrap; }}
.chip-ok {{ background: var(--ok-soft); color: var(--ok); }}
.chip-warn {{ background: var(--warn-soft); color: var(--warn); }}
.chip-fail {{ background: var(--fail-soft); color: var(--fail); }}

.erd-frame {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; margin-top: 1rem; overflow-x: auto; }}
.erd-fallback {{ max-width: 100%; height: auto; display: block; }}

.egrid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 0.8rem; margin-top: 1rem; }}
.ecard {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.9rem 1rem; }}
.ecard-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; }}
.ecard-name {{ font-family: 'IBM Plex Mono', monospace; font-weight: 500; font-size: 0.9rem; }}
.ecard-grain {{ color: var(--muted); font-size: 0.85rem; margin: 0.5rem 0; }}
.ecard-meta {{ display: flex; gap: 0.9rem; font-size: 0.78rem; color: var(--muted); }}

.mgrid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; margin-top: 1rem; }}
.mcard {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.1rem 1.2rem; }}
.mcard-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; margin-bottom: 0.6rem; }}
.mcard-name {{ font-weight: 600; font-size: 0.95rem; }}
.formula {{ background: var(--accent-soft); color: var(--accent); padding: 0.4rem 0.6rem; border-radius: 6px; font-size: 0.82rem; margin: 0 0 0.6rem; }}
.mcard-rationale {{ font-size: 0.88rem; margin: 0 0 0.5rem; }}
.mcard-caveat {{ font-size: 0.82rem; color: var(--muted); margin: 0; }}

.muted-inline {{ color: var(--muted); font-size: 0.9rem; }}

.pending-group {{ margin-top: 1.4rem; }}
.pending-entity {{ font-size: 0.85rem; font-weight: 500; color: var(--accent); margin: 0 0 0.5rem; text-transform: lowercase; }}
.rrow {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.8rem 1rem; margin-bottom: 0.6rem; }}
.rrow-key {{ font-size: 0.72rem; color: var(--muted); margin-bottom: 0.35rem; }}
.rrow-text {{ font-size: 0.88rem; margin: 0 0 0.6rem; }}
.rrow-cmd {{ display: flex; align-items: center; gap: 0.6rem; background: var(--accent-soft); border-radius: 6px; padding: 0.35rem 0.5rem; }}
.rrow-cmd code {{ flex: 1; font-size: 0.78rem; color: var(--accent); overflow-x: auto; white-space: nowrap; }}
.copy-btn {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; border: 1px solid var(--accent); background: transparent; color: var(--accent); border-radius: 4px; padding: 0.15rem 0.5rem; cursor: pointer; }}
.copy-btn:hover {{ background: var(--accent); color: var(--surface); }}
.copy-btn:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 1px; }}

.fixrow {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.8rem 1rem; margin-bottom: 0.6rem; }}
.diff-line {{ font-size: 0.82rem; padding: 0.15rem 0.5rem; border-radius: 4px; margin-top: 0.3rem; }}
.diff-old {{ background: var(--fail-soft); color: var(--fail); }}
.diff-new {{ background: var(--ok-soft); color: var(--ok); }}

.owl-status {{ margin-top: 1rem; }}
.owl-pre {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.2rem; margin-top: 0.8rem; max-height: 420px; overflow: auto; font-size: 0.78rem; line-height: 1.6; white-space: pre; }}
.owl-report {{ margin-top: 1rem; }}
.owl-report summary {{ cursor: pointer; color: var(--accent); font-size: 0.88rem; }}

section.gaps ul {{ padding-left: 1.2rem; color: var(--muted); font-size: 0.92rem; }}
footer {{ margin-top: 4rem; padding-top: 1.5rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85rem; }}
footer code {{ font-family: 'IBM Plex Mono', monospace; background: var(--accent-soft); color: var(--accent); padding: 0.1rem 0.4rem; border-radius: 4px; }}
</style>

<div class="wrap">
  <h1>Ontology Status Report</h1>
  <p class="lede">jaffle_shop, fully modeled — every claim below is either mechanically verified against the dbt manifest or explicitly flagged for a human. Nothing in between.</p>

  <div class="stat-strip">
    <div class="stat"><div class="stat-n">{totals['n_entities']}</div><div class="stat-l">Entities</div></div>
    <div class="stat"><div class="stat-n">{totals['n_relationships']}</div><div class="stat-l">Relationships</div></div>
    <div class="stat"><div class="stat-n">{totals['n_metrics']}</div><div class="stat-l">Metrics</div></div>
    <div class="stat"><div class="stat-n">{totals['n_failures']}</div><div class="stat-l">Failures</div></div>
    <div class="stat"><div class="stat-n">{totals['n_coverage_gaps']}</div><div class="stat-l">Coverage gaps</div></div>
    <div class="stat"><div class="stat-n">{signed_pct}%</div><div class="stat-l">Review signed off</div></div>
    <div class="stat"><div class="stat-n">{totals['n_owl_triples']}</div><div class="stat-l">OWL triples</div></div>
    <div class="stat"><div class="stat-n">{'✓' if totals['owl_conforms'] else '✗'}</div><div class="stat-l">SHACL conforms</div></div>
  </div>

  <h2>Relationship diagram</h2>
  <p class="lede" style="margin-top:0">Generated straight from the same Relationship objects the citations are checked against — built on ID-sanitization and diagram-generation patterns already proven across internal dbt tooling I've built elsewhere, extended here with real cardinality instead of a generic dependency edge. order_items and products don't appear in an edge here for a reason, not an omission: neither has a relationships test declared at the mart layer (see their entity summaries) — the diagram doesn't invent an edge just to look complete.</p>
  <div class="erd-frame">
    <pre class="mermaid" id="erd-live">{erd_source}</pre>
    <img class="erd-fallback" id="erd-fallback" src="media/erd.png" alt="Relationship diagram (static fallback, jaffle_shop doesn't change so this stays accurate)" style="display:none">
  </div>

  <h2>Entities</h2>
  <div class="egrid">{cards}
  </div>

  <h2>Derived metrics</h2>
  <div class="mgrid">{mcards}
  </div>

  <h2>Review workspace</h2>
  <p class="lede" style="margin-top:0">Every item here is flagged because it genuinely can't be checked by machine — read the citation, then run the command to sign off. Nothing here should be trusted just because it's written down.</p>
  {pending_html}

  <h2>Coverage gaps</h2>
  <p class="lede" style="margin-top:0">Columns real in the dbt manifest that no entity documents at all — a different failure class from a wrong claim: there's nothing here to fail, because nothing was claimed. Informational, not blocking.</p>
  <ul class="gapslist">{gaps_html}
  </ul>

  <h2>Suggested fixes</h2>
  <p class="lede" style="margin-top:0">When a claim fails because it doesn't match the manifest, the correct text is already known — not a guess, the same fact the failure was checked against. Shown for copy-paste into the source file, never applied automatically.</p>
  {fixes_html}

  <h2>OWL export</h2>
  <p class="lede" style="margin-top:0">The same ontology above, translated into real OWL (Turtle) — every entity a class, every column a property, every citation an annotation. This is the part that's reusable outside this repo: paste it into Protege or GraphDB, no Python required. Validated against <code>shapes.ttl</code> (SHACL) below — conforming here proves the graph is structurally well-formed, not that its claims are true against the manifest; that's still the citation validator's job, above.</p>
  <div class="owl-status">
    <span class="chip chip-{'ok' if totals['owl_conforms'] else 'fail'}">{'SHACL: conforms' if totals['owl_conforms'] else 'SHACL: violations found'}</span>
  </div>
  <pre class="owl-pre mono">{e(owl_ttl)}</pre>
  <details class="owl-report">
    <summary>Full SHACL validation report</summary>
    <pre class="owl-pre mono">{e(owl_shacl_report)}</pre>
  </details>

  <h2 class="gaps-title">Honest gaps</h2>
  <section class="gaps">
    <ul>
      <li>The OWL/SHACL layer above validates structure (every class has a grain, every property has a source, cardinality values are legal) — it does not re-check citation correctness against the dbt manifest. That mechanical check stays the citation validator's job, alone.</li>
      <li>{totals['n_pending']} review item(s) are mechanically unfalsifiable (grain, cardinality reasoning) and are pending human signoff — not a bug, the gate working as intended.</li>
      <li>Grain and cardinality reasoning stay human-review forever, by design — not a limitation waiting to be automated away.</li>
    </ul>
  </section>

  <footer>
    Generated by <code>render_ontology.py</code> from the live Pydantic ontology + validator results — never hand-edited. Re-run after any change to <code>generate_*.py</code>, <code>structural_facts.json</code>, or <code>review_signoffs.json</code>.
  </footer>
</div>

<script type="module">
  // Live-render first; fall back to the static PNG (media/erd.png, regenerated
  // via mmdc only if the entities change -- jaffle_shop doesn't, so it stays
  // accurate) if the CDN import fails or rendering itself throws. Covers both
  // failure modes with one try/catch, not just "script tag didn't load."
  const live = document.getElementById('erd-live');
  const fallback = document.getElementById('erd-fallback');
  try {{
    const {{ default: mermaid }} = await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs');
    mermaid.initialize({{
      startOnLoad: false,
      theme: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'default',
    }});
    await mermaid.run({{ nodes: [live] }});
  }} catch (err) {{
    console.warn('Mermaid failed to load or render, showing the static fallback:', err);
    live.style.display = 'none';
    fallback.style.display = 'block';
  }}
</script>
"""


if __name__ == "__main__":
    entity_results, metric_results, totals, coverage_gaps, suggested_fixes, owl_ttl, owl_shacl_report = build()
    html_out = render(entity_results, metric_results, totals, coverage_gaps, suggested_fixes, owl_ttl, owl_shacl_report)
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ontology_report.html")
    out_path.write_text(html_out)
    print(f"Wrote {out_path} -- {totals['n_entities']} entities, {totals['n_metrics']} metrics, "
          f"{totals['n_failures']} failures, {totals['n_pending']} pending signoffs, "
          f"{totals['n_coverage_gaps']} coverage gaps, {len(suggested_fixes)} suggested fixes, "
          f"{totals['n_owl_triples']} OWL triples, SHACL conforms={totals['owl_conforms']}.")
