"""Governance gate: every mart model and every mart column must be documented.

Reads target/manifest.json after `dbt build` (or `dbt parse`). Exits non-zero with the list
of gaps so CI blocks the PR.
"""
import json
import sys
from pathlib import Path

manifest = json.loads((Path(__file__).resolve().parents[1] / "target" / "manifest.json").read_text())
gaps = []
for node in manifest["nodes"].values():
    if node["resource_type"] != "model" or "marts" not in node["fqn"]:
        continue
    if not node.get("description", "").strip():
        gaps.append(f"{node['name']}: model has no description")
    if not node["columns"]:
        gaps.append(f"{node['name']}: no columns documented")
    for col in node["columns"].values():
        if not col.get("description", "").strip():
            gaps.append(f"{node['name']}.{col['name']}: column has no description")

if gaps:
    print("Undocumented mart objects:\n  " + "\n  ".join(gaps))
    sys.exit(1)
print("Docs check passed: every mart model and column is documented.")
