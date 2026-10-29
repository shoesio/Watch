/* Explicit remote-button experiment. Never changes startup settings on app load. */
(function () {
 'use strict';
 var target='SamsungWatch', plugin, panel, transport, keys={KEY_RED:108,KEY_GREEN:20}, installed=false;
 function message(value) { if(panel){panel.innerHTML='';panel.appendChild(document.createTextNode(value));} }
 function send(event, detail) {
  transport=new Image();transport.src='http://192.168.0.146/event?component=watch-autoboot-trial&event='+encodeURIComponent(event)+'&detail='+encodeURIComponent(JSON.stringify(detail))+'&time='+new Date().getTime();
 }
 function value(id) { var raw=plugin.GetProfile(id); if(typeof raw!=='string' && typeof raw!=='number'){throw new Error('No profile value');}return String(raw); }
 function snapshot() {return {ticker_id:value(0),autoboot:value(3)};}
 function set(id,text) {var result=plugin.SetProfile(id,text);return {field:id,result:String(result).substr(0,60),readback:value(id)};}
 function restorePartial() {
  // Restore the already recorded 0/0 baseline, with autoboot disabled first.
  var before=snapshot();
  if (before.ticker_id!==target && before.ticker_id!=='0') {throw new Error('Different startup app selected');}
  if (before.autoboot!=='0' && before.autoboot!=='1') {throw new Error('Unexpected autoboot value');}
  var off=set(3,'0');if(off.readback!=='0'){throw new Error('Could not disable autoboot');}
  var id=set(0,'0');if(id.readback!=='0'){throw new Error('Could not restore ticker ID');}
  return snapshot();
 }
 function enable() {
  var original,steps=[];
  try {
   var model=document.getElementById('watchStartupNNavi').GetModelCode();
   if(model!=='12_X10PLUS_MFM' || String(window.curWidget && window.curWidget.id)!==target){throw new Error('Unexpected TV or app');}
   original=snapshot();
   if(original.ticker_id!=='0' || original.autoboot!=='0'){message('Startup settings already differ from the backed-up baseline. No change made.');send('skipped',original);return;}
   // Harmless same-value setter check, before changing either setting.
   steps.push(set(3,'0'));
   if(steps[0].readback!=='0' || !/^(1|true)$/.test(steps[0].result)){throw new Error('Profile writes were not accepted');}
   steps.push(set(0,target));if(steps[1].readback!==target){throw new Error('TV did not accept this app ID');}
   steps.push(set(3,'1'));if(steps[2].readback!=='1'){throw new Error('TV did not accept autoboot');}
   send('enabled',{before:original,after:snapshot(),steps:steps});
   message('Autostart settings saved and read back. Test one normal off/on cycle. GREEN restores the original off setting.');
  } catch(error) {
   var state={steps:steps,error:String(error.message).substr(0,120)};
   if(original && original.ticker_id==='0' && original.autoboot==='0'){
    try{state.restored=restorePartial();}catch(restoreError){state.restore_error=String(restoreError.message).substr(0,120);}
   }
   send('failed',state);message(state.restore_error?'Test failed; restoration needs checking. Keep TV on and report this message.':'TV did not accept the experiment. Original off settings restored or retained.');
  }
 }
 function restore() {
  try{var after=restorePartial();send('restored',after);message('Original startup settings restored: ticker ID 0; autoboot off.');}
  catch(error){send('restore-failed',{error:String(error.message).substr(0,120)});message('Could not restore settings. Keep TV on and report this message.');}
 }
 function init() {
  if(installed || !window.Watch || !window.WatchBootProbe){return;}installed=true;
  plugin=document.getElementById('watchStartupTVMW');
  if(!plugin){message('Startup probe unavailable. No change made.');return;}
  try{keys=new window.Common.API.TVKeyValue();}catch(ignore){}
  panel=document.createElement('div');panel.id='startupTrial';
  panel.style.cssText='position:absolute;z-index:99999;left:80px;right:80px;top:30px;padding:18px;background:#152631;color:white;font:24px Arial;';
  document.body.appendChild(panel);
  message('Autostart experiment: RED sets this app as ticker + autoboot on. GREEN restores the saved off settings. Nothing changes until you press a colour key.');
  var previous=window.Watch.key;
  window.Watch.key=function(event){
   var code=event.keyCode;
   if(code===(keys.KEY_RED || 108) || code===(keys.KEY_GREEN || 20)){
    if(event.preventDefault){event.preventDefault();}
    if(code===(keys.KEY_RED || 108)){enable();}else{restore();}return false;
   }
   return previous.call(window.Watch,event);
  };
  send('available',{baseline:snapshot()});
 }
 window.WatchBootTrial={enable:enable,restore:restore,init:init};
 if(window.addEventListener){window.addEventListener('load',function(){window.setTimeout(init,4500);},false);}
}());
