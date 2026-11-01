const assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),{JSDOM}=require('jsdom');
const root=path.join(__dirname,'widget');
for(const custom of [false,true]){
 const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{runScripts:'outside-only',url:'http://fixture/'}),w=dom.window;
 let calls=[],blocked=0,prevented=0,previous=0;
 w.onShow=()=>previous++;
 w.WATCH_CONNECTION={base:'http://fixture',key:'SET_DURING_PI_PACKAGING'};
 w.Common={API:{Widget:function(){this.sendReadyEvent=()=>calls.push('ready');this.blockNavigation=()=>blocked++;},TVKeyValue:function(){if(custom){this.KEY_VOL_UP=107;this.KEY_VOL_DOWN=111;this.KEY_MUTE=127;}},Plugin:function(){this.unregistKey=k=>calls.push(k);}}};
 w.document.getElementById('pluginObjectNNavi').SetBannerState=n=>calls.push('banner:'+n);
 w.eval(fs.readFileSync(path.join(root,'watch.js'),'utf8'));w.Watch.init();
 assert.deepEqual(calls,['ready']);w.onShow();assert.equal(previous,1);
 assert.deepEqual(calls,['ready','banner:1',...(custom?[107,111,127]:[7,11,27])]);
 for(const modal of ['searchMenu','genreMenu','credits']){
  w.document.getElementById(modal).style.display='block';
  for(const keyCode of custom?[107,111,127]:[7,11,27])assert.equal(w.Watch.key({keyCode,preventDefault(){prevented++;}}),true);
  assert.equal(w.document.getElementById(modal).style.display,'block');w.document.getElementById(modal).style.display='none';
 }
 assert.equal(blocked,0);assert.equal(prevented,0);
 w.Common.API.Plugin=function(){throw new Error('unavailable')};w.onShow();
 w.Watch.shutdown();dom.window.close();
}
console.log('PASS: onShow restores native volume/mute after ready, preserves previous lifecycle, releases only audio keys and never swallows them in dialogs.');
