"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import StudioNavigation from "@/components/layout/StudioNavigation";
import SavedResultsSidebar from "@/components/saved-results/SavedResultsSidebar";
import SavedResultViewer from "@/components/saved-results/SavedResultViewer";
import { deleteSavedResult, getSavedResult, listSavedResults } from "@/lib/api/savedResults";
import type { SavedResultMeta } from "@/schemas/resultsSchema";

export default function SavedResultsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const savedResultsQuery = useQuery({
    queryKey: ["saved-results"],
    queryFn: listSavedResults
  });

  const sortedResults = useMemo(
    () =>
      [...(savedResultsQuery.data ?? [])].sort(
        (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
      ),
    [savedResultsQuery.data]
  );

  const activeId = selectedId ?? sortedResults[0]?.id ?? null;

  const detailQuery = useQuery({
    queryKey: ["saved-results", activeId],
    queryFn: () => getSavedResult(activeId as string),
    enabled: Boolean(activeId)
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSavedResult,
    onSuccess: async (_, deletedId) => {
      queryClient.removeQueries({ queryKey: ["saved-results", deletedId] });
      queryClient.setQueryData<SavedResultMeta[]>(["saved-results"], (current) =>
        current?.filter((result) => result.id !== deletedId) ?? []
      );

      if (activeId === deletedId) {
        setSelectedId(null);
      }

      await queryClient.invalidateQueries({ queryKey: ["saved-results"] });
      toast.success("Saved result deleted");
    },
    onError: (error) => {
      toast.error("Failed to delete saved result", {
        description: error instanceof Error ? error.message : "Please try again."
      });
    }
  });

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[224px_minmax(0,1fr)]">
      <StudioNavigation active="archive" />
      <main className="min-w-0">
        <div className="flex min-h-[52px] flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-3 sm:px-9">
          <span className="terminal-kicker">KRONOS / RESEARCH ARCHIVE / 002</span>
          <Link href="/" className="terminal-link inline-flex items-center gap-2">
            <HugeiconsIcon icon={ArrowLeft01Icon} size={15} strokeWidth={1.5} /> Back to studio
          </Link>
        </div>

        <section className="relative overflow-hidden border-b border-border px-6 pb-9 pt-12 sm:px-9 sm:pb-11 sm:pt-14">
          <span className="terminal-kicker"><span className="terminal-accent">02</span> / YOUR RESEARCH HISTORY</span>
          <h1 className="terminal-heading mt-5 text-[clamp(3.5rem,7vw,7rem)]">
            SAVED<br /><span className="terminal-accent">SIGNALS.</span>
          </h1>
          <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
            <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
              Return to earlier forecasts, compare your thinking, and keep a record of what the models said.
            </p>
            <span className="terminal-mono border-b-2 border-[#FF3D00] pb-2 text-sm text-[#FF3D00]">{String(sortedResults.length).padStart(2, "0")} / RESULTS</span>
          </div>
        </section>

        <div className="flex min-h-[720px] flex-col md:flex-row">
          <SavedResultsSidebar
            results={sortedResults}
            selectedId={activeId}
            isLoading={savedResultsQuery.isLoading}
            isError={savedResultsQuery.isError}
            deletingId={deleteMutation.isPending ? deleteMutation.variables ?? null : null}
            onSelect={(id) => setSelectedId(id)}
            onRetry={() => savedResultsQuery.refetch()}
            onDelete={(id) => deleteMutation.mutate(id)}
          />
          <div className="flex min-w-0 flex-1 flex-col bg-background">
            <div className="sticky top-0 z-30 flex min-h-14 items-center justify-between gap-3 border-b border-border bg-background px-5 py-3 sm:px-7">
              <div className="flex items-center gap-3">
                <span className="terminal-kicker"><span className="terminal-accent">03</span> / SELECTED RESULT</span>
              </div>
              <span className="terminal-mono text-[11px] text-muted-foreground">ARCHIVE / DETAIL</span>
            </div>
            <SavedResultViewer
              detail={detailQuery.data}
              isLoading={detailQuery.isLoading || detailQuery.isFetching}
              isError={detailQuery.isError}
              onRetry={() => detailQuery.refetch()}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
