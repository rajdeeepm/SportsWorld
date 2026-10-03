export type WSHandler=(message:any)=>void;
export class EventSocket{private ws?:WebSocket;private stopped=false;private retry=500;constructor(private eventId:string,private onMessage:WSHandler,private onStatus:(s:string)=>void,private lastSeen=0){}
start(){this.stopped=false;this.connect()}
private connect(){const proto=location.protocol==='https:'?'wss':'ws';const base=(import.meta as any).env?.VITE_WS_BASE ?? `${proto}://${location.host}`;this.onStatus('connecting');this.ws=new WebSocket(`${base}/ws/events/${this.eventId}?last_seen_sequence=${this.lastSeen}`);this.ws.onopen=()=>{this.retry=500;this.onStatus('live')};this.ws.onmessage=(e)=>{const m=JSON.parse(e.data);if(m.sequence)this.lastSeen=Math.max(this.lastSeen,m.sequence);this.onMessage(m)};this.ws.onclose=()=>{if(this.stopped)return;this.onStatus('reconnecting');setTimeout(()=>this.connect(),this.retry);this.retry=Math.min(8000,this.retry*1.8)};this.ws.onerror=()=>this.ws?.close()}
stop(){this.stopped=true;this.ws?.close()}}
