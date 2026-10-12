import type { ProviderAllowance as Allowance } from "@/schemas/groqAnalysisSchema";

const dollars = (value: number) => value.toLocaleString(undefined, {
  style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4,
});

export default function ProviderAllowance({ allowance }: { allowance: Allowance }) {
  return <div className="mt-3 space-y-2 border-t border-border pt-3 text-xs text-muted-foreground">
    {allowance.balance_remaining_usd != null && <p>Account balance <span className="terminal-mono text-foreground">{dollars(allowance.balance_remaining_usd)}</span></p>}
    {allowance.key_status === "available" && <>
      <p>{allowance.spending_scope === "effective" ? "Effective" : "Key"} spending cap {allowance.spending_limit_usd == null ? "not set" : dollars(allowance.spending_limit_usd)}{allowance.limit_reset ? ` · ${allowance.limit_reset}` : ""}</p>
      {allowance.spending_remaining_usd != null && <p>{dollars(allowance.spending_remaining_usd)} remaining{allowance.spending_percent != null ? ` · ${allowance.spending_percent.toFixed(2)}% consumed` : ""}</p>}
      {allowance.key_usage_daily_usd != null && <p>Key spend today <span className="terminal-mono">{dollars(allowance.key_usage_daily_usd)}</span></p>}
      {allowance.spending_used_usd != null && <p>Reported {allowance.spending_scope === "effective" ? "budget" : "key"} spend <span className="terminal-mono">{dollars(allowance.spending_used_usd)}</span></p>}
    </>}
    {allowance.balance_status === "permission_required" && <p>Balance access requires a management key with reporting permission.</p>}
    {allowance.balance_status === "unavailable" && <p>Account balance could not be refreshed.</p>}
    {allowance.key_status === "unavailable" && <p>Key usage could not be refreshed.</p>}
    <p className="terminal-mono text-[10px]">Checked {new Date(allowance.checked_at_utc).toLocaleTimeString()} · cached for up to a minute</p>
  </div>;
}
