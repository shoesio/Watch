const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const calls=[],timers=[],window={addEventListener(){},setTimeout(fn,ms){timers.push([fn,ms]);return timers.length},clearTimeout(){}};
const document={body:{appendChild(){}},createElement(){return {style:{},setAttribute(){},GetSource(){return 3},GetState_Show(){return 0},ChangeWidgetMode(v){calls.push(['full',v]);return 1},SetBannerState(v){calls.push(['banner',v]);return true}}}};
vm.runInNewContext(fs.readFileSync(__dirname+'/presentation.js','utf8'),{window,document,Image:function(){}});
window.WatchStartupScreen.init();assert.deepEqual(timers.map(v=>v[1]),[0,1500,4500]);timers.forEach(([fn])=>fn());
assert.equal(calls.filter(v=>v[0]==='full'&&v[1]===0).length,3);assert.equal(calls.filter(v=>v[0]==='banner'&&v[1]===1).length,3);
window.WatchStartupScreen.shutdown();assert.deepEqual(calls.at(-1),['banner',2]);const n=calls.length;timers.forEach(([fn])=>fn());assert.equal(calls.length,n);
console.log('PASS: bounded fullscreen/volume-only setup; banner restoration on exit; no source changes or persistent profile writes.');
