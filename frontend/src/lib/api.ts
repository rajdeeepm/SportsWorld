const BASE=(import.meta as any).env?.VITE_API_BASE ?? '/api';
export async function api<T>(path:string,init?:RequestInit):Promise<T>{const r=await fetch(`${BASE}${path}`,{...init,headers:{'Content-Type':'application/json',...(init?.headers||{})}});if(!r.ok){const text=await r.text();throw new Error(`${r.status}: ${text}`)}return r.json() as Promise<T>}
export const getJSON=<T,>(path:string)=>api<T>(path);
export const postJSON=<T,>(path:string,body:any)=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export function downloadJSON(name:string,data:any){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download=name;a.click();URL.revokeObjectURL(a.href)}
