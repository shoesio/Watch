const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function fixture({markers=true,wrongSource=false,conflict=false,final=false,metadataFailure=false,reduced=false,lateFeatures=false,unknownVersion=false,unavailable=false,credits=false}={}) {
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'widget/index.html'),'utf8'),{runScripts:'outside-only',url:'http://fixture/'}),w=dom.window;
 const native=[],calls=[],prepares=[];let q={revision:0,autoplay:false,current:null,items:[]},start=120,seq=0;
 const real=w.setTimeout.bind(w);w.setTimeout=(fn,ms)=>real(fn,[500,1500,2000].includes(ms)?1:ms===1000?25:ms);
 w.matchMedia=()=>({matches:reduced});w.WATCH_CONNECTION={base:'http://pi',key:'fixture'};
 w.Common={API:{Widget:function(){this.sendReadyEvent=()=>{};this.blockNavigation=()=>{};},TVKeyValue:function(){}}};
 const successor={id:'ep2',title:'Second episode',show_title:'Show',season:'2',episode_number:1,artwork:'poster',available:true};
 w.XMLHttpRequest=function(){
  this.open=(method,url)=>{this.method=method;this.url=url};this.setRequestHeader=()=>{};this.abort=()=>{};
  this.send=body=>{
   const data=body?JSON.parse(body):null;calls.push({method:this.method,path:this.url.replace('http://pi',''),data});let value={ok:true},status=200;
   const url=this.url;
   if(url.includes('/api/library'))value={items:[{id:'show',title:'Show'}],page:0,total:1};
   else if(url.includes('/api/seasons/'))value={items:[{id:'all',title:'All episodes'}],page:0,total:1};
   else if(url.includes('/api/episodes/'))value={items:[{id:'ep1',title:'First episode'}],page:0,total:1};
   else if(url.endsWith('/api/prepare')&&this.method==='POST'){prepares.push(data);start=data.start_position===undefined?120:data.start_position;seq++;value={job:'job'};}
   else if(url.endsWith('/api/prepare/job'))value={state:'ready',ticket:'ticket'+seq,episode_id:prepares.at(-1).episode_id,title:'First episode',show_title:'Show',start_position:start,duration_seconds:600,url:'http://pi/stream',metadata:{source_key:'source',version_id:unknownVersion?null:'exact123',provider:'BBC iPlayer'}};
   else if(url.endsWith('/capabilities'))value={schema_version:1,marker_timebase:'episode',series_queue:true};
   else if(url.includes('/playback/features?')){
    if(metadataFailure){status=503;value={error:'Unavailable'}}
    else value={episode_id:'ep1',source_key:wrongSource?'different':'source',version_id:unknownVersion?null:'exact123',timebase:'episode',status:'available',credits:credits?[{kind:'credits',title:'Credits',start:550,end:600}]:[],chapters:[{title:'Opening',start:30,end:100},{title:'Chapter two',start:200,end:590}],skip_markers:markers?[{kind:'intro',start:120,end:160},{kind:'recap',start:-1,end:90}]:[]};
   }
   else if(url.includes('/up-next?'))value={episode_id:'ep1',next_episode:final?null:{...successor,available:!unavailable}};
   else if(url.endsWith('/queue/advance')){
    assert.ok(calls.some(c=>c.method==='DELETE'&&c.data.completed===true),'completion saved before advance');
    if(conflict){status=409;value={error:'Conflict'};q={...q,revision:q.revision+1,current:null,items:[]};}
    else {q={...q,revision:q.revision+1,current:final?null:successor,items:[]};value=q;}
   }
   else if(url.endsWith('/queue')){
    if(this.method==='POST')q={revision:q.revision+1,autoplay:data.autoplay,current:{id:data.episode_id},items:final?[]:[successor]};value=q;
   }
   this.status=status;this.readyState=4;this.responseText=JSON.stringify(value);real(()=>this.onreadystatechange(),lateFeatures&&url.includes('/playback/features?')?200:0);
  };
 };
 for(const fn of ['Play','Pause','Stop','Resume','SetDisplayArea'])w.document.getElementById('player')[fn]=(...a)=>{native.push([fn,...a]);return 1};
 for(const file of ['playback-extras.js','watch.js'])w.eval(fs.readFileSync(path.join(__dirname,'widget',file),'utf8'));
 const press=keyCode=>w.Watch.key({keyCode,preventDefault(){}});
 w.Watch.init();await wait(20);press(13);await wait(20);press(13);await wait(80);
 w.Watch.tick(500000);w.Watch.tick(501000);w.Watch.buffered();
 return {w,dom,press,prepares,calls,native,close(){w.Watch.shutdown();dom.window.close();}};
}
(async()=>{
 let f=await fixture();let {w,press,prepares,calls,native}=f;
 assert.equal(prepares.length,1,'metadata must not pre-prepare');
 assert.match(w.document.getElementById('featureActions').textContent,/Skip intro/);
 assert.ok(calls.find(c=>c.path.includes('source_key=source')&&c.path.includes('version_id=exact123')&&c.path.includes('ticket=ticket1')));
 press(19);press(40);press(13);await wait(80);
 assert.equal(prepares.at(-1).start_position,160,'skip uses absolute marker end, not relay-relative time');
 w.Watch.buffered();assert.equal(w.document.getElementById('control1').textContent,'Play','skip keeps pause');
 press(415);await wait(80);w.Watch.tick(700000);w.Watch.tick(701000);w.Watch.buffered();
 assert.equal(prepares.at(-1).start_position,160,'unpause preserves skipped position');
 assert.doesNotMatch(w.document.getElementById('featureActions').textContent,/Skip intro/);
 press(40);press(13);assert.equal(w.document.getElementById('chapterMenu').style.display,'block');press(40);press(13);await wait(80);
 assert.equal(prepares.at(-1).start_position,200,'chapter uses episode-relative seek');
 w.Watch.tick(500000);w.Watch.tick(501000);w.Watch.buffered();
 press(40);press(39);press(13);await wait(20);
 assert.match(w.document.getElementById('featureActions').textContent,/Autoplay: On/);
 assert.doesNotMatch(w.document.getElementById('featureActions').textContent,/Play next|Up next/);
 const before=prepares.length;
 w.Watch.tick(890000);assert.equal(w.document.getElementById('upNextCard').style.display,'block');
 assert.match(w.document.getElementById('upNextPlay').textContent,/10/);
 assert.equal(w.document.getElementById('upNextHeading').textContent,'UP NEXT');
 assert.equal(w.document.getElementById('upNextCard').parentNode,w.document.body,'card independent of transport hiding');
 assert.equal(prepares.length,before,'no prepare at final ten second cue');
 press(8);w.Watch.tick(900000);w.Watch.ended();w.Watch.ended();await wait(50);
 assert.equal(calls.filter(c=>c.path.endsWith('/queue/advance')).length,1,'double completion advances once');
 assert.equal(prepares.length,before,'Back cancels autoplay but natural completion is saved');f.close();
 for(const opts of [{wrongSource:true},{metadataFailure:true},{unknownVersion:true}]){
  f=await fixture(opts);assert.doesNotMatch(f.w.document.getElementById('featureActions').textContent,/Skip intro|Chapters/);assert.equal(f.prepares.length,1);f.close();
 }
 // Verified credits may offer the card early; the cue cannot prepare video.
 f=await fixture({credits:true});f.w.Watch.tick(931000);assert.equal(f.w.document.getElementById('upNextCard').style.display,'block');assert.equal(f.prepares.length,1);assert.equal(f.w.document.getElementById('upNextPlay').textContent,'Next episode');f.close();
 f=await fixture({credits:true,wrongSource:true});f.w.Watch.tick(931000);assert.equal(f.w.document.getElementById('upNextCard').style.display,'none');assert.equal(f.prepares.length,1);f.close();
 // Automatic continuation only after completion and countdown, with saved progress.
 f=await fixture({markers:false});f.press(40);f.press(39);f.press(13);await wait(20);
 f.w.Watch.tick(970000);assert.equal(f.prepares.length,1);f.w.Watch.tick(980000);f.w.Watch.ended();await wait(350);
 assert.equal(f.prepares.at(-1).episode_id,'ep2');assert.equal(f.prepares.at(-1).start_position,0);f.close();
 for(const opts of [{final:true},{conflict:true},{reduced:true}]){
  f=await fixture(opts);
  if(!opts.final){f.press(40);f.press(39);f.press(39);f.press(13);await wait(20);}
  f.w.Watch.tick(970000);f.w.Watch.tick(980000);f.w.Watch.ended();await wait(350);
  assert.equal(f.prepares.length,1,'final/conflict/reduced-motion cannot automatically prepare');f.close();
 }
 f=await fixture();f.press(40);f.press(39);f.press(13);assert.equal(f.w.document.getElementById('chapterMenu').style.display,'block');f.press(413);assert.equal(f.w.document.getElementById('shell').style.display,'block');f.close();
 f=await fixture({unavailable:true});assert.doesNotMatch(f.w.document.getElementById('featureActions').textContent,/Play next/);f.close();
 // Out-of-date requests after leaving the player cannot add controls or start playback.
 f=await fixture({lateFeatures:true});f.press(8);f.w.Watch.tick(900000);f.w.Watch.ended();await wait(250);
 assert.equal(f.w.document.getElementById('featureActions').textContent,'');assert.equal(f.prepares.length,1);f.close();
 console.log('PASS: exact-source markers, absolute skip/chapter seeks, paused skip/resume, metadata absence, completion-before-advance, duplicate completion, full-art Up next, final-ten-second countdown, natural-only autoplay and cancellation, conflicts, final episodes and reduced motion.');
})().catch(e=>{console.error(e);process.exitCode=1});
