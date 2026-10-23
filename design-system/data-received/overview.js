/* overview.js: shared by Original data received and the systems inventory. build_received.py inlines it.
   - The one tooltip: any [data-tip] element shows it on hover and on keyboard focus. Its text is the attribute,
     unless the page defines window.BS_TIP(key), which may return HTML for that key (Escape closes it).
   - Folders of data: a folder's button shows or hides its own files.
   - Step chips: "+n" shows the chips after the first three. */
(function(){
'use strict';
var tip=document.getElementById('tip'),tipFor=null;
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function showTip(el){
  var key=el.getAttribute('data-tip'),h=(window.BS_TIP&&window.BS_TIP(key))||(key&&key.indexOf('|')<0?'<p>'+esc(key)+'</p>':'');
  if(!h)return;
  if(tipFor&&tipFor!==el){tipFor.removeAttribute('aria-describedby');tipFor.classList.remove('is-tip')}
  tipFor=el;tip.innerHTML=h;tip.hidden=false;el.setAttribute('aria-describedby','tip');el.classList.add('is-tip');
  var r=el.getBoundingClientRect(),w=tip.offsetWidth,t=tip.offsetHeight,vw=document.documentElement.clientWidth;
  var x=Math.max(8,Math.min(r.left,vw-w-8)),y=r.bottom+6;
  if(y+t>window.innerHeight-8&&r.top-t-6>8)y=r.top-t-6;
  tip.style.transform='translate('+Math.round(x)+'px,'+Math.round(y)+'px)';
}
function hideTip(){if(tipFor){tipFor.removeAttribute('aria-describedby');tipFor.classList.remove('is-tip')}tipFor=null;tip.hidden=true}
window.BS_HIDE_TIP=hideTip;
document.addEventListener('mouseover',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');if(el&&el!==tipFor)showTip(el)});
document.addEventListener('mouseout',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');if(el&&el===tipFor&&!el.contains(e.relatedTarget)&&document.activeElement!==el)hideTip()});
document.addEventListener('focusin',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');if(el)showTip(el);else if(tipFor)hideTip()});
document.addEventListener('focusout',function(e){if(e.target===tipFor)hideTip()});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!tip.hidden){hideTip();e.stopImmediatePropagation()}},true);
window.addEventListener('scroll',function(){if(tipFor&&document.activeElement!==tipFor)hideTip()},{passive:true});

document.addEventListener('click',function(e){
  var f=e.target.closest('.fold');
  if(f){
    var open=f.getAttribute('aria-expanded')!=='true',d=f.getAttribute('data-dir');
    f.setAttribute('aria-expanded',String(open));
    Array.prototype.forEach.call(document.querySelectorAll('tr[data-in]'),function(tr){if(tr.getAttribute('data-in')===d)tr.hidden=!open});
    return;
  }
  var m=e.target.closest('.more');
  if(m){
    Array.prototype.forEach.call(m.parentNode.querySelectorAll('.step[hidden]'),function(s){s.hidden=false});
    var first=m.parentNode.querySelectorAll('.step')[3];
    m.remove();if(first)first.focus({preventScroll:true});
  }
});
})();
