import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  blueprintsApi,
  type BlueprintListItem,
} from "@/lib/api/blueprints-client";
import {
  X,
  Search,
  FileText,
  BookOpen,
  Loader2,
  Tag,
  ChevronRight,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BlueprintSelection {
  blueprint_id: string;
  name: string;
  content: string;
}

interface BlueprintSelectorProps {
  open: boolean;
  onClose: () => void;
  onSelect: (selection: BlueprintSelection) => void;
}

// ---------------------------------------------------------------------------
// Category styles
// ---------------------------------------------------------------------------

const CATEGORY_STYLES: Record<string, string> = {
  strategy: "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400",
  product: "bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400",
  marketing: "bg-pink-50 dark:bg-pink-900/20 text-pink-600 dark:text-pink-400",
  content: "bg-teal-50 dark:bg-teal-900/20 text-teal-600 dark:text-teal-400",
  research: "bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400",
  operations: "bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400",
  general: "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BlueprintSelector({ open, onClose, onSelect }: BlueprintSelectorProps) {
  const [blueprints, setBlueprints] = useState<BlueprintListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchBlueprints = useCallback(async () => {
    setLoading(true);
    try {
      const result = await blueprintsApi.list({
        category: categoryFilter !== "all" ? categoryFilter : undefined,
        search: searchQuery || undefined,
      });
      setBlueprints(result.blueprints);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, searchQuery]);

  useEffect(() => {
    if (open) {
      fetchBlueprints();
    }
  }, [open, fetchBlueprints]);

  const handleSelect = async (bp: BlueprintListItem) => {
    try {
      const full = await blueprintsApi.get(bp.blueprint_id);
      onSelect({
        blueprint_id: bp.blueprint_id,
        name: bp.name,
        content: full.content,
      });
      onClose();
    } catch {
      // silently fail
    }
  };

  const handlePreview = async (bp: BlueprintListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setPreviewId(bp.blueprint_id);
    setPreviewLoading(true);
    try {
      const full = await blueprintsApi.get(bp.blueprint_id);
      setPreviewContent(full.content || "No content available.");
    } catch {
      setPreviewContent("Failed to load content.");
    } finally {
      setPreviewLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-neutral-900 rounded-xl w-full max-w-3xl max-h-[80vh] flex flex-col mx-4 border border-neutral-200 dark:border-neutral-800 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-primary-500" />
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
              Select Blueprint
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <X className="w-5 h-5 text-neutral-500" />
          </button>
        </div>

        {/* Search + Filters */}
        <div className="px-6 py-3 border-b border-neutral-200 dark:border-neutral-800 flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
            <input
              type="text"
              placeholder="Search blueprints..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
            />
          </div>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-2 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-xs focus:ring-2 focus:ring-primary-500/30 outline-none"
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
        </div>

        {/* List + Preview */}
        <div className="flex-1 overflow-hidden flex">
          {/* Blueprint list */}
          <div className={cn(
            "overflow-y-auto",
            previewId ? "w-1/2 border-r border-neutral-200 dark:border-neutral-800" : "w-full"
          )}>
            {loading ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
              </div>
            ) : blueprints.length === 0 ? (
              <div className="text-center py-10 text-neutral-500 dark:text-neutral-400 text-sm">
                No blueprints found
              </div>
            ) : (
              <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {blueprints.map((bp) => (
                  <div
                    key={bp.blueprint_id}
                    onClick={() => handleSelect(bp)}
                    className={cn(
                      "px-5 py-3.5 cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors group",
                      previewId === bp.blueprint_id && "bg-primary-50/50 dark:bg-primary-500/5"
                    )}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-3 min-w-0">
                        <FileText className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0" />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-sm text-neutral-900 dark:text-white">
                              {bp.name}
                            </span>
                            <span
                              className={cn(
                                "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                                CATEGORY_STYLES[bp.category] ?? CATEGORY_STYLES.general
                              )}
                            >
                              {bp.category_label || bp.category}
                            </span>
                          </div>
                          {bp.description && (
                            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 line-clamp-1">
                              {bp.description}
                            </p>
                          )}
                          {bp.tags.length > 0 && (
                            <div className="flex items-center gap-1 mt-1">
                              <Tag className="w-2.5 h-2.5 text-neutral-400" />
                              {bp.tags.slice(0, 3).map((tag) => (
                                <span
                                  key={tag}
                                  className="text-[10px] text-neutral-400"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                          onClick={(e) => handlePreview(bp, e)}
                          className="p-1 rounded hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors opacity-0 group-hover:opacity-100"
                          title="Preview"
                        >
                          <ChevronRight className="w-4 h-4 text-neutral-400" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Preview pane */}
          {previewId && (
            <div className="w-1/2 overflow-y-auto p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-neutral-900 dark:text-white">
                  Preview
                </h3>
                <button
                  onClick={() => setPreviewId(null)}
                  className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                >
                  <X className="w-4 h-4 text-neutral-400" />
                </button>
              </div>
              {previewLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="w-5 h-5 animate-spin text-primary-500" />
                </div>
              ) : (
                <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap text-xs">
                  {previewContent}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
