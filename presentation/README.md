# FastFence presentation and recorded demo

English slides and video captions, with Polish speaker notes. The revised deck
contains six main slides and one appendix with verification evidence.

## Revised showcase

Use the revised materials for the product pitch:

- [Workflow demo with instrumental music](output/fastfence-demo-v3.mp4)
- [Revised editable presentation](output/fastfence-pitch-v2.pptx)
- [Revised PDF presentation](output/fastfence-pitch-v2.pdf)
- [Polish opening, closing and technical answers](showcase-script.pl.md)
- [Official criteria mapped to evidence](demo-criteria-map.md)
- [Actual OpenAI SDK integration results](output/integration-demo-evidence.json)

The current film lasts **2 minutes 20 seconds** and shows actual 1.0.7 outcomes. It has
English on-screen explanations and music, without a voiceover. Scene duration
does not measure request latency. Full-screen recorded interactions show policy
editing, protection decisions, Laya review and document OCR. Two brief code/result
scenes reproduce the sanitized output from a separate real OpenAI SDK run, with
one allowed request and the same request blocked after a live policy change.
The benchmark scene separates historical local-control latency from controlled
queue tests and real-model integration checks.

For a three-minute presentation, use a ten-second spoken opening, play the film,
then close in twenty seconds with the operational guarantees and launch command.
The Polish script provides these short lines plus longer speaking notes. The additional slides support a
presentation without video or questions after the pitch.

The music is an original instrumental generated for FastFence, without vocals
or third-party audio samples. Its source is `scripts/build_soundtrack.py` and
`scripts/soundtrack_synthesis.py`. The video uses `scripts/build_showcase.py`.
With NumPy, Pillow and FFmpeg available, build the soundtrack first, then the
video; the v3 builder is `scripts/build_demo_v3.py`. To generate the longer music,
pass `--duration 140 --soft-start 70 --soft-end 106 --output presentation/output/fastfence-soundtrack-v3.m4a`
to the soundtrack builder. Private
masters and intermediate frames remain under `state/private/`.

The [previous edited film](output/fastfence-demo-v2.mp4) and original recordings
below remain available. The latest film is v3.

## Original recording and supporting materials

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
