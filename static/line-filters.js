// Saved choices do not depend on which vehicles are currently in the live feed.
const lineFilter={
  key:'turin.savedLines.v1',selected:new Set(),saved:[],names:new Map(),signature:'',
  load(){
    try{
      const data=JSON.parse(localStorage.getItem(this.key)||'[]');
      if(Array.isArray(data))this.saved=data.filter(r=>r&&typeof r.id==='string'&&typeof r.line==='string').slice(0,500);
      for(const r of this.saved){this.selected.add(r.id);this.names.set(r.id,r.line);}
    }catch{/* A blocked store must not prevent filtering. */}
  },
  matches(vehicle){return !this.selected.size||this.selected.has(vehicle.route_id);},
  ingest(vehicles){
    for(const v of vehicles)if(v.route_id)this.names.set(v.route_id,v.line);
    this.draw();
  },
  draw(){
    const query=$('line-search').value.trim().toLowerCase();
    const rows=[...this.names].sort((a,b)=>a[1].localeCompare(b[1],undefined,{numeric:true}));
    const signature=JSON.stringify([rows,query]);
    if(signature!==this.signature){
      this.signature=signature;const list=$('line-options'),top=list.scrollTop;list.replaceChildren();
      for(const [id,line] of rows){
        if(query&&!line.toLowerCase().includes(query))continue;
        const label=document.createElement('label'),input=document.createElement('input'),text=document.createElement('span');
        input.type='checkbox';input.value=id;input.checked=this.selected.has(id);text.textContent=line;
        input.addEventListener('change',()=>{
          input.checked?this.selected.add(id):this.selected.delete(id);this.changed();
        });
        label.append(input,text);list.append(label);
      }
      if(!list.children.length)list.textContent=this.names.size?'No matching lines':'Loading lines…';
      list.scrollTop=top;
    }
    for(const input of $('line-options').querySelectorAll('input'))input.checked=this.selected.has(input.value);
    const names=[...this.selected].map(id=>this.names.get(id)||id).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
    $('line-summary').textContent=names.length?names.join(', '):'All lines';
    $('line-summary').title=names.length?`${names.length} selected: ${names.join(', ')}`:'All lines';
    $('lines-restore').hidden=!this.saved.length;
  },
  changed(){
    this.draw();$('lines-status').textContent='';render();
    if(this.selected.size===1){const id=[...this.selected][0];selectTransit('line',{route_id:id,line:this.names.get(id)||id});}
    else clearSelection();
  },
  clearTemporary(){this.selected.clear();this.draw();},
  async catalogue(){
    try{
      const response=await fetch('/api/catalogue/routes',{signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw Error('Lines loading');
      const routes=await response.json();
      for(const [id,row] of Object.entries(routes))if(['0','3'].includes(row.route_type))this.names.set(id,row.route_short_name||id);
      this.draw();
    }catch{setTimeout(()=>this.catalogue(),15000);}
  },
  init(){
    $('line-search').addEventListener('input',()=>this.draw());
    $('lines-all').addEventListener('click',()=>{this.selected.clear();this.changed();});
    $('lines-save').addEventListener('click',()=>{
      const saved=[...this.selected].map(id=>({id,line:this.names.get(id)||id}));
      try{localStorage.setItem(this.key,JSON.stringify(saved));this.saved=saved;this.draw();$('lines-status').textContent='Saved';}
      catch{$('lines-status').textContent='Could not save in this browser.';}
    });
    $('lines-restore').addEventListener('click',()=>{this.selected=new Set(this.saved.map(r=>r.id));this.changed();});
    this.draw();this.catalogue();
  }
};
lineFilter.load();
