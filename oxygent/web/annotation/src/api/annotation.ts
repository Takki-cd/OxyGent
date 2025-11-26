import axios from 'axios'

const client = axios.create({ baseURL: '/annotation' })

export async function login(username: string, password: string) {
  const res = await client.post('/auth/login', { username, password })
  return res.data
}

export async function searchAnnotations(q: string, page = 1, pageSize = 20) {
  const res = await client.get('/annotations/search', { params: { q, page, page_size: pageSize } })
  return res.data
}