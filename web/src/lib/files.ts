// Upload formats the backend reads (MATERIALS_API.md). The browser's own MIME type is unreliable, so the extension decides.
export const FILE_TYPES: Record<string, string> = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  odt: 'application/vnd.oasis.opendocument.text',
  odp: 'application/vnd.oasis.opendocument.presentation',
  ods: 'application/vnd.oasis.opendocument.spreadsheet',
  rtf: 'application/rtf',
  html: 'text/html',
  htm: 'text/html',
  csv: 'text/csv',
  md: 'text/markdown',
  txt: 'text/plain',
  json: 'application/json',
}
export const FILE_ACCEPT = Object.keys(FILE_TYPES).map(e => `.${e}`).join(',')
export const FILE_HELP = 'PDF, Word, PowerPoint, Excel, OpenDocument, RTF, HTML, text'
export const MAX_FILE_BYTES = 10 * 1024 * 1024
export const MAX_TEXT_BYTES = 500 * 1024

const ext = (name: string) => (name.match(/\.([A-Za-z0-9]+)$/)?.[1] ?? '').toLowerCase()
export const isPdf = (name: string) => ext(name) === 'pdf'
/** The content type to send with the presign call, by file extension. */
export const mimeFor = (name: string) => FILE_TYPES[ext(name)] ?? 'application/octet-stream'

/** A friendly problem with this file, or null if it can be uploaded. Text-like files are held to the smaller text limit. */
export function fileProblem(f: { name: string; size: number }): string | null {
  const e = ext(f.name)
  if (e === 'doc' || e === 'ppt' || e === 'xls') return `Old .${e} files can't be read. Save it as PDF or .${e}x and add it again.`
  if (!FILE_TYPES[e]) return `That file type isn't supported. Use ${FILE_HELP}.`
  if (f.size > MAX_FILE_BYTES) return 'That file is over 10 MB.'
  if (['txt', 'md', 'csv', 'json', 'html', 'htm'].includes(e) && f.size > MAX_TEXT_BYTES) return 'Text files can be up to 500 KB.'
  return null
}
