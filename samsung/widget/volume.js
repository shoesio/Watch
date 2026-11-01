/* ES5 Orsay: Watch presentation, real TV audio, native fallback. */
var WatchVolume = (function () {
 'use strict';
 var audio,plugin,nnavi,keys={},enabled=false,timer=null;
 var names=['KEY_VOL_UP','KEY_VOL_DOWN','KEY_MUTE'],codes=[7,11,27];
 function code(i){return typeof keys[names[i]]==='number'?keys[names[i]]:codes[i];}
 function level(){var n=Number(audio.GetVolume());if(!isFinite(n)||n<0||n>100){throw new Error('Volume unavailable');}return n;}
 function muted(){var value=audio.GetUserMute();if(value===true||value===1||value==='1'){return true;}if(value===false||value===0||value==='0'){return false;}throw new Error('Mute unavailable');}
 function accepted(value){if(value!==true&&value!==1&&value!=='1'){throw new Error('Audio command declined');}}
 function hide(){clearTimeout(timer);timer=null;var node=document.getElementById('volumeHUD');if(node){node.className='';}}
 function restore(){enabled=false;hide();try{nnavi.SetBannerState(1);}catch(ignore){}if(plugin){for(var i=0;i<3;i+=1){try{plugin.unregistKey(code(i));}catch(ignoreKey){}}}}
 function show(value,mute){
  var hud=document.getElementById('volumeHUD');if(!hud){return;}
  hud.className='visible'+(mute?' muted':'');
  hud.setAttribute('aria-label',mute?'Muted':'Volume '+Math.round(value));
  document.getElementById('volumeFill').style.height=(mute?0:value)+'%';
  document.getElementById('volumeNumber').textContent=mute?'Muted':String(Math.round(value));
  document.getElementById('volumeSymbol').textContent=mute?'×':')';
  clearTimeout(timer);timer=setTimeout(hide,1200);
 }
 function init(values){
  keys=values||{};audio=document.getElementById('pluginObjectAudio');nnavi=document.getElementById('pluginObjectNNavi');
  try{
   plugin=new Common.API.Plugin();
   if(typeof audio.SetVolumeWithKey!=='function'||typeof audio.SetUserMute!=='function'){throw new Error('Audio unavailable');}
   level();muted();
   for(var i=0;i<3;i+=1){plugin.registKey(code(i));}
   nnavi.SetBannerState(0);enabled=true;
  }catch(ignore){restore();}
 }
 function handle(key){
  var index=-1;for(var i=0;i<3;i+=1){if(key===code(i)){index=i;}}
  if(index<0||!enabled){return false;}
  var attempted=false;
  try{
   var value=level(),mute=muted();
   if(index===2){attempted=true;accepted(audio.SetUserMute(mute?0:1));}
   else{
    if(mute){attempted=true;accepted(audio.SetUserMute(0));}
    if((index===0&&value<100)||(index===1&&value>0)){attempted=true;accepted(audio.SetVolumeWithKey(index===0?0:1));}
   }
   show(level(),muted());return true;
  }catch(ignore){restore();return attempted;}
 }
 function shutdown(){restore();try{nnavi.SetBannerState(2);}catch(ignore){}}
 return {init:init,handle:handle,hide:hide,shutdown:shutdown};
}());
