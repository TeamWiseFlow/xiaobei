#!/usr/bin/env python3
"""Content-Graph IR for content-producer html-video workflow.

Usage:
  python3 content_graph.py validate <graph.json>   — Validate content-graph
  python3 content_graph.py topo-sort <graph.json>   — Topological sort nodes
  python3 content_graph.py to-frames <graph.json>   — Convert to frame list (for rendering)
"""
import sys
import json
from pathlib import Path

def validate_graph(graph: dict) -> list[str]:
    """Validate content-graph structure. Returns list of errors."""
    errors = []

    if graph.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")

    if "nodes" not in graph or not isinstance(graph["nodes"], list):
        errors.append("nodes must be a list")
        return errors

    if len(graph["nodes"]) == 0:
        errors.append("nodes cannot be empty")

    node_ids = set()
    for i, node in enumerate(graph["nodes"]):
        nid = node.get("id")
        if not nid:
            errors.append(f"node[{i}] missing id")
            continue
        if nid in node_ids:
            errors.append(f"node[{i}] duplicate id: {nid}")
        node_ids.add(nid)

        if node.get("kind") not in ("text", "entity", "data"):
            errors.append(f"node '{nid}': kind must be text/entity/data")

        if "templateRef" not in node:
            errors.append(f"node '{nid}': missing templateRef")

    # Validate edges
    if "edges" in graph:
        for i, edge in enumerate(graph["edges"]):
            if edge.get("from") not in node_ids:
                errors.append(f"edge[{i}]: 'from' references unknown node '{edge.get('from')}'")
            if edge.get("to") not in node_ids:
                errors.append(f"edge[{i}]: 'to' references unknown node '{edge.get('to')}'")
            if edge.get("kind") not in ("sequence", "dependency", "contrast"):
                errors.append(f"edge[{i}]: kind must be sequence/dependency/contrast")
            if edge.get("from") == edge.get("to"):
                errors.append(f"edge[{i}]: self-edge on '{edge.get('from')}'")

    # Check for cycles in dependency edges
    if "edges" in graph:
        dep_edges = [(e["from"], e["to"]) for e in graph["edges"] if e.get("kind") == "dependency"]
        # Kahn's algorithm for cycle detection
        in_degree = {nid: 0 for nid in node_ids}
        adj = {nid: [] for nid in node_ids}
        for frm, to in dep_edges:
            adj[frm].append(to)
            in_degree[to] = in_degree.get(to, 0) + 1

        queue = [nid for nid in node_ids if in_degree[nid] == 0]
        visited = 0
        while queue:
            node = queue.pop(0)
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited < len(node_ids):
            errors.append("cycle detected in dependency edges")

    return errors

def topo_sort(graph: dict) -> list[str]:
    """Topological sort using Kahn's algorithm with sequence-edge preference."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    node_ids = [n["id"] for n in nodes]
    node_order = {nid: i for i, nid in enumerate(node_ids)}

    # Build adjacency from dependency edges only
    in_degree = {nid: 0 for nid in node_ids}
    adj = {nid: [] for nid in node_ids}

    for edge in edges:
        frm, to, kind = edge.get("from"), edge.get("to"), edge.get("kind")
        if kind == "dependency" and frm in node_order and to in node_order:
            adj[frm].append(to)
            in_degree[to] = in_degree.get(to, 0) + 1

    # Kahn's algorithm
    result = []
    available = [nid for nid in node_ids if in_degree[nid] == 0]

    # Sort available by sequence-edge preference, then original order
    seq_order = {}
    for edge in edges:
        if edge.get("kind") == "sequence":
            frm, to = edge.get("from"), edge.get("to")
            if frm in node_order and to in node_order:
                seq_order[to] = frm

    def sort_key(nid):
        # Nodes that are sequence-targets of already-sorted nodes come first
        return node_order.get(nid, 999)

    available.sort(key=sort_key)

    while available:
        node = available.pop(0)
        result.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                available.append(neighbor)
        available.sort(key=sort_key)

    return result

def to_frames(graph: dict) -> list[dict]:
    """Convert content-graph to ordered frame list for rendering."""
    order = topo_sort(graph)
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}

    frames = []
    for i, nid in enumerate(order):
        node = nodes_by_id.get(nid)
        if not node:
            continue
        frame = {
            "order": i + 1,
            "id": nid,
            "templateRef": node.get("templateRef", ""),
            "variables": node.get("variables", {}),
            "durationSec": node.get("durationSec", 5),
            "hasTts": node.get("hasTts", False),
            "ttsText": node.get("ttsText", ""),
            "ttsVoice": node.get("ttsVoice", ""),
            "frameIntent": node.get("frameIntent", ""),
            "label": node.get("label", ""),
        }
        frames.append(frame)

    return frames

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    graph_path = sys.argv[2]

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    if cmd == "validate":
        errors = validate_graph(graph)
        if errors:
            print("VALIDATION FAILED:")
            for e in errors:
                print(f"  ❌ {e}")
            sys.exit(1)
        else:
            print("VALIDATION PASSED ✓")

    elif cmd == "topo-sort":
        order = topo_sort(graph)
        print(json.dumps(order, ensure_ascii=False, indent=2))

    elif cmd == "to-frames":
        frames = to_frames(graph)
        print(json.dumps(frames, ensure_ascii=False, indent=2))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
