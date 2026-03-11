import { api } from "@/lib/transport";

export interface Persona {
  id: string;
  name: string;
  description: string;
  type: string;
  system_prompt?: string;
  icon?: string;
  category?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CreatePersonaRequest {
  name: string;
  description: string;
  persona_type_id: string;
  user_id?: string;
  credentials?: Record<string, unknown>;
  category?: string;
  icon?: string;
  status?: string;
  // Desktop-only convenience fields (mapped before sending)
  type?: string;
  system_prompt?: string;
}

export interface PersonaType {
  id: string;
  name: string;
  description: string;
  category: string;
  icon?: string;
  enabled: boolean;
}

export async function getPersonaTypes(): Promise<PersonaType[]> {
  const { data } = await api.get<{ persona_types: PersonaType[] } | PersonaType[]>("/persona-types/");
  if (Array.isArray(data)) return data;
  return (data as { persona_types: PersonaType[] }).persona_types ?? [];
}

export async function getPersonas(): Promise<Persona[]> {
  const { data } = await api.get<{ personas: Persona[] } | Persona[]>("/personas/");
  if (Array.isArray(data)) return data;
  return (data as { personas: Persona[] }).personas ?? [];
}

export async function getPersona(id: string): Promise<Persona> {
  const { data } = await api.get<Persona>(`/personas/${id}`);
  return data;
}

export async function createPersona(persona: CreatePersonaRequest): Promise<Persona> {
  const payload = {
    name: persona.name,
    description: persona.description,
    persona_type_id: persona.persona_type_id || persona.type || "generic",
    user_id: persona.user_id || "desktop-user",
    credentials: persona.credentials ?? {},
    category: persona.category,
    icon: persona.icon,
    status: persona.status || "active",
  };
  const { data } = await api.post<Persona>("/personas/", payload);
  return data;
}

export async function updatePersona(id: string, persona: Partial<CreatePersonaRequest>): Promise<Persona> {
  const { data } = await api.put<Persona>(`/personas/${id}`, persona);
  return data;
}

export async function deletePersona(id: string): Promise<void> {
  await api.delete(`/personas/${id}`);
}
