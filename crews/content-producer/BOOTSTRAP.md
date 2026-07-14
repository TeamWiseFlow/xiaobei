# Video-Producer Bootstrap

This one-time bootstrap collects user preferences and verifies the environment before video production work starts. If this crew is being enabled through Main Agent and has no direct work channel yet, Main Agent may ask these questions on behalf of this crew and write the answers into the crew workspace.

## Step 1: User Preferences

Collect:

- **Default language**: primary language for video content (e.g., 中文, English)
- **Default video style**: preferred visual style (e.g., tech demo, storytelling, tutorial, promotional)
- **Default duration target**: typical video length (e.g., 30s, 60s, 3min)
- **Common publishing platforms**: which platforms videos will be published to (affects aspect ratio, format, and platform-specific requirements)

## Step 2: Environment Verification

On first startup, check and report to user:

1. `SILICONFLOW_API_KEY` is set → required for TTS + image/video generation
2. `moviepy` is installed: `python3 -c "import moviepy; print('ok')"` → required for t2video composition
3. `requests` is installed: `python3 -c "import requests; print('ok')"` → required for t2video
4. Output directories exist: `mkdir -p output_videos video_assets`

Optional (for footage modes):
- `PEXELS_API_KEY` is set → enables `pexels-footage` skill
- `PIXABAY_API_KEY` is set → enables `pixabay-footage` skill

If SILICONFLOW_API_KEY or moviepy check fails, report clearly and spawn IT Engineer to resolve.

## Completion

After bootstrap is complete:

1. Update `MEMORY.md` with user preferences (replace `待记录` placeholders).
2. Delete `BOOTSTRAP.md` from the runtime workspace.
3. Suggest the next step, such as creating the first video project.
