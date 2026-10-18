import type { PresignedPost } from 'shared/types'

export const MAX_PDF_BYTES = 10 * 1024 * 1024

/** Sends the PDF straight to S3 (multipart form POST): every presigned field first, the file LAST as "file".
 *  Never logs the URL or fields. Resolves on 204/2xx. */
export async function uploadPdf(upload: PresignedPost, file: { uri: string; name: string }): Promise<void> {
  return uploadFile(upload, { ...file, type: 'application/pdf' })
}

export async function uploadFile(upload: PresignedPost, file: { uri: string; name: string; type: string }): Promise<void> {
  const form = new FormData()
  for (const [k, v] of Object.entries(upload.fields)) form.append(k, v)
  // React Native's FormData accepts a { uri, name, type } descriptor for files.
  form.append('file', { uri: file.uri, name: file.name, type: file.type } as unknown as Blob)
  let res: Response
  try {
    res = await fetch(upload.url, { method: 'POST', body: form })
  } catch {
    throw new Error("The upload couldn't reach the server. Check your connection and try again.")
  }
  if (!res.ok) {
    throw new Error(res.status === 403 ? 'The upload link expired or the file was rejected. Try again.' : `Upload failed (${res.status}).`)
  }
}
