let locationWatch=null,locationMarker=null,accuracyCircle=null,centerLocation=true;
const locateButton=$('locate'),locationStatus=$('location-status');
locateButton.addEventListener('click',()=>{
  if(!window.isSecureContext){locationStatus.textContent='Open with HTTPS to use your location.';return;}
  if(!navigator.geolocation){locationStatus.textContent='Location is unavailable in this browser.';return;}
  centerLocation=true;
  if(locationMarker){map.setView(locationMarker.getLatLng(),16);centerLocation=false;return;}
  if(locationWatch!==null)return;
  locateButton.classList.add('loading');locationStatus.textContent='Finding your location…';
  locationWatch=navigator.geolocation.watchPosition(position=>{
    const {latitude,longitude,accuracy}=position.coords,point=[latitude,longitude];
    if(!locationMarker){
      accuracyCircle=L.circle(point,{radius:accuracy,color:'#2563eb',weight:1,fillOpacity:.08,interactive:false}).addTo(map);
      locationMarker=L.circleMarker(point,{radius:8,color:'#fff',weight:3,fillColor:'#2563eb',fillOpacity:1}).addTo(map).bindTooltip('You are here');
    }else{locationMarker.setLatLng(point);accuracyCircle.setLatLng(point).setRadius(accuracy);}
    if(centerLocation){map.setView(point,16);centerLocation=false;}
    locateButton.classList.remove('loading');locateButton.classList.add('active');locationStatus.textContent='';
  },error=>{
    navigator.geolocation.clearWatch(locationWatch);locationWatch=null;locateButton.classList.remove('loading');
    locationStatus.textContent=error.code===1?'Allow location access in your browser.':error.code===3?'Location timed out. Tap to retry.':'Location unavailable. Tap to retry.';
  },{enableHighAccuracy:true,maximumAge:10000,timeout:15000});
});
$('panel-toggle').addEventListener('click',()=>{
  const collapsed=document.querySelector('.panel').classList.toggle('collapsed');
  $('panel-toggle').setAttribute('aria-expanded',String(!collapsed));$('panel-chevron').textContent=collapsed?'⌃':'⌄';
});
function popupPadding(){
  const panel=document.querySelector('.panel').getBoundingClientRect(),mobile=matchMedia('(max-width:600px)').matches;
  document.documentElement.style.setProperty('--map-bottom-inset',mobile?`${panel.height}px`:'0px');
  const options={autoPanPaddingTopLeft:mobile?[12,12]:[panel.right+12,12],autoPanPaddingBottomRight:mobile?[12,panel.height+12]:[12,12]};
  Object.assign(stopPopup.options,options);
  for(const marker of markers.values())if(marker.getPopup())Object.assign(marker.getPopup().options,options);
}
map.on('popupopen',()=>{popupPadding();const popup=document.querySelector('.leaflet-popup');if(popup){/* Reapply padding on newly created popups. */ for(const marker of markers.values())if(marker.isPopupOpen())marker.getPopup().update();if(boardSelection)stopPopup.update();}});
new ResizeObserver(popupPadding).observe(document.querySelector('.panel'));
window.addEventListener('resize',popupPadding);
