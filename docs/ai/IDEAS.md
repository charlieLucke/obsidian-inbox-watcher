# Ideas

> Out-of-scope ideas captured during work, to revisit later.
> Nothing here is committed. This is a parking lot.

---

## Pending

- [ ] **2026-05-20: OCR PDF Fallback.** If an incoming PDF contains scanned images instead of text, extract text using an OCR library (like `pytesseract` or direct Gemini multimodal page ingestion). *Effort: Medium.*
- [ ] **2026-05-20: Qdrant Vector DB Indexing.** Integrate with a local Qdrant database to store vector embeddings of notes, allowing semantic queries and automated relationship linking within Obsidian. *Effort: High.*
- [ ] **2026-05-20: Telegram Ingestion Webhook.** Create a lightweight API webhook so the user can forward text, links, or documents via a Telegram bot, which writes them directly to the watched Raw folder. *Effort: Medium.*
- [ ] **2026-05-20: Automatic Backlinking.** Let Gemini suggest links to existing notes in the processed categories during Markdown compilation, enriching Obsidian's graphical knowledge graph automatically. *Effort: Medium.*
- [ ] **2026-05-29: Crash-safe processing via a `_processing/` claim (deferred WI-4).** The flow is write-note → move-original; a crash between the two re-processes the raw file on restart (WI-3's `_v2` guard mitigates but doesn't eliminate the duplicate). Atomically move each raw file into `VAULT_WATCHER_PROCESSING_DIR/<uuid>/` at the *start* of handling to claim it; on success move the original to archive, on failure to `failed/`; on startup drain leftover `processing/<uuid>/` dirs to `failed/` with reason `interrupted`. This is the one item that reshapes ordering/idempotency, so it was deferred from the hub-migration plan. Note: `VAULT_WATCHER_PROCESSING_DIR` is already mentioned in the docs/hub topology as a future local-only dir. *Effort: Medium; touches concurrency — see plan WI-4.*
- [ ] **2026-05-29: Send PDFs to Gemini multimodally (deferred WI-6).** `pypdf` extracts no text from scanned PDFs → empty text → dead-lettered. Sending the PDF bytes directly to Gemini (it is multimodal) handles scanned docs **and** removes local parsing load from the weak hub CPU (J3710). Trade-off: higher per-call token cost/size vs. handling scans + no local OCR. Supersedes the 2026-05-20 "OCR PDF Fallback" idea (prefer Gemini multimodal over `pytesseract`, given the no-local-heavy-processing hub constraint). *Effort: Medium; behaviour/design change, own plan.*
