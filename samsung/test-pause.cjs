const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.join(__dirname,'widget');
const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{runScripts:'outside-only',url:'http://fixture.local/'});
const w=dom.window;
const realTimeout=w.setTimeout.bind(w);
w.setTimeout=(fn,ms,...args)=>realTimeout(fn,[500,1500,2000,5000,10000].includes(ms)?1:ms,...args);
let failing=false,holding=false,prepares=[],native=[];
w.WATCH_CONNECTION={base:'http://pi',key:'fixture'};
w.Common={API:{Widget:function(){this.sendReadyEvent=()=>{};this.blockNavigation=()=>{};},TVKeyValue:function(){}}};
w.XMLHttpRequest=function(){
 this.open=(method,url)=>{this.method=method;this.url=url};this.setRequestHeader=()=>{};this.abort=()=>{};
 this.send=body=>{
  let data={ok:true};
  if(this.url.includes('/api/library'))data={items:[{id:'show',title:'Show',brands:[]}],total:1,page:0};
  else if(this.url.includes('/api/seasons/'))data={items:[{id:'all',title:'All episodes'}],total:1,page:0};
  else if(this.url.includes('/api/episodes/'))data={items:[{id:'ep',title:'Episode'}],total:1,page:0};
  else if(this.method==='POST'&&this.url.endsWith('/api/prepare')){prepares.push(JSON.parse(body));data={job:'job'}}
  else if(this.url.endsWith('/api/prepare/job'))data=holding?{state:'preparing'}:failing?{state:'failed',error:'Fixture outage'}:{state:'ready',ticket:'ticket',episode_id:'ep',title:'Episode',show_title:'Show',description:'Synopsis',art:'poster',brands:[],start_position:prepares.at(-1).start_position||0,duration_seconds:1000,url:'http://pi/media/fixture/stream.ts'};
  this.status=200;this.readyState=4;this.responseText=JSON.stringify(data);realTimeout(()=>this.onreadystatechange(),0);
 }
};
const player=w.document.getElementById('player');
for(const fn of ['Play','Pause','Stop','Resume','SetDisplayArea'])player[fn]=(...args)=>{native.push([fn,...args]);return 1};
const stylesheet=w.document.createElement('style');stylesheet.textContent=fs.readFileSync(path.join(root,'watch.css'),'utf8');w.document.head.appendChild(stylesheet);
w.eval(fs.readFileSync(path.join(root,'watch.js'),'utf8'));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const press=keyCode=>w.Watch.key({keyCode,preventDefault(){}});
(async()=>{
 w.Watch.init();await wait(20);press(13);await wait(20);press(13);await wait(30);
 w.Watch.buffered();w.Watch.tick(1000);w.Watch.tick(121000);
 assert.match(w.document.getElementById('timeLabel').textContent,/2:01/);
 const count=prepares.length;
 // Simulate a long pause with clock drift, buffer and terminal callbacks.
 press(19);press(19);
 assert.equal(w.document.getElementById('control1').textContent,'Play');
 w.Watch.tick(421000);w.Watch.buffering();w.Watch.buffered();w.Watch.failed();w.Watch.ended();
 await wait(20);
 assert.equal(prepares.length,count);
 assert.match(w.document.getElementById('timeLabel').textContent,/2:01/);
 assert.equal(w.document.getElementById('bufferSpinner').style.display,'none');
 holding=true;press(415);await wait(20);
 assert.equal(prepares.length,count+1);
 assert.equal(prepares.at(-1).start_position,121);
 assert.equal(native.filter(c=>c[0]==='Resume').length,0);
 assert.equal(w.document.getElementById('shell').style.display,'none');
 assert.equal(w.document.getElementById('bufferSpinner').style.display,'block');
 w.Watch.ended();holding=false;await wait(30);
 w.Watch.tick(700000);w.Watch.tick(701000);w.Watch.buffered();
 assert.match(w.document.getElementById('timeLabel').textContent,/2:02/);
 assert.equal(w.document.getElementById('bufferSpinner').style.display,'none');
 // The on-screen toggle must use the same exact-position resume path.
 press(13);assert.equal(w.document.getElementById('control1').textContent,'Play');
 w.Watch.tick(900000);press(13);await wait(30);
 assert.equal(prepares.at(-1).start_position,122);
 assert.equal(native.filter(c=>c[0]==='Resume').length,0);
 w.Watch.shutdown();dom.window.close();console.log('PASS: paused position stays fixed through drift and late callbacks; remote and screen resume reopen VOD at the exact pause position without leaving player.');
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1});
