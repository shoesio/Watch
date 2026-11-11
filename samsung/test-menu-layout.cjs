const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'widget/index.html'),'utf8'),{runScripts:'outside-only'}),w=dom.window;
const style=w.document.createElement('style');style.textContent=fs.readFileSync(path.join(__dirname,'widget/watch.css'),'utf8');w.document.head.appendChild(style);
for(const name of ['','cinema','all-shows','show-detail','film-detail']){
 w.document.body.className=name;
 const menu=w.getComputedStyle(w.document.getElementById('navigation'));
 assert.equal(menu.top,'0px',name+' menu stays at the top');assert.equal(menu.left,'0px');assert.equal(menu.width,'1280px');assert.equal(menu.height,'64px');assert.equal(parseFloat(menu.borderRadius),0);
 const tools=w.getComputedStyle(w.document.getElementById('sectionTools'));assert.ok(parseFloat(tools.top)>=parseFloat(menu.height)+12);
 for(const id of ['seriesMenu','genreMenu'])assert.ok(parseFloat(w.getComputedStyle(w.document.getElementById(id)).top)>=parseFloat(tools.top)+parseFloat(tools.height)+8);
}
assert.deepEqual(Array.from(w.document.querySelectorAll('#navigation span')).map(e=>e.id),['nav0','nav1','nav8','nav2','nav9','nav10']);
for(const id of ['nav7','nav17','nav11','nav12'])assert.equal(w.document.getElementById(id).parentNode.id,'sectionTools');
dom.window.close();console.log('PASS: full-width fixed primary menu on Home, Shows, Discover, show and film screens; contextual tools and dialogs occupy separate rows.');
