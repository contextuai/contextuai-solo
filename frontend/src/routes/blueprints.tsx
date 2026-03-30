import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  blueprintsApi,
  type BlueprintListItem,
} from "@/lib/api/blueprints-client";
import {
  FileText,
  Plus,
  Search,
  Filter,
  RefreshCw,
  Loader2,
  Tag,
  Eye,
  Trash2,
  X,
  BookOpen,
} from "lucide-react";
import { useBackendStatus } from "@/contexts/backend-status-context";
import { BackendWaiting } from "@/components/backend-waiting";

// ---------------------------------------------------------------------------
// Category config
// ---------------------------------------------------------------------------

const CATEGORY_COLORS: Record<string, { label: string; cls: string }> = {
  strategy: {
    label: "Strategy",
    cls: "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400",
  },
  product: {
    label: "Product",
    cls: "bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400",
  },
  marketing: {
    label: "Marketing",
    cls: "bg-pink-50 dark:bg-pink-900/20 text-pink-600 dark:text-pink-400",
  },
  content: {
    label: "Content",
    cls: "bg-teal-50 dark:bg-teal-900/20 text-teal-600 dark:text-teal-400",
  },
  research: {
    label: "Research",
    cls: "bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400",
  },
  operations: {
    label: "Operations",
    cls: "bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400",
  },
  general: {
    label: "General",
    cls: "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400",
  },
};

