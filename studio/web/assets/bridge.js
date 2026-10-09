/* The hosted interface talks only to the user's loopback engine. */
const Bridge = (() => {
 const local = ['localhost','127.0.0.1'].includes(location.hostname);
 const base = local ? '' : 'http://127.0.0.1:7861';
 let token = '', popup;try{token=localStorage.getItem('after-bridge-token')||'';}catch{}
 const cache = new Map();
 async function fetchLocal(path, options={}) {
  if(!path.startsWith('/api/') && !path.startsWith('/media/') && !path.startsWith('/uploads/')) throw new Error('Chemin local invalide.');
  if(!local && !token) throw new Error('Connecte ton Mac pour commencer.');
  const headers = new Headers(options.headers);
  if(!local) headers.set('Authorization','Bearer '+token);
  let response;
  try {response=await fetch(base+path,{...options,headers,signal:options.signal||AbortSignal.timeout(15000),credentials:'omit',...(!local?{targetAddressSpace:'loopback'}:{})});}
  catch (error) {console.warn('AFTER local connection:',error.name,error.message);throw new Error(error.name==='TimeoutError'?'Le navigateur n’a pas répondu à la connexion locale. Autorise l’accès au réseau local ou ouvre directement le studio sur ce Mac.':'Moteur inaccessible. Lance AFTER sur ton Mac et autorise l’accès au réseau local dans le navigateur.');}
  if(response.status===401){token='';try{localStorage.removeItem('after-bridge-token');}catch{}}
  return response;
 }
 async function media(path){
  if(local)return path;
  if(cache.has(path))return cache.get(path);
  const response=await fetchLocal(path);
  if(!response.ok)throw new Error('Création inaccessible. Reconnecte ton Mac.');
  const url=URL.createObjectURL(await response.blob());cache.set(path,url);return url;
 }
 function setToken(value){token=value.trim();try{localStorage.setItem('after-bridge-token',token);}catch{}window.dispatchEvent(new Event('bridge-connected'));}
 function connect(){
  if(local)return;
  popup=window.open(base+'/?pair_origin='+encodeURIComponent(location.origin),'after-pair','popup,width=600,height=650');
  if(!popup)window.dispatchEvent(new CustomEvent('bridge-error',{detail:'Autorise les pop-ups pour connecter ton Mac.'}));
 }
 window.addEventListener('message',event=>{
  if(local||event.origin!==base||event.source!==popup||event.data?.type!=='after-paired'||typeof event.data.token!=='string')return;
  setToken(event.data.token);
 });
 return {local,fetch:fetchLocal,media,connect,setToken,get paired(){return local||!!token;}};
})();
