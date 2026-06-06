# Extraction Log

## Browser/Source Access

- Chrome initially had one open tab titled `Treatment plan timelines` at the Loom share URL.
- The Chrome automation bridge successfully claimed the tab and captured the first visible screen.
- A Loom menu overlay caused one click to land on an Atlassian billing login page. No credentials or sensitive data were entered or submitted.
- The Chrome automation bridge then became unresponsive, so extraction continued through the public Loom page state and local video processing.
- The Chrome tab was restored to the Loom share URL with AppleScript after the fallback extraction.

## Downloaded Evidence

- Loom public HTML contained Apollo state with video metadata, HLS playlist path, transcript path, and captions path.
- Transcript status was `success`, language `en`.
- Video recording type was `screen_cam`.
- Source dimensions were 1856 x 1080.
- Duration was about 255 seconds.
- Raw signed URLs were not preserved in repo metadata; signed query strings were redacted after assets were downloaded.

## Local Processing

- `ffmpeg` downloaded and merged the HLS source video after rewriting temporary signed child playlists in `/tmp`.
- `ffprobe` captured source stream metadata.
- `ffmpeg` extracted:
  - one frame for every transcript phrase start,
  - regular 15-second interval frames,
  - a 15-second contact sheet.

## Known Limits

- Local OCR was not available (`tesseract` not installed), so text extraction relied on Loom captions plus manual visual inspection of high-resolution frames.
- The video discusses Asana manual tracking, but it does not visibly switch into Asana. No Asana UI details were inferred.
- Raw video frames include PHI-like chart data. Written artifacts intentionally avoid copying those identifiers.
- The visible `Next Review Due` date creates a logic ambiguity: it appears to align with the level-of-care change date, while the current repo implementation calculates recurring review due dates from the latest valid staff signature date.
