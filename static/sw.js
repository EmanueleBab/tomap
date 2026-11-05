const SHELL_CACHE='transit-shell-v2';
importScripts('/static/watch-db.js');
self.addEventListener('install',event=>{
  event.waitUntil(caches.open(SHELL_CACHE).then(cache=>cache.addAll(['/static/offline.html','/static/icon-192.png'])).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',event=>event.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('transit-shell-')&&key!==SHELL_CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())
));
self.addEventListener('fetch',event=>{
  // Never cache positions, arrivals or map tiles as if they were live.
  if(event.request.mode==='navigate')event.respondWith(fetch(event.request).catch(()=>caches.match('/static/offline.html')));
});
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const stop=event.notification.data?.stop;
  event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async clients=>{
    const target=clients.find(client=>new URL(client.url).origin===self.location.origin);
    if(target){await target.focus();target.postMessage({type:'open-stop',stop});}
    else await self.clients.openWindow(stop?`/?stop=${encodeURIComponent(stop.id)}`:'/');
  }));
});
self.addEventListener('push',event=>{
  event.waitUntil((async()=>{
    let payload;try{payload=event.data.json();}catch{return;}
    const watches=await watchDB.get('watches')||[];
    const watch=watches.find(w=>w.stop.id===payload.stop?.id);
    // Drop arrivals queued before this stop was turned off or its settings changed.
    if(!watch?.enabled||watch.revision!==payload.revision||payload.arrival<=Date.now()/1000||Date.now()/1000-payload.sent_at>90)return;
    await self.registration.showNotification(payload.title,{body:payload.body,tag:payload.tag,
      icon:'/static/icon-192.png',badge:'/static/icon-192.png',data:{stop:payload.stop},renotify:false});
  })());
});
