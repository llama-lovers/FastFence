# FastFence presentation and recorded demo

English slides and video captions, with Polish speaker notes. The main pitch
uses slides 1–7 and takes approximately three minutes. Slide 8 is an optional
benchmark appendix with its original package version and measurement scope.

## Deliverables

- [Editable PowerPoint](output/fastfence-pitch.pptx)
- [PDF slides](output/fastfence-pitch.pdf)
- [Recorded product demo](output/fastfence-demo.mp4)
- [English video captions](output/demo-captions.srt)
- [Polish narration and manual demo instructions](demo-script.pl.md)
- [Evidence and claim boundaries](evidence.md)
- [Outcomes from the recorded session](output/demo-evidence.json)

Open the PPTX or PDF for the pitch. Play the MP4 separately when introducing
the recorded demonstration. The video has English captions and no recorded
voice. The Polish script is ready for the presenter to read or record.
The MP4 is a local deliverable, not a published YouTube link.

The footage uses an isolated installation of public PyPI FastFence 1.0.7 and
actual local models. Its displayed rules and decisions are real. Test prompts
are synthetic and contain no customer data. Connection credentials are outside
the exported footage. The demonstration changes only its disposable policy.

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
The automated recorder is `scripts/record_demo.py`; run it with `--help` for
its explicit inputs. It requires Playwright Chromium and FFmpeg.
Use a fresh, isolated FastFence installation: the recorder activates rules.
Never point it at an operator's active configuration. Keep any credentials file
outside this directory and outside source control.

Test counts establish the stated test scopes, not universal semantic accuracy.
The 1,000-request result uses a controlled provider. The separate 12-request
check uses actual Laya and Ollama. Historical latency figures belong to 1.0.2.
