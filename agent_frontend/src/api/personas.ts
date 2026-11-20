import request from './request'

export interface Persona {
  id: string | null
  name: string
  instruction: string
  version: number
  active: boolean
}

export async function listPersonas() {
  const { data } = await request.get<{ personas: Persona[] }>('/api/profile/personas')
  return data.personas
}

export async function createPersona(body: Pick<Persona, 'name' | 'instruction'>) {
  const { data } = await request.post<Persona>('/api/profile/personas', body)
  return data
}

export async function updatePersona(id: string, body: Partial<Pick<Persona, 'name' | 'instruction' | 'active'>>) {
  const { data } = await request.patch<Persona>(`/api/profile/personas/${encodeURIComponent(id)}`, body)
  return data
}
