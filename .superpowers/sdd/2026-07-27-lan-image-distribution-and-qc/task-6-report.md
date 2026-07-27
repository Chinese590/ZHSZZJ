# Task 6 report — High-DPI preview

## Change
- `_preview_size()` now scales the viewport by `devicePixelRatioF()`, rounds up, and clamps each edge to 1024–4096 physical pixels.
- Existing preview cache, thumbnail decode, and 1:1 full-resolution loading path remain unchanged.

## Verification
- Red test before implementation: `test_preview_size_uses_physical_pixels_and_not_legacy_2560_cap` failed with `(2560, 2560)` instead of `(4096, 3600)`.
- `$env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONPATH='desktop/production'; & 'D:\Ai agent\projects\ZHSZZJ\.venv\Scripts\python.exe' -m pytest desktop/tests/test_image_loader.py desktop/tests/test_image_viewer.py -q` — 7 passed in 1.88s.
- `git diff --check` — passed.
- `ocr review --audience agent --timeout 2` could not run: no OCR LLM endpoint is configured.
