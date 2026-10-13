import { endpoint } from "@/utils/handleAPI";
import { ScannerEventSchema, type ScannerEvent } from "@/schemas/signalScannerSchema";

export const scannerErrors:Record<string,string> = {
  GROQ_DAILY_CAP:"This scan would exceed the daily Groq allowance. Your completed reviews are preserved below.",
  GROQ_RATE_LIMITED:"Groq needs more time to refill its allowance. Start another scan shortly.",
  GROQ_INVALID_OUTPUT:"Groq could not finish a valid review. No signal was accepted for this pair.",
  GROQ_TRANSPORT_ERROR:"The connection to Groq timed out. Completed reviews remain visible.",
  PROVIDER_NOT_CONFIGURED:"Connect Groq in the backend before starting a scan.",
};

export async function runSignalScan(input:{interval:"15m"|"1h";pairs:number}, signal:AbortSignal, onEvent:(event:ScannerEvent)=>void) {
  const response=await fetch(endpoint("/analysis/scanner/stream"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input),cache:"no-store",signal});
  if (!response.ok) throw new Error(response.status===409?"Another scan is still running or stopping. Try again once it finishes.":"The scanner could not start. Check the local backend connection.");
  if (!response.body) throw new Error("Streaming is unavailable in this browser.");
  const reader=response.body.getReader();
  const decoder=new TextDecoder();
  let pending="", terminal=false;
  function consume(line:string) {
    if (!line.trim()) return;
    const parsed=ScannerEventSchema.safeParse(JSON.parse(line));
    if(!parsed.success)throw new Error("The scanner returned an invalid update. Reload the page and try again.");
    const event=parsed.data;
    if(event.type==="scan_completed"||event.type==="scan_error") terminal=true;
    onEvent(event);
  }
  try {
    while(true) {
      const {done,value}=await reader.read();
      pending+=decoder.decode(value,{stream:!done});
      const lines=pending.split("\n");pending=lines.pop()??"";
      for(const line of lines) consume(line);
      if(done)break;
      if(pending.length>1000000)throw new Error("The scanner returned an invalid stream.");
    }
    consume(pending);
    if(!terminal&&!signal.aborted)throw new Error("The scan connection ended before completion. Completed reviews remain visible.");
  } finally { await reader.cancel().catch(()=>undefined); reader.releaseLock(); }
}
