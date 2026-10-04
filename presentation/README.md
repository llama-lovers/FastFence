# FastFence presentation and recorded demo

English slides and video captions, with Polish speaker notes. The main pitch
uses slides 1–7 and takes approximately three minutes. Slide 8 is an optional
benchmark appendix with its original package version and measurement scope.

## Deliverables

- [Editable PowerPoint](output/fastfence-pitch.pptx)
- [PDF slides](output/fastfence-pitch.pdf)
- [Recorded product demo](output/fastfence-demo.mp4)
- [Synthetic source PDF](assets/demo-document.pdf) and [approved Markdown](output/demo-document-approved.md)
- [OCR outcomes](output/ocr-demo-evidence.json)
- [English video captions](output/demo-captions.srt)
- [Polish narration and manual demo instructions](demo-script.pl.md)
- [Evidence and claim boundaries](evidence.md)
- [Outcomes from the recorded session](output/demo-evidence.json)

Open the PPTX or PDF for the pitch. Play the MP4 separately when introducing
the recorded demonstration. The video has English captions and no recorded
voice. The Polish script is ready for the presenter to read or record.
The combined MP4 lasts **144.933 seconds**: the original 90-second policy demo,
a six-second source-PDF preview, then the document workflow from a separate
isolated session. The MP4 is a local deliverable, not a published YouTube link.

The footage uses an isolated installation of public PyPI FastFence 1.0.7 and
actual local models. Its displayed rules and decisions are real. Test prompts
are synthetic and contain no customer data. Connection credentials are outside
the exported footage. The demonstration changes only its disposable policy.

The [two-page document sample](assets/demo-document.pdf) contains only synthetic
service-report content and `example.com` contact addresses. Document protection
uses local OCR and input privacy redaction. The approved Markdown is the text
eligible for a business-model call; the source PDF is not sent to that model.
Both recorded document requests detected `pii_email` and returned two
`[REDACTED:pii_email]` markers. Extraction did not invoke the business model;
completion invoked Qwen with Laya input and output checks passing. The downloaded
Markdown contains neither original contact address. These are recorded outcomes,
not an OCR accuracy or latency benchmark. This demonstrates masking, not
public/private-key recovery or editing PDF pixels.

## Rebuild the deck

`scripts/build-deck.mjs` uses the supplied `@oai/artifact-tool` runtime and the
screenshots in `assets/`. It creates editable slide text, an architecture
diagram and native evidence tables. It does not modify the product.

Set `PRESENTATION_SKILL_DIR`, `RUNTIME_NODE_MODULES` and `RUNTIME_PYTHON` to the
presentation skill and its supplied runtime, then run the script with that
runtime's Node executable. The default output name must not already exist;
set `DECK_OUTPUT_NAME` to a new filename when preparing a revision.
Private draft renders and validation receipts stay under
`state/private/presentation-build/`.

## Record another session

Use the instructions and fallback plan in [the Polish script](demo-script.pl.md).
The policy recorder is `scripts/record_demo.py`; the document extension uses
`scripts/record_ocr_demo.py`. Run each with `--help` for its explicit inputs. It requires Playwright Chromium and FFmpeg.
Use a fresh, isolated FastFence installation: the recorder activates rules.
Never point it at an operator's active configuration. Keep any credentials file
outside this directory and outside source control.

Test counts establish the stated test scopes, not universal semantic accuracy.
The 1,000-request result uses a controlled provider. The separate 12-request
check uses actual Laya and Ollama. Historical latency figures belong to 1.0.2.
