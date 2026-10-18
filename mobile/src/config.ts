// The ONE place the app reads backend settings. These are public identifiers, not secrets.
// EXAMPLE DEFAULTS: set EXPO_PUBLIC_* env vars (or edit the placeholders) to point at YOUR deployment
// (values come from the CDK stack outputs; see README).
export const config = {
  region: process.env.EXPO_PUBLIC_REGION ?? 'us-east-1',
  userPoolId: process.env.EXPO_PUBLIC_USER_POOL_ID ?? 'REPLACE_WITH_STUDENT_USER_POOL_ID',
  userPoolClientId: process.env.EXPO_PUBLIC_USER_POOL_CLIENT_ID ?? 'REPLACE_WITH_STUDENT_CLIENT_ID',
  apiUrl: process.env.EXPO_PUBLIC_API_URL ?? 'REPLACE_WITH_API_URL',
}
