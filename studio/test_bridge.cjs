const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup({local=false,stored='',storageFails=false}={}){
 const listeners={}, calls=[], events=[], popup={};let value=stored;
 const context=vm.createContext({location:{hostname:local?'127.0.0.1':'after-studio.vercel.app',origin:local?'http://127.0.0.1:7861':'https://after-studio.vercel.app'},Headers,AbortSignal,URL,Response,Blob,console,
 localStorage:{getItem(){if(storageFails)throw Error('blocked');return value;},setItem(k,v){if(storageFails)throw Error('blocked');value=v;},removeItem(){value='';}},
 Event:class {constructor(type){this.type=type;}},CustomEvent:class{constructor(type,options){this.type=type;Object.assign(this,options);}},
 window:{open:()=>popup,addEventListener:(name,fn)=>listeners[name]=fn,dispatchEvent:e=>events.push(e.type)},
 fetch:async(url,options)=>{calls.push({url,options});return new Response('image',{status:200});}});
 vm.runInContext(fs.readFileSync(__dirname+'/web/assets/bridge.js','utf8'),context);
 return {bridge:vm.runInContext('Bridge',context),context,listeners,calls,events,popup};
}
test('cloud cannot request the Mac before pairing',async()=>{
 const {bridge,calls}=setup();await assert.rejects(bridge.fetch('/api/jobs'),/Connecte/);assert.equal(calls.length,0);
});
test('pair message requires both exact origin and original popup',()=>{
 const s=setup();s.bridge.connect();
 for(const [origin,source] of [['https://evil.example',s.popup],['http://127.0.0.1:7861',{}]])s.listeners.message({origin,source,data:{type:'after-paired',token:'secret'}});
 assert.equal(s.bridge.paired,false);
 s.listeners.message({origin:'http://127.0.0.1:7861',source:s.popup,data:{type:'after-paired',token:'secret'}});
 assert.equal(s.bridge.paired,true);assert.deepEqual(s.events,['bridge-connected']);
});
test('token is sent only in an authorization header to fixed loopback',async()=>{
 const s=setup({stored:'secret'});await s.bridge.fetch('/api/jobs');
 assert.equal(s.calls[0].url,'http://127.0.0.1:7861/api/jobs');
 assert.equal(s.calls[0].options.headers.get('Authorization'),'Bearer secret');
 assert.equal(s.calls[0].options.credentials,'omit');
 await assert.rejects(s.bridge.fetch('https://evil.example'),/invalide/);
});
test('401 discards stale pairing and local mode never sends a token',async()=>{
 const s=setup({stored:'secret'});s.context.fetch=async()=>new Response('',{status:401});await s.bridge.fetch('/api/jobs');assert.equal(s.bridge.paired,false);
 const l=setup({local:true,stored:'secret'});await l.bridge.fetch('/api/config');assert.equal(l.calls[0].options.headers.has('Authorization'),false);
});
test('private browsing storage failures retain session-only pairing',()=>{
 const s=setup({storageFails:true});s.bridge.setToken('secret');assert.equal(s.bridge.paired,true);
});
test('authenticated media uses a cached blob URL',async()=>{
 const s=setup({stored:'secret'});const a=await s.bridge.media('/media/a.jpg');const b=await s.bridge.media('/media/a.jpg');assert.equal(a,b);assert.ok(a.startsWith('blob:'));assert.equal(s.calls.length,1);
});
