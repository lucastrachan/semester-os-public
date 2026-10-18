import React from 'react'
import ReactDOM from 'react-dom/client'
import { Amplify } from 'aws-amplify'
import { cognitoUserPoolsTokenProvider } from 'aws-amplify/auth/cognito'
import { sessionStorage as amplifySessionStorage } from 'aws-amplify/utils'
import '../../web/src/styles/index.css'
import './admin.css'
import App from './App'
import { setConfig, type AdminConfig } from './api'

async function bootstrap() {
  const root = ReactDOM.createRoot(document.getElementById('root')!)
  try {
    const res = await fetch('/config.json', { cache: 'no-store' })
    const config = (await res.json()) as AdminConfig
    if (!config.adminUserPoolId || !config.adminClientId || !config.apiUrl) throw new Error('config incomplete')
    setConfig(config)
    // Tokens live in sessionStorage (cleared when the tab closes), not localStorage.
    cognitoUserPoolsTokenProvider.setKeyValueStorage(amplifySessionStorage)
    Amplify.configure({
      Auth: { Cognito: { userPoolId: config.adminUserPoolId, userPoolClientId: config.adminClientId } },
    })
    root.render(<React.StrictMode><App /></React.StrictMode>)
  } catch {
    root.render(
      <main className="ops-center"><div className="window"><div className="window-body">
        <h1>Admin site is not configured</h1>
        <p className="muted">config.json is missing or incomplete. Run scripts/deploy_admin.py.</p>
      </div></div></main>,
    )
  }
}

bootstrap()
