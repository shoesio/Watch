const assert=require('node:assert/strict');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function focusNav(w,press,id){
 const target=w.document.getElementById('nav'+id),band=target.parentNode.id;
 assert.notEqual(target.style.display,'none','navigation item is visible: '+id);
 for(let i=0;i<40&&!w.document.querySelector('#navigation .focus');i++){press(38);await wait(12);}
 assert.ok(w.document.querySelector('#navigation .focus'),'Up reaches the fixed primary row');
 if(band!=='navigation'){
  press(40);await wait(12);
  if(band==='heroControls' && !w.document.querySelector('#heroControls .focus')){press(40);await wait(12);}
 }
 for(let i=0;i<22;i++)press(37);
 for(let i=0;i<22&&!target.className.includes('focus');i++)press(39);
 assert.ok(target.className.includes('focus'),'remote can reach '+id+' in '+band);
}
module.exports={focusNav};
