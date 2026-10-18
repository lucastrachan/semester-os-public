// Cognito via amazon-cognito-identity-js (SRP, pure JS, works in Expo Go). Tokens live in expo-secure-store.
// Only the refresh token is persisted; the ID token stays in memory and is refreshed when it is about to expire.
import 'react-native-get-random-values'
import * as SecureStore from 'expo-secure-store'
import {
  AuthenticationDetails,
  CognitoRefreshToken,
  CognitoUser,
  CognitoUserAttribute,
  CognitoUserPool,
  CognitoUserSession,
} from 'amazon-cognito-identity-js'
import { config } from '../config'

// In-memory Storage so the SDK never writes tokens anywhere we don't control.
class MemoryStorage {
  private m: Record<string, string> = {}
  setItem(k: string, v: string) { this.m[k] = v; return v }
  getItem(k: string) { return k in this.m ? this.m[k] : (undefined as unknown as string) }
  removeItem(k: string) { delete this.m[k]; return true }
  clear() { this.m = {}; return {} }
}

const pool = new CognitoUserPool({
  UserPoolId: config.userPoolId,
  ClientId: config.userPoolClientId,
  Storage: new MemoryStorage() as any,
})

const KEY_REFRESH = 'semesteros.refreshToken'
const KEY_EMAIL = 'semesteros.email'

let session: CognitoUserSession | null = null
let currentEmail: string | null = null

const user = (email: string) => new CognitoUser({ Username: email, Pool: pool, Storage: new MemoryStorage() as any })

/** Turn Cognito/Lambda errors into text a student can act on. Mirrors web AuthPage friendlyError. */
export function friendlyError(err: unknown): string {
  const e = err as { name?: string; code?: string; message?: string }
  let msg = e?.message ?? String(err)
  // Cognito wraps the pre-signup Lambda's message: strip the prefix (the web app does the same).
  msg = msg.replace(/^PreSignUp failed with error\s*/i, '').trim()
  if (isUnknownCampus(msg)) return EDU_ONLY
  const name = e?.name ?? e?.code ?? ''
  const has = (s: string) => name.includes(s) || msg.includes(s)
  if (has('UserNotFoundException') || has('NotAuthorizedException') || msg.includes('Incorrect username or password'))
    return 'Incorrect email or password.'
  if (has('UsernameExistsException')) return 'An account with this email already exists. Sign in instead.'
  if (has('InvalidPasswordException')) return 'Password must be at least 8 characters and include a number.'
  if (has('CodeMismatchException')) return 'That code is incorrect. Check your email and try again.'
  if (has('ExpiredCodeException')) return 'That code has expired. Request a new one.'
  if (has('LimitExceededException') || has('TooManyRequestsException')) return 'Too many attempts. Wait a minute and try again.'
  if (has('NetworkError') || msg.toLowerCase().includes('network')) return "Can't reach Semester OS. Check your connection."
  return msg
}

/** True when the pre-signup Lambda rejected the school domain (.edu only). */
export const isUnknownCampus = (msg: string) => msg.includes('.edu email addresses') || msg.includes("isn't on Semester OS")
export const EDU_ONLY = 'Semester OS supports US colleges (.edu email addresses) for now.'

export function signUp(email: string, password: string): Promise<void> {
  return new Promise((resolve, reject) => {
    pool.signUp(email, password, [new CognitoUserAttribute({ Name: 'email', Value: email })], [], (err) =>
      err ? reject(err) : resolve(),
    )
  })
}

export function confirmSignUp(email: string, code: string): Promise<void> {
  return new Promise((resolve, reject) => {
    user(email).confirmRegistration(code.trim(), true, (err) => (err ? reject(err) : resolve()))
  })
}

export function resendCode(email: string): Promise<void> {
  return new Promise((resolve, reject) => {
    user(email).resendConfirmationCode((err) => (err ? reject(err) : resolve()))
  })
}

async function persist(email: string, s: CognitoUserSession) {
  session = s
  currentEmail = email
  await SecureStore.setItemAsync(KEY_REFRESH, s.getRefreshToken().getToken())
  await SecureStore.setItemAsync(KEY_EMAIL, email)
}

export function signIn(email: string, password: string): Promise<void> {
  return new Promise((resolve, reject) => {
    user(email).authenticateUser(new AuthenticationDetails({ Username: email, Password: password }), {
      onSuccess: (s) => { persist(email, s).then(() => resolve(), reject) },
      onFailure: reject,
      newPasswordRequired: () => reject(new Error('This account needs a new password. Reset it on the website.')),
    })
  })
}

function refresh(email: string, refreshToken: string): Promise<CognitoUserSession> {
  return new Promise((resolve, reject) => {
    user(email).refreshSession(new CognitoRefreshToken({ RefreshToken: refreshToken }), (err, s) => {
      if (err || !s) return reject(err ?? new Error('refresh failed'))
      resolve(s)
    })
  })
}

/** Try to resume a saved session at launch. Returns the email, or null when signed out. */
export async function restoreSession(): Promise<string | null> {
  try {
    const [rt, email] = await Promise.all([
      SecureStore.getItemAsync(KEY_REFRESH),
      SecureStore.getItemAsync(KEY_EMAIL),
    ])
    if (!rt || !email) return null
    session = await refresh(email, rt)
    currentEmail = email
    return email
  } catch {
    await clearStored()
    return null
  }
}

/** A fresh Cognito ID token (the API wants the ID token, not the access token). */
export async function getIdToken(): Promise<string | null> {
  if (!session || !currentEmail) return null
  const exp = session.getIdToken().getExpiration() * 1000
  if (exp - Date.now() > 60_000) return session.getIdToken().getJwtToken()
  try {
    session = await refresh(currentEmail, session.getRefreshToken().getToken())
    return session.getIdToken().getJwtToken()
  } catch {
    return null
  }
}

async function clearStored() {
  session = null
  currentEmail = null
  await SecureStore.deleteItemAsync(KEY_REFRESH).catch(() => {})
  await SecureStore.deleteItemAsync(KEY_EMAIL).catch(() => {})
}

export async function signOut() {
  await clearStored()
}
