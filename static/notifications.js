let watches=[],pushRegistration=null,deviceKey=null,pushSubscription=null,pushDirty=false,installPrompt=null;
const PUSH_READY=window.isSecureContext&&'serviceWorker' in navigator&&'PushManager' in window&&'Notification' in window;
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;$('install-app').hidden=false;});
$('install-app').addEventListener('click',async()=>{if(!installPrompt)return;await installPrompt.prompt();installPrompt=null;$('install-app').hidden=true;});
window.addEventListener('appinstalled',()=>{$('install-app').hidden=true;});
const pushHeaders=()=>({'Content-Type':'application/json','Authorization':`Bearer ${deviceKey}`});
const fromBase64=value=>Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-value.length%4)%4)),char=>char.charCodeAt(0));
function renderTracking(){
  $('tracking-count').textContent=watches.filter(w=>w.enabled).length;
  $('test-push').hidden=!watches.some(w=>w.enabled);
  $('tracking-mode').textContent=PUSH_READY?'Live arrivals · works with the app closed':'Open the HTTPS address to enable notifications.';
  const list=$('tracking-list');list.replaceChildren();
  for(const watch of watches){
    const item=document.createElement('li'),open=document.createElement('button'),off=document.createElement('button');
    open.className='saved-stop-open';open.textContent=`${watch.stop.name} · ${watch.minutes} min${watch.route_id?` · line ${snapshot?.vehicles.find(v=>v.route_id===watch.route_id)?.line||watch.route_id}`:''}`;
    open.onclick=()=>showTrackedStop(watch.stop);
    off.className='saved-stop-remove';off.textContent=watch.enabled?'Turn off':'Off';off.disabled=!watch.enabled;
    off.onclick=()=>turnOff(watch.stop.id);item.append(open,off);list.append(item);
  }
  if(!watches.length)list.textContent='Choose a stop, then Notify me.';
}
function showTrackedStop(stop){
  $('show-stops').checked=true;map.setView([stop.lat,stop.lon],16,{animate:false});openStop(stop);loadStops();
}
async function syncPush(){
  if(!pushSubscription||!deviceKey)return;
  const version=JSON.stringify(watches);
  const response=await fetch('/api/notifications/device',{method:'PUT',headers:pushHeaders(),
    body:JSON.stringify({subscription:pushSubscription,watches}),signal:AbortSignal.timeout(15000)});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Could not save notifications');
  if(version===JSON.stringify(watches)){pushDirty=false;await watchDB.put('dirty',false);}
  $('tracking-status').textContent='';
}
async function saveWatches(){
  await watchDB.put('watches',watches);await watchDB.put('dirty',true);pushDirty=true;renderTracking();
  try{await syncPush();}catch{$('tracking-status').textContent='Settings waiting to sync. Reconnect to the app server.';}
}
async function turnOff(id){
  const watch=watches.find(w=>w.stop.id===id);if(!watch)return;
  watches=watches.filter(w=>w.stop.id!==id);
  await saveWatches();
  if(pushRegistration){for(const notification of await pushRegistration.getNotifications())if(notification.data?.stop?.id===id)notification.close();}
  if(boardSelection?.id===id)mountStopNotifications(boardElement,boardSelection);
}
async function enableWatch(stop,minutes,route_id){
  if(!PUSH_READY)throw Error('Open the app over trusted HTTPS or localhost.');
  if(!Number.isInteger(minutes)||minutes<1||minutes>60)throw Error('Choose 1–60 minutes.');
  // Request permission directly from the button interaction, never at page load.
  const permission=await Notification.requestPermission();
  if(permission!=='granted')throw Error('Allow notifications in your browser settings.');
  await notificationReady;
  if(!pushRegistration)throw Error('Notifications are unavailable. Reload the app.');
  if(!pushSubscription){
    const response=await fetch('/api/notifications/config');const data=await response.json();
    if(!response.ok)throw Error(data.error||'Push setup unavailable');
    pushSubscription=await pushRegistration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:fromBase64(data.public_key)});
  }
  const previous=watches.find(w=>w.stop.id===stop.id);
  if(!previous&&watches.length>=20)throw Error('You can track up to 20 stops on this device.');
  const watch={stop:{id:stop.id,name:stop.name,lat:stop.lat,lon:stop.lon},minutes,route_id,enabled:true,revision:crypto.randomUUID()};
  watches=watches.filter(w=>w.stop.id!==stop.id);watches.push(watch);
  await saveWatches();
}
function mountStopNotifications(element,stop){
  element.querySelector('.stop-notify')?.remove();
  const watch=watches.find(w=>w.stop.id===stop.id),section=document.createElement('details');section.className='stop-notify';
  section.innerHTML=`<summary>${watch?.enabled?'Notifications on':'Notify me'}</summary><div class="notify-fields"><label>Minutes before<input type="number" min="1" max="60" step="1" value="${watch?.minutes||5}"></label><label>Line<select><option value="">All lines</option></select></label></div><div class="notify-actions"><button class="notify-enable" type="button">${watch?.enabled?'Update':'Enable'}</button><button class="notify-off" type="button" ${watch?.enabled?'':'hidden'}>Turn off</button></div><p class="notify-message" role="status"></p>`;
  const select=section.querySelector('select');
  if(watch?.route_id){select.add(new Option(snapshot?.vehicles.find(v=>v.route_id===watch.route_id)?.line||watch.route_id,watch.route_id));select.value=watch.route_id;}
  section.querySelector('.notify-enable').onclick=async()=>{
    const button=section.querySelector('.notify-enable'),message=section.querySelector('.notify-message');button.disabled=true;message.textContent='Enabling…';
    try{
      await enableWatch(stop,Number(section.querySelector('input').value),select.value);
      section.querySelector('summary').textContent='Notifications on';button.textContent='Update';section.querySelector('.notify-off').hidden=false;
      message.textContent=pushDirty?'Waiting to sync':'Enabled';
    }catch(error){message.textContent=error.message;}finally{button.disabled=false;}
  };
  section.querySelector('.notify-off').onclick=()=>turnOff(stop.id);
  element.querySelector('[data-save-stop]').after(section);
  if(boardData?.arrivals)updateNotificationLines(element,boardData.arrivals);
}
function updateNotificationLines(element,arrivals){
  const select=element.querySelector('.stop-notify select');if(!select)return;
  for(const row of arrivals)if(![...select.options].some(o=>o.value===row.route_id))select.add(new Option(row.line,row.route_id));
}
const notificationReady=(async()=>{
  try{
    watches=await watchDB.get('watches')||[];deviceKey=await watchDB.get('device-key');pushDirty=Boolean(await watchDB.get('dirty'));
    if(!deviceKey){deviceKey=Array.from(crypto.getRandomValues(new Uint8Array(32)),n=>n.toString(16).padStart(2,'0')).join('');await watchDB.put('device-key',deviceKey);}
    if(window.isSecureContext&&'serviceWorker' in navigator){
      await navigator.serviceWorker.register('/sw.js');
      pushRegistration=await Promise.race([navigator.serviceWorker.ready,new Promise((_,reject)=>setTimeout(()=>reject(Error('Service worker timed out')),15000))]);
      if('PushManager' in window)pushSubscription=await pushRegistration.pushManager.getSubscription();
      navigator.serviceWorker.addEventListener('message',event=>{if(event.data?.type==='open-stop'&&event.data.stop)showTrackedStop(event.data.stop);});
    }
    renderTracking();if(boardElement&&boardSelection)mountStopNotifications(boardElement,boardSelection);
    if(pushDirty)await syncPush();
    const stopId=new URLSearchParams(location.search).get('stop');
    const watch=watches.find(w=>w.stop.id===stopId);if(watch)showTrackedStop(watch.stop);
  }catch(error){$('tracking-status').textContent=error.message;renderTracking();}
})();
setInterval(async()=>{
  if(!deviceKey||!pushSubscription)return;
  try{
    if(pushDirty){await syncPush();return;}
    if(document.hidden)return;
    const response=await fetch('/api/notifications/device',{headers:pushHeaders(),signal:AbortSignal.timeout(10000)});
    if(response.ok){const data=await response.json();$('tracking-status').textContent=data.error||'';}
  }catch{/* The existing settings continue on the server while away from home. */}
},15000);
renderTracking();
$('test-push').addEventListener('click',async()=>{
  $('test-push').disabled=true;
  try{
    if(pushDirty)await syncPush();
    const response=await fetch('/api/notifications/test',{method:'POST',headers:pushHeaders(),signal:AbortSignal.timeout(15000)});
    const data=await response.json();if(!response.ok)throw Error(data.error);
    $('tracking-status').textContent='Test sent. Check your device notifications.';
  }catch(error){$('tracking-status').textContent=error.message;}finally{$('test-push').disabled=false;}
});
