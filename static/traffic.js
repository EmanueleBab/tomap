/* Measured sensor locations, not inferred congestion or road geometry. */
(() => {
  const toggle=$('show-traffic'), key=$('traffic-key'), status=$('traffic-status');
  // Share Canvas hit testing with stops/vehicles so empty canvas areas don't
  // intercept clicks intended for traffic points on a lower pane.
  const renderer=transitRenderer;
  const layer=L.layerGroup(), points=new Map();
  const attribution='<a href="https://muoversiatorino.it/it/open-data/">Traffic: City of Turin / 5T</a>';
  let data=null, received=0, busy=false, lastAttempt=0, failed=false;
  const format=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Rome',hour:'2-digit',minute:'2-digit'});
  const timeLabel=t=>format.format(new Date(t*1000));
  const value=(n,unit)=>n==null?'Unavailable':`${Math.round(n).toLocaleString()} ${unit}`;
  function draw(){
    if(!toggle.checked)return;
    if(!data){status.textContent=failed?'Traffic unavailable. Retrying…':'Loading traffic…';return;}
    const now=data.server_time+(Date.now()-received)/1000;
    const stale=!data.end_time||now-data.end_time>900;
    const bounds=map.getBounds().pad(0.15), groups=new Map();
    for(const s of data.sensors){
      if(!bounds.contains([s.lat,s.lon]))continue;
      const id=`${s.lat},${s.lon}`;
      if(!groups.has(id))groups.set(id,[]);
      groups.get(id).push(s);
    }
    for(const [id,point] of points)if(!groups.has(id)){layer.removeLayer(point);points.delete(id);}
    for(const [id,sensors] of groups){
      const speeds=sensors.flatMap(s=>s.readings.map(r=>r.speed)).filter(n=>n!=null);
      const speed=speeds.length?Math.min(...speeds):null;
      const color=stale||speed==null?'#8b969f':speed<20?'#b74669':speed<40?'#c58120':'#168c87';
      const html=`<div class="popup-title"><b>Traffic</b>${stale?' · Old reading':''}</div>`+
        (data.end_time?`<div class="fine">${timeLabel(data.start_time)}–${timeLabel(data.end_time)} · ${ageText(now-data.end_time)}</div>`:'')+
        sensors.map(s=>`<div class="traffic-reading"><b>${escapeHtml(s.road)}</b>${s.direction?`<div class="fine">Direction: ${escapeHtml(s.direction)} (5T)</div>`:''}`+
          s.readings.map(r=>`<div>Average speed: ${value(r.speed,'km/h')}</div><div>Flow: ${value(r.flow,'vehicles/h')}</div>${r.vehicle_type!=='All'?`<div>${escapeHtml(r.vehicle_type)}</div>`:''}`).join('')+'</div>').join('');
      let point=points.get(id);
      if(!point){point=L.circleMarker([sensors[0].lat,sensors[0].lon],{renderer,radius:8,weight:2,color:'#fff',fillOpacity:0.9}).bindPopup(html,{maxWidth:300}).addTo(layer);points.set(id,point);}
      point.setStyle({fillColor:color});
      point.bringToBack();
      if(point._trafficHtml!==html){point.setPopupContent(html);point._trafficHtml=html;}
    }
    status.textContent=(!data.end_time?'Waiting for traffic readings':`${stale?'Old readings · ':''}${timeLabel(data.end_time)} · 5 min averages`)+((failed||data.error)?' · Connection lost':'');
  }
  async function refresh(){
    if(!toggle.checked||document.hidden||busy)return;
    if(Date.now()-lastAttempt<60000){draw();return;}
    lastAttempt=Date.now();busy=true;
    try{const response=await fetch('/api/traffic',{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error();data=await response.json();received=Date.now();failed=false;}
    catch{failed=true;}finally{busy=false;draw();}
  }
  function update(){
    key.hidden=!toggle.checked;
    try{localStorage.setItem('turin.traffic',String(toggle.checked));}catch{}
    if(toggle.checked){layer.addTo(map);map.attributionControl.addAttribution(attribution);draw();refresh();}
    else{map.removeLayer(layer);map.attributionControl.removeAttribution(attribution);}
  }
  try{toggle.checked=localStorage.getItem('turin.traffic')==='true';}catch{}
  toggle.addEventListener('change',update);map.on('moveend',draw);
  document.addEventListener('visibilitychange',refresh);
  setInterval(refresh,60000);update();
})();
