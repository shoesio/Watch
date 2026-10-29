/* Read-only Orsay startup investigation. No profile setters or filesystem writes. */
(function () {
 'use strict';
 var transport;
 function read(object, method, argument) {
  try {
   if (!object) { return {state:'missing-plugin'}; }
   var result = typeof argument === 'undefined' ? object[method]() : object[method](argument);
   if (typeof result !== 'string' && typeof result !== 'number' && typeof result !== 'boolean') { return {state:'no-value',type:typeof result}; }
   return {state:'returned',type:typeof result,value:String(result).substr(0,160)};
  } catch (error) { return {state:'unavailable',type:String(error.name || 'Error').substr(0,32)}; }
 }
 function plugin(id, clsid) {
  var object = document.getElementById(id);
  if (!object) {
   object = document.createElement('object');object.id=id;
   object.setAttribute('classid', 'clsid:SAMSUNG-INFOLINK-'+clsid);
   object.style.position='absolute';object.style.width='0px';object.style.height='0px';
   document.body.appendChild(object);
  }
  return object;
 }
 function collect(tvmw, nnavi) {
  var report = {schema:1,mode:'read-only',
   firmware:read(nnavi,'GetFirmware'), model:read(nnavi,'GetModelCode'),
   profiles:{ticker_id:read(tvmw,'GetProfile',0),autoboot:read(tvmw,'GetProfile',3),
    ticker_duration:read(tvmw,'GetProfile',4),ticker_safe:read(tvmw,'GetProfile',7)}};
  try { report.widget_id=String(window.curWidget && window.curWidget.id || '').substr(0,120); } catch (ignore) {}
  try { report.widget_path=String(window.location.pathname || '').substr(0,240); } catch (ignore2) {}
  return report;
 }
 function run() {
  var tvmw=plugin('watchStartupTVMW','TVMW'), nnavi=plugin('watchStartupNNavi','NNAVI');
  var report=collect(tvmw,nnavi);window.WATCH_BOOT_REPORT=report;
  // Only non-secret diagnostics go to the existing LAN event collector.
  transport=new Image();transport.src='http://192.168.0.146/event?component=watch-autoboot&report='+encodeURIComponent(JSON.stringify(report))+'&time='+new Date().getTime();
 }
 window.WatchBootProbe={collect:collect,run:run};
 if (window.addEventListener) { window.addEventListener('load',function () {window.setTimeout(run,4000);},false); }
}());
