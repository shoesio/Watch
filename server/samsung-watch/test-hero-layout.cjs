const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'widget/index.html'),'utf8'),{runScripts:'outside-only'}),w=dom.window;
const css=w.document.createElement('style');css.textContent=fs.readFileSync(path.join(__dirname,'widget/watch.css'),'utf8');w.document.head.appendChild(css);
const style=id=>w.getComputedStyle(w.document.getElementById(id));
for(const name of ['live-browse','show-detail','film-detail']){
 w.document.body.className=name;
 const menu=style('navigation'),art=style('heroArt'),hero=style('hero'),fade=style('heroBottom'),text=style('heroText');
 assert.ok(parseFloat(art.top)>=parseFloat(menu.height),name+' image starts below the menu');
 assert.ok(Math.abs(parseFloat(art.top)+parseFloat(art.height)-parseFloat(hero.height))<.01,name+' art and fade have the same bottom edge');
 assert.equal(art.overflow,'hidden');assert.equal(fade.bottom,'0px');assert.ok(Number(fade.zIndex)>Number(art.zIndex),'fade above clipped image');
 assert.ok(Number(text.zIndex)>Number(fade.zIndex),'information above fade');
 if(name==='live-browse')assert.ok(parseFloat(text.top)>=parseFloat(menu.height)+48,'live info is below the fixed menu and tools');
}
w.document.body.className='cinema';const art=style('cinemaHeroArt'),hero=style('cinemaHero'),fade=style('cinemaHeroBottom');
assert.equal(parseFloat(art.top),parseFloat(style('navigation').height));assert.equal(parseFloat(art.top)+parseFloat(art.height),parseFloat(hero.height));assert.equal(art.overflow,'hidden');assert.equal(fade.bottom,'0px');assert.ok(Number(fade.zIndex)>Number(art.zIndex));
assert.equal(w.document.getElementById('cinemaHeroImage').parentNode.id,'cinemaHeroArt');assert.equal(w.document.getElementById('heroImage').parentNode.id,'heroArt');
dom.window.close();console.log('PASS: hero photos are clipped below the menu, visible-frame crops and fades share their lower edge, explicit layers protect the fade, and live info clears navigation.');
