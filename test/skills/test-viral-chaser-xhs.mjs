import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'

import { getXhsVideoViaHunter, XhsHunterFailure } from '../../crews/main/skills/viral-chaser/scripts/platforms/xhs-hunter.ts'

function fakeHunter(root, body) {
  const bin = join(root, 'bin')
  mkdirSync(bin)
  const command = join(bin, 'xhs-hunter')
  writeFileSync(command, `#!/usr/bin/env node\n${body}\n`, { mode: 0o755 })
  return bin
}

test('XHS video metadata and local file come from xhs-hunter', async () => {
  const root = mkdtempSync(join(tmpdir(), 'viral-xhs-'))
  const oldPath = process.env.PATH
  try {
    const bin = fakeHunter(root, `
const fs = require('node:fs')
const path = require('node:path')
const args = process.argv.slice(2)
if (args[0] !== 'fetch' || args[2] !== '--output-dir' || args[4] !== '--download-media') process.exit(9)
const file = path.join(args[3], 'video.mp4')
fs.mkdirSync(args[3], { recursive: true })
fs.writeFileSync(file, 'video bytes')
process.stdout.write(JSON.stringify({ok:true, note:{type:'video', note_id:'abc', title:'标题', content:'正文', author:{nickname:'作者', user_id:'u1'}, publish_time_ms:1700000000000, tags:['话题'], images:['https://example.test/cover'], metrics:{liked_count_num:12, comment_count_num:3, collected_count_num:4, share_count_num:5}}, media_paths:[file]}))
`)
    process.env.PATH = `${bin}:${oldPath}`
    const result = await getXhsVideoViaHunter(
      'https://www.xiaohongshu.com/explore/abc?xsec_token=token', 'abc', join(root, 'out'))
    assert.equal(result.localVideoPath, join(root, 'out', 'video.mp4'))
    assert.equal(result.stats.likeCount, 12)
    assert.equal(result.createTime, 1700000000)
    assert.equal(result.title, '标题')
  } finally {
    process.env.PATH = oldPath
    rmSync(root, { recursive: true, force: true })
  }
})

test('missing PC session is surfaced without another download path', async () => {
  const root = mkdtempSync(join(tmpdir(), 'viral-xhs-'))
  const oldPath = process.env.PATH
  try {
    const bin = fakeHunter(root, `process.stdout.write(JSON.stringify({ok:false,error:'SESSION_MISSING',message:'需要登录'})); process.exit(2)`)
    process.env.PATH = `${bin}:${oldPath}`
    await assert.rejects(
      getXhsVideoViaHunter('https://www.xiaohongshu.com/explore/abc', 'abc', join(root, 'out')),
      error => error instanceof XhsHunterFailure && error.code === 'SESSION_EXPIRED',
    )
  } finally {
    process.env.PATH = oldPath
    rmSync(root, { recursive: true, force: true })
  }
})
