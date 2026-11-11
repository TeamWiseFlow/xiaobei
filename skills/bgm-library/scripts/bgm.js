#!/usr/bin/env node

/**
 * BGM Library - Background Music CLI for video projects.
 * Search, filter, and download royalty-free music from ccMixter.
 *
 * 纯文本输出（无 chalk/ora），agent 友好，无 ANSI 转义码污染 stdout。
 */

import { program, Option } from 'commander';
import { queryApi, termsFor, rankTracks } from './search.js';
import {
  downloadTrack,
  updateManifest,
  generateAttribution,
  buildManifestEntry,
} from './downloader.js';

// ─── Constants ───────────────────────────────────────────────────────────────

/**
 * Predefined tag presets for common video scenarios.
 */
const PRESETS = {
  travel: {
    name: '旅行/Vlog (Travel/Vlog)',
    description: 'Bright, upbeat, rhythmic — perfect for travel vlogs',
    tags: 'upbeat',
  },
  tech: {
    name: '科技/产品 (Tech/Corporate)',
    description: 'Modern, clean, forward-moving — tech demos and corporate',
    tags: 'electronic',
  },
  lofi: {
    name: '咖啡馆/学习 (Café/LoFi)',
    description: 'Relaxed, rhythmic, chill — study, café, lifestyle',
    tags: 'chill',
  },
  food: {
    name: '美食/生活 (Food/Lifestyle)',
    description: 'Warm, light, unobtrusive — cooking and lifestyle',
    tags: 'acoustic',
  },
  workout: {
    name: '运动/健身 (Workout/Fitness)',
    description: 'Strong beat, high energy — gym, sports, motivation',
    tags: 'edm',
  },
};

// Blocked license keywords (case-insensitive)
const BLOCKED_LICENSES = ['noncommercial', 'noderivs', 'no-deriv', 'nc', 'nd'];

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Check if a license is commercially safe (CC BY or CC BY-SA).
 */
function isCommercialSafe(licenseName) {
  const lower = licenseName.toLowerCase();
  return !BLOCKED_LICENSES.some((kw) => lower.includes(kw));
}

/**
 * Get the best MP3 file from a track's files array.
 * Prefers "Main Mix" or first mp3 file.
 */
function getBestFile(track) {
  if (!track.files || track.files.length === 0) return null;

  const mainMix = track.files.find(
    (f) =>
      f.file_nicname?.toLowerCase().includes('main') ||
      f.file_nicname?.toLowerCase() === 'mp3'
  );
  if (mainMix) return mainMix;

  const mp3 = track.files.find(
    (f) => f.file_format_info?.['default-ext'] === 'mp3'
  );
  return mp3 || track.files[0];
}

/**
 * Format track info for display (plain text).
 */
function formatTrack(track, index) {
  const file = getBestFile(track);
  const duration = file?.file_format_info?.ps || '?';
  const bpm = track.upload_extra?.bpm || '?';
  const tags =
    track.upload_extra?.usertags?.split(',').slice(0, 5).join(', ') || '';

  return [
    `  #${index + 1} ${track.upload_name} (ID: ${track.upload_id})`,
    `     Artist: ${track.user_real_name || track.user_name}`,
    `     Duration: ${duration}  BPM: ${bpm}  License: ${track.license_name}`,
    `     Tags: ${tags}`,
    `     URL: ${track.file_page_url}`,
  ].join('\n');
}

/**
 * Format file size for display.
 */
