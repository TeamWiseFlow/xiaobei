---
name: manim-explainer
description: Build reusable Manim explainers for technical concepts, graphs, system
  diagrams, and product walkthroughs, then hand off to the wider video stack if needed.
  Use when the user wants a clean animated explainer rather than a generic talking-head
  script.
metadata:
  openclaw:
    emoji: 🎬
    requires:
      bins:
      - python3
      - manim
      - ffmpeg
---

# Manim Explainer

Use Manim for technical explainers where motion, structure, and clarity matter more than photorealism.

## When to Activate

- the user wants a technical explainer animation
- the concept is a graph, workflow, architecture, metric progression, or system diagram
- the user wants a short product or launch explainer for X or a landing page
- the visual should feel precise instead of generically cinematic

## Tool Requirements

- `manim` CLI for scene rendering
- `ffmpeg` for post-processing if needed
- `fragment-assembly` for combining rendered video with TTS audio
- `siliconflow-tts` for voiceover generation

## Default Output

- short 16:9 MP4
- one thumbnail or poster frame
- storyboard plus scene plan

## Workflow

1. Define the core visual thesis in one sentence.
2. Break the concept into 3 to 6 scenes.
3. Decide what each scene proves.
4. Write the scene outline before writing Manim code.
5. Render the smallest working version first.
6. Tighten typography, spacing, color, and pacing after the render works.
7. Hand off to the wider video stack only if it adds value.

## Scene Planning Rules

- each scene should prove one thing
- avoid overstuffed diagrams
- prefer progressive reveal over full-screen clutter
- use motion to explain state change, not just to keep the screen busy
- title cards should be short and loaded with meaning

## Network Graph Default

For social-graph and network-optimization explainers:

- show the current graph before showing the optimized graph
- distinguish low-signal follow clutter from high-signal bridges
- highlight warm-path nodes and target clusters
- if useful, add a final scene showing the self-improvement lineage that informed the skill

## Render Conventions

- default to 16:9 landscape unless the user asks for vertical
- start with a low-quality smoke test render
- only push to higher quality after composition and timing are stable
- export one clean thumbnail frame that reads at social size

```bash
# 冒烟测试（低质量，优先用此验证构图）
./skills/manim-explainer/scripts/render-manim.sh <scene_file>.py <ClassName> low ./output

# 中等质量预览
./skills/manim-explainer/scripts/render-manim.sh <scene_file>.py <ClassName> medium ./output

# 正式输出（高质量）
./skills/manim-explainer/scripts/render-manim.sh <scene_file>.py <ClassName> high ./output
```

脚本自动完成：渲染 → 定位 MP4 → 导出第 2 秒封面帧，最后输出 JSON：
```json
{"ok": true, "video": "./output/scene_Class_low.mp4", "thumbnail": "./output/scene_Class_thumbnail.png"}
```

## Reusable Starter

Use [assets/network_graph_scene.py](assets/network_graph_scene.py) as a starting point for network-graph explainers.

Example smoke test:

```bash
./skills/manim-explainer/scripts/render-manim.sh assets/network_graph_scene.py NetworkGraphExplainer low ./output
```

## Output Format

Return:

- core visual thesis
- storyboard
- scene outline
- render plan
- any follow-on polish recommendations

## Related Skills

- `fragment-assembly` for combining rendered video with TTS audio
- `siliconflow-tts` for voiceover generation
- `content-check` for verifying output quality and duration
