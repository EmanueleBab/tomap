/* Real observations only: no simulated positions or interpolated journeys. */
const $ = id => document.getElementById(id);
const map = L.map('map', {zoomControl:false}).setView([45.0703,7.6869],13);
map.createPane('transit');map.getPane('transit').style.zIndex=450;
const transitRenderer=new TransitCanvas({pane:'transit',padding:0.3,tolerance:4});
L.control.zoom({position:'topright'}).addTo(map);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom:19, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);
const markers = new Map();
let mode='all', snapshot=null, browserError=false, receivedAt=0;
let focusedVehicle=null;
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ageText = seconds => seconds < 60 ? `${Math.max(0,Math.floor(seconds))}s ago` : `${Math.floor(seconds/60)}m ago`;
const localTime = new Intl.DateTimeFormat('en-GB', {timeZone:'Europe/Rome',hour:'2-digit',minute:'2-digit',second:'2-digit'});
function arrivalTime(timestamp, now){
  if(timestamp == null) return 'Unavailable';
  const delta=Math.round(timestamp-now), abs=Math.abs(delta);
  const duration=abs<60?`${abs}s`:`${Math.floor(abs/60)}m ${abs%60}s`;
  return `${localTime.format(new Date(timestamp*1000))} · ${delta>=0?`in ${duration}`:`${duration} ago`}`;
}
function render(updateMarkers=true){
  if(!snapshot) return;
  const now=snapshot.server_time+(Date.now()-receivedAt)/1000;
  const visible=snapshot.vehicles.filter(v=>(mode==='all'||v.mode===mode)&&lineFilter.matches(v)&&(! $('vehicle').value.trim()||`${v.id} ${v.label}`.toLowerCase().includes($('vehicle').value.trim().toLowerCase())));
  const ids=new Set(visible.map(v=>v.id));
  for(const [id,marker] of markers){if(!ids.has(id)){map.removeLayer(marker);markers.delete(id);}}
  for(const v of visible){
    let marker=markers.get(v.id);
    if(!updateMarkers&&!marker?.isPopupOpen())continue;
    const timestamp=v.timestamp||snapshot.feed_timestamp;
    const stale=!timestamp||now-timestamp>snapshot.stale_seconds||!snapshot.fetched_at||now-snapshot.fetched_at>snapshot.stale_seconds;
    const styleKey=`${v.line}|${v.mode}|${stale}|${focusedVehicle===v.id}|${v.bearing}`;

    const popup=`<div class="popup-title"><b>Line ${escapeHtml(v.line)}</b> · ${escapeHtml(v.mode)}</div><div class="popup-line">Vehicle ${escapeHtml(v.label)}${v.label!==v.id?` (${escapeHtml(v.id)})`:''}</div>${v.destination?`<div class="popup-line">To ${escapeHtml(v.destination)}</div>`:''}<div class="popup-line">${v.timestamp?'Position': 'Feed'}: ${timestamp?ageText(now-timestamp):'time unknown'}${stale?' · stale':''}</div><div class="popup-line">Occupancy: ${v.occupancy?escapeHtml(v.occupancy.toLowerCase().replaceAll('_',' ')):'Unknown'}${v.occupancy_percentage!=null?` (${v.occupancy_percentage}%)`:''}${stale?' · stale observation':''}</div>${v.speed!==null?`<div class="popup-line">${v.speed} km/h</div>`:''}`;
    if(!marker){
      marker=new VehicleBadge([v.lat,v.lon],{renderer:transitRenderer,...badgeStyle(v,stale,focusedVehicle===v.id)}).addTo(map).bindPopup(popup);
      marker.on('popupopen',()=>{const current=snapshot?.vehicles.find(item=>item.id===v.id);if(current)selectTransit('vehicle',current);});
      markers.set(v.id,marker);
    }
    if(updateMarkers){
      const old=marker.getLatLng();if(old.lat!==v.lat||old.lng!==v.lon)marker.setLatLng([v.lat,v.lon]);
      if(marker._styleKey!==styleKey){marker.setStyle(badgeStyle(v,stale,focusedVehicle===v.id));marker._styleKey=styleKey;}
    }
    if(updateMarkers||marker.isPopupOpen())marker.setPopupContent(popup);
  }
  $('count').textContent=`${visible.length} ${visible.length===1?'vehicle':'vehicles'}`;
  const feedOld=!snapshot.feed_timestamp||now-snapshot.feed_timestamp>snapshot.stale_seconds;
  const failed=browserError||snapshot.error;
  $('status').classList.toggle('warning',Boolean(failed||feedOld));
  $('status').textContent=browserError?'Connection lost. Retrying automatically.':snapshot.error||(!snapshot.fetched_at?'Waiting for GTT positions…':feedOld?'GTT positions are old or their time is unknown.':!snapshot.vehicles.length?'GTT currently reports no positions.':!visible.length?'No vehicles match these filters.':'');
  $('freshness').textContent=`Feed: ${snapshot.feed_timestamp?ageText(now-snapshot.feed_timestamp):'time unknown'}${snapshot.metadata_ready?'':' · Line details loading or unavailable'}`;
}
function updateLines(){lineFilter.ingest(snapshot?.vehicles||[]);}
function focusVehicle(id){
  const vehicle=snapshot?.vehicles.find(v=>v.id===id);
  if(!vehicle)return false;
  mode='all';lineFilter.clearTemporary();$('vehicle').value='';focusedVehicle=id;
  document.querySelectorAll('[data-mode]').forEach(b=>{const active=b.dataset.mode==='all';b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  updateLines();render();
  map.closePopup();map.setView([vehicle.lat,vehicle.lon],17,{animate:false});
  const marker=markers.get(id);marker.bringToFront();marker.openPopup();
  return true;
}
let refreshTimer=null, refreshBusy=false;
async function refresh(){
  if(refreshBusy)return;
  clearTimeout(refreshTimer);
  refreshBusy=true;
  try{
  if(!document.hidden){
    try{
      const response=await fetch('/api/vehicles',{cache:'no-store',signal:AbortSignal.timeout(15000)});
      if(!response.ok) throw Error('Feed request failed');
      snapshot=await response.json();receivedAt=Date.now();browserError=false;updateLines();render();
    }catch(error){browserError=true;if(snapshot)render();else{$('status').textContent='Cannot connect. Retrying automatically.';$('status').classList.add('warning');}}
  }
  }finally{
    refreshBusy=false;
    refreshTimer=setTimeout(refresh,(snapshot?.poll_seconds||5)*1000);
  }
}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
window.addEventListener('pageshow',()=>refresh());
window.addEventListener('online',()=>refresh());
document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{
  mode=button.dataset.mode;
  document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  if(snapshot){updateLines();render();}
}));
$('vehicle').addEventListener('input',render);
new ResizeObserver(()=>map.invalidateSize()).observe(document.querySelector('.panel'));
$('reset').addEventListener('click',()=>map.setView([45.0703,7.6869],13));
setInterval(()=>{if(!document.hidden)render(false);},1000);
lineFilter.init();
refresh();
