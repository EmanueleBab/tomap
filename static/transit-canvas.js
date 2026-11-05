// Leaflet 1.9.4 Canvas extension: retain the rounded route badges without a DOM
// marker per vehicle. Stops and vehicles share a canvas so hit testing works
// through empty space, with vehicles drawn last above the stop circles.
const TransitCanvas=L.Canvas.extend({
  _updateVehicle(layer){
    if(!this._drawing||layer._empty())return;
    const ctx=this._ctx,p=layer._point,o=layer.options,w=o.badgeWidth,h=26;
    ctx.save();ctx.globalAlpha=1;
    if(Number.isFinite(o.bearing)){
      ctx.save();ctx.translate(p.x,p.y);ctx.rotate(o.bearing*Math.PI/180);
      const distance=Math.max(w/2,13)+7;
      ctx.beginPath();ctx.moveTo(0,-distance-6);ctx.lineTo(-4,-distance+1);ctx.lineTo(4,-distance+1);ctx.closePath();
      ctx.fillStyle=o.badgeColor;ctx.fill();ctx.strokeStyle='white';ctx.lineWidth=1;ctx.stroke();ctx.restore();
    }
    if(o.focused){ctx.strokeStyle='#ffcc00';ctx.lineWidth=4;ctx.beginPath();ctx.roundRect(p.x-w/2-5,p.y-h/2-5,w+10,h+10,10);ctx.stroke();}
    ctx.beginPath();ctx.roundRect(p.x-w/2,p.y-h/2,w,h,8);
    ctx.fillStyle=o.badgeColor;ctx.shadowColor='#102c3d60';ctx.shadowBlur=5;ctx.shadowOffsetY=2;ctx.fill();
    ctx.shadowColor='transparent';ctx.lineWidth=2;ctx.strokeStyle='white';ctx.stroke();
    ctx.fillStyle='white';ctx.font='750 12px system-ui, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(o.label,p.x,p.y+.5);
    ctx.restore();
  }
});
const VehicleBadge=L.CircleMarker.extend({
  _updatePath(){this._renderer._updateVehicle(this);},
  _containsPoint(point){return Boolean(this._point&&Math.abs(point.x-this._point.x)<=this.options.badgeWidth/2+3&&Math.abs(point.y-this._point.y)<=16);}
});
const badgeMeasure=document.createElement('canvas').getContext('2d');
badgeMeasure.font='750 12px system-ui, sans-serif';
function badgeStyle(vehicle,stale,focused){
  const width=Math.max(30,Math.ceil(badgeMeasure.measureText(vehicle.line).width)+12);
  return {label:vehicle.line,badgeWidth:width,radius:Math.max(width/2+16,30),focused,bearing:vehicle.bearing,
    badgeColor:stale?'#89939a':vehicle.mode==='tram'?'#bd4c29':vehicle.mode==='bus'?'#067d99':'#5d627c'};
}