function CategoryBadge({ category }: { category: string }) {
  const info = CATEGORY_COLORS[category] ?? CATEGORY_COLORS.general;
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium",
        info.cls
      )}
    >
      {info.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function BlueprintsPage() {
  const { status: backendStatus } = useBackendStatus();
  const [blueprints, setBlueprints] = useState<BlueprintListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string>("");
  const [previewName, setPreviewName] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const result = await blueprintsApi.list({
        category: categoryFilter !== "all" ? categoryFilter : undefined,
        search: searchQuery || undefined,
        source: sourceFilter !== "all" ? sourceFilter : undefined,
      });
      setBlueprints(result.blueprints);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [categoryFilter, searchQuery, sourceFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handlePreview = async (bp: BlueprintListItem) => {
    setPreviewId(bp.blueprint_id);
    setPreviewName(bp.name);
    setPreviewLoading(true);
    try {
      const full = await blueprintsApi.get(bp.blueprint_id);
      setPreviewContent(full.content || "No content available.");
    } catch {
      setPreviewContent("Failed to load blueprint content.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleDelete = async (bp: BlueprintListItem) => {
    if (bp.is_system) return;
    try {
      await blueprintsApi.delete(bp.blueprint_id);
      loadData();
    } catch {
      // silently fail
    }
  };

  return (
    <div className="flex flex-col h-full bg-neutral-50 dark:bg-neutral-950">
      {/* Header */}
      <div className="border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary-50 dark:bg-primary-500/10">
              <BookOpen className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
                Blueprints
              </h1>
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                {blueprints.length} blueprint{blueprints.length !== 1 ? "s" : ""} &middot; Workflow guides for your agents
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              title="Refresh"
            >
              <RefreshCw
                className={cn(
                  "w-5 h-5 text-neutral-500",
                  refreshing && "animate-spin"
                )}
              />
            </button>
            <button
              onClick={() => setCreateOpen(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors text-sm font-medium"
            >
              <Plus className="w-4 h-4" />
              Create Blueprint
            </button>
          </div>
        </div>
      </div>

      {/* Search + Filters */}
      <div className="px-6 py-4 flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <input
            type="text"
            placeholder="Search blueprints..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
          />
        </div>
        <Filter className="w-4 h-4 text-neutral-400" />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-2 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-xs focus:ring-2 focus:ring-primary-500/30 outline-none"
        >
          <option value="all">All categories</option>
          <option value="strategy">Strategy</option>
          <option value="product">Product</option>
          <option value="marketing">Marketing</option>
          <option value="content">Content</option>
          <option value="research">Research</option>
          <option value="operations">Operations</option>
          <option value="general">General</option>
        </select>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          className="px-2 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-xs focus:ring-2 focus:ring-primary-500/30 outline-none"
        >
          <option value="all">All sources</option>
          <option value="library">Library</option>
          <option value="custom">Custom</option>
        </select>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {loading && backendStatus !== "ready" ? (
          <BackendWaiting />
        ) : loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
          </div>
        ) : blueprints.length === 0 ? (
          <div className="text-center py-20">
            <BookOpen className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">
              No blueprints found
            </h3>
            <p className="text-neutral-500 dark:text-neutral-400 mb-6 text-sm">
              {searchQuery || categoryFilter !== "all"
                ? "Try adjusting your filters."
                : "Blueprints may still be loading. Try syncing from the library."}
            </p>
            <div className="flex items-center justify-center gap-3">
              {!searchQuery && categoryFilter === "all" && (
                <button
                  onClick={async () => {
                    setRefreshing(true);
                    try {
                      await blueprintsApi.sync();
                    } catch { /* ignore */ }
                    loadData();
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-primary-300 dark:border-primary-700 text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-500/10 transition-colors text-sm font-medium"
                >
                  <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
                  Sync Library
                </button>
              )}
              <button
                onClick={() => setCreateOpen(true)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors text-sm font-medium"
              >
                <Plus className="w-4 h-4" />
                Create Blueprint
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {blueprints.map((bp) => (
              <div
                key={bp.blueprint_id}
                className="bg-white dark:bg-neutral-900 rounded-xl p-5 border border-neutral-200 dark:border-neutral-800 hover:shadow-md hover:border-primary-300 dark:hover:border-primary-700 transition-all group"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="p-2 rounded-lg bg-primary-50 dark:bg-primary-500/10">
                      <FileText className="w-4 h-4 text-primary-500" />
                    </div>
                    <CategoryBadge category={bp.category} />
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handlePreview(bp)}
                      className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors opacity-0 group-hover:opacity-100"
                      title="Preview"
                    >
                      <Eye className="w-4 h-4 text-neutral-400" />
                    </button>
                    {!bp.is_system && (
                      <button
                        onClick={() => handleDelete(bp)}
                        className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors opacity-0 group-hover:opacity-100"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4 text-red-400" />
                      </button>
                    )}
                  </div>
                </div>
                <h3 className="font-medium text-neutral-900 dark:text-white mb-1 line-clamp-1">
                  {bp.name}
                </h3>
                {bp.description && (
                  <p className="text-sm text-neutral-500 dark:text-neutral-400 line-clamp-2 mb-3">
                    {bp.description}
                  </p>
                )}
                {bp.tags.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <Tag className="w-3 h-3 text-neutral-400" />
                    {bp.tags.slice(0, 4).map((tag) => (
                      <span
                        key={tag}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-3 flex items-center justify-between text-xs text-neutral-400">
                  <span>
                    {bp.is_system ? "System" : "Custom"}
                  </span>
                  {bp.usage_count > 0 && (
                    <span>Used {bp.usage_count}x</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Preview Modal */}
      {previewId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-neutral-900 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col mx-4 border border-neutral-200 dark:border-neutral-800 shadow-xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                {previewName}
              </h2>
              <button
                onClick={() => setPreviewId(null)}
                className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              >
                <X className="w-5 h-5 text-neutral-500" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-4">
              {previewLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
                </div>
              ) : (
                <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
                  {previewContent}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Create Blueprint Modal */}
      {createOpen && (
        <CreateBlueprintDialog
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            loadData();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create Blueprint Dialog
// ---------------------------------------------------------------------------

function CreateBlueprintDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("general");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!name.trim() || !content.trim()) {
      setError("Name and content are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await blueprintsApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
        category,
        content: content.trim(),
        tags: tags
          .split(",")
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create blueprint");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-neutral-900 rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col mx-4 border border-neutral-200 dark:border-neutral-800 shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Create Blueprint
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <X className="w-5 h-5 text-neutral-500" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {error && (
            <div className="text-sm text-red-500 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Sprint Planning Guide"
              maxLength={200}
              className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Description
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of what this blueprint guides"
              maxLength={2000}
              className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
            />
          </div>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 outline-none"
              >
                <option value="strategy">Strategy</option>
                <option value="product">Product</option>
                <option value="marketing">Marketing</option>
                <option value="content">Content</option>
                <option value="research">Research</option>
                <option value="operations">Operations</option>
                <option value="general">General</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Tags (comma-separated)
              </label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="e.g., brainstorm, strategy, planning"
                className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Content (Markdown)
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Write your blueprint guide in markdown...&#10;&#10;## Objective&#10;Describe the goal...&#10;&#10;## Steps&#10;1. First step...&#10;2. Second step..."
              rows={12}
              className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm font-mono focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none resize-y"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-neutral-200 dark:border-neutral-800">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name.trim() || !content.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            Create Blueprint
          </button>
        </div>
      </div>
    </div>
  );
}
