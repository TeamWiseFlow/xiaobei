#!/usr/bin/env python3
"""Template registry for content-producer html-video 9:16 templates.

Usage:
  python3 registry.py list              — List all templates
  python3 registry.py search <intent>   — Search by intent keyword
  python3 registry.py inspect <id>      — Show template details
  python3 registry.py inject <id> <outdir> <vars_json> — Inject variables into template
"""
import sys
import os
import json
import re
import shutil
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent

def load_manifest(template_dir: Path) -> dict | None:
    yaml_path = template_dir / "template.yaml"
    if not yaml_path.exists():
        return None
    # Minimal YAML parser (no dependency)
    text = yaml_path.read_text(encoding="utf-8")
    manifest = {}
    current_key = None
    for line in text.splitlines():
        if line.startswith("spec_version:"):
            manifest["spec_version"] = line.split(":", 1)[1].strip()
        elif line.startswith("id:"):
            manifest["id"] = line.split(":", 1)[1].strip()
        elif line.startswith("name:"):
            manifest["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("engine:"):
            manifest["engine"] = line.split(":", 1)[1].strip()
        elif line.startswith("category:"):
            manifest["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("  default:"):
            if current_key == "resolution":
                manifest["default_resolution"] = line.split("default:", 1)[1].strip()
        elif line.startswith("    min_sec:"):
            manifest["min_sec"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("    max_sec:"):
            manifest["max_sec"] = int(line.split(":", 1)[1].strip())
        elif line.strip().startswith("resolution:"):
            current_key = "resolution"
    manifest["dir"] = str(template_dir)
    return manifest

def list_templates() -> list[dict]:
    templates = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        if d.is_dir() and (d / "template.yaml").exists():
            m = load_manifest(d)
            if m:
                templates.append(m)
    return templates

def search_templates(intent: str) -> list[dict]:
    all_t = list_templates()
    results = []
    intent_lower = intent.lower()
    for t in all_t:
        score = 0
        searchable = f"{t.get('id','')} {t.get('name','')} {t.get('category','')}".lower()
        for word in intent_lower.split():
            if word in searchable:
                score += 1
        if score > 0:
            t["score"] = score
            results.append(t)
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results

def inject_template(template_id: str, output_dir: str, variables: dict) -> str:
    """Inject variables into template HTML and write to output_dir."""
    template_dir = TEMPLATES_DIR / template_id
    if not template_dir.exists():
        raise FileNotFoundError(f"Template not found: {template_id}")

    source_html = template_dir / "source" / "index.html"
    if not source_html.exists():
        raise FileNotFoundError(f"Template source not found: {source_html}")

    html = source_html.read_text(encoding="utf-8")

    # Replace PLACEHOLDER_* with variable values
    for key, value in variables.items():
        placeholder = f"PLACEHOLDER_{key.upper()}"
        html = html.replace(placeholder, str(value))

    # Write output
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    output_file = out_path / "index.html"
    output_file.write_text(html, encoding="utf-8")

    return str(output_file)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        for t in list_templates():
            print(f"  {t['id']:30s}  {t.get('name',''):25s}  {t.get('category',''):15s}  {t.get('min_sec','?')}-{t.get('max_sec','?')}s")

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: registry.py search <intent>")
            sys.exit(1)
        results = search_templates(sys.argv[2])
        if not results:
            print("No matches found.")
        for t in results:
            print(f"  {t['id']:30s}  score={t['score']}  {t.get('name','')}")

    elif cmd == "inspect":
        if len(sys.argv) < 3:
            print("Usage: registry.py inspect <id>")
            sys.exit(1)
        template_dir = TEMPLATES_DIR / sys.argv[2]
        yaml_path = template_dir / "template.yaml"
        if yaml_path.exists():
            print(yaml_path.read_text(encoding="utf-8"))
        else:
            print(f"Template not found: {sys.argv[2]}")

    elif cmd == "inject":
        if len(sys.argv) < 5:
            print("Usage: registry.py inject <id> <outdir> <vars_json>")
            sys.exit(1)
        template_id = sys.argv[2]
        outdir = sys.argv[3]
        variables = json.loads(sys.argv[4])
        result = inject_template(template_id, outdir, variables)
        print(f"Injected: {result}")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
