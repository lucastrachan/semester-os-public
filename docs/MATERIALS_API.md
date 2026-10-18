# Materials API

## Supported upload formats

| MIME type | Extension(s) | Max size |
|---|---|---|
| `application/pdf` | `.pdf` | 12 MB |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `.docx` | 12 MB |
| `application/vnd.openxmlformats-officedocument.presentationml.presentation` | `.pptx` | 12 MB |
| `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `.xlsx` | 12 MB |
| `application/vnd.oasis.opendocument.text` | `.odt` | 12 MB |
| `application/vnd.oasis.opendocument.presentation` | `.odp` | 12 MB |
| `application/vnd.oasis.opendocument.spreadsheet` | `.ods` | 12 MB |
| `application/rtf` or `text/rtf` | `.rtf` | 12 MB |
| `text/html` | `.html`, `.htm` | 12 MB |
| `text/plain` | `.txt`, `.md` | 500 KB |
| `text/csv` | `.csv` | 500 KB |
| `application/json` | `.json` | 500 KB |

Legacy formats (`.doc`, `.ppt`, `.xls`) return a `400 unsupported_format` error with a message to save as PDF.

## Safety limits (zip-based formats)

All zip-based formats (docx, pptx, xlsx, odt, odp, ods) are validated before extraction:

- Max 600 zip entries
- Max 25 MB total uncompressed content
- Encrypted/password-protected entries rejected
- Zip bomb detection: compressed ratio > 100× rejected

## Extraction (stdlib only, no external deps)

- **docx**: regex on `word/document.xml` `<w:t>` runs, paragraph by paragraph
- **pptx**: regex on `ppt/slides/slideN.xml` `<a:t>` runs, up to 40 slides
- **xlsx**: regex on `xl/sharedStrings.xml` + `xl/worksheets/sheet*.xml` cell values
- **odt/odp/ods**: regex on `content.xml` `<text:p>` and `<text:h>` elements
- **rtf**: strip control words with regex, decode `\'XX` hex escapes
- **html**: strip `<script>` and `<style>` blocks, then all tags; unescape entities
- **csv/json**: decoded as UTF-8 plain text

## Sources cap

`prompt_block` returns at most **3 sources**, deduplicated by URL (for index links) or `(materialId, title)` (for regular materials).

## Blackboard content index

A paste with title `"Blackboard content index"` is the class index uploaded by the browser extension.
It replaces any earlier index (replace-by-title). Index chunks are parsed for Blackboard links in the format:

```
Folder > Sub-folder > Item title [Type] <https://blackboard.example.edu/path>
```

Only `https://` URLs are included in sources.

When the student's question names an index item not yet fetched, the tutor returns a `fetchSuggestion: {title, url, path}` and a one-sentence reply.

## S3 key format

```
materials/{sub}/{courseId}/{matId}.{ext}
```

Supported extensions in the key: `pdf`, `txt`, `docx`, `pptx`, `xlsx`, `odt`, `odp`, `ods`, `rtf`, `html`, `csv`, `json`.
