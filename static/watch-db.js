// Shared with the service worker so turning a stop off also drops queued pushes.
const watchDB={
  async open(){return new Promise((resolve,reject)=>{
    const request=indexedDB.open('transit-notifications',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('settings');
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
  });},
  async get(key){const db=await this.open();return new Promise((resolve,reject)=>{
    const tx=db.transaction('settings','readonly'),request=tx.objectStore('settings').get(key);
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);tx.oncomplete=()=>db.close();
  });},
  async put(key,value){const db=await this.open();return new Promise((resolve,reject)=>{
    const tx=db.transaction('settings','readwrite');tx.objectStore('settings').put(value,key);
    tx.oncomplete=()=>{db.close();resolve();};tx.onerror=()=>{db.close();reject(tx.error);};
  });}
};
