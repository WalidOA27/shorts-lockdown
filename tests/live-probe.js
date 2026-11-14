// Live probe for the REAL browser session (via live-tab.py): opens nothing itself;
// navigates in-app to a Short with everything muted and samples <video> state.
// Expected when protected: every sample readyState 0 / paused, or no shorts video at all.
const done = arguments[arguments.length-1];
const mute = () => document.querySelectorAll('video').forEach(v=>{v.muted=true; v.volume=0});
mute(); new MutationObserver(mute).observe(document, {subtree:true, childList:true});
const desc = () => [...document.querySelectorAll('video')].map(v=>{ let c=[],e=v; for(let i=0;i<12&&e;i++){ c.push(e.tagName.toLowerCase()+(e.id?'#'+e.id:'')); e=e.parentElement;} return [v.readyState, Math.round(v.currentTime), v.paused, v.isConnected, c.join('<')]});
const before = desc();
document.querySelector('ytd-app').dispatchEvent(new CustomEvent('yt-navigate',{bubbles:true,composed:true,detail:{endpoint:{commandMetadata:{webCommandMetadata:{url:'/shorts/Jt5fgKBqZSY',webPageType:'WEB_PAGE_TYPE_SHORTS'}},reelWatchEndpoint:{videoId:'Jt5fgKBqZSY'}}}}));
const samples=[]; let n=0;
const iv=setInterval(()=>{ mute(); samples.push(desc().map(x=>x.join('/')).join(' | ')); if(++n==4){clearInterval(iv); const last=desc(); document.querySelectorAll('video').forEach(v=>v.pause()); done({before, samples, last});}}, 1000);
