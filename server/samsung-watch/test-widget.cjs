const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.join(__dirname, 'widget');
const dom = new JSDOM(fs.readFileSync(path.join(root, 'index.html'), 'utf8'), {runScripts:'outside-only', url:'http://fixture.local/'});
const w = dom.window;
let calls = [], native = [], releases = 0, returned = 0, chosenStart = 0;
const programmes = Array.from({length:10}, (_,i)=>({id:'show'+i,title:'Programme '+i,show_logo:'logo-fixture',show_title:'Programme '+i,image:'image-fixture',meta:'BBC iPlayer',description:'Programme description',brands:[{id:'bbc',name:'BBC iPlayer'}]}));
const episodes = [{id:'ep1',title:'Episode 1',meta:'BBC iPlayer',description:'Episode description',brands:[{id:'channel4',name:'Channel 4'}]}];
w.WATCH_CONNECTION = {base:'http://pi', key:'test-only'};
w.Common = {API:{Widget:function(){this.sendReadyEvent=()=>{};this.blockNavigation=()=>{};this.sendReturnEvent=()=>returned++;this.sendExitEvent=()=>{};},TVKeyValue:function(){}}};
w.XMLHttpRequest = function(){
 this.open=(method,url)=>{this.method=method;this.url=url;}; this.setRequestHeader=()=>{};this.abort=()=>{};
 this.send=body=>{
  calls.push({method:this.method,url:this.url,body});
  let data;
  if(this.url.includes('/api/library')||this.url.includes('/api/suggestions')){const query=new URL(this.url).searchParams,page=Number(query.get('page')),size=Number(query.get('size'));data={items:programmes.slice(page*size,page*size+size),page,total:10,genres:['Comedy','Drama']};}
  else if(this.url.includes('/api/seasons/')) data={items:[{id:'all',title:'All episodes'}],total:1,page:0};
  else if(this.url.includes('/api/episodes/')) data={items:episodes,total:1,page:0};
  else if(this.method==='POST' && this.url.endsWith('/api/prepare')) {chosenStart=JSON.parse(body).start_position||0;data={job:'job1'};}
  else if(this.method==='GET' && this.url.endsWith('/api/prepare/job1')) data={state:'ready',ticket:'ticket1',title:'Episode 1',show_title:'Programme 4',description:'Episode synopsis',season:'2',episode_number:3,show_logo:'logo-fixture',url:'http://pi/media/ticket1/stream.ts',episode_id:'ep1',start_position:chosenStart,duration_seconds:1000,spec:{quality:'HD',height:720,width:1280},brands:[{id:'channel4',name:'Channel 4'}]};
  else {data={ok:true};if(this.method==='DELETE' && this.url.includes('/api/play/'))releases++;}
  this.status=200;this.responseText=JSON.stringify(data);this.readyState=4;
  w.setTimeout(()=>this.onreadystatechange(),0);
 };
};
const player=w.document.getElementById('player');
for(const fn of ['SetDisplayArea','Stop','Play','Pause','Resume']) player[fn]=(...a)=>{native.push([fn,...a]);return 1;};
w.eval(fs.readFileSync(path.join(root,'watch.js'),'utf8'));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const press=keyCode=>w.Watch.key({keyCode,preventDefault(){}});
(async()=>{
 w.Watch.init();await wait(20);
 assert.equal(w.document.querySelectorAll('.card').length,4);
 assert.equal(w.document.querySelector('#heroBrands img').alt,'BBC iPlayer');
 const showLogo=w.document.getElementById('showLogo');showLogo.onload();assert.equal(showLogo.style.display,'block');press(38);press(40);assert.equal(showLogo.style.display,'block');
 const picture=w.document.querySelector('.card .picture img');assert.equal(picture.style.width,'280px');assert.equal(picture.style.visibility,'hidden');assert.ok(picture.src.includes('size=thumb'));
 Object.defineProperty(picture,'naturalWidth',{value:400});Object.defineProperty(picture,'naturalHeight',{value:800});picture.onload();
 assert.equal(picture.style.width,'280px');assert.equal(picture.style.height,'560px');
 assert.equal(picture.style.top,'-230px');assert.equal(picture.style.visibility,'visible');picture.onload();assert.equal(picture.style.width,'280px');assert.equal(picture.style.height,'560px');
 for(let i=0;i<4;i++)press(39);await wait(20);
 assert.equal(w.document.querySelectorAll('.card').length,4);
 assert.match(w.document.getElementById('pageLabel').textContent,/2 \/ 3/);
 press(13);await wait(20);assert.equal(w.document.querySelectorAll('.card').length,1);assert.equal(showLogo.style.display,'block');assert.equal(w.document.getElementById('nav7').style.display,'none');
 press(8);await wait(20);assert.match(w.document.getElementById('pageLabel').textContent,/2 \/ 3/);
 press(13);await wait(20);press(13);await wait(20);press(13);await wait(650);
 assert.ok(native.some(c=>c[0]==='Play'&&c[1].endsWith('stream.ts')));
 assert.equal(w.document.getElementById('shell').style.display,'none');w.Watch.tick(1000);w.Watch.tick(121000);assert.match(w.document.getElementById('timeLabel').textContent,/2:01/);assert.equal(w.document.getElementById('timelineDot').style.left,'12.1%');press(417);await wait(700);assert.equal(JSON.parse(calls.filter(c=>c.method==='POST'&&c.url.endsWith('/api/prepare')).at(-1).body).start_position,151);assert.equal(JSON.parse(calls.find(c=>c.method==='DELETE'&&c.url.includes('/api/play/')).body).position,121);
 assert.equal(w.document.getElementById('qualityBadge').textContent,'HD');assert.equal(w.document.getElementById('qualityBadge').style.display,'block');assert.equal(w.document.querySelector('#playingBrands img').alt,'Channel 4');w.Watch.buffered();assert.equal(w.document.getElementById('qualityBadge').style.display,'block');await wait(3100);assert.equal(w.document.getElementById('qualityBadge').style.display,'none');assert.equal(w.document.getElementById('playback').style.display,'none');press(39);assert.equal(w.document.getElementById('qualityBadge').style.display,'block');press(13);assert.equal(native.at(-1)[0],'Pause');assert.equal(w.document.getElementById('playback').className,'paused');assert.equal(w.document.getElementById('playingDescription').textContent,'Episode synopsis');assert.equal(w.document.getElementById('playingEpisode').textContent,'Series 2 · Episode 3 · 17 min');w.document.getElementById('playingLogo').onload();assert.equal(w.document.getElementById('playingLogo').style.display,'block');
 press(13);assert.equal(native.at(-1)[0],'Resume');assert.equal(w.document.getElementById('playback').className,'');
 press(19);press(38);assert.equal(w.document.getElementById('playbackHelp').className,'timeline-focus');const beforeScrub=calls.filter(c=>c.url.endsWith('/api/prepare')).length;for(let i=0;i<8;i++)press(39);assert.match(w.document.getElementById('timeLabel').textContent,/Jump to/);assert.equal(calls.filter(c=>c.url.endsWith('/api/prepare')).length,beforeScrub);press(40);assert.equal(w.document.getElementById('playbackHelp').className,'');press(415);press(19);press(38);press(39);press(39);press(13);await wait(700);assert.equal(JSON.parse(calls.filter(c=>c.method==='POST'&&c.url.endsWith('/api/prepare')).at(-1).body).start_position,171);
 press(8);await wait(20);assert.equal(native.at(-1)[0],'Stop');assert.equal(releases,3);assert.equal(w.document.getElementById('qualityBadge').style.display,'none');
 assert.equal(w.document.getElementById('shell').style.display,'block');
 press(13);await wait(650);w.Watch.failed();await wait(20);
 assert.match(w.document.getElementById('status').textContent,/Reconnecting 1/);assert.equal(w.document.getElementById('shell').style.display,'none');assert.equal(w.document.getElementById('playback').style.display,'block');assert.equal(w.document.getElementById('bufferSpinner').style.display,'block');await wait(2700);assert.equal(w.document.getElementById('shell').style.display,'none');assert.equal(JSON.parse(calls.filter(c=>c.method==='POST'&&c.url.endsWith('/api/prepare')).at(-1).body).start_position,0);w.Watch.buffering();assert.equal(w.document.getElementById('bufferSpinner').style.display,'block');assert.equal(w.document.getElementById('shell').style.display,'none');assert.match(w.document.getElementById('playbackStatus').textContent,/Buffering/);w.Watch.buffered();assert.equal(w.document.getElementById('bufferSpinner').style.display,'none');w.Watch.ended();await wait(20);assert.match(w.document.getElementById('status').textContent,/Reconnecting 2/);
 assert.ok(!calls.some(c=>c.url.includes('8123')||c.url.includes('play_media')));
 press(8);await wait(20);press(8);await wait(20);press(8);await wait(20);
 // Return from the result grid opens navigation, including from later pages.
 press(8);press(39);press(13);await wait(20);
 assert.equal(w.document.body.className,'all-shows');assert.equal(w.document.querySelectorAll('.card').length,8);
 assert.ok(w.document.getElementById('card0').className.includes('focus'));
 press(40);assert.ok(w.document.getElementById('card4').className.includes('focus'));
 press(40);await wait(20);assert.match(w.document.getElementById('pageLabel').textContent,/2 \/ 2/);
 press(38);await wait(20);assert.match(w.document.getElementById('pageLabel').textContent,/1 \/ 2/);assert.ok(w.document.getElementById('card4').className.includes('focus'));
 // Right edge of the first row pages forwards; left edge pages back to the same row.
 press(38);for(let i=0;i<4;i++)press(39);await wait(20);assert.match(w.document.getElementById('pageLabel').textContent,/2 \/ 2/);
 press(37);await wait(20);assert.match(w.document.getElementById('pageLabel').textContent,/1 \/ 2/);assert.ok(w.document.getElementById('card3').className.includes('focus'));
 press(8);for(let i=0;i<8;i++)press(39);press(13);assert.equal(w.document.getElementById('genreMenu').style.display,'block');assert.equal(w.document.getElementById('genreHeading').textContent,'Filter shows');
 press(40);press(13);await wait(20);assert.ok(calls.at(-1).url.includes('genre=Comedy'));
 press(8);press(39);press(13);await wait(20);assert.ok(calls.at(-1).url.includes('tab=3'));assert.ok(calls.at(-1).url.endsWith('genre='));
 press(457);assert.equal(w.document.getElementById('credits').style.display,'block');press(8);assert.equal(w.document.getElementById('credits').style.display,'none');
 assert.equal(w.document.getElementById('nav1').textContent,'Shows');assert.equal(w.document.getElementById('brand'),null);assert.equal(w.document.getElementById('nav3'),null);assert.equal(w.document.getElementById('nav4'),null);assert.equal(w.document.getElementById('nav5'),null);assert.equal(w.document.getElementById('nav6'),null);assert.equal(w.document.getElementById('control0'),null);assert.equal(w.document.getElementById('control2'),null);
 w.Watch.shutdown();dom.window.close();
 console.log('PASS: pagination, episode selection, back restores focus, native playback, pause/resume, release, errors, no external TV control.');
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1;});
