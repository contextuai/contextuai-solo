import { api } from "@/lib/transport";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Blueprint {
  id?: string;
  blueprint_id: string;
  name: string;
  description?: string;
  category: string;
  category_label?: string;
  content: string;
  tags: string[];
  recommended_agents: string[];
  sections: Record<string, string>;
  source: "library" | "custom";
  is_system: boolean;
  usage_count: number;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface BlueprintListItem {
  id?: string;
  blueprint_id: string;
  name: string;
  description?: string;
  category: string;
  category_label?: string;
  tags: string[];
  source: "library" | "custom";
  is_system: boolean;
  usage_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface BlueprintCatalogEntry {
  slug: string;
  name: string;
  category: string;
  category_label: string;
  description: string;
  tags: string[];
  recommended_agents: string[];
}

export interface BlueprintCatalog {
  blueprints: BlueprintCatalogEntry[];
  total_count: number;
  categories: Record<string, number>;
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

export const blueprintsApi = {
  // DB-backed endpoints (system + custom)
  list: async (params: {
    category?: string;
    search?: string;
    source?: string;
    page?: number;
    page_size?: number;
  } = {}): Promise<{
    blueprints: BlueprintListItem[];
    total_count: number;
    page: number;
    page_size: number;
  }> => {
    const query = new URLSearchParams();
    if (params.category) query.set("category", params.category);
    if (params.search) query.set("search", params.search);
    if (params.source) query.set("source", params.source);
    if (params.page) query.set("page", String(params.page));
    if (params.page_size) query.set("page_size", String(params.page_size));
    const qs = query.toString();
    const { data } = await api.get<Record<string, unknown>>(
      `/blueprints/${qs ? `?${qs}` : ""}`
    );
    const raw = data as Record<string, unknown>;
    return {
      blueprints: (raw.blueprints ?? []) as BlueprintListItem[],
      total_count: (raw.total_count ?? 0) as number,
      page: (raw.page ?? 1) as number,
      page_size: (raw.page_size ?? 20) as number,
    };
  },

  get: async (blueprintId: string): Promise<Blueprint> => {
    const { data } = await api.get<{ data: Blueprint }>(
      `/blueprints/${blueprintId}`
    );
    return (data as { data: Blueprint }).data;
  },

  create: async (payload: {
    name: string;
    description?: string;
    category: string;
    content: string;
    tags?: string[];
  }): Promise<Blueprint> => {
    const { data } = await api.post<{ data: Blueprint }>("/blueprints/", payload);
    return (data as { data: Blueprint }).data;
  },

  update: async (
    blueprintId: string,
    payload: Record<string, unknown>
  ): Promise<Blueprint> => {
    const { data } = await api.patch<{ data: Blueprint }>(
      `/blueprints/${blueprintId}`,
      payload
    );
    return (data as { data: Blueprint }).data;
  },

  delete: async (blueprintId: string): Promise<void> => {
    await api.delete(`/blueprints/${blueprintId}`);
  },

  // Library endpoints (file-based)
  listLibrary: async (
    category?: string
  ): Promise<BlueprintCatalog> => {
    const qs = category ? `?category=${category}` : "";
    const { data } = await api.get<Record<string, unknown>>(
      `/blueprints/library${qs}`
    );
    const raw = data as Record<string, unknown>;
    return {
      blueprints: (raw.blueprints ?? []) as BlueprintCatalogEntry[],
      total_count: (raw.total_count ?? 0) as number,
      categories: (raw.categories ?? {}) as Record<string, number>,
    };
  },

  searchLibrary: async (
    query: string
  ): Promise<{ blueprints: BlueprintCatalogEntry[]; total_count: number }> => {
    const { data } = await api.get<Record<string, unknown>>(
      `/blueprints/library/search?q=${encodeURIComponent(query)}`
    );
    const raw = data as Record<string, unknown>;
    return {
      blueprints: (raw.blueprints ?? []) as BlueprintCatalogEntry[],
      total_count: (raw.total_count ?? 0) as number,
    };
  },

  getLibraryDetail: async (
    category: string,
    slug: string
  ): Promise<Record<string, unknown>> => {
    const { data } = await api.get<{ data: Record<string, unknown> }>(
      `/blueprints/library/${category}/${slug}`
    );
    return (data as { data: Record<string, unknown> }).data;
  },

  sync: async (): Promise<{ message: string }> => {
    const { data } = await api.post<{ message: string }>(
      "/blueprints/library/sync"
    );
    return data as { message: string };
  },
};
