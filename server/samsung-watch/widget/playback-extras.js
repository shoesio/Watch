/* ES5 Orsay transport extras. Metadata/queue calls never prepare video. */
var WatchExtras = (function () {
 'use strict';
 var host, epoch=0, active=null, features=null, queue=null, next=null, enabled=false;
 var focus=-1, chapter=-1, buttons=[], timer=null, countdown=0, completed=false, queueBusy=false;
 function el(id) { return document.getElementById(id); }
 function label(id,value) { el(id).textContent=value || ''; }
 function cancel() {
  epoch+=1; countdown=0;clearTimeout(timer); timer=null; active=null; features=null; queue=null; next=null;
  enabled=false; focus=-1; chapter=-1; buttons=[]; completed=false; queueBusy=false;
  el('playback').setAttribute('data-up-next','false');label('featureHint','');el('playbackHelp').setAttribute('data-extra-focus','false');el('featureActions').innerHTML='';el('chapterMenu').style.display='none';el('upNextCard').style.display='none';
 }
 function call(method,path,data,done) {
  var mine=epoch;host.request(method,path,data,function(error,value,status) { if (mine===epoch && active) { done(error,value,status); } });
 }
 function matches(value) { return value && active && value.episode_id===active.episode_id && value.source_key===active.metadata.source_key && (value.version_id || null)===(active.metadata.version_id || null) && value.timebase==='episode'; }
 function valid(rows,skip) {
  var out=[],i,r;
  for (i=0;i<(rows || []).length;i+=1) {
   r=rows[i];if (!r || typeof r.start!=='number' || typeof r.end!=='number' || !isFinite(r.start) || !isFinite(r.end) || r.start<0 || r.end<=r.start || (active.duration_seconds && r.end>active.duration_seconds)) { continue; }
   if (skip && r.kind!=='intro' && r.kind!=='recap') { continue; }out.push(r);
  }return out;
 }
 function getFeatures(retry) {
  if (!active.metadata || !active.metadata.source_key || !active.ticket) { return; }
  var m=active.metadata;
  var path='/api/playback/features?episode_id='+encodeURIComponent(active.episode_id)+'&source_key='+encodeURIComponent(m.source_key)+'&ticket='+encodeURIComponent(active.ticket);
  if (m.version_id) { path+='&version_id='+encodeURIComponent(m.version_id); }
  call('GET',path,null,function(err,data,status) {
   features=null;
   if (status===409 && retry) { getFeatures(false);return; }
   if (!err && matches(data) && data.status==='available') {
    features={chapters:valid(data.chapters,false),skip_markers:valid(data.skip_markers,true)};
    if (m.provider==='BBC iPlayer' && !m.version_id) { features=null; }
   }paint();
  });
 }
 function begin(data) {
  cancel(); active=data;
  if (data.live || !data.episode_id) { return; }
  call('GET','/api/playback/capabilities',null,function(err,caps) {
   if (err || caps.schema_version!==1 || caps.marker_timebase!=='episode') { return; }
   enabled=true;getFeatures(true);
   call('GET','/api/playback/up-next?episode_id='+encodeURIComponent(active.episode_id),null,function(error,value) {
    if (!error && value.episode_id===active.episode_id) { next=value.next_episode && value.next_episode.available!==false ? value.next_episode:null;paint(); }
   });
   if (caps.series_queue) { loadQueue(true); }
  });
 }
 function loadQueue(seed) {
  call('GET','/api/playback/queue',null,function(err,value) {
   if (err) { return; }queue=value;
   if (seed && !completed && (!value.current || value.current.id!==active.episode_id)) { saveQueue(value.autoplay===true); }
   else { paint(); }
  });
 }
 function saveQueue(autoplay) {
  if (!queue || queueBusy || completed) { return; }queueBusy=true;
  call('POST','/api/playback/queue',{episode_id:active.episode_id,expected_revision:queue.revision,autoplay:autoplay},function(err,value,status) {
   queueBusy=false;
   if (!err) { queue=value;paint(); }
   else if (status===409) { queue=null;loadQueue(false); } // Re-evaluate, never replay a stale mutation.
  });
 }
 function currentMarker() {
  if (!features || completed) { return null; }var p=host.state().position,i,m;
  for(i=0;i<features.skip_markers.length;i+=1) { m=features.skip_markers[i];if (m.start<=p && p<m.end) { return m; } }return null;
 }
 function card() {
  var show=!!next && (completed || (focus>=0 && buttons[focus] && /^(next|autoplay)$/.test(buttons[focus].id)));
  el('playback').setAttribute('data-up-next',show?'true':'false');
  el('upNextCard').style.display=show?'block':'none';if(!show) { return; }
  label('upNextHeading',countdown>0?'Up next in '+countdown+' seconds':'Up next');
  label('upNextShow',next.show_title || '');label('upNextTitle',next.title);
  label('upNextDetails',(next.season?'Series '+next.season+' · ':'')+(next.episode_number?'Episode '+next.episode_number:''));
  var img=el('upNextImage'),src=host.image(next.thumbnail || next.artwork,'thumb');if(img.getAttribute('src')!==src) { img.src=src; }
 }
 function paint() {
  var prior=focus>=0 && buttons[focus]?buttons[focus].id:null,m=currentMarker(),i,node;
  buttons=[];
  if(m) { buttons.push({id:'skip',title:m.kind==='recap'?'Skip recap':'Skip intro',marker:m}); }
  if(features && features.chapters.length && !completed) { buttons.push({id:'chapters',title:'Chapters'}); }
  if(next) { buttons.push({id:'next',title:'Play next'}); }
  if(next && queue && queue.current && queue.current.id===active.episode_id && !completed) { buttons.push({id:'autoplay',title:'Autoplay: '+(queue.autoplay?'On':'Off')}); }
  if(completed) { buttons.push({id:'close',title:countdown>0?'Cancel autoplay':'Close'}); }
  if(prior) { focus=-1;for(i=0;i<buttons.length;i+=1) { if(buttons[i].id===prior) { focus=i; } } }
  if(focus>=buttons.length) { focus=buttons.length-1; }
  el('playbackHelp').setAttribute('data-extra-focus',focus>=0?'true':'false');
  label('featureHint',buttons.length && !completed ? (focus>=0?'Left / Right · Choose    OK · Activate    Up · Transport':'Down · Chapters and next episode') : '');
  el('featureActions').innerHTML='';
  for(i=0;i<buttons.length;i+=1) { node=document.createElement('span');node.textContent=buttons[i].title;node.className=i===focus?'selected':'';el('featureActions').appendChild(node); }
  card();
 }
 function chapters() {
  var list=el('chapterRows'),rows=features?features.chapters:[],i,node,first;
  list.innerHTML='';first=Math.floor(chapter/7)*7;
  for(i=first;i<Math.min(first+7,rows.length);i+=1) { node=document.createElement('div');node.textContent=host.clock(rows[i].start)+'   '+rows[i].title;node.className=i===chapter?'selected':'';list.appendChild(node); }
  label('chapterPage',(first+1)+'–'+Math.min(first+7,rows.length)+' of '+rows.length);el('chapterMenu').style.display='block';
 }
 function activate() {
  var b=buttons[focus];if(!b) { return; }
  if(b.id==='skip') { var m=currentMarker();if(m) { host.seek(m.end); } }
  else if(b.id==='chapters') { chapter=0;chapters(); }
  else if(b.id==='next') { var item=next;cancel();host.play(item); }
  else if(b.id==='autoplay' && !queueBusy) { saveQueue(!queue.autoplay); }
  else if(b.id==='close') { cancel();host.close(); }
 }
 function key(k) {
  if(!active) { return false; }
  if(k==='stop') { cancel();host.close();return true; }
  if(chapter>=0) {
   if(k==='back') { chapter=-1;el('chapterMenu').style.display='none';host.reveal(); }
   else if(k==='up' || k==='down') { chapter=Math.max(0,Math.min(features.chapters.length-1,chapter+(k==='up'?-1:1)));chapters(); }
   else if(k==='ok') { var target=features.chapters[chapter].start;chapter=-1;el('chapterMenu').style.display='none';host.seek(target); }
   return true;
  }
  if(completed) {
   if(k==='back' || k==='stop') { cancel();host.close();return true; }
   if(k==='left' || k==='right') { focus=Math.max(0,Math.min(buttons.length-1,focus+(k==='left'?-1:1)));paint(); }
   else if(k==='ok' || k==='play') { activate(); }
   return true;
  }
  if(focus>=0) {
   if(k==='up' || k==='back') { focus=-1;paint();host.reveal();return true; }
   if(k==='left' || k==='right') { focus=Math.max(0,Math.min(buttons.length-1,focus+(k==='left'?-1:1)));paint();return true; }
   if(k==='ok') { activate();return true; }
   if(k==='down') { return true; }
  }
  if(k==='down' && buttons.length && !host.state().timeline && !host.state().waiting) { focus=0;paint();host.reveal();return true; }
  return false;
 }
 function finish() {
  if(!enabled || !active || completed) { return false; }
  completed=true;features=null;focus=-1;chapter=-1;el('chapterMenu').style.display='none';
  var mine=epoch;
  host.finish(function(error) {
   if(mine!==epoch || !active) { return; }
   if(error) { cancel();host.close();return; }
   // Completion is saved before this read/advance. Never prepare from these calls.
   call('GET','/api/playback/queue',null,function(err,value) {
    if(err || !value.current || value.current.id!==active.episode_id) { showEnd(false);return; }
    queue=value;
    call('POST','/api/playback/queue/advance',{completed_episode_id:active.episode_id,expected_revision:queue.revision},function(error,result,status) {
     if(error) {
      if(status===409) { call('GET','/api/playback/queue',null,function(e,q) { queue=e?null:q;next=queue && queue.current && queue.current.available && next && queue.current.id===next.id ? queue.current:null;showEnd(false); }); }
      else { showEnd(false); }
      return;
     }
     queue=result;next=result.current && result.current.available ? result.current:null;showEnd(result.autoplay===true);
    });
   });
  });return true;
 }
 function showEnd(autoplay) {
  if(!next) { cancel();host.close();return; }
  var reduced=window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  countdown=autoplay && !reduced ? 10:0;focus=0;paint();host.reveal();
  if(countdown) { var mine=epoch;function step() { if(mine!==epoch || !completed) { return; }countdown-=1;paint();if(countdown<=0) { var item=next;cancel();host.play(item); }else { timer=setTimeout(step,1000); } }timer=setTimeout(step,1000); }
 }
 return {init:function(h) { host=h; },begin:begin,cancel:cancel,key:key,tick:paint,complete:finish};
}());
