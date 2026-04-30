import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Database,
  FileText,
  Loader2,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  listDocuments,
  listKnowledgeBases,
  queryKnowledgeBase,
  uploadDocuments,
  type KbCitation,
  type KbDocument,
  type KbUploadResult,
  type KnowledgeBase,
} from "@/lib/api/knowledge-base-client";

const SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"];
const SUPPORTED_HUMAN = "PDF, DOCX, TXT, MD";

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function StatusPill({ status }: { status: KbDocument["status"] }) {
  const styles: Record<KbDocument["status"], string> = {
    ready:
      "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    indexing:
      "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400",
    pending:
      "bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300",
    error: "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium capitalize",
        styles[status],
      )}
    >
      {status}
    </span>
  );
}

export default function KnowledgePage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const reloadList = useCallback(async () => {
    setLoadingList(true);
    try {
      const items = await listKnowledgeBases();
      setKbs(items);
      if (!selectedId && items.length > 0) setSelectedId(items[0].id);
    } catch (e) {
      console.error("Failed to load KBs:", e);
    } finally {
      setLoadingList(false);
    }
  }, [selectedId]);

  useEffect(() => {
    reloadList();
  }, [reloadList]);

  const selectedKb = useMemo(
    () => kbs.find((k) => k.id === selectedId) ?? null,
    [kbs, selectedId],
  );

  async function handleCreate() {
    const name = createName.trim();
    if (!name) {
      setCreateError("Name is required");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const kb = await createKnowledgeBase({
        name,
        description: createDesc.trim() || undefined,
      });
      setKbs((prev) => [kb, ...prev]);
      setSelectedId(kb.id);
      setCreateOpen(false);
      setCreateName("");
      setCreateDesc("");
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Failed to create");
    } finally {
      setCreating(false);
    }
  }

  async function handleDeleteKb(kb: KnowledgeBase) {
    if (
      !confirm(
        `Delete "${kb.name}"? This removes all ${kb.doc_count} document(s) and ${kb.chunk_count} chunk(s).`,
      )
    ) {
      return;
    }
    await deleteKnowledgeBase(kb.id);
    const remaining = kbs.filter((k) => k.id !== kb.id);
    setKbs(remaining);
    setSelectedId(remaining[0]?.id ?? null);
  }

  return (
    <div className="flex h-full overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      {/* Left rail — KB list */}
      <aside className="flex flex-col w-72 border-r border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
        <div className="flex items-center justify-between px-4 h-16 border-b border-neutral-200 dark:border-neutral-800">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-primary-500" />
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-white">
              Knowledge Bases
            </h2>
          </div>
          <Button
            size="sm"
            variant="primary"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="w-3.5 h-3.5" />
            New
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
          {loadingList && (
            <div className="flex items-center gap-2 px-3 py-4 text-xs text-neutral-500">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
            </div>
          )}
          {!loadingList && kbs.length === 0 && (
            <div className="px-3 py-8 text-xs text-center text-neutral-500 dark:text-neutral-400">
              No knowledge bases yet. Create one to get started.
            </div>
          )}
          {kbs.map((kb) => (
            <button
              key={kb.id}
              onClick={() => setSelectedId(kb.id)}
              className={cn(
                "w-full flex items-start gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors",
                "hover:bg-neutral-100 dark:hover:bg-neutral-800",
                selectedId === kb.id &&
                  "bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300",
              )}
            >
              <Database
                className={cn(
                  "w-4 h-4 flex-shrink-0 mt-0.5",
                  selectedId === kb.id
                    ? "text-primary-500"
                    : "text-neutral-400",
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate text-neutral-900 dark:text-white">
                  {kb.name}
                </div>
                <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5">
                  {kb.doc_count} doc{kb.doc_count === 1 ? "" : "s"} ·{" "}
                  {kb.chunk_count} chunk{kb.chunk_count === 1 ? "" : "s"}
                </div>
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* Right pane — selected KB */}
      <div className="flex-1 overflow-y-auto">
        {selectedKb ? (
          <KbDetail
            kb={selectedKb}
            onChange={reloadList}
            onDelete={() => handleDeleteKb(selectedKb)}
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-neutral-500 dark:text-neutral-400">
            <BookOpen className="w-12 h-12 mb-3 opacity-50" />
            <p className="text-sm">
              Select or create a knowledge base to manage documents.
            </p>
          </div>
        )}
      </div>

      {/* Create dialog */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New knowledge base"
        actions={
          <>
            <Button
              variant="ghost"
              onClick={() => setCreateOpen(false)}
              disabled={creating}
            >
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={creating}>
              {creating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Create
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Name"
            placeholder="e.g. Personal IRS docs"
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            autoFocus
            error={createError ?? undefined}
          />
          <Input
            label="Description (optional)"
            placeholder="What's in this KB?"
            value={createDesc}
            onChange={(e) => setCreateDesc(e.target.value)}
          />
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Embeddings: all-MiniLM-L6-v2 (384-dim). Documents stay on this
            machine.
          </p>
        </div>
      </Dialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Right pane — selected KB
// ---------------------------------------------------------------------------

function KbDetail({
  kb,
  onChange,
  onDelete,
}: {
  kb: KnowledgeBase;
  onChange: () => void | Promise<void>;
  onDelete: () => void;
}) {
  const [tab, setTab] = useState<"docs" | "query">("docs");

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 px-8 pt-8 pb-4 border-b border-neutral-200 dark:border-neutral-800">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-white truncate">
            {kb.name}
          </h1>
          {kb.description && (
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
              {kb.description}
            </p>
          )}
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
            {kb.doc_count} document{kb.doc_count === 1 ? "" : "s"} ·{" "}
            {kb.chunk_count} chunk{kb.chunk_count === 1 ? "" : "s"} ·{" "}
            {kb.embedding_model} ({kb.embedding_dim}-dim)
          </p>
        </div>
        <Button variant="danger" size="sm" onClick={onDelete}>
          <Trash2 className="w-3.5 h-3.5" />
          Delete KB
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 px-6 pt-3 border-b border-neutral-200 dark:border-neutral-800">
        {(
          [
            { id: "docs", label: "Documents" },
            { id: "query", label: "Test Query" },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "px-4 py-2 text-sm font-medium rounded-t-lg transition-colors",
              tab === t.id
                ? "text-primary-600 dark:text-primary-400 border-b-2 border-primary-500 -mb-px"
                : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6">
        {tab === "docs" ? (
          <DocumentsTab kb={kb} onChange={onChange} />
        ) : (
          <QueryTab kb={kb} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Documents tab — upload + list
// ---------------------------------------------------------------------------

function DocumentsTab({
  kb,
  onChange,
}: {
  kb: KnowledgeBase;
  onChange: () => void | Promise<void>;
}) {
  const [docs, setDocs] = useState<KbDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<KbUploadResult[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setDocs(await listDocuments(kb.id));
    } finally {
      setLoading(false);
    }
  }, [kb.id]);

  useEffect(() => {
    reload();
  }, [reload]);

  const acceptable = useCallback((file: File) => {
    const lower = file.name.toLowerCase();
    return SUPPORTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  }, []);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const arr = Array.from(files).filter(acceptable);
      if (arr.length === 0) {
        alert(`Only ${SUPPORTED_HUMAN} files are supported.`);
        return;
      }
      setUploading(true);
      setUploadResults([]);
      try {
        const results = await uploadDocuments(kb.id, arr);
        setUploadResults(results);
        await reload();
        await onChange();
      } catch (e) {
        alert(e instanceof Error ? e.message : "Upload failed");
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [acceptable, kb.id, onChange, reload],
  );

  async function handleDeleteDoc(doc: KbDocument) {
    if (!confirm(`Delete "${doc.filename}"?`)) return;
    await deleteDocument(kb.id, doc.id);
    await reload();
    await onChange();
  }

  return (
    <div className="space-y-6">
      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex flex-col items-center justify-center gap-2 px-6 py-12 rounded-2xl border-2 border-dashed cursor-pointer transition-colors",
          dragOver
            ? "border-primary-500 bg-primary-50 dark:bg-primary-500/10"
            : "border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800",
        )}
      >
        <Upload
          className={cn(
            "w-6 h-6",
            dragOver
              ? "text-primary-500"
              : "text-neutral-400 dark:text-neutral-500",
          )}
        />
        <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {uploading ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Indexing…
            </span>
          ) : (
            <>Drop files here, or click to choose</>
          )}
        </p>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          Supported: {SUPPORTED_HUMAN}
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={SUPPORTED_EXTENSIONS.join(",")}
          className="hidden"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
      </div>

      {/* Upload results banner */}
      {uploadResults.length > 0 && (
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-4 py-3 text-xs text-neutral-700 dark:text-neutral-300">
          <div className="flex items-center justify-between mb-2">
            <span className="font-medium">Last upload</span>
            <button
              onClick={() => setUploadResults([])}
              className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <ul className="space-y-1">
            {uploadResults.map((r, i) => (
              <li key={i} className="flex items-center gap-2">
                <StatusPill
                  status={r.status === "ready" ? "ready" : "error"}
                />
                <span className="truncate">{r.filename}</span>
                {r.status === "ready" && (
                  <span className="text-neutral-500">
                    · {r.chunks ?? 0} chunks
                    {r.pages ? `, ${r.pages} pages` : ""}
                  </span>
                )}
                {r.status === "error" && (
                  <span className="text-red-500">· {r.error}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Document list */}
      <div>
        <h3 className="text-sm font-semibold text-neutral-900 dark:text-white mb-3">
          Documents
        </h3>
        {loading ? (
          <p className="text-sm text-neutral-500">Loading…</p>
        ) : docs.length === 0 ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            No documents yet. Upload some PDFs or text files to start.
          </p>
        ) : (
          <ul className="rounded-xl border border-neutral-200 dark:border-neutral-800 divide-y divide-neutral-200 dark:divide-neutral-800 bg-white dark:bg-neutral-900">
            {docs.map((doc) => (
              <li
                key={doc.id}
                className="flex items-center gap-4 px-4 py-3 text-sm"
              >
                <FileText className="w-4 h-4 text-neutral-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-neutral-900 dark:text-white truncate">
                    {doc.filename}
                  </div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                    {formatBytes(doc.size_bytes)} · {doc.chunk_count} chunk
                    {doc.chunk_count === 1 ? "" : "s"}
                    {doc.page_count > 0 && ` · ${doc.page_count} pages`}
                    {doc.error && ` · ${doc.error}`}
                  </div>
                </div>
                <StatusPill status={doc.status} />
                <button
                  onClick={() => handleDeleteDoc(doc)}
                  className="p-1.5 rounded-lg text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Query tab — semantic search test
// ---------------------------------------------------------------------------

function QueryTab({ kb }: { kb: KnowledgeBase }) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [running, setRunning] = useState(false);
  const [citations, setCitations] = useState<KbCitation[]>([]);
  const [searched, setSearched] = useState(false);

  async function runQuery(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setRunning(true);
    setSearched(true);
    try {
      setCitations(await queryKnowledgeBase(kb.id, query.trim(), topK));
    } catch (err) {
      alert(err instanceof Error ? err.message : "Query failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={runQuery} className="flex items-end gap-3">
        <div className="flex-1">
          <Input
            label="Test query"
            placeholder='e.g. "What is the standard deduction for 2024?"'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="w-24">
          <Input
            label="Top K"
            type="number"
            min={1}
            max={20}
            value={topK}
            onChange={(e) =>
              setTopK(Math.max(1, Math.min(20, Number(e.target.value) || 5)))
            }
          />
        </div>
        <Button type="submit" disabled={running || !query.trim()}>
          {running ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Search className="w-3.5 h-3.5" />
          )}
          Search
        </Button>
      </form>

      <div>
        {!searched && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Run a query to preview what the model would receive as grounding
            context.
          </p>
        )}
        {searched && citations.length === 0 && !running && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            No matches. Try a different phrasing or upload more documents.
          </p>
        )}
        {citations.length > 0 && (
          <ol className="space-y-3">
            {citations.map((c, i) => (
              <li
                key={`${c.doc_id}-${c.chunk_index}`}
                className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-4 py-3"
              >
                <div className="flex items-center justify-between mb-1.5 text-xs text-neutral-500 dark:text-neutral-400">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="font-mono text-primary-500">
                      [{i + 1}]
                    </span>
                    <FileText className="w-3.5 h-3.5" />
                    <span className="font-medium text-neutral-700 dark:text-neutral-300">
                      {c.filename}
                    </span>
                    {c.page ? <span>· p.{c.page}</span> : null}
                  </span>
                  <span className="font-mono">
                    score {c.score.toFixed(3)}
                  </span>
                </div>
                <p className="text-sm text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap">
                  {c.excerpt}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
