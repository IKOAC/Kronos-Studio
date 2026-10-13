import { z } from "zod";
const number = z.number().finite();
export const ScannerSetupSchema = z.object({
  symbol: z.string(), interval: z.enum(["15m", "1h"]), side: z.enum(["long", "short"]),
  last_close: number.positive(), entry: number.positive(), stop: number.positive(), target: number.positive(),
  net_reward_risk: number.positive(), fee_bps: number.nonnegative(), slippage_bps: number.nonnegative(),
  atr: number.positive(), atr_pct: number, spread_pct: number.nonnegative(), quote_volume: number.nonnegative(),
  checks: z.array(z.object({ label: z.string(), passed: z.boolean(), detail: z.string() })),
  checks_passed: z.number().int().nonnegative(), technical_pass: z.boolean(),
  candle_closed_at: z.string().datetime({offset:true}), expires_at: z.string().datetime({offset:true}),
  chart: z.array(z.object({ time: z.string(), close: number.positive() })),
});
export type ScannerSetup = z.infer<typeof ScannerSetupSchema>;
export const RoleSchema = z.enum(["bull", "bear", "research_manager"]);
export type ScannerRole = z.infer<typeof RoleSchema>;
const findings = z.object({summary:z.string(), setup_verdict:z.enum(["supports","rejects","unclear"]).nullable(), supporting_evidence_ids:z.array(z.string()), conflicting_evidence_ids:z.array(z.string()), limitations:z.array(z.string())});
const event = <T extends string, S extends z.ZodType>(type:T, data:S) => z.object({type:z.literal(type),data,at:z.string().datetime({offset:true})});
export const ScannerEventSchema = z.discriminatedUnion("type",[
  event("heartbeat",z.object({})),
  event("scan_started",z.object({universe:z.array(z.string()),interval:z.string(),pairs:z.number()})),
  event("screening",z.object({symbol:z.string()})),
  event("screened",z.object({setup:ScannerSetupSchema})),
  event("pair_skipped",z.object({symbol:z.string(),message:z.string()})),
  event("shortlist",z.object({symbols:z.array(z.string())})),
  event("pair_started",z.object({setup:ScannerSetupSchema})),
  event("agent_started",z.object({symbol:z.string(),role:RoleSchema})),
  event("agent_completed",z.object({symbol:z.string(),role:RoleSchema,findings})),
  event("pair_completed",z.object({setup:ScannerSetupSchema,qualified:z.boolean(),reason:z.string(),summary:z.string()})),
  event("signal",z.object({setup:ScannerSetupSchema,summary:z.string()})),
  event("scan_error",z.object({symbol:z.string().optional(),code:z.string(),message:z.string()})),
  event("scan_completed",z.object({signals:z.number(),message:z.string()})),
]);
export type ScannerEvent = z.infer<typeof ScannerEventSchema>;
export type ScannerMessage = Extract<ScannerEvent,{type:"agent_completed"}>;
