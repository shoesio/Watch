const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'widget/index.html'),'utf8'),{runScripts:'outside-only',url:'http://fixture/'}),w=dom.window,wait=ms=>new Promise(r=>setTimeout(r,ms));
const real=w.setTimeout.bind(w);w.setTimeout=(fn,ms)=>real(fn,[500,1500].includes(ms)?1:ms);let hold=true,prepares=0;
const channel={id:'bbc_live',episode_id:'bbc_live',title:'BBC One',live:true,channel_brand:'bbcone',show_logo:'not-a-channel-logo',brands:[{id:'bbc',name:'BBC iPlayer'}],guide:{now:{title:'Programme',art:'photo'}}};
w.WATCH_CONNECTION={base:'http://pi',key:'fixture'};w.Common={API:{Widget:function(){this.sendReadyEvent=()=>{};this.blockNavigation=()=>{}},TVKeyValue:function(){}}};
w.XMLHttpRequest=function(){this.open=(method,url)=>{this.method=method;this.url=url};this.setRequestHeader=()=>{};this.abort=()=>{};this.send=body=>{
 let d={ok:true};if(this.url.includes('/api/library'))d={items:[channel],total:1,page:0};
 else if(this.url.includes('/api/suggestions'))d={items:[],total:0,page:0};
 else if(this.method==='POST'&&this.url.endsWith('/api/prepare')){prepares++;d={job:'job'};}
 else if(this.url.endsWith('/api/prepare/job'))d=hold?{state:'preparing'}:{...channel,state:'ready',ticket:'ticket',episode_id:'bbc_live',url:'http://pi/stream',title:'Programme',show_title:'BBC One'};
 this.status=200;this.readyState=4;this.responseText=JSON.stringify(d);real(()=>this.onreadystatechange(),0);
 }};
for(const n of ['Play','Pause','Stop','Resume','SetDisplayArea'])w.document.getElementById('player')[n]=()=>1;
w.eval(fs.readFileSync(path.join(__dirname,'widget/watch.js'),'utf8'));const press=keyCode=>w.Watch.key({keyCode,preventDefault(){}});
function onlyChannel(id){const node=w.document.getElementById(id);assert.equal(node.querySelectorAll('img').length,1);assert.equal(node.querySelectorAll('.brandLogo').length,0);assert.ok(node.querySelector('.channelMark').src.endsWith('/images/marks/bbcone.png'));}
(async()=>{
 w.Watch.init();await wait(30);onlyChannel('heroBrands');assert.equal(w.document.getElementById('title').style.display,'none','channel mark replaces the repeated channel heading');assert.equal(w.document.getElementById('eyebrow').textContent,'');assert.equal(w.document.getElementById('showLogo').style.display,'none');assert.equal(w.document.querySelectorAll('.card .brands img').length,0);
 const failed=w.document.querySelector('#heroBrands .channelMark');failed.onerror();assert.equal(w.document.getElementById('title').style.display,'block','missing channel artwork retains a text fallback');
 press(13);onlyChannel('playingBrands');assert.equal(w.document.getElementById('playingShow').style.display,'none');await wait(20);assert.equal(w.document.getElementById('bufferSpinner').style.display,'block');onlyChannel('playingBrands');
 hold=false;await wait(30);w.Watch.buffered();press(19);assert.equal(w.document.getElementById('playback').className,'paused');onlyChannel('playingBrands');assert.equal(w.document.getElementById('playingShow').style.display,'none');assert.equal(w.document.getElementById('playingTitle').textContent,'Programme');assert.equal(w.document.getElementById('playingLogo').style.display,'none');assert.equal(prepares,1);
 w.Watch.shutdown();dom.window.close();console.log('PASS: live selection, loading and pause show only the selected channel mark; provider and secondary show logos are suppressed.');
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
