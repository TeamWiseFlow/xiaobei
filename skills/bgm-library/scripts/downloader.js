/**
 * BGM Library - Download & Attribution Module
 * Handles MP3 download from ccMixter with referer, manifest, and attribution generation.
 */

import axios from 'axios';
import https from 'https';
import fs from 'fs/promises';
import path from 'path';

// ccMixter SSL certificate chain is incomplete — tolerate it.
const httpsAgent = new https.Agent({ rejectUnauthorized: false });

const MANIFEST_FILE = 'music_manifest.json';
const ATTRIBUTION_FILE = 'ATTRIBUTION.txt';

/**
 * Download an MP3 file from ccMixter with proper referer header.
 * @param {Object} track - Track metadata from ccMixter API
 * @param {string} track.download_url - Direct MP3 download URL
 * @param {string} track.file_page_url - Page URL (used as referer)
 * @param {string} track.file_name - Original filename
 * @param {string} outputDir - Target directory
 * @param {Object} options - { force: boolean }
 * @returns {Object} { filePath, fileName, size }
 */
export async function downloadTrack(track, outputDir, options = {}) {
  await fs.mkdir(outputDir, { recursive: true });

  // Sanitize filename
  const fileName = track.file_name.replace(/[^a-zA-Z0-9_\-\.]/g, '_');
  const filePath = path.join(outputDir, fileName);

  // Check if already exists
  if (!options.force) {
    try {
      await fs.access(filePath);
      return { filePath, fileName, size: 0, skipped: true };
    } catch {
      // File doesn't exist, proceed
    }
  }

  const response = await axios({
    method: 'get',
    url: track.download_url,
    responseType: 'arraybuffer',
    httpsAgent,
    headers: {
      'Referer': track.file_page_url,
      'User-Agent': 'bgm-library/1.0 (CodeBuddy Remotion Plugin)',
    },
    timeout: 60000,
  });

  if (response.status !== 200) {
    throw new Error(`Download failed: HTTP ${response.status}`);
  }

  await fs.writeFile(filePath, Buffer.from(response.data));

  return {
    filePath,
    fileName,
    size: response.data.byteLength,
    skipped: false,
  };
}

/**
 * Update music_manifest.json in the output directory.
 * @param {string} outputDir - Directory containing the manifest
 * @param {Object} entry - Manifest entry to add
 */
export async function updateManifest(outputDir, entry) {
  const manifestPath = path.join(outputDir, MANIFEST_FILE);
  let manifest = { tracks: [] };

  try {
    const data = await fs.readFile(manifestPath, 'utf-8');
    manifest = JSON.parse(data);
  } catch {
    // New manifest
  }

  // Remove existing entry for same upload_id (re-download)
  manifest.tracks = manifest.tracks.filter(
    (t) => t.upload_id !== entry.upload_id
  );

  manifest.tracks.push({
    upload_id: entry.upload_id,
    title: entry.title,
    artist: entry.artist,
    source_url: entry.source_url,
    artist_url: entry.artist_url,
    license_name: entry.license_name,
    license_url: entry.license_url,
    file_name: entry.file_name,
    bpm: entry.bpm || null,
    duration: entry.duration || null,
    downloaded_at: new Date().toISOString(),
  });

  await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
}

/**
 * Generate ATTRIBUTION.txt from manifest in TASL format.
 * (Title / Author / Source / License)
 * @param {string} outputDir - Directory containing manifest
 */
export async function generateAttribution(outputDir) {
  const manifestPath = path.join(outputDir, MANIFEST_FILE);
  const attrPath = path.join(outputDir, ATTRIBUTION_FILE);

  let manifest;
  try {
    const data = await fs.readFile(manifestPath, 'utf-8');
    manifest = JSON.parse(data);
  } catch {
    return null;
  }

  if (!manifest.tracks || manifest.tracks.length === 0) {
    return null;
  }

  const lines = [
    '=== Music Attribution ===',
    `Generated: ${new Date().toISOString()}`,
    `Source: ccMixter (https://ccmixter.org)`,
    '',
  ];

  for (const track of manifest.tracks) {
    lines.push(`"${track.title}" by ${track.artist}`);
    lines.push(`  Source: ${track.source_url}`);
    lines.push(`  License: ${track.license_name} (${track.license_url})`);
    lines.push('');
  }

  lines.push('---');
  lines.push('All tracks sourced from ccMixter under Creative Commons licenses.');

  const content = lines.join('\n') + '\n';
  await fs.writeFile(attrPath, content);
  return content;
}

/**
 * Build a manifest entry from ccMixter API track data.
 * @param {Object} apiTrack - Raw track from ccMixter API response
 * @param {Object} fileInfo - The specific file object from apiTrack.files[]
 * @returns {Object} Manifest entry
 */
export function buildManifestEntry(apiTrack, fileInfo) {
  return {
    upload_id: apiTrack.upload_id,
    title: apiTrack.upload_name,
    artist: apiTrack.user_real_name || apiTrack.user_name,
    source_url: apiTrack.file_page_url,
    artist_url: apiTrack.artist_page_url,
    license_name: apiTrack.license_name,
    license_url: apiTrack.license_url,
    file_name: fileInfo.file_name,
    bpm: apiTrack.upload_extra?.bpm || null,
    duration: fileInfo.file_format_info?.ps || null,
  };
}
