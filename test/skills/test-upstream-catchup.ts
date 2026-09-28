import test from 'node:test'
import assert from 'node:assert/strict'
import { collectComments } from '../../crews/main/skills/expert-douyin/tools/douyin-comments/scripts/fetch_comments.ts'
const item=(cid:string)=>({cid,text:cid})
const page=(comments:unknown[],cursor=0,has_more=0,total=0)=>({ok:true,status:200,data:{status_code:0,comments,cursor,has_more,total}}) as any

test('Douyin HTTP 200 empty body and status 8 are not expired login and do not retry',async()=>{
  for (const response of [{ok:true,status:200,data:null}, {ok:true,status:200,data:{status_code:8}}]) {
    let calls=0
    const result=await collectComments('123',40,async()=>{calls++;return response})
    assert.equal(result.ok,false)
    assert.match(result.error!,/^COMMENT_API_UNAVAILABLE/)
    assert.equal(calls,1)
  }
})
test('Douyin deduplicates, retains partial comments and stops stalled cursor',async()=>{
  let calls=0; const waits:number[]=[]
  const result=await collectComments('123',40,async()=>++calls===1
    ?page([item('a')],20,1,100):page([item('a')],20,1,100),async ms=>{waits.push(ms)})
  assert.equal(result.ok,false)
  assert.equal(result.fetched,1)
  assert.match(result.error!,/PAGINATION_STALLED/)
  assert.equal(calls,2)
  assert.equal(waits.length,1)
  assert.ok(waits[0]>=1000 && waits[0]<3000)
})
test('Douyin true empty is valid, positive-total empty is not',async()=>{
  assert.equal((await collectComments('123',40,async()=>page([]))).ok,true)
  assert.equal((await collectComments('123',40,async()=>page([],0,0,10))).ok,false)
  assert.equal((await collectComments('123',40,async()=>({ok:true,status:200,data:{status_code:0,comments:[]}}))).ok,false)
})
test('Douyin keeps final page, marks limit truncation and preserves request failure',async()=>{
  assert.equal((await collectComments('123',40,async()=>page([item('a')],0,0,1))).fetched,1)
  assert.equal((await collectComments('123',1,async()=>page([item('a')],20,1,10))).truncated,true)
  assert.match((await collectComments('123',40,async()=>{throw new Error('network')})).error!,/COMMENT_REQUEST_FAILED: network/)
})
