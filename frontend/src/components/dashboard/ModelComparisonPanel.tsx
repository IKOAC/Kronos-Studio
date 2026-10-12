import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ModelComparison } from "@/schemas/predictionSchema";

type ModelComparisonPanelProps = {
  comparisons: ModelComparison[];
};

const directionLabel: Record<ModelComparison["direction"], string> = {
  up: "Upward",
  down: "Downward",
  flat: "Flat"
};

function formatChange(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function ModelComparisonPanel({ comparisons }: ModelComparisonPanelProps) {
  if (comparisons.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Model comparison ({comparisons.length})</CardTitle>
        <CardDescription>
          Each forecast is shown with its directional agreement across the selected models.
          Agreement is not a probability that the forecast will be accurate.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {comparisons.map((item) => (
          <div key={item.model_name} className="rounded-lg border p-4 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold">{item.model.name}</p>
                <p className="break-all text-xs text-muted-foreground">{item.model.model_id}</p>
                <p className="text-sm text-muted-foreground">{directionLabel[item.direction]} direction</p>
              </div>
              <span className="text-sm font-medium tabular-nums">{formatChange(item.predicted_change_pct)}</span>
            </div>
            <div className="flex items-end justify-between gap-2">
              <div>
                <p className="text-xs text-muted-foreground">Directional agreement</p>
                <p className="text-2xl font-semibold tabular-nums">{comparisons.length > 1 ? `${item.confidence_score.toFixed(0)}%` : "—"}</p>
              </div>
              <span className="text-xs rounded-md border px-2 py-1">{item.confidence_label}</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden" aria-label={`Directional agreement ${item.confidence_score}%`}>
              <div className="h-full rounded-full bg-primary" style={{ width: `${item.confidence_score}%` }} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
