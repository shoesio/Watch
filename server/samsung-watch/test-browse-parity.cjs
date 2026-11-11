const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'widget/index.html'),'utf8'),{runScripts:'outside-only',url:'http://fixture/'}),w=dom.window;
let calls=[],prepares=[];
const css=w.document.createElement('style');css.textContent=fs.readFileSync(path.join(__dirname,'widget/watch.css'),'utf8');w.document.head.appendChild(css);
const show={id:'show',title:'My Show',home_episode:'e1',brands:[],hero:'hero',image:'landscape'},film={id:'film',title:'Film',film:true,episode_id:'film-ep',brands:[],hero:'film-art'};
const eps=Array.from({length:8},(_,i)=>({id:'e'+(8-i),display_title:'Series '+(i<4?'2':'1')+': Episode '+(i<4?4-i:8-i),title:'Episode '+(8-i),meta:'29 Min • HD',description:'Actual synopsis',image:'episode-art',brands:[]}));
w.WATCH_CONNECTION={base:'http://pi',key:'fixture'};w.Common={API:{Widget:function(){this.sendReadyEvent=()=>{};this.blockNavigation=()=>{}},TVKeyValue:function(){}}};w.matchMedia=()=>({matches:false});
w.XMLHttpRequest=function(){this.open=(method,url)=>{this.method=method;this.url=url};this.setRequestHeader=()=>{};this.abort=()=>{};this.send=body=>{
 calls.push({method:this.method,url:this.url,data:body?JSON.parse(body):null});let data={ok:true};const u=new URL(this.url);
 if(u.pathname==='/api/library'||u.pathname==='/api/suggestions'){const isFilm=u.searchParams.get('tab')==='3';data={items:isFilm?[film]:u.searchParams.get('tab')==='2'?[{id:'live',title:'Live',live:true}]:[show],page:0,total:1};}
 else if(u.pathname==='/api/show/show')data={...show,home_episode:undefined};
 else if(u.pathname==='/api/show/film')data=film;
 else if(u.pathname==='/api/episodes/show'){
  let page=Number(u.searchParams.get('page'))||0,items=eps;const selected=u.searchParams.get('season');if(selected==='s1')items=eps.slice(4).map(e=>({...e,display_title:e.display_title.replace(/^Series 1: /,'')}));
  let index=null;if(u.searchParams.get('focus_episode')==='e1'&&selected==='all'){page=1;index=3;}
  data={items:items.slice(page*4,page*4+4),page,total:items.length,focus_index:index};
 }
 else if(u.pathname==='/api/seasons/show')data={items:[{id:'all',title:'All series'},{id:'s2',title:'Series 2'},{id:'s1',title:'Series 1'}],total:3,page:0};
 else if(this.method==='POST'&&u.pathname==='/api/prepare'){prepares.push(JSON.parse(body));data={job:'job'};}
 else if(u.pathname==='/api/prepare/job')data={state:'preparing'};
 this.status=200;this.readyState=4;this.responseText=JSON.stringify(data);w.setTimeout(()=>this.onreadystatechange(),0);
 }};
for(const name of ['Play','Pause','Stop','Resume','SetDisplayArea'])w.document.getElementById('player')[name]=()=>1;
w.eval(fs.readFileSync(path.join(__dirname,'widget/watch.js'),'utf8'));const press=keyCode=>w.Watch.key({keyCode,preventDefault(){}});
async function nav(id){for(let i=0;i<12&&!w.document.querySelector('#navigation .focus,#heroControls .focus');i++){press(38);await wait(10);}for(let i=0;i<22;i++)press(37);for(let i=0;i<22&&!w.document.getElementById('nav'+id).className.includes('focus');i++)press(39);assert.ok(w.document.getElementById('nav'+id).className.includes('focus'),'remote can reach nav '+id);press(13);await wait(30);}
(async()=>{
 w.Watch.init();await wait(30);press(13);await wait(40);
 const hero=w.document.getElementById('heroImage');Object.defineProperty(hero,'naturalWidth',{value:1000});Object.defineProperty(hero,'naturalHeight',{value:1500});hero.onload();
 assert.ok(Math.abs(parseFloat(hero.style.top)+parseFloat(hero.style.height)/3-400/3)<1,'hero upper thirds align');
 assert.equal(w.getComputedStyle(w.document.querySelector('.picture')).height,'157.5px');
 assert.equal(prepares.length,0);assert.equal(w.document.body.className,'show-detail');assert.ok(w.document.getElementById('card3').className.includes('focus'));
 assert.equal(w.document.getElementById('nav17').textContent,'All series');assert.equal(w.document.getElementById('nav16').textContent,'Choose episode');
 assert.match(calls.find(c=>c.url.includes('/episodes/')).url,/season=all.*focus_episode=e1/);
 assert.equal(w.document.querySelector('.name').textContent,'Series 1: Episode 4');assert.equal(w.document.querySelector('.meta').textContent,'29 Min • HD');
 await nav(16);assert.ok(w.document.getElementById('card3').className.includes('focus'));assert.equal(prepares.length,0);
 await nav(17);assert.equal(w.document.getElementById('seriesMenu').style.display,'block');press(40);press(40);press(13);await wait(30);
 assert.equal(w.document.getElementById('nav17').textContent,'Series 1');assert.equal(w.document.querySelector('.name').textContent,'Episode 4');
 await nav(0);assert.equal(w.document.body.className,'');assert.equal(w.document.getElementById('nav17').style.display,'none');
 await nav(8);press(13);await wait(30);assert.equal(w.document.body.className,'film-detail');assert.equal(w.document.getElementById('nav16').textContent,'Play');assert.equal(prepares.length,0);
 // Explicit sidebar selection resets the section instead of returning to its film.
 await nav(1);assert.equal(w.document.body.className,'all-shows');assert.equal(w.document.getElementById('nav17').style.display,'none');
 await nav(2);press(13);await wait(15);assert.equal(prepares.at(-1).episode_id,'live','live tunes directly');
 w.Watch.shutdown();dom.window.close();console.log('PASS: explicit show/film details, All series and retained filter, exact named-episode focus, Choose episode, root sidebar destinations and direct live tuning.');
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
