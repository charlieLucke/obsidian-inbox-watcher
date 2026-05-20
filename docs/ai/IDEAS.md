# Ideas

> Out-of-scope ideas captured during work, to revisit later.
> Nothing here is committed. This is a parking lot.

---

## Pending

- [ ] **2026-05-20: OCR PDF Fallback.** If an incoming PDF contains scanned images instead of text, extract text using an OCR library (like `pytesseract` or direct Gemini multimodal page ingestion). *Effort: Medium.*
- [ ] **2026-05-20: Qdrant Vector DB Indexing.** Integrate with a local Qdrant database to store vector embeddings of notes, allowing semantic queries and automated relationship linking within Obsidian. *Effort: High.*
- [ ] **2026-05-20: Telegram Ingestion Webhook.** Create a lightweight API webhook so the user can forward text, links, or documents via a Telegram bot, which writes them directly to the watched Raw folder. *Effort: Medium.*
- [ ] **2026-05-20: Automatic Backlinking.** Let Gemini suggest links to existing notes in the processed categories during Markdown compilation, enriching Obsidian's graphical knowledge graph automatically. *Effort: Medium.*
