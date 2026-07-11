const desktopBaseUrl = process.env.IZ_CNA_E2E_BASE_URL ?? 'http://127.0.0.1:8765'
const bootstrapUsername = process.env.IZ_CNA_E2E_ADMIN_USERNAME ?? 'e2eadmin'
const bootstrapPassword = process.env.IZ_CNA_E2E_BOOTSTRAP_PASSWORD ?? 'E2eAdminPass1'
const activePassword = process.env.IZ_CNA_E2E_ADMIN_PASSWORD ?? 'E2eActivePass456'

async function responseJson(response) {
  if (!response.ok) throw new Error(`Desktop E2E setup failed with HTTP ${response.status}.`)
  return response.json()
}

export default async function prepareDesktopAdmin() {
  const activeLogin = await fetch(`${desktopBaseUrl}/api/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: bootstrapUsername, password: activePassword }),
  })
  if (activeLogin.ok) return
  const login = await responseJson(await fetch(`${desktopBaseUrl}/api/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: bootstrapUsername, password: bootstrapPassword }),
  }))
  if (!login.must_reset_password) return
  await responseJson(await fetch(`${desktopBaseUrl}/api/users/me/change-password`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${login.access_token}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({ current_password: bootstrapPassword, new_password: activePassword }),
  }))
}
