const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'widget/index.html'),'utf8'),{runScripts:'outside-only'}),w=dom.window;
const css=w.document.createElement('style');css.textContent=fs.readFileSync(path.join(__dirname,'widget/watch.css'),'utf8');w.document.head.appendChild(css);
const style=id=>w.getComputedStyle(w.document.getElementById(id));
for(const name of ['live-browse','show-detail','film-detail']){
 w.document.body.className=name;
 const menu=style('navigation'),art=style('heroArt'),hero=style('hero'),fade=style('heroBottom'),text=style('heroText');
 assert.equal(parseFloat(art.top),0,name+' decorative art can extend behind the bar');assert.ok(menu.backgroundColor.startsWith('rgba('),'menu is semi-transparent');assert.ok(parseFloat(menu.backgroundColor.split(',').pop())<.75,'menu opacity is reduced');
 assert.ok(Math.abs(parseFloat(art.top)+parseFloat(art.height)-parseFloat(hero.height))<.01,name+' art and fade have the same bottom edge');
 assert.equal(art.overflow,'hidden');assert.equal(fade.bottom,'0px');assert.ok(Number(fade.zIndex)>Number(art.zIndex),'fade above clipped image');
 assert.ok(Number(text.zIndex)>Number(fade.zIndex),'information above fade');
 if(name==='live-browse')assert.ok(parseFloat(text.top)>=parseFloat(menu.height)+48,'live info is below the fixed menu and tools');
}
w.document.body.className='cinema';const art=style('cinemaHeroArt'),hero=style('cinemaHero'),fade=style('cinemaHeroBottom');
assert.equal(parseFloat(art.top),0);assert.equal(parseFloat(art.top)+parseFloat(art.height),parseFloat(hero.height));assert.equal(art.overflow,'hidden');assert.equal(fade.bottom,'0px');assert.ok(Number(fade.zIndex)>Number(art.zIndex));
assert.equal(w.document.getElementById('cinemaHeroImage').parentNode.id,'cinemaHeroArt');assert.equal(w.document.getElementById('heroImage').parentNode.id,'heroArt');
dom.window.close();console.log('PASS: hero art extends behind the translucent menu, visible-frame crops preserve menu clearance, fades share the image edge and live text stays clear.');
