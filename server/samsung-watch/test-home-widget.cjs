const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom'),root=path.join(__dirname,'widget');
const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{runScripts:'outside-only',url:'http://fixture.local'}),w=dom.window;
const timers=w.setTimeout.bind(w);w.setTimeout=(fn,ms)=>timers(fn,ms===500?1:ms);
let prepares=[],seasonRequests=0;
const item={id:'series',title:'My Show',home_episode:'version_resume',episode_id:'version_resume',home_reason:'Continue watching',meta:'Continue watching · Series 2 · Episode 3',hero:'episode-art',image:'episode-art',brands:[]};
w.WATCH_CONNECTION={base:'http://pi',key:'fixture'};w.Common={API:{Widget:function(){this.sendReadyEvent=()=>{};this.blockNavigation=()=>{}},TVKeyValue:function(){}}};
w.XMLHttpRequest=function(){this.open=(method,url)=>{this.method=method;this.url=url};this.setRequestHeader=()=>{};this.abort=()=>{};this.send=body=>{
 let data={ok:true};if(this.url.includes('/api/library'))data={items:[item],total:1,page:0};
 else if(this.url.includes('/api/suggestions'))data={items:[item],total:1,page:0};
 else if(this.url.includes('/api/show/'))data={id:'series',title:'My Show',brands:[]};
 else if(this.url.includes('/api/episodes/'))data={items:[{id:'new',title:'Episode 6'},{id:'version_resume',title:'Episode 3'}],total:6,page:1,focus_index:1};
 else if(this.url.includes('/api/seasons')){seasonRequests++;data={items:[],total:0,page:0};}
 else if(this.method==='POST'&&this.url.endsWith('/api/prepare')){prepares.push(JSON.parse(body));data={job:'job'};}
 else if(this.url.endsWith('/api/prepare/job'))data={state:'ready',ticket:'ticket',episode_id:'version_resume',title:'Episode 3',show_title:'My Show',url:'http://pi/fixture.ts',start_position:120,duration_seconds:1000};
 this.status=200;this.readyState=4;this.responseText=JSON.stringify(data);timers(()=>this.onreadystatechange(),0);
 }};
const player=w.document.getElementById('player');for(const fn of ['Play','Pause','Stop','Resume','SetDisplayArea'])player[fn]=()=>1;
w.eval(fs.readFileSync(path.join(root,'watch.js'),'utf8'));const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{w.Watch.init();await wait(30);w.Watch.key({keyCode:13,preventDefault(){}});await wait(40);
 assert.equal(prepares.length,0);assert.ok(w.document.getElementById('card1').className.includes('focus'));assert.match(w.document.getElementById('pageLabel').textContent,/2 \/ 2/);w.Watch.key({keyCode:13,preventDefault(){}});await wait(40);assert.equal(prepares[0].episode_id,'version_resume');assert.equal('start_position' in prepares[0],false);assert.equal(seasonRequests,0);
 assert.equal(w.document.getElementById('shell').style.display,'none');w.Watch.shutdown();dom.window.close();console.log('PASS: Continue Watching opens All series, focuses its exact episode on the right page, and only explicitly selecting it plays.');
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
