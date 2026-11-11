/* ES5: virtual shelves. At most two visible rails, with bounded image requests. */
var WatchCinema=(function(){
 'use strict';
 var host,serial=0,on=false,model=null,rail=0,index=0,hero=0,mode='hero',pages={},loading={},errors={},pendingDraw=false,focusedCard=null,heroSignature='';
 function el(id){return document.getElementById(id);}
 function text(id,value){el(id).textContent=value || '';}
 function visibleRows(){return mode==='hero'?[0]:[rail,rail+1];}
 function snap(){return on?{rail:rail,index:index,hero:hero,mode:mode,pages:pages}:null;}
 function suspend(){serial+=1;on=false;el('cinema').style.display='none';}
 function safe(){return serial;}
 function load(tab,genre,restore,done){
  serial+=1;var mine=serial;on=true;model=null;pages={};loading={};errors={};focusedCard=null;heroSignature='';rail=0;index=0;hero=0;mode=tab===0 || tab===3?'hero':'rows';
  el('cinema').style.display='block';el('cinemaHero').style.display='none';el('cinemaHero')._shown=false;document.body.setAttribute('data-cinema-mode','rows');el('cinemaRails').innerHTML='';el('cinemaRails')._signature='';text('cinemaHeading','Loading your library…');
  host.request('GET','/api/cinema?section='+(tab===3?'films':tab===1?'shows':'home')+'&genre='+encodeURIComponent(genre || ''),null,function(err,data){
   if(mine!==serial){return;}if(err){on=false;el('cinema').style.display='none';done(err);return;}
   if(!data || !Array.isArray(data.shelves)){on=false;done('Shelf metadata unavailable');return;}model=data;
   if(restore){rail=Math.max(0,Math.min((data.shelves || []).length-1,restore.rail || 0));index=restore.index || 0;hero=restore.hero || 0;mode=restore.mode || mode;}
   if(!(data.heroes || []).length){mode='rows';}if(genre){mode='rows';}
   drawHero();draw();done(null,data);loadVisible(restore);
  });
 }
 function getPage(r,page,done){
  if(!model || !model.shelves[r]){if(done){done();}return;}
  var row=model.shelves[r],key=row.id+':'+page;if(pages[key]){if(done){done(pages[key]);}return;}
  if(loading[key]){return;}loading[key]=true;delete errors[key];var mine=serial;
  host.request('GET','/api/cinema/shelf?snapshot='+encodeURIComponent(model.snapshot)+'&id='+encodeURIComponent(row.id)+'&page='+page,null,function(err,data){
   if(mine!==serial){return;}delete loading[key];if(!err){pages[key]=data;}else{errors[key]=true;}
   if(done){done(err?null:data);}scheduleDraw();
  });
 }
 function pageFor(r){var row=model.shelves[r],size=row && row.layout==='portrait'?5:4;return r===rail?Math.floor(index/size):0;}
 function loadVisible(restore){var rows=visibleRows();for(var i=0;i<rows.length;i+=1){if(model.shelves[rows[i]]){getPage(rows[i],pageFor(rows[i]));}}}
 function scheduleDraw(){if(pendingDraw){return;}pendingDraw=true;setTimeout(function(){pendingDraw=false;if(on){draw();}},0);}
 function heroItem(){return model && model.heroes && model.heroes[hero%model.heroes.length];}
 function drawHero(){
  var item=heroItem(),shown=mode==='hero' && item,frame=el('cinemaHero');
  if(frame._shown!==!!shown){frame._shown=!!shown;frame.style.display=shown?'block':'none';}
  if(!shown){var hidden=el('cinemaHeroImage');if(hidden._source){hidden._source=null;hidden.onload=null;hidden.removeAttribute('src');}heroSignature='';return;}
  var actionClass=host.inNav()?'':'selected';if(el('cinemaHeroAction').className!==actionClass){el('cinemaHeroAction').className=actionClass;}
  var identity=[item.id,item.home_episode || '',hero].join(':');if(identity===heroSignature){return;}heroSignature=identity;
  text('cinemaHeroTitle',item.title);text('cinemaHeroDescription',item.description);text('cinemaHeroCaption',item.meta || '');
  host.brands(el('cinemaHeroBrands'),item.brands,item.channel_brand,item.title,item.live);
  var photo=el('cinemaHeroImage'),source=host.art(item);
  if(photo._source!==source){photo._source=source;host.cover(photo,960,315.75,false,true,48);photo.src=source;}
  var logo=el('cinemaHeroLogo'),mark=!item.live && item.show_logo,logoSource=mark && !item.artwork_contains_title ? host.logo(mark):'';
  if(logoSource){
   logo.onload=function(){logo.style.display='block';el('cinemaHeroTitle').style.display='none';};logo.onerror=function(){logo.style.display='none';el('cinemaHeroTitle').style.display='block';};
   if(logo._source!==logoSource){logo._source=logoSource;logo.style.display='none';el('cinemaHeroTitle').style.display='block';logo.src=logoSource;}
   else if(logo.complete && logo.naturalWidth){logo.onload();}
  }else{logo.style.display='none';el('cinemaHeroTitle').style.display='block';}
  text('cinemaHeroAction',item.live?'Watch live':item.film?'View film':'Choose episode');text('cinemaHeroCount',(hero+1)+' / '+model.heroes.length);
  el('cinemaHeroAction').className=host.inNav()?'':'selected';
 }
 function card(item,r,i,focused){
  var row=model.shelves[r],portrait=row.layout==='portrait',node=document.createElement('div'),surface=document.createElement('div'),picture=document.createElement('div'),img=document.createElement('img'),shade=document.createElement('div'),caption=document.createElement('div'),title=document.createElement('div'),brands=document.createElement('div');
  node.className='cinemaCard'+(item.live?' live':'')+(portrait?' portrait':'')+(focused&&!host.inNav()?' focus':'');node.setAttribute('data-id',item.id);surface.className='cinemaSurface';picture.className='cinemaPicture';shade.className='cinemaCardShade';caption.className='cinemaCaption';title.className='cinemaCardTitle';brands.className='cinemaBrands';
  title.textContent=item.title;host.brands(brands,item.brands,item.channel_brand,item.title,item.live);var photo=portrait?host.image(item.poster,'poster'):item.channel_brand?host.art(item,'thumb'):host.image(item.home_episode?item.image:(item.card_artwork || item.image || item.hero),'thumb');
  host.cover(img,portrait?156:210,portrait?234:118.125,portrait || (!!item.channel_brand && !(item.guide && item.guide.now && item.guide.now.art)));img.src=photo;img.alt='';picture.appendChild(img);surface.appendChild(picture);surface.appendChild(shade);surface.appendChild(brands);
  if(!portrait){
   var short=document.createElement('div');short.className='cinemaCardInfo';short.textContent=item.caption || item.home_reason || (item.live && item.guide && item.guide.now ? item.guide.now.title:'');surface.appendChild(short);
   if(row.layout==='continuing' && item.show_logo && host.logo(item.show_logo)){var logo=document.createElement('img');logo.className='cinemaCardLogo';logo.src=host.logo(item.show_logo);logo.alt=item.title;surface.appendChild(logo);}
   if(item.progress){var track=document.createElement('div'),fill=document.createElement('div');track.className='cinemaProgress';fill.style.width=Math.max(0,Math.min(100,Number(item.progress)))+'%';track.appendChild(fill);surface.appendChild(track);}
  }
  node.appendChild(surface);caption.appendChild(title);node.appendChild(caption);return node;
 }
 function draw(){
  if(!on || !model){return;}if(document.body.getAttribute('data-cinema-mode')!==mode){document.body.setAttribute('data-cinema-mode',mode);}if(document.body.getAttribute('data-cinema-section')!==model.section){document.body.setAttribute('data-cinema-section',model.section);}drawHero();
  text('cinemaHeading',model.section==='films'?'Films':model.section==='shows'?'Shows':'');
  var root=el('cinemaRails'),wanted=visibleRows(),signature=mode+':'+rail+':'+wanted.map(function(r){var p=pages[(model.shelves[r] || {}).id+':'+pageFor(r)];return r+':'+pageFor(r)+':'+(errors[(model.shelves[r] || {}).id+':'+pageFor(r)]?'error:':'')+(p?p.items.map(function(x){return x.id+(x.home_episode || '');}).join(','):'loading');}).join('|');
  if(root._signature===signature){paintFocus();return;}root._signature=signature;var reused={},old=root.children,keep=[];for(var j=0;j<old.length;j+=1){if(old[j]._key){reused[old[j]._key]=old[j];}}
  for(var n=0;n<wanted.length;n+=1){var r=wanted[n],row=model.shelves[r];if(!row){continue;}var box=document.createElement('div'),heading=document.createElement('h2'),cards=document.createElement('div'),p=pages[row.id+':'+pageFor(r)];var cacheKey=row.id+':'+pageFor(r)+':'+(errors[row.id+':'+pageFor(r)]?'error:':'')+(p?p.items.map(function(item){return item.id+(item.home_episode || '');}).join(','):'loading');if(reused[cacheKey]){box=reused[cacheKey];var railClass='cinemaRail'+(n===1?' preview':'')+(row.layout==='portrait'?' posters':'');if(box.className!==railClass){box.className=railClass;}keep.push(box);continue;}box._key=cacheKey;box.className='cinemaRail'+(n===1?' preview':'')+(row.layout==='portrait'?' posters':'');box.setAttribute('data-rail',r);box._cards=[];heading.textContent=row.title;cards.className='cinemaRailCards';box.appendChild(heading);box.appendChild(cards);
   if(p){for(var i=0;i<p.items.length;i+=1){var tile=card(p.items[i],r,i,false);box._cards.push(tile);cards.appendChild(tile);}var count=document.createElement('div');count.className='cinemaRailCount';count.textContent=(p.page+1)+' / '+Math.ceil(p.total/p.size);box.appendChild(count);}
   else{var loading=document.createElement('div');loading.className='cinemaLoading';loading.textContent=errors[row.id+':'+pageFor(r)]?'Cannot load this row. OK · Retry':'Loading…';cards.appendChild(loading);}keep.push(box);
  }
  for(var gone=root.children.length-1;gone>=0;gone-=1){if(keep.indexOf(root.children[gone])<0){root.removeChild(root.children[gone]);}}
  for(var k=0;k<keep.length;k+=1){if(root.children[k]!==keep[k]){root.insertBefore(keep[k],root.children[k] || null);}}
  while(root.children.length>keep.length){root.removeChild(root.lastChild);}
  paintFocus();
 }
 function paintFocus(){
  if(!model){return;}var next=null,root=el('cinemaRails'),children=root.children;
  if(mode!=='hero' && !host.inNav()){
   for(var i=0;i<children.length;i+=1){if(Number(children[i].getAttribute('data-rail'))===rail){var size=model.shelves[rail].layout==='portrait'?5:4;next=(children[i]._cards || [])[index%size] || null;break;}}
  }
  if(next===focusedCard){return;}
  if(focusedCard){focusedCard.className=focusedCard.className.replace(' focus','');}
  focusedCard=next;if(next){next.className+=' focus';}
 }
 function activeItem(){if(mode==='hero'){return heroItem();}var row=model.shelves[rail],p=row&&pages[row.id+':'+pageFor(rail)];return p&&p.items[index%p.size];}
 function key(key){
  if(!on || !model || host.inNav()){return false;}
  if(key==='back'){host.nav();paintFocus();drawHero();return true;}
  if(mode==='hero'){
   if(key==='left' || key==='right'){hero=(hero+(key==='right'?1:model.heroes.length-1))%model.heroes.length;drawHero();}
   else if(key==='down'){mode='rows';rail=0;index=0;draw();loadVisible();}
   else if(key==='up'){host.nav();drawHero();}
   else if(key==='ok' || key==='play'){var item=activeItem();if(item){host.choose(item);}}
   return true;
  }
  var row=model.shelves[rail],size=row&&row.layout==='portrait'?5:4;if(!row){if(key==='up'){host.nav();}return true;}
  if(key==='left' || key==='right' || key==='pageLeft' || key==='pageRight'){var previous=index;index=Math.max(0,Math.min((row?row.total:1)-1,index+(key==='left'?-1:key==='right'?1:key==='pageLeft'?-size:size)));if(Math.floor(previous/size)===pageFor(rail) && pages[row.id+':'+pageFor(rail)]){paintFocus();}else{draw();getPage(rail,pageFor(rail));}}
  else if(key==='down'){if(rail+1<model.shelves.length){rail+=1;index=0;draw();loadVisible();}}
  else if(key==='up'){if(rail>0){rail-=1;index=0;draw();loadVisible();}else if(model.heroes && model.heroes.length && model.section!=='shows'){mode='hero';draw();loadVisible();}else{host.nav();paintFocus();}}
  else if(key==='ok' || key==='play'){var selected=activeItem();if(selected){host.choose(selected);}else{getPage(rail,pageFor(rail));}}
  return true;
 }
 return {init:function(h){host=h;},load:load,key:key,suspend:suspend,snapshot:snap,active:function(){return on;},enter:function(){draw();},paint:function(){if(on && model){paintFocus();drawHero();}}};
}());
