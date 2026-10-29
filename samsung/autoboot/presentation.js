/* Claim full-screen presentation after native ticker launch; no persistent settings. */
(function () {
 'use strict';
 var timers=[],objects={},sender,active=true;
 function plugin(name) {
  if(objects[name]){return objects[name];}
  var p=document.createElement('object');p.id='watchStartup'+name;
  p.setAttribute('classid','clsid:SAMSUNG-INFOLINK-'+name);p.style.cssText='position:absolute;width:0;height:0';
  document.body.appendChild(p);objects[name]=p;return p;
 }
 function call(p,method,arg) {
  try{return {state:'returned',value:String(typeof arg==='undefined'?p[method]():p[method](arg)).substr(0,80)};}
  catch(error){return {state:'unavailable',type:String(error.name || 'Error').substr(0,32)};}
 }
 function apply(attempt) {
  if(!active){return;}
  var video=plugin('VIDEO'),nnavi=plugin('NNAVI'),windowPlugin=plugin('WINDOW');
  var report={attempt:attempt,source:call(windowPlugin,'GetSource'),video_state:call(windowPlugin,'GetState_Show'),
   full_screen:call(video,'ChangeWidgetMode',0),banners:call(nnavi,'SetBannerState',1)};
  sender=new Image();sender.src='http://192.168.0.146/event?component=watch-startup-screen&report='+encodeURIComponent(JSON.stringify(report))+'&time='+new Date().getTime();
 }
 function init(){
  // One initial call and two bounded retries for the TV's delayed boot/onshow path.
  timers.push(window.setTimeout(function(){apply(0);},0));
  timers.push(window.setTimeout(function(){apply(1);},1500));
  timers.push(window.setTimeout(function(){apply(2);},4500));
 }
 function shutdown(){active=false;for(var i=0;i<timers.length;i+=1){window.clearTimeout(timers[i]);}
  // Restore volume/channel banners for normal tuner use after leaving Watch.
  if(objects.NNAVI){call(objects.NNAVI,'SetBannerState',2);}
 }
 window.WatchStartupScreen={init:init,shutdown:shutdown};
 if(window.addEventListener){window.addEventListener('load',init,false);window.addEventListener('unload',shutdown,false);}
}());
