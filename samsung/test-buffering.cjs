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
 const oldPoster=w.document.getElementById('preloadPhoto'), lateLoad=oldPoster.onload;
 assert.equal(oldPoster.style.display,'none');assert.equal(oldPoster.hasAttribute('src'),false);
 w.Watch.buffered();
 const clearedPoster=w.document.getElementById('preloadPhoto');
 assert.notEqual(clearedPoster,oldPoster);assert.equal(oldPoster.isConnected,false);
 assert.equal(clearedPoster.style.display,'none');assert.equal(clearedPoster.hasAttribute('src'),false);
 if(lateLoad)lateLoad();assert.equal(clearedPoster.style.display,'none');
 w.Watch.tick(1000);w.Watch.tick(121000);
 assert.ok(w.document.getElementById('pauseShade'));
 assert.equal(w.getComputedStyle(w.document.getElementById('pauseInfo')).padding,'0px');
 assert.equal(w.getComputedStyle(w.document.getElementById('playbackHelp')).padding,'0px');
 assert.equal(w.getComputedStyle(w.document.getElementById('pauseInfo')).backgroundColor,'rgba(0, 0, 0, 0)');
 assert.equal(w.getComputedStyle(w.document.getElementById('playbackHelp')).backgroundColor,'rgba(0, 0, 0, 0)');
 const callsBeforeClean=native.length, positionBeforeClean=w.document.getElementById('timeLabel').textContent;
 press(457);assert.notEqual(w.document.documentElement.style.opacity,'0');assert.equal(native.length,callsBeforeClean);
 assert.equal(w.document.getElementById('timeLabel').textContent,positionBeforeClean);

 // Committing a scrub keeps the frozen player visible throughout delayed preparation.
 const pausesBefore=native.filter(c=>c[0]==='Pause').length;
 press(38);assert.equal(w.document.getElementById('playbackHelp').className,'timeline-focus');press(39);press(8);assert.equal(w.document.getElementById('playbackHelp').className,'');assert.equal(w.document.getElementById('control1').textContent,'Pause');assert.equal(native.filter(c=>c[0]==='Pause').length,pausesBefore);
 press(38);press(39);press(39);holding=true;press(13);
 assert.equal(w.document.getElementById('shell').style.display,'none');assert.equal(w.document.getElementById('bufferSpinner').style.display,'block');assert.equal(w.document.getElementById('control4'),null);
 await wait(30);assert.equal(w.document.getElementById('shell').style.display,'none');assert.equal(w.document.getElementById('playback').style.display,'block');assert.equal(prepares.at(-1).start_position,141);assert.equal(w.document.body.getAttribute('data-player-open'),'true');assert.equal(w.document.getElementById('bufferSpinner').textContent,'');
 // Late completion from the stream being replaced must not close the player.
 w.Watch.ended();assert.equal(w.document.getElementById('shell').style.display,'none');
 holding=false;await wait(30);w.Watch.ended();assert.equal(w.document.getElementById('shell').style.display,'none');w.Watch.tick(1000);w.Watch.tick(2000);w.Watch.buffered();assert.equal(w.document.getElementById('bufferSpinner').style.display,'none');assert.equal(w.document.getElementById('shell').style.display,'none');
 w.Watch.buffering();
 assert.equal(w.document.getElementById('shell').style.display,'none');assert.equal(w.document.getElementById('bufferSpinner').style.display,'block');
 failing=true;w.Watch.failed();await wait(120);
 assert.equal(w.document.getElementById('shell').style.display,'none');assert.equal(w.document.getElementById('playback').style.display,'block');
 assert.match(w.document.getElementById('playbackStatus').textContent,/Connection unavailable/);assert.equal(w.document.getElementById('bufferSpinner').style.display,'none');
 assert.ok(native.some(c=>c[0]==='Pause'));assert.equal(prepares.at(-1).start_position,140);
 failing=false;press(13);await wait(40);assert.equal(w.document.getElementById('shell').style.display,'none');w.Watch.buffered();
 assert.equal(w.document.getElementById('bufferSpinner').style.display,'none');press(8);await wait(10);assert.equal(w.document.getElementById('shell').style.display,'block');
 w.Watch.shutdown();dom.window.close();console.log('PASS: confirmed timeline seek and buffering/retry stay in player, freezes frame, preserves position, exhausted retries offer manual retry, Back closes.');
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1});
