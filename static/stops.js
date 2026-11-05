// Stop boards are independent of vehicle filters: scheduled vehicles may not
// yet have a position in the live feed.
const stopMarkers=new Map();
let stopRequest=null, stopTimer=null, boardSelection=null, boardData=null, boardReceivedAt=0, boardError=false, boardElement=null;
let visibleStops=[], savedStops=[];
const SAVED_KEY='turin.savedStops.v1';
try{
  const stored=JSON.parse(localStorage.getItem(SAVED_KEY)||'[]');
  if(Array.isArray(stored))savedStops=stored.filter(s=>s&&typeof s.id==='string'&&typeof s.name==='string'&&Number.isFinite(s.lat)&&Number.isFinite(s.lon)&&Math.abs(s.lat)<=90&&Math.abs(s.lon)<=180);
}catch(error){/* A blocked or invalid store must not prevent the map loading. */}
const stopPopup=L.popup({className:'stop-popup',maxWidth:340,minWidth:270,maxHeight:230});
function isSaved(id){return savedStops.some(s=>s.id===id);}
function saveChanged(){
  try{localStorage.setItem(SAVED_KEY,JSON.stringify(savedStops));$('saved-note').textContent='';}
  catch(error){$('saved-note').textContent='Browser storage unavailable. Saved for this session only.';}
  renderSavedMenu();syncStopMarkers();updateSaveButton();
}
function toggleSaved(stop){
  if(isSaved(stop.id))savedStops=savedStops.filter(s=>s.id!==stop.id);
  else savedStops.push({id:stop.id,name:stop.name,lat:stop.lat,lon:stop.lon,code:stop.code||''});
  saveChanged();
}
function renderSavedMenu(){
  $('saved-count').textContent=String(savedStops.length);
  const list=$('saved-list');list.replaceChildren();
  if(!savedStops.length){const item=document.createElement('li');item.textContent='Open a stop and press Save stop.';list.append(item);}
  for(const stop of savedStops){
    const item=document.createElement('li'),open=document.createElement('button'),remove=document.createElement('button');
    open.textContent=stop.name;open.className='saved-stop-open';
    open.addEventListener('click',()=>{$('show-stops').checked=true;map.setView([stop.lat,stop.lon],16,{animate:false});openStop(stop);loadStops();});
    remove.textContent='Remove';remove.className='saved-stop-remove';remove.setAttribute('aria-label',`Remove saved stop ${stop.name}`);
    remove.addEventListener('click',()=>toggleSaved(stop));item.append(open,remove);list.append(item);
  }
}
function updateSaveButton(){
  const button=boardElement?.querySelector('[data-save-stop]');
  if(!button||!boardSelection)return;
  const saved=isSaved(boardSelection.id);
  button.textContent=saved?'Unsave stop':'Save stop';button.setAttribute('aria-pressed',String(saved));
}
function vehicleForRow(row){
  const vehicles=snapshot?.vehicles||[];
  return vehicles.find(v=>v.trip_id===row.trip_id&&v.start_date===row.service_date&&(!row.vehicle_id||v.id===row.vehicle_id));
}
function renderBoard(){
  if(!boardSelection||!boardData||!boardElement)return;
  // Keep the popup and its scroll container mounted across countdowns and feed
  // updates. Keyed rows also preserve keyboard focus on vehicle buttons.
  const scroller=stopPopup.getElement()?.querySelector('.leaflet-popup-content');
  const scrollTop=scroller?.scrollTop||0;
  const now=boardData.server_time+(Date.now()-boardReceivedAt)/1000;
  const body=boardElement.querySelector('tbody');
  const existing=new Map([...body.children].map(row=>[row.dataset.key,row]));
  boardData.arrivals.forEach((r,index)=>{
    const key=JSON.stringify([r.trip_id,r.service_date,r.sequence]);
    let row=existing.get(key);
    if(!row){row=document.createElement('tr');row.dataset.key=key;row.innerHTML='<td><b></b><small></small><button class="vehicle-link" type="button"></button><small class="vehicle-unavailable"></small></td><td class="planned-time"></td><td class="live-time"></td>';}
    existing.delete(key);
    if(body.children[index]!==row)body.insertBefore(row,body.children[index]||null);
    row.querySelector('b').textContent=r.line;
    row.querySelector('small').textContent=r.destination;
    const vehicle=vehicleForRow(r),button=row.querySelector('.vehicle-link'),unavailable=row.querySelector('.vehicle-unavailable');
    button.hidden=!vehicle;unavailable.hidden=Boolean(vehicle);
    if(vehicle){
      button.textContent=`Vehicle ${vehicle.label} · show on map`;
      button.onclick=()=>{if(!focusVehicle(vehicle.id)){boardElement.querySelector('.board-message').textContent='This vehicle is no longer on the map.';fetchBoard();}};
    }else unavailable.textContent=r.vehicle?`Vehicle ${r.vehicle} · location unavailable`:'Vehicle location unavailable';
    const old=r.updated_at&&now-r.updated_at>boardData.stale_seconds;
    row.querySelector('.planned-time').textContent=arrivalTime(r.planned,now)+(r.approximate?' (approx.)':'');
    row.querySelector('.live-time').textContent=r.live==null?r.status:old?'Estimate stale':r.live<now?'Updating…':arrivalTime(r.live,now);
  });
  for(const row of existing.values())row.remove();
  boardElement.querySelector('.board-message').textContent=boardError?'Connection lost. Showing last results; retrying.':boardData.error||'';
  boardElement.querySelector('.board-empty').textContent=boardData.arrivals.length?'':'No scheduled arrivals in the next 90 minutes.';
  if(typeof updateNotificationLines==='function')updateNotificationLines(boardElement,boardData.arrivals);
  if(scroller)scroller.scrollTop=scrollTop;
}
async function fetchBoard(){
  const selected=boardSelection;
  if(!selected||document.hidden)return;
  try{
    const response=await fetch(`/api/stops/${encodeURIComponent(selected.id)}/arrivals`,{cache:'no-store',signal:AbortSignal.timeout(12000)});
    const data=await response.json();
    if(boardSelection!==selected)return;
    if(!response.ok)throw Error(data.error||'Unable to load arrivals');
    boardData=data;boardReceivedAt=Date.now();boardError=false;renderBoard();
  }catch(error){
    if(boardSelection!==selected)return;
    boardError=true;
    if(boardData)renderBoard();else if(boardElement)boardElement.querySelector('.board-message').textContent='Arrivals unavailable. Retrying automatically.';
  }
}
function openStop(stop){
  // Closing an earlier popup fires popupclose synchronously.
  map.closePopup();
  boardSelection=stop;boardData=null;boardError=false;
  selectTransit('stop',stop);
  boardElement=document.createElement('div');boardElement.className='stop-board';
  boardElement.innerHTML=`<b>${escapeHtml(stop.name)}</b><button type="button" class="save-stop" data-save-stop>Save stop</button><p class="board-message" role="status">Loading arrivals…</p><table><thead><tr><th>Line / destination</th><th>Planned</th><th>Live estimate</th></tr></thead><tbody></tbody></table><p class="board-empty"></p>`;
  boardElement.querySelector('[data-save-stop]').addEventListener('click',()=>toggleSaved(stop));
  updateSaveButton();
  if(typeof mountStopNotifications==='function')mountStopNotifications(boardElement,stop);
  stopPopup.setLatLng([stop.lat,stop.lon]).setContent(boardElement).openOn(map);
  // Prevent wheel/touch scrolling in the board from zooming or dragging the map.
  L.DomEvent.disableScrollPropagation(boardElement);
  L.DomEvent.disableClickPropagation(boardElement);
  fetchBoard();
}
map.on('popupclose',event=>{if(event.popup===stopPopup){boardSelection=null;boardData=null;boardElement=null;}});
function syncStopMarkers(){
  const bounds=map.getBounds(),desired=new Map();
  if($('show-stops').checked){
    if(map.getZoom()>=13)for(const stop of visibleStops)desired.set(stop.id,stop);
    for(const stop of savedStops)if(bounds.contains([stop.lat,stop.lon]))desired.set(stop.id,stop);
  }
  for(const [id,marker] of stopMarkers){if(!desired.has(id)){map.removeLayer(marker);stopMarkers.delete(id);}}
  for(const stop of desired.values()){
    const saved=isSaved(stop.id),style={radius:saved?7:5,color:saved?'#493a00':'#444',weight:2,fillColor:saved?'#ffd85a':'white',fillOpacity:1};
    let marker=stopMarkers.get(stop.id);
    if(!marker){
      marker=L.circleMarker([stop.lat,stop.lon],{renderer:transitRenderer,...style}).addTo(map);
      marker.on('click',()=>openStop(stop));marker.bindTooltip(escapeHtml(stop.name),{direction:'top'});stopMarkers.set(stop.id,marker);
    }
    if(marker._saved!==saved){marker.setStyle(style);marker._saved=saved;}
  }
  for(const marker of markers.values())marker.bringToFront();
}
async function loadStops(){
  stopRequest?.abort();
  if(!$('show-stops').checked||map.getZoom()<13){
    visibleStops=[];syncStopMarkers();
    $('stops-hint').textContent=$('show-stops').checked?'Zoom in for all stops. Saved stops are highlighted.':'Stops hidden.';
    if(boardSelection&&!$('show-stops').checked)map.closePopup(stopPopup);
    return;
  }
  const controller=new AbortController();stopRequest=controller;
  const bounds=map.getBounds();
  const query=[bounds.getSouth(),bounds.getWest(),bounds.getNorth(),bounds.getEast()].join(',');
  try{
    const response=await fetch(`/api/stops?bounds=${encodeURIComponent(query)}`,{signal:controller.signal});
    const data=await response.json();
    if(controller!==stopRequest)return;
    if(!response.ok)throw Error(data.error||'Stops unavailable');
    visibleStops=data.stops;syncStopMarkers();
    $('stops-hint').textContent='Click a stop for arrivals. Saved stops are highlighted.';
  }catch(error){
    if(error.name==='AbortError')return;
    $('stops-hint').textContent='Stops loading or unavailable. Retrying…';
  }
}
map.on('moveend',()=>{clearTimeout(stopTimer);stopTimer=setTimeout(loadStops,200);});
$('show-stops').addEventListener('change',loadStops);
setInterval(()=>{if(!document.hidden){fetchBoard();if(!stopMarkers.size)loadStops();}},5000);
setInterval(()=>{if(!document.hidden)renderBoard();},1000);
renderSavedMenu();loadStops();
