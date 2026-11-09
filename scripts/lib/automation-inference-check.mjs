// Read-only metadata inspection shared by upgrade-time and manual native migration.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);

export function resolveJobModel(config, job) {
  const agent=job.agentId ?? job.effectiveAgentId ?? 'main';
  const primary=value=>typeof value==='string'?value:value?.primary;
  const reference=job.payload?.model ?? primary(config.agents?.entries?.[agent]?.model) ?? primary(config.agents?.defaults?.model);
  if(typeof reference!=='string')return {agent};
  let model=reference.trim(),profileHint;
  let delimiter=model.indexOf('@',model.lastIndexOf('/')+1);
  if(delimiter>0) {
    for(const suffix of [/^\d{8}(?:@|$)/,/^(?:i?q\d+(?:_[a-z0-9]+)*|\d+bit)(?:@|$)/i]) {
      if(suffix.test(model.slice(delimiter+1)))delimiter=model.indexOf('@',delimiter+1);
      if(delimiter<0)break;
    }
    if(delimiter>0){profileHint=model.slice(delimiter+1).trim();model=model.slice(0,delimiter).trim();}
  }
  if(!model.includes('/')) {
    const aliases=Object.entries(config.agents?.defaults?.models??{}).filter(([,entry])=>entry?.alias===model);
    if(aliases.length===1)model=aliases[0][0];
  }
  return {agent,reference,model,profileHint,provider:model.includes('/')?model.split('/')[0]:null};
}

export function inspectLegacyAccounts(config, configFile) {
  const profiles=Object.values(config.auth?.profiles??{}).filter(p=>p?.provider);
  // Direct provider/API-key installations need no stored-account migration.
  if(!profiles.length) return [];
  const database=path.join(process.env.OPENCLAW_STATE_DIR ?? path.dirname(path.resolve(configFile)), 'state/openclaw.sqlite');
  if(!fs.existsSync(database)) return [];
  const {DatabaseSync}=require('node:sqlite');
  const db=new DatabaseSync(database,{readOnly:true});
  try {
    if(!db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cron_jobs'").get()) return [];
    return db.prepare('SELECT job_id,job_json FROM cron_jobs').all().flatMap(row=>{
      const job=JSON.parse(row.job_json);
      if(!job.enabled || job.declarationKey || job.payload?.kind!=='agentTurn' || job.sessionTarget==='main' || job.inferenceBinding || job.runtimeAuthority) return [];
      const {agent,model,provider,profileHint}=resolveJobModel(config,job);
      if(!provider || !profiles.some(p=>p.provider===provider)) return [];
      // An explicitly configured provider key owns this route unless the model
      // explicitly selects a stored profile; do not change existing billing paths.
      const directKey=config.models?.providers?.[provider]?.apiKey;
      if(!profileHint && ((typeof directKey==='string'&&directKey.trim()) || (directKey&&typeof directKey==='object'))) return [];
      return [{id:row.job_id,name:job.name,agent,model,provider,...(profileHint?{profileHint}:{})}];
    });
  }finally{db.close();}
}
