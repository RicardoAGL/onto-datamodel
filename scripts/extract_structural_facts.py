"""Extract structural facts from a dbt project's manifest.json.

This is the "free" layer -- everything here is already true in the dbt
project, no LLM call needed. Same idea as dbt-graphify: most lineage
questions are structural, not semantic, and dbt already has the answer
sitting in target/manifest.json.

Output: one JSON blob with per-model column facts (from schema.yml
descriptions + unique/not_null tests) and explicit relationship edges
(from `relationships` tests), which is exactly the ground truth the
ontology-generation step should be grounded against and validated
against later.
"""
import json
import re
import sys
from pathlib import Path

# jaffle_shop's manifest only ever renders ref()/source() with single
# quotes -- this held until run against a real second (private) dbt
# project, whose formatter renders double quotes instead
# (ref("publication")). Quote-style agnostic on purpose now: a portability
# bug this pipeline's own "prove it on a second project" step exists to
# catch, not a hypothetical.
REF_PATTERN = re.compile(r"""ref\(["']([^"']+)["']\)""")
SOURCE_PATTERN = re.compile(r"""source\(["']([^"']+)["'],\s*["']([^"']+)["']\)""")


def _model_name_from_jinja(model_jinja: str) -> str | None:
    """The manifest's test kwargs carry the model as a Jinja template
    string, e.g. "{{ get_where_subquery(ref('stg_customers')) }}" for a
    model, or "{{ get_where_subquery(source('raw', 'raw_customers')) }}"
    for a source (a raw seed table). Only ref() targets are part of the
    model-level ontology this extracts -- source()-targeted tests are
    skipped (returns None), since seeds/sources aren't modeled entities
    here."""
    ref_match = REF_PATTERN.search(model_jinja)
    if ref_match:
        return ref_match.group(1)
    if SOURCE_PATTERN.search(model_jinja):
        return None
    raise ValueError(f"unrecognized model reference shape: {model_jinja!r}")


def extract(manifest: dict) -> dict:
    models = {}
    for node_id, node in manifest["nodes"].items():
        if node.get("resource_type") != "model":
            continue
        name = node["name"]
        columns = {}
        for col_name, col in node.get("columns", {}).items():
            columns[col_name] = {
                "description": col.get("description") or None,
                "data_type": col.get("data_type"),
                "unique": False,
                "not_null": False,
            }
        depends_on_ids = node.get("depends_on", {}).get("nodes", [])
        depends_on_models = [
            manifest["nodes"][dep]["name"]
            for dep in depends_on_ids
            if dep in manifest["nodes"]
            and manifest["nodes"][dep].get("resource_type") == "model"
        ]
        models[name] = {
            "description": node.get("description") or None,
            "columns": columns,
            "depends_on": depends_on_models,
        }

    relationships = []
    for node in manifest["nodes"].values():
        if node.get("resource_type") != "test":
            continue
        meta = node.get("test_metadata")
        if not meta:
            continue

        kwargs = meta["kwargs"]
        model_jinja = kwargs.get("model", "")

        if meta["name"] == "unique":
            model_name = _model_name_from_jinja(model_jinja)
            if model_name is None:
                continue  # source-level test, not a modeled entity here
            col = kwargs["column_name"]
            if model_name in models and col in models[model_name]["columns"]:
                models[model_name]["columns"][col]["unique"] = True

        elif meta["name"] == "not_null":
            model_name = _model_name_from_jinja(model_jinja)
            if model_name is None:
                continue
            col = kwargs["column_name"]
            if model_name in models and col in models[model_name]["columns"]:
                models[model_name]["columns"][col]["not_null"] = True

        elif meta["name"] == "relationships":
            from_model = _model_name_from_jinja(model_jinja)
            to_model = _model_name_from_jinja(kwargs["to"])
            if from_model is None or to_model is None:
                continue  # relationship touches a source, not two models
            relationships.append({
                "from_model": from_model,
                "from_column": kwargs["column_name"],
                "to_model": to_model,
                "to_column": kwargs["field"],
            })

    return {"models": models, "relationships": relationships}


def main():
    manifest_path = Path(sys.argv[1] if len(sys.argv) > 1 else "target/manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)

    facts = extract(manifest)

    out_path = Path("structural_facts.json")
    with open(out_path, "w") as f:
        json.dump(facts, f, indent=2)

    print(f"Extracted {len(facts['models'])} models, {len(facts['relationships'])} relationships")
    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
