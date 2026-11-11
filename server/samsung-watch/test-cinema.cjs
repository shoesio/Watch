const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'widget/index.html'),'utf8'),{runScripts:'outside-only',url:'http://fixture'}),w=dom.window,wait=ms=>new Promise(r=>setTimeout(r,ms));
let calls=[],prepares=[];const item=i=>({id:'show'+i,title:'Show '+i,hero:'hero',image:'photo',poster:'poster'+i,home_episode:'ep'+i,brands:[]});
w.WATCH_CONNECTION={base:'http://pi',key:'fixture'};w.Common={API:{Widget:function(){this.sendReadyEvent=()=>{};this.blockNavigation=()=>{}},TVKeyValue:function(){}}};
w.XMLHttpRequest=function(){this.open=(method,url)=>{this.method=method;this.url=url};this.setRequestHeader=()=>{};this.abort=()=>{};this.send=body=>{
 const u=new URL(this.url);calls.push(u.pathname+u.search);let data={ok:true};
 if(u.pathname==='/api/cinema')data={snapshot:'snapshot',section:u.searchParams.get('section'),heroes:[item(0),item(1)],genres:['Comedy'],shelves:[{id:'continue',title:'Continue Watching',layout:'continuing',total:12},{id:'posters',title:'Picked for you',layout:'portrait',total:10},{id:'more',title:'More shows',layout:'landscape',total:20}]};
 else if(u.pathname==='/api/cinema/shelf'){const id=u.searchParams.get('id'),page=Number(u.searchParams.get('page')),size=id==='posters'?5:4;data={id,page,size,total:id==='continue'?12:20,items:Array.from({length:size},(_,i)=>item(i+page*size))};}
 else if(u.pathname.startsWith('/api/show/'))data={...item(0),id:u.pathname.split('/').at(-1),home_episode:undefined};
 else if(u.pathname.startsWith('/api/episodes/'))data={items:[{id:'ep0',title:'Episode 1'}],total:1,page:0,focus_index:0};
 else if(u.pathname==='/api/prepare'){prepares.push(JSON.parse(body));data={job:'job'};}
 this.status=200;this.readyState=4;this.responseText=JSON.stringify(data);w.setTimeout(()=>this.onreadystatechange(),0);
 }};
for(const n of ['Play','Pause','Stop','Resume','SetDisplayArea'])w.document.getElementById('player')[n]=()=>1;
for(const n of ['cinema.js','watch.js'])w.eval(fs.readFileSync(path.join(__dirname,'widget',n),'utf8'));
const press=keyCode=>w.Watch.key({keyCode,preventDefault(){}});
(async()=>{
 w.Watch.init();await wait(40);assert.equal(w.document.body.className,'cinema');assert.equal(w.document.body.getAttribute('data-cinema-mode'),'hero');assert.equal(w.document.querySelectorAll('.cinemaRail').length,1);
 assert.equal(calls.filter(c=>c.startsWith('/api/cinema/shelf')).length,1,'only visible shelf fetched');assert.equal(w.document.getElementById('cinemaHeroAction').textContent,'Choose episode');
 press(13);await wait(30);press(8);await wait(40);assert.equal(w.document.getElementById('cinemaHero').style.display,'block','cached hero remains visible after returning to Home');
 press(40);await wait(30);assert.equal(w.document.body.getAttribute('data-cinema-mode'),'rows');assert.equal(w.document.querySelectorAll('.cinemaRail').length,2);assert.equal(w.document.querySelectorAll('.cinemaCard').length,9);
 assert.ok(w.document.querySelector('.cinemaCard.focus'));assert.equal(w.document.body.getAttribute('data-focus-motion'),'false','native Orsay uses instant static focus');
 const existing=w.document.querySelector('.cinemaSurface');const requests=calls.length;const mutations=new w.MutationObserver(()=>{});mutations.observe(w.document.getElementById('shell'),{attributes:true,childList:true,subtree:true});press(39);const changed=mutations.takeRecords();mutations.disconnect();assert.equal(calls.length,requests,'within-page focus makes no requests');assert.equal(changed.length,2,'only the previous and next focus attributes change');assert.ok(changed.every(m=>m.type==='attributes'&&m.attributeName==='class'&&m.target.className.includes('cinemaCard'))); assert.equal(w.document.querySelector('.cinemaSurface'),existing,'focus reuses artwork surfaces');
 for(let i=0;i<4;i++)press(39);await wait(25);assert.ok(calls.some(c=>c.includes('id=continue&page=1')));assert.equal(prepares.length,0);
 press(40);await wait(25);assert.equal(w.document.querySelector('.cinemaRail').className.includes('posters'),true);assert.ok(w.document.querySelectorAll('.cinemaRail').length<=2);
 press(13);await wait(30);assert.equal(w.document.body.className,'show-detail');assert.equal(prepares.length,0);assert.ok(calls.some(c=>c.includes('focus_episode=ep0')));
 press(8);await wait(40);assert.equal(w.document.body.className,'cinema');assert.equal(w.document.querySelector('.cinemaRail').getAttribute('data-rail'),'1','Back restores the originating shelf');
 assert.ok(w.document.querySelectorAll('.cinemaCard').length<=10);
 w.Watch.shutdown();dom.window.close();console.log('PASS: cinematic spotlight, lazy virtual rails, real portrait pages, remote paging, surface reuse, exact episode routing and shelf restoration; no early playback.');
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
