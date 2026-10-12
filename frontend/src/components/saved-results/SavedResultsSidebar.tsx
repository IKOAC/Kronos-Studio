"use client";

import { RefreshCw, SearchX, Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import type { SavedResultMeta } from "@/schemas/resultsSchema";

type SavedResultsSidebarProps = {
  results: SavedResultMeta[];
  selectedId: string | null;
  isLoading: boolean;
  isError: boolean;
  deletingId: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
  onDelete: (id: string) => void;
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(value));
}

export default function SavedResultsSidebar({
  results,
  selectedId,
  isLoading,
  isError,
  deletingId,
  onSelect,
  onRetry,
  onDelete
}: SavedResultsSidebarProps) {
  return (
    <aside className="flex w-full min-w-0 shrink-0 flex-col border-b border-border bg-card md:w-[288px] md:border-b-0 md:border-r" aria-label="Saved forecasts">
      <div className="flex min-h-14 items-center justify-between gap-2 border-b border-border px-5 py-5">
        <div>
          <span className="terminal-kicker"><span className="terminal-accent">01</span> / LIBRARY</span>
          <h2 className="mt-2 font-sans text-lg font-extrabold tracking-[-0.05em]">Research index</h2>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Refresh saved results" title="Refresh saved results" onClick={onRetry} disabled={isLoading}>
          <RefreshCw size={17} strokeWidth={1.5} className={isLoading ? "animate-spin" : ""} />
        </Button>
      </div>
      <div className="max-h-[340px] min-w-0 overflow-y-auto md:max-h-[780px]" aria-live="polite">
        {isLoading ? (
          <div className="space-y-px bg-border">
            {Array.from({ length: 5 }).map((_, index) => <div key={index} className="h-24 animate-pulse bg-card" />)}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-start gap-3 p-6">
            <SearchX size={24} strokeWidth={1.5} className="text-[#FF3D00]" />
            <p className="text-sm font-semibold">Unable to load archive</p>
            <p className="text-sm leading-relaxed text-muted-foreground">Check the results API and try again.</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        ) : results.length === 0 ? (
          <div className="flex flex-col items-start gap-3 p-6">
            <SearchX size={24} strokeWidth={1.5} className="text-[#FF3D00]" />
            <p className="text-sm font-semibold">No saved forecasts</p>
            <p className="text-sm leading-relaxed text-muted-foreground">Saved research will appear here after your first forecast.</p>
          </div>
        ) : (
          <ol className="divide-y divide-border">
            {results.map((result, index) => {
              const active = selectedId === result.id;
              return (
                <li key={result.id} className={`group relative flex min-w-0 items-stretch border-l-2 ${active ? "border-[#FF3D00] bg-[#FF3D00]/[0.06]" : "border-transparent hover:bg-muted/60"}`}>
                  <button type="button" aria-current={active ? "true" : undefined} onClick={() => onSelect(result.id)}
                    className="flex min-h-[100px] min-w-0 flex-1 flex-col items-start justify-center gap-2 py-4 pl-5 pr-1 text-left focus-visible:outline-offset-[-3px]">
                    <span className="terminal-mono text-[10px] text-[#FF3D00]">{String(index + 1).padStart(2, "0")} / {result.type === "predict/price/batch" ? "BATCH" : "SINGLE"}</span>
                    <span className="w-full truncate font-sans text-sm font-semibold tracking-[-0.015em]" title={result.label || "Untitled forecast"}>{result.label || "Untitled forecast"}</span>
                    <span className="terminal-mono text-[10px] text-muted-foreground">{formatDate(result.created_at)}</span>
                  </button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <button type="button" className="my-auto mr-3 flex size-9 shrink-0 items-center justify-center text-muted-foreground transition-colors hover:text-destructive focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FF3D00]"
                        aria-label={`Delete ${result.label || "untitled forecast"}`} disabled={deletingId === result.id}>
                        <Trash2 size={16} strokeWidth={1.5} />
                      </button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete saved result?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This permanently deletes {result.label || "the selected prediction"}. The action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction className="bg-destructive/20 text-destructive hover:bg-destructive/30" onClick={() => onDelete(result.id)} disabled={deletingId === result.id}>
                          {deletingId === result.id ? "Deleting…" : "Delete result"}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </li>
              );
            })}
          </ol>
        )}
      </div>
      <div className="mt-auto hidden border-t border-border px-5 py-5 md:block">
        <span className="terminal-kicker !text-[9px]">READ ONLY / STORED FORECASTS</span>
      </div>
    </aside>
  );
}
