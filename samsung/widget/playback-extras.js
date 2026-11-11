/* ES5 Orsay transport extras. Metadata/queue calls never prepare video. */
var WatchExtras = (function () {
 'use strict';
 var host, epoch=0, active=null, features=null, queue=null, next=null, enabled=false;
 var focus=-1, chapter=-1, buttons=[], timer=null, countdown=0, completed=false, queueBusy=false;
 var offered=false, dismissed=false, cardFocus=-1, actionSignature='', cardSignature='', autoplayCancelled=false;
 function el(id) { return document.getElementById(id); }
 function label(id,value) { el(id).textContent=value || ''; }
 function cancel() {
  epoch+=1; countdown=0;clearTimeout(timer); timer=null; active=null; features=null; queue=null; next=null;
  offered=false;dismissed=false;cardFocus=-1;actionSignature='';cardSignature='';autoplayCancelled=false;
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
    features={chapters:valid(data.chapters,false),skip_markers:valid(data.skip_markers,true),credits:valid(data.credits,false)};
    features.credits=features.credits.concat(features.chapters.filter(function (c) { return c.kind==='credits' || c.kind==='end_credits'; }));
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
  var state=host.state(),duration=Number(active && active.duration_seconds)||0,verified=features?features.credits:[],cue=false,i;
  if(next && !completed && !dismissed && state.playing && !state.paused && !state.waiting && !state.timeline) {
   for(i=0;i<verified.length;i+=1) { if(verified[i].start<=state.position && state.position<verified[i].end) { cue=true; } }
   if(!verified.length && duration>10 && state.position>=duration-10 && state.position<duration) { cue=true; }
   if(cue && !offered) { offered=true;cardFocus=0; }
  }
  var show=!!next && !dismissed && (completed || offered) && (completed || (!state.paused && !state.waiting));
  el('upNextCard').style.display=show?'block':'none';if(!show) { return; }
  var reduced=window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  countdown=!completed && !autoplayCancelled && queue && queue.autoplay && !reduced && duration-state.position<=10 ? Math.max(0,Math.ceil(duration-state.position)) : 0;
  var signature=[next.id,cardFocus,countdown,completed].join(':');if(signature===cardSignature) { return; }cardSignature=signature;
  label('upNextHeading','UP NEXT');label('upNextShow',next.show_title || '');
  var title=String(next.title || '').replace(/^(?:Series|Season)\s+[^:]+:\s*/i,'').replace(/^\d+\.\s*/, '');
  label('upNextTitle',title);
  var season=String(next.season || ''),parts=[];if(season) { parts.push(/^Series\s/i.test(season)?season:'Series '+season); }
  if(next.episode_number) { parts.push('Episode '+next.episode_number); }
  if(Number(next.duration_seconds)>0) { parts.push(Math.floor(Number(next.duration_seconds)/60)+' Min'); }
  label('upNextDetails',parts.join(' • '));
  label('upNextPlay','Next episode'+(countdown>0?'  ·  '+countdown:''));label('upNextExit','Exit');
  el('upNextPlay').className=cardFocus===0?'selected':'';el('upNextExit').className=cardFocus===1?'selected':'';
  host.brands(el('upNextBrands'),(next.brands || active.brands || []).slice(0,1));
  var img=el('upNextImage'),src=host.image(next.thumbnail || next.artwork,'card');
  if(img._watchSource!==src) { img._watchSource=src;host.cover(img,306,190.5,false);img.src=src; }
 }
 function paint() {
  if(!active) { return; }
  var prior=focus>=0 && buttons[focus]?buttons[focus].id:null,m=currentMarker(),i,node;
  buttons=[];
  if(m) { buttons.push({id:'skip',title:m.kind==='recap'?'Skip recap':'Skip intro',marker:m}); }
  if(features && features.chapters.length && !completed) { buttons.push({id:'chapters',title:'Chapters'}); }
  if(next && queue && queue.current && queue.current.id===active.episode_id && !completed) { buttons.push({id:'autoplay',title:'Autoplay: '+(queue.autoplay?'On':'Off')}); }

  if(prior) { focus=-1;for(i=0;i<buttons.length;i+=1) { if(buttons[i].id===prior) { focus=i; } } }
  if(focus>=buttons.length) { focus=buttons.length-1; }
  el('playbackHelp').setAttribute('data-extra-focus',focus>=0?'true':'false');
  label('featureHint',buttons.length && !completed ? (focus>=0?'Left / Right · Choose    OK · Activate    Up · Transport':'Down · Playback options') : '');
  var signature=buttons.map(function (b,i) { return b.id+':'+b.title+':'+(i===focus); }).join('|');
  if(signature!==actionSignature) { actionSignature=signature;el('featureActions').innerHTML='';
  for(i=0;i<buttons.length;i+=1) { node=document.createElement('span');node.textContent=buttons[i].title;node.className=i===focus?'selected':'';el('featureActions').appendChild(node); }
  }
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
  if((offered || completed) && !dismissed && next && cardFocus>=0) {
   if(k==='back' || k==='up') { dismissed=true;autoplayCancelled=true;cardFocus=-1;card();if(completed) { cancel();host.close(); }else { host.reveal(); }return true; }
   if(k==='left' || k==='right') { cardFocus=k==='left'?0:1;card();return true; }
   if(k==='ok' || k==='play') { if(cardFocus===0) { var item=next;cancel();host.play(item); }else { cancel();host.close(); }return true; }
   if(k==='down') { return true; }
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
  if(!next || dismissed) { cancel();host.close();return; }
  var reduced=window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  // The countdown was inside Next episode during the final ten seconds.
  // Its expiry alone never starts video; this path follows natural completion,
  // successful completion persistence and a successful revisioned advance only.
  if(autoplay && offered && !autoplayCancelled && !reduced) { var item=next;cancel();host.play(item);return; }
  offered=true;cardFocus=0;cardSignature='';paint();
 }

 return {init:function(h) { host=h;document.body.appendChild(el('upNextCard')); },begin:begin,cancel:cancel,key:key,tick:paint,complete:finish};
}());
