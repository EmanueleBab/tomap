const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const listeners={},shown=[];
let watches=[];
const context={
  importScripts(){},watchDB:{get:async()=>watches},Date,URL,
  self:{addEventListener:(name,fn)=>listeners[name]=fn,registration:{showNotification:async(title,options)=>shown.push({title,options})}}
};
vm.runInNewContext(fs.readFileSync('static/sw.js','utf8'),context);
const now=Date.now()/1000;
const payload={title:'Line 4',body:'Stop',stop:{id:'s'},revision:'r1',arrival:now+120,sent_at:now,tag:'arrival'};
async function push(value){let pending;listeners.push({data:{json:()=>value},waitUntil:p=>pending=p});await pending;}
(async()=>{
  watches=[{stop:{id:'s'},enabled:true,revision:'r1'}];await push(payload);assert.equal(shown.length,1);
  watches=[];await push(payload);assert.equal(shown.length,1,'removed watches suppress queued pushes');
  watches=[{stop:{id:'s'},enabled:false,revision:'r1'}];await push(payload);assert.equal(shown.length,1);
  watches=[{stop:{id:'s'},enabled:true,revision:'r2'}];await push(payload);assert.equal(shown.length,1,'changed settings suppress old pushes');
  watches=[{stop:{id:'s'},enabled:true,revision:'r1'}];
  await push({...payload,arrival:now-1});await push({...payload,sent_at:now-100});assert.equal(shown.length,1,'late pushes must not alert');
  console.log('Service worker: active delivery and five suppression cases passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
