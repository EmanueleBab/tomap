// Extra details load only for the current selection; route geometry is static.
map.createPane('routes');map.getPane('routes').style.zIndex=410;map.getPane('routes').style.pointerEvents='none';
const routeRenderer=L.canvas({pane:'routes',padding:.3});
const routeLayers=L.featureGroup().addTo(map);
let selection=null,selectionVersion=0,detailRequest=null,alertRequest=null,alertData=null;
const routeColors=['#126aa5','#b44725','#6a479b','#08775f','#a66800','#a23569'];
const pretty=value=>value==null||value===''?'Unknown':String(value).replaceAll('_',' ').toLowerCase();
function clearSelection(){
  selection=null;selectionVersion++;detailRequest?.abort();routeLayers.clearLayers();$('selection').hidden=true;
  focusedVehicle=null;render();refreshAlerts();
}
async function selectTransit(type,item){
  const same=selection?.type===type&&selection?.item.id===item.id&&selection?.item.route_id===item.route_id&&selection?.item.trip_id===item.trip_id;
  selection={type,item};if(same)return;
  const version=++selectionVersion;
  routeLayers.clearLayers();$('route-legend').replaceChildren();$('selection').hidden=false;
  $('selection-title').textContent=type==='vehicle'?`Line ${item.line} · vehicle ${item.label}`:type==='stop'?item.name:`Line ${item.line}`;
  $('vehicle-details').hidden=type!=='vehicle';$('vehicle-info').textContent=type==='vehicle'?'Loading vehicle details…':'';
  $('route-status').textContent='Loading route paths…';
  if(type==='vehicle'){focusedVehicle=item.id;render();refreshVehicleDetails();}
  refreshAlerts();
  const params=new URLSearchParams(type==='vehicle'?{trip_id:item.trip_id}:type==='stop'?{stop_id:item.id}:{route_id:item.route_id});
  try{
    const response=await fetch(`/api/geometry?${params}`,{signal:AbortSignal.timeout(20000)});
    const data=await response.json();if(version!==selectionVersion)return;
    if(!response.ok)throw Error(data.error||'Route paths unavailable');
    const colors=new Map();
    for(const path of data.paths){
      if(!colors.has(path.route_id))colors.set(path.route_id,{color:routeColors[colors.size%routeColors.length],line:path.line});
      const {color}=colors.get(path.route_id);
      L.polyline(path.points,{renderer:routeRenderer,color,weight:4,opacity:.8,interactive:false,smoothFactor:1.5}).addTo(routeLayers);
    }
    for(const {color,line} of colors.values()){
      const chip=document.createElement('span');chip.textContent=`Line ${line}`;chip.style.borderLeft=`4px solid ${color}`;$('route-legend').append(chip);
    }
    $('route-status').textContent=data.paths.length?'':'Route unavailable';
    if(!$('show-route').checked)map.removeLayer(routeLayers);
  }catch(error){if(version===selectionVersion)$('route-status').textContent=error.message;}
}
function rawDetails(title,value){
  if(!value)return '';
  return `<details class="raw-data"><summary>${escapeHtml(title)}</summary><pre>${escapeHtml(JSON.stringify(value,null,2))}</pre></details>`;
}
async function refreshVehicleDetails(){
  if(selection?.type!=='vehicle'||document.hidden)return;
  const selected=selection,version=selectionVersion;
  detailRequest?.abort();detailRequest=new AbortController();
  try{
    const response=await fetch(`/api/vehicles/${encodeURIComponent(selected.item.id)}/details`,{signal:detailRequest.signal,cache:'no-store'});
    const data=await response.json();if(version!==selectionVersion)return;
    if(!response.ok)throw Error(data.error||'Details unavailable');
    const v=data.vehicle,now=Date.now()/1000,stale=!v.timestamp||now-v.timestamp>120;
    const attrs=[['Destination',v.destination],['Speed',v.speed==null?null:`${v.speed} km/h`],
      ['Occupancy',v.occupancy?`${pretty(v.occupancy)}${v.occupancy_percentage!=null?` · ${v.occupancy_percentage}%`:''}${stale?' · stale':''}`:null],
      ['Wheelchair access',data.trip_update_fresh&&data.wheelchair?pretty(data.wheelchair):null],
      ['Registration',data.license_plate],['Traffic',v.congestion?pretty(v.congestion):null]];
    const element=$('vehicle-info');
    element.innerHTML=`<dl>${attrs.filter(([,value])=>value).map(([k,value])=>`<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(value)}</dd>`).join('')}</dl>`;
    if(v.trip_id!==selected.item.trip_id)selectTransit('vehicle',v);
  }catch(error){if(error.name!=='AbortError'&&version===selectionVersion)$('vehicle-info').textContent=error.message;}
}
function alertQuery(){
  if(!selection||$('alert-scope').value==='all')return '';
  const {type,item}=selection;
  return new URLSearchParams(type==='stop'?{stop_id:item.id}:type==='vehicle'?{route_id:item.route_id,trip_id:item.trip_id}:{route_id:item.route_id}).toString();
}
async function refreshAlerts(){
  if(document.hidden)return;
  alertRequest?.abort();const controller=new AbortController();alertRequest=controller;
  try{
    const response=await fetch(`/api/alerts?${alertQuery()}`,{signal:controller.signal,cache:'no-store'});
    if(!response.ok)throw Error('Cannot load alerts');
    const data=await response.json();if(controller!==alertRequest)return;
    alertData=data;$('alert-count').textContent=data.alerts.length;
    $('alert-status').textContent=data.error?'Alerts unavailable':data.fetched_at&&data.server_time-data.fetched_at>120?'Alerts may be out of date':'';
    renderAlerts();
  }catch(error){if(error.name!=='AbortError')$('alert-status').textContent='Alerts unavailable. Retrying…';}
}
function renderAlerts(){
  if(!$('alerts-menu').open||!alertData)return;
  const list=$('alert-list'),top=list.scrollTop;
  const opened=new Set([...list.querySelectorAll('details[open]')].map(d=>d.dataset.id));
  list.replaceChildren();
  for(const alert of alertData.alerts){
    const d=document.createElement('details');d.dataset.id=alert.id;d.open=opened.has(alert.id);
    d.innerHTML=`<summary>${escapeHtml(alert.title||'Service notice')}</summary><p class="fine">${escapeHtml(alert.timing)} · ${escapeHtml(pretty(alert.effect))} · ${escapeHtml(pretty(alert.severity))}</p><p>${escapeHtml(alert.description)}</p>`;
    if(/^https?:\/\//i.test(alert.url)){const link=document.createElement('a');link.href=alert.url;link.target='_blank';link.rel='noopener';link.textContent='GTT notice';d.append(link);}
    list.append(d);
  }
  if(!alertData.alerts.length)list.textContent='No current or upcoming notices published for this selection.';
  list.scrollTop=top;
}
$('clear-selection').addEventListener('click',clearSelection);
$('fit-route').addEventListener('click',()=>{
  if(!routeLayers.getLayers().length)return;
  const panel=document.querySelector('.panel').getBoundingClientRect(),mobile=matchMedia('(max-width:600px)').matches;
  map.fitBounds(routeLayers.getBounds(),{paddingTopLeft:mobile?[25,25]:[panel.right+25,25],paddingBottomRight:mobile?[25,panel.height+25]:[65,25],maxZoom:16});
});
$('show-route').addEventListener('change',()=>{$('show-route').checked?routeLayers.addTo(map):map.removeLayer(routeLayers);});
$('alert-scope').addEventListener('change',refreshAlerts);$('alerts-menu').addEventListener('toggle',renderAlerts);
setInterval(refreshVehicleDetails,5000);setInterval(refreshAlerts,30000);refreshAlerts();
