#!/usr/bin/env node
// Adopt configured accounts for legacy jobs through native RPC, never raw state writes.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {isDeepStrictEqual} from 'node:util';
import {setTimeout as delay} from 'node:timers/promises';
import {inspectLegacyAccounts,resolveJobModel} from './lib/automation-inference-check.mjs';
export {inspectLegacyAccounts} from './lib/automation-inference-check.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const missingAccount = 'Automation has no recorded inference account.';

export function planRepairs(jobs, config, profile, legacyIds) {
  const account = config.auth?.profiles?.[profile];
  if (!account?.provider) throw new Error('Select an existing configured inference profile with --profile.');
  return jobs.filter(job => job.enabled && !job.declarationKey && job.payload?.kind === 'agentTurn' &&
    (legacyIds ? legacyIds.includes(job.id) : (job.state?.lastError ?? job.lastRunError ?? '').startsWith(missingAccount))).map(job => {
    const {model,provider,profileHint}=resolveJobModel(config,job);
    if (!model || provider !== account.provider || (profileHint && profileHint!==profile && `${provider}:${profileHint}`!==profile))
      throw new Error(`Job ${job.id}: model/profile route requires explicit review; no jobs were changed.`);
    if (!job.configRevision) throw new Error(`Job ${job.id}: native config revision is required.`);
    return {id:job.id, name:job.name, profile, revision:job.configRevision, originalModel:job.payload.model ?? null,
      model, selectedModel:`${model}@${profile}`, before:job};
  });
}

export function planAutomaticRepairs(jobs, config, legacy) {
  const plans=[],errors=[];
  for(const candidate of legacy) {
    const job=jobs.find(j=>j.id===candidate.id);
    if(!job){errors.push(`${candidate.id}: not found in the serving Gateway`);continue;}
    if(!job.enabled || job.declarationKey || job.payload?.kind!=='agentTurn')continue;
    const {provider,profileHint}=resolveJobModel(config,job);
    const profiles=Object.entries(config.auth?.profiles??{}).filter(([,p])=>p?.provider===provider).map(([id])=>id);
    const hinted=profileHint?profiles.find(id=>id===profileHint||id===`${provider}:${profileHint}`):undefined;
    const ordered=(config.auth?.order?.[provider]??[]).find(id=>profiles.includes(id));
    const profile=profileHint?hinted:(ordered??(profiles.length===1?profiles[0]:undefined));
    if(!profile){errors.push(`${job.name??job.id} (${job.id}): choose a ${provider??'matching'} account with --profile and --job, or configure auth.order`);continue;}
    try{plans.push(...planRepairs([job],config,profile,[job.id]));}catch(error){errors.push(error.message);}
  }
  if(errors.length)throw new Error(`Automation account migration needs a selection; no jobs were changed:\n${errors.join('\n')}`);
  return plans;
}

export async function readInventory(rpc, {waitMs=0,now=Date.now,sleep=delay,notify=()=>{}}={}) {
  const deadline=now()+waitMs;
  let first;
  for(;;) {
    try { first=await rpc('cron.list',{includeDisabled:true,offset:0,limit:100});break; }
    catch(error) {
      if(now()>=deadline || /unauthorized|forbidden|missing scope|invalid.*token/i.test(error.message))throw error;
      notify('Waiting for Gateway before automation account migration...');
      await sleep(Math.min(2000,Math.max(1,deadline-now())));
    }
  }
  const jobs=[...first.jobs];
  let page=first,offset=0;
  while(page.hasMore) {
    if(!Number.isInteger(page.nextOffset)||page.nextOffset<=offset)throw new Error('Invalid native pagination; no jobs were changed.');
    offset=page.nextOffset;
    page=await rpc('cron.list',{includeDisabled:true,offset,limit:100});
    jobs.push(...page.jobs);
  }
  return jobs;
}

function protectedDefinition(job) {
  return {agentId:job.agentId, enabled:job.enabled, schedule:job.schedule,
    sessionTarget:job.sessionTarget, wakeMode:job.wakeMode, delivery:job.delivery,
    payload:job.payload, failureAlert:job.failureAlert, deleteAfterRun:job.deleteAfterRun};
}

export async function applyRepair(plan, rpc) {
  const before = await rpc('cron.get', {id:plan.id});
  if (before.configRevision !== plan.revision) throw new Error(`Job ${plan.id} changed; rerun preview.`);
  let after = await rpc('cron.update', {id:plan.id, expectedConfigRevision:plan.revision,
    patch:{payload:{kind:'agentTurn', model:plan.selectedModel}}});
  // Account ownership survives model clearing; retain the user's model inheritance.
  const restoredModel = plan.originalModel;
  if (!after.configRevision) throw new Error(`Job ${plan.id}: update acknowledged without revision; inspect before retrying.`);
  after = await rpc('cron.update', {id:plan.id, expectedConfigRevision:after.configRevision,
    patch:{payload:{kind:'agentTurn', model:restoredModel}}});
  const verified = await rpc('cron.get', {id:plan.id});
  if (!isDeepStrictEqual(protectedDefinition(before), protectedDefinition(verified)))
    throw new Error(`Job ${plan.id}: account adopted but definition verification failed; inspect the saved snapshot.`);
  return {id:plan.id, name:plan.name, adopted:true, definitionPreserved:true, configRevision:verified.configRevision};
}

