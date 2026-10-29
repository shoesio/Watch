const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture({deny=false,rejectId=false,ticker='0',auto='0'}={}){
 const state={0:ticker,3:auto},writes=[],events=[];
 const plugin={GetProfile(id){return state[id]},SetProfile(id,v){writes.push([id,v]);if(deny)return 0;if(rejectId&&id===0&&v==='SamsungWatch')return 0;state[id]=v;return 1;}};
 const node=()=>({style:{},appendChild(){},innerHTML:''});
 const doc={getElementById(id){return id==='watchStartupTVMW'?plugin:{GetModelCode(){return '12_X10PLUS_MFM'}}},createElement:node,createTextNode(v){return v},body:node()};
 const window={Watch:{key(){return 'original'}},WatchBootProbe:{},curWidget:{id:'SamsungWatch'},addEventListener(){},Common:{API:{TVKeyValue:function(){this.KEY_RED=108;this.KEY_GREEN=20}}}};
 const Image=function() {Object.defineProperty(this,'src',{set(v){events.push(v)}})};
 vm.runInNewContext(fs.readFileSync(__dirname+'/trial.js','utf8'),{window,document:doc,Image});window.WatchBootTrial.init();
 return {window,state,writes,events};
}
let f=fixture();assert.equal(f.writes.length,0,'Loading must never write');f.window.Watch.key({keyCode:108,preventDefault(){}});assert.equal(f.state[0],'SamsungWatch');assert.equal(f.state[3],'1');assert.ok(f.events.some(v=>v.includes('event=enabled')));
f.window.Watch.key({keyCode:20,preventDefault(){}});assert.equal(f.state[0],'0');assert.equal(f.state[3],'0');assert.deepEqual(f.writes.slice(-2),[[3,'0'],[0,'0']]);
f=fixture({rejectId:true});f.window.WatchBootTrial.enable();assert.equal(f.state[0],'0');assert.equal(f.state[3],'0');assert.ok(!f.writes.some(([id,v])=>id===3&&v==='1'));
f=fixture({deny:true});f.window.WatchBootTrial.enable();assert.equal(f.state[0],'0');assert.equal(f.state[3],'0');
f=fixture({ticker:'AnotherApp'});f.window.WatchBootTrial.enable();assert.equal(f.writes.length,0);f.window.WatchBootTrial.restore();assert.equal(f.writes.length,0);
assert.equal(f.window.Watch.key({keyCode:13}),'original');console.log('PASS: no writes on opening, explicit colour keys only, two-field readback, rejected-ID rollback, disabled-first restore, unrelated app preserved.');