function formatSize(bytes) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)}MB`;
}

// ─── Commands ────────────────────────────────────────────────────────────────

program
  .name('bgm-library')
  .description('Search & download royalty-free background music from ccMixter (CC BY / CC BY-SA only)')
  .version('1.0.0');

// ── search ───────────────────────────────────────────────────────────────────

program
  .command('search [keywords...]')
  .description('Search ccMixter for background music tracks')
  .option('-l, --limit <n>', 'Max results', '10')
  .option('-p, --preset <name>', 'Use a predefined tag preset (travel, tech, lofi, food, workout)')
  .option('--commercial-only', 'Only show commercially safe licenses (CC BY / CC BY-SA)', true)
  .option('--no-commercial-only', 'Include all licenses')
  .option('--sort <field>', 'Sort by: date, name, score', 'score')
  .addOption(new Option('--match <mode>', 'Tag matching: any or all').choices(['any', 'all']).default('any'))
  .action(async (keywords, opts) => {
    try {
      let tags;
      if (opts.preset) {
        const preset = PRESETS[opts.preset.toLowerCase()];
        if (!preset) {
          console.error(`✗ Unknown preset: ${opts.preset}`);
          console.error(`Available: ${Object.keys(PRESETS).join(', ')}`);
          process.exit(1);
        }
        tags = preset.tags;
        console.log(`Searching with preset "${opts.preset}" (${preset.name})...`);
      } else if (keywords.length > 0) {
        tags = termsFor(keywords.join(' ')).join(' ');
        console.log('Searching ccMixter...');
      } else {
        console.error('✗ Provide keywords or --preset');
        process.exit(1);
      }

      const params = { tags, type: opts.match, limit: opts.limit, sort: opts.sort };
      if (opts.commercialOnly) params.lic = 'open';

      const tracks = await queryApi(params);
      const filtered = opts.commercialOnly
        ? tracks.filter((t) => isCommercialSafe(t.license_name))
        : tracks;

      if (filtered.length === 0) {
        console.log('No tracks found matching your query. Try English tags, --match any, or --preset.');
        return;
      }

      console.log(`\nFound ${filtered.length} track(s):\n`);
      for (let i = 0; i < filtered.length; i++) {
        console.log(formatTrack(filtered[i], i));
        if (i < filtered.length - 1) console.log();
      }
      console.log(`\nUse: bgm-library download <ID> to download a track.`);
    } catch (err) {
      console.error(`✗ Search failed: ${err.message}`);
      process.exit(1);
    }
  });

// ── download ─────────────────────────────────────────────────────────────────

program
  .command('download <uploadId>')
  .description('Download a track by ccMixter upload ID')
  .option('-o, --output <dir>', 'Output directory', './public')
  .option('--force', 'Overwrite existing files', false)
  .action(async (uploadId, opts) => {
    try {
      console.log(`Fetching track ${uploadId}...`);
      const tracks = await queryApi({ ids: uploadId });

      if (tracks.length === 0) {
        console.error(`✗ Track not found: ${uploadId}`);
        process.exit(1);
      }

      const track = tracks[0];

      if (!isCommercialSafe(track.license_name)) {
        console.error(
          `✗ Track "${track.upload_name}" has license "${track.license_name}" which is NOT commercially safe. Use --force to override.`
        );
        if (!opts.force) process.exit(1);
      }

      const file = getBestFile(track);
      if (!file) {
        console.error('✗ No downloadable MP3 file found for this track.');
        process.exit(1);
      }

      console.log(`Downloading "${track.upload_name}" (${file.file_format_info?.ps || '?'})...`);

      const result = await downloadTrack(
        {
          download_url: file.download_url,
          file_page_url: track.file_page_url,
          file_name: file.file_name,
        },
        opts.output,
        { force: opts.force }
      );

      if (result.skipped) {
        console.log(
          `ℹ "${track.upload_name}" already exists at ${result.filePath} (use --force to overwrite)`
        );
      } else {
        console.log(
          `✓ Downloaded "${track.upload_name}" → ${result.filePath} (${formatSize(result.size)})`
        );
      }

      const entry = buildManifestEntry(track, file);
      await updateManifest(opts.output, entry);
      await generateAttribution(opts.output);

      console.log(`  Manifest: ${opts.output}/music_manifest.json`);
      console.log(`  Attribution: ${opts.output}/ATTRIBUTION.txt`);
      console.log(`\nRemotion usage:`);
      console.log(`  <Audio src={staticFile('${file.file_name}')} volume={0.3} loop />`);
    } catch (err) {
      console.error(`✗ Download failed: ${err.message}`);
      process.exit(1);
    }
  });

// ── pick ─────────────────────────────────────────────────────────────────────

program
  .command('pick <theme>')
  .description('Download a tag-matched candidate; audition before mixing')
  .option('-o, --output <dir>', 'Output directory', './public')
  .option('-l, --limit <n>', 'Number of candidates to evaluate', '5')
  .option('--force', 'Overwrite existing files', false)
  .addOption(new Option('--match <mode>', 'Tag matching: any or all').choices(['any', 'all']).default('any'))
  .action(async (theme, opts) => {
    try {
      console.log(`Finding BGM candidates for "${theme}"...`);

      const terms = termsFor(theme);
      const tags = terms.join(' ');

      const tracks = await queryApi({
        tags,
        type: opts.match,
        lic: 'open',
        limit: opts.limit,
        sort: 'score',
      });

      const safe = rankTracks(tracks.filter((t) => isCommercialSafe(t.license_name) && getBestFile(t)), terms);

      if (safe.length === 0) {
        console.error('✗ No commercially safe tracks found for this theme. Try English tags or search --preset; no unrelated fallback was downloaded.');
        process.exit(1);
      }

      const picked = safe[0];
      const file = getBestFile(picked);

      if (!file) {
        console.error('✗ No downloadable file found.');
        process.exit(1);
      }

      console.log(`Downloading "${picked.upload_name}" by ${picked.user_real_name || picked.user_name}...`);

      const result = await downloadTrack(
        {
          download_url: file.download_url,
          file_page_url: picked.file_page_url,
          file_name: file.file_name,
        },
        opts.output,
        { force: opts.force }
      );

      const entry = buildManifestEntry(picked, file);
      await updateManifest(opts.output, entry);
      await generateAttribution(opts.output);

      if (result.skipped) {
        console.log(`ℹ Already downloaded: ${result.filePath}`);
      } else {
        console.log(
          `✓ Downloaded "${picked.upload_name}" → ${result.filePath} (${formatSize(result.size)})`
        );
      }

      console.log();
      console.log(formatTrack(picked, 0));
      console.log(`\nRemotion usage:`);
      console.log(`  <Audio src={staticFile('${file.file_name}')} volume={0.3} loop />`);
      console.log(`\nAttribution:`);
      console.log(
        `  "${picked.upload_name}" by ${picked.user_real_name || picked.user_name} — ${picked.license_name}`
      );
    } catch (err) {
      console.error(`✗ Pick failed: ${err.message}`);
      process.exit(1);
    }
  });

// ── presets ───────────────────────────────────────────────────────────────────

program
  .command('presets')
  .description('List predefined tag presets for common video scenarios')
  .action(() => {
    console.log('\nAvailable BGM Presets:\n');

    for (const [key, preset] of Object.entries(PRESETS)) {
      console.log(`  ${key.padEnd(10)} ${preset.name}`);
      console.log(`  ${' '.repeat(10)} ${preset.description}`);
      console.log(`  ${' '.repeat(10)} Tags: ${preset.tags}`);
      console.log();
    }

    console.log(`Use: bgm-library search --preset <name> to search with a preset.`);
  });

// ── info ─────────────────────────────────────────────────────────────────────

program
  .command('info <uploadId>')
  .description('Show detailed info about a track')
  .action(async (uploadId) => {
    try {
      console.log(`Fetching track ${uploadId}...`);
      const tracks = await queryApi({ ids: uploadId });

      if (tracks.length === 0) {
        console.error(`✗ Track not found: ${uploadId}`);
        process.exit(1);
      }

      const track = tracks[0];

      console.log();
      console.log(track.upload_name);
      console.log('─'.repeat(40));
      console.log(`Artist:       ${track.user_real_name || track.user_name}`);
      console.log(`Upload ID:    ${track.upload_id}`);
      console.log(`License:      ${track.license_name}`);
      console.log(`License URL:  ${track.license_url}`);
      console.log(`Page:         ${track.file_page_url}`);
      console.log(`Artist Page:  ${track.artist_page_url}`);
      console.log(`BPM:          ${track.upload_extra?.bpm || 'N/A'}`);
      console.log(`Date:         ${track.upload_date_format}`);

      const safe = isCommercialSafe(track.license_name);
      console.log(`Commercial:   ${safe ? 'YES (safe)' : 'NO (restricted)'}`);

      if (track.upload_extra?.usertags) {
        console.log(`Tags:         ${track.upload_extra.usertags.replace(/,/g, ', ')}`);
      }

      console.log();
      console.log('Files:');
      for (const f of track.files || []) {
        const dur = f.file_format_info?.ps || '?';
        const size = f.file_filesize || '?';
        console.log(`  ${f.file_nicname || 'mp3'} — ${dur} ${size} — ${f.file_name}`);
      }
    } catch (err) {
      console.error(`✗ Info failed: ${err.message}`);
      process.exit(1);
    }
  });

program.parse();