async function main(args) {
  let profile, apply=false, useCurrentAccount=false, automatic=false;
  const jobIds=[];
  let configFile=process.env.OPENCLAW_CONFIG_PATH ?? path.join(process.env.OPENCLAW_STATE_DIR ?? path.join(os.homedir(),'.openclaw'),'openclaw.json');
  for(let i=0;i<args.length;i++) {
    if(args[i]==='--profile' && args[i+1]) profile=args[++i];
    else if(args[i]==='--config' && args[i+1]) configFile=args[++i];
    else if(args[i]==='--apply') apply=true;
    else if(args[i]==='--use-current-account') useCurrentAccount=true;
    else if(args[i]==='--auto') automatic=true;
    else if(args[i]==='--job' && args[i+1]) jobIds.push(args[++i]);
    else throw new Error('Usage: repair-automation-inference.mjs --auto|--profile PROFILE|--use-current-account [--job ID] [--config FILE] [--apply]');
  }
  const config=JSON.parse(fs.readFileSync(configFile,'utf8'));
  if(automatic && (profile || useCurrentAccount))throw new Error('Use --auto or an explicit account selection.');
  if(automatic && !Object.values(config.auth?.profiles??{}).some(p=>p?.provider)){
    console.log(JSON.stringify({mode:'auto',skipped:true,reason:'no-stored-accounts',repaired:0}));return;
  }
  if(config.gateway?.mode==='remote')throw new Error('Run this local repair on the serving Gateway host.');
  if(useCurrentAccount) {
    if(profile)throw new Error('Choose --profile or --use-current-account.');
    const profiles=Object.keys(config.auth?.profiles??{});
    if(profiles.length!==1)throw new Error('Current account is ambiguous; select it explicitly with --profile. No jobs were changed.');
    profile=profiles[0];
  }
  if(!automatic && !profile) throw new Error('Choose the account explicitly with --profile or --use-current-account; preview is the default.');
  const build=JSON.parse(fs.readFileSync(path.join(root,'openclaw/dist/build-info.json'),'utf8'));
  const pin=fs.readFileSync(path.join(root,'openclaw.version'),'utf8');
  if(build.version!==pin.match(/^OPENCLAW_VERSION=(.+)$/m)?.[1] || build.commit!==pin.match(/^OPENCLAW_COMMIT=(.+)$/m)?.[1])
    throw new Error('Build and version pin differ; no account adoption was attempted.');
  const env={...process.env, OPENCLAW_CONFIG_PATH:path.resolve(configFile),OPENCLAW_STATE_DIR:process.env.OPENCLAW_STATE_DIR??path.dirname(path.resolve(configFile))};
  const rpc=(method,params)=>{
    const result=spawnSync(process.execPath,[path.join(root,'openclaw/dist/index.js'),'gateway','call',method,'--params',JSON.stringify(params),'--json'],
      {env,encoding:'utf8',timeout:method==='cron.list'?15000:45000,maxBuffer:16*1024*1024});
    if(result.error) throw result.error;
    if(result.status!==0) throw new Error(`Native ${method} failed; stop and inspect before retrying. ${result.stderr.slice(-1000)}`);
    return JSON.parse(result.stdout);
  };
  const jobs=await readInventory(rpc,{waitMs:automatic?60000:0,notify:message=>console.error(message)});
  // Gateway may import legacy Cron state during startup; inspect only after its
  // native inventory is ready, including installations that had no SQL rows yet.
  const legacy=inspectLegacyAccounts(config,configFile).filter(j=>!jobIds.length||jobIds.includes(j.id));
  const scopedJobs=jobIds.length?jobs.filter(j=>jobIds.includes(j.id)):jobs;
  const plans=automatic?planAutomaticRepairs(scopedJobs,config,legacy):planRepairs(scopedJobs,config,profile,legacy.map(p=>p.id));
  console.log(JSON.stringify({mode:apply?'apply':'preview',automatic,profile,jobs:plans.map(({before,...p})=>p)},null,2));
  if(!apply || !plans.length)return;
  const directory=path.join(env.OPENCLAW_STATE_DIR,'backups','automation-inference',new Date().toISOString().replaceAll(':','-'));
  fs.mkdirSync(directory,{recursive:true,mode:0o700});
  fs.writeFileSync(path.join(directory,'before.json'),JSON.stringify(plans.map(p=>p.before),null,2)+'\n',{mode:0o600});
  const receipts=[];
  for(const plan of plans) {
    receipts.push(await applyRepair(plan,rpc));
    fs.writeFileSync(path.join(directory,'receipts.json'),JSON.stringify(receipts,null,2)+'\n',{mode:0o600});
  }
  console.log(JSON.stringify({repaired:receipts.length,snapshot:directory,manualRunsRequested:false}));
}

if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(error=>{console.error(error.message);process.exitCode=1;});
}
