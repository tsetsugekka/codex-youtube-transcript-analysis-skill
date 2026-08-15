---
name: analyze-youtube-video
description: Find a requested YouTube video or the latest relevant upload from a named channel, extract its available captions with the bundled transcript tool, and use the timestamped transcript as grounded source material for the user's requested task. Use when the user provides a YouTube URL or asks Codex to locate a video and create an abstract or detailed summary, organize viewpoints, build an outline or timeline, extract structured information, compare videos, fact-check claims, or answer questions from the transcript in a RAG-style grounded workflow; also use when the local subtitle environment needs first-time setup or repair.
---

# Analyze YouTube Video

Resolve the correct YouTube URL, extract timestamped subtitles with the bundled script, and use the transcript only according to the user's requested task or question.

## Feature and Boundary

Prefer subtitle-first processing because it converts a video into compact text before model use. This usually uses substantially fewer input tokens than sending the full video, audio, or sampled frames to a multimodal model, making long-video summarization, extraction, organization, and question answering faster and more economical.

Require an accessible YouTube caption track, either human-authored or automatically generated. Treat videos with no captions, disabled captions, inaccessible private or members-only captions, or captions blocked by region, age, authentication, or YouTube request restrictions as unsupported by this Skill's default workflow.

When captions cannot be retrieved, state that the subtitle workflow cannot process the video. Do not infer the video's contents from its title, thumbnail, description, comments, search snippets, or related coverage. Offer audio transcription or multimodal video analysis only as a separate workflow, explain the additional requirements or cost, and obtain the user's permission before proceeding.

Treat transcript-based work as processing of spoken content only. It is not sufficient when the user's question depends on video frames, charts, demonstrations, gestures, on-screen text omitted from captions, speaker identity from the image, music, sound effects, vocal tone, or editing choices.

When those non-text signals are material, tell the user that the subtitle workflow cannot answer reliably by itself. Explain which visual or audio evidence is missing and ask whether to augment or replace it with image, audio, or multimodal video analysis. Do not present a transcript-only conclusion as if the full audiovisual content was inspected.

## Canonical Paths

Resolve `SKILL_DIR` to the installed directory containing this `SKILL.md`. Do not use the literal placeholder below. Keep these paths canonical:

- Extractor: `$SKILL_DIR/scripts/extract_transcript.py`
- Dependency lock: `$SKILL_DIR/requirements.txt`
- Virtual environment: `$SKILL_DIR/.venv/`
- Temporary transcripts: `tmp/youtube-analysis/`
- Durable user-requested studies: `research/youtube/<YYYY-MM-DD_topic>/`

Keep `$SKILL_DIR/scripts/extract_transcript.py` as the single source of truth. Treat the Python script as a subtitle extractor only; do not embed a fixed analysis framework in it.

## Workflow

### 1. Resolve the Request

Identify:

- the target channel, creator, video, or topic;
- whether the user wants the latest upload or a particular date/title;
- whether Shorts, livestreams, premieres, members-only videos, or reposts are in scope;
- the exact task, question, output format, and requested depth.

Use an explicit user-provided URL directly after validating that it is a YouTube URL. When the user names a channel or asks for the latest video, search the current internet and prefer the official channel or official video page. Verify the channel identity, title, URL, and any explicitly sourced upload date needed to select the correct video before extracting subtitles. If the date cannot be confirmed, do not infer it; use other verified selection evidence or ask a concise question when the candidates remain ambiguous.

Treat URL parameters such as `t=51s`, `start=51`, or timestamp fragments as playback navigation only. Unless the user explicitly asks to start at that time, analyze that segment, or restrict the task to a stated range, extract and process the complete video from the beginning. Do not infer a partial-video scope merely because the submitted URL contains a timestamp. When the user explicitly requests a segment, preserve enough context before and after the range to interpret it accurately.

For “latest video,” normally select the newest completed public upload with usable content. Do not substitute a scheduled premiere, still-running livestream, Short, or third-party repost unless it matches the request. If two candidates remain materially ambiguous, ask one concise question.

### 2. Check and Bootstrap the Environment

Check existing state before installing anything:

```bash
command -v python3
python3 --version
test -f "$SKILL_DIR/scripts/extract_transcript.py"
test -f "$SKILL_DIR/requirements.txt"
test -x "$SKILL_DIR/.venv/bin/python"
```

If the bundled extractor or requirements file is absent, report that the Skill installation is incomplete and offer to reinstall it. Do not reconstruct missing package files from memory. The requirements file contains:

```text
youtube-transcript-api==1.2.4
requests==2.32.5
urllib3<2
```

If `python3` exists but the virtual environment is absent, initialize it and install only inside that environment:

```bash
python3 -m venv "$SKILL_DIR/.venv"
"$SKILL_DIR/.venv/bin/python" -m pip install -r "$SKILL_DIR/requirements.txt"
```

If the environment exists, avoid reinstalling on every run. Verify the dependency first:

```bash
"$SKILL_DIR/.venv/bin/python" -c "from youtube_transcript_api import YouTubeTranscriptApi; print('ok')"
```

If verification fails, rerun the requirements installation. Do not use global `pip`, `sudo pip`, or modify the system Python environment.

Require Python 3.9 or newer. If Python itself is missing, unusable, or too old to create the environment, stop before installing it. Tell the user that Python is required, state the detected problem and proposed installation method, explicitly offer to install it, and obtain the user's permission before running Homebrew, an OS installer, `pyenv`, or any other Python installation command. Treat a sandbox or network approval as separate from this user authorization.

If `venv` or `pip` is missing because the Python installation is incomplete, apply the same authorization rule before installing or replacing system-level Python components. Running `ensurepip` inside an already-created project virtual environment is allowed.

### 3. Extract the Transcript and Metadata

Create a temporary task directory. Save structured JSON first as the analysis source of truth, and generate the timestamped text only as a reading aid:

```bash
mkdir -p tmp/youtube-analysis
"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/extract_transcript.py" \
  "YOUTUBE_URL" \
  --format json \
  --output "tmp/youtube-analysis/VIDEO_ID.json" \
  --text-output "tmp/youtube-analysis/VIDEO_ID.txt"
```

Use `--languages` when the likely caption language differs from the default `zh-Hans,zh-Hant,zh,en,ja`. Read the complete transcript before drawing conclusions; do not analyze only the first lines or search snippets.

Analyze from the JSON, not from the reading text. Preserve and use every segment's original floating-point `start` and `duration`, together with `language`, `language_code`, `is_generated`, and `track_type`. The reading text deliberately renders human-friendly integer timestamps and must not replace the JSON for evidence selection, chunking, transcript-type reporting, or precise source navigation.

Resolve video metadata in this fixed fallback order:

1. Use the extractor's parsed YouTube video-page metadata.
2. If title or channel is still missing, use the extractor's YouTube oEmbed fallback.
3. If required metadata remains missing, search the current web and use the official YouTube video/search result where possible.

Inspect `video.metadata_sources`, `video.metadata_errors`, and `video.date_status` before presenting metadata. A metadata failure does not by itself mean subtitle extraction failed. Never infer an upload or publication date from the title, video ID, surrounding search results, channel cadence, or current date. Use a date as an upload/publication date only when the source explicitly identifies it as such. If only `video.title_date` is available, label it explicitly as `title date` (or the equivalent in the response language) and make clear that it is not a verified upload/publication date. If no date can be confirmed, label it `date unknown` (or the equivalent in the response language).

If no captions are available, try one reasonable alternate language ordering. If that still fails, report that the video lacks accessible captions or that YouTube blocked the request. Do not invent an analysis from the title and description. Do not automatically fall back to downloading video, transcribing audio, or sending the YouTube URL to a multimodal model; ask the user before expanding to an audio-transcription workflow.

When YouTube appears rate-limited or blocked, report the host or endpoint family and observed error, then stop increasing request volume.

### 4. Use the Transcript According to the Prompt

Let the user's prompt determine what to do with the transcript. Do not force a generic summary, viewpoint-analysis template, stock-analysis template, or fixed list of fields. The extractor's role ends after producing timestamped subtitle text.

Adapt to common task types:

- For an abstract or summary, match the requested length and level of detail while preserving the speaker's main structure and qualifications.
- For viewpoint organization, group claims, reasoning, evidence, predictions, actions, and caveats without turning inference into a direct quotation.
- For outlines, timelines, key points, entities, numbers, or other structured extraction, use the format requested by the user and retain the supporting timestamps.
- For comparison across multiple videos, extract each transcript separately and preserve the video identity and timestamp provenance of every conclusion.
- For RAG-style question answering, treat the transcript as the retrieval corpus. Retrieve the passages relevant to the question, answer only from supported content, add timestamp links, and say clearly when the transcript does not contain enough evidence to answer.

When a transcript is too long for reliable direct use, split it into coherent timestamp-preserving chunks, retrieve the most relevant chunks for the user's question, and keep enough neighboring context to avoid misreading isolated sentences. Do not discard timestamp provenance during chunking.

Distinguish clearly between:

- statements made by the speaker;
- conclusions inferred from the transcript;
- facts independently verified from external sources.

For time-sensitive fact-checking or market validation, browse current primary sources and label that work as external verification. For transcript-only summarization, organization, extraction, or question answering, do not imply that the speaker's claims were independently verified.

Read the complete transcript when the task depends on overall context. For targeted RAG-style questions, inspect the retrieved passages plus their surrounding context. Complete the requested task directly and quote only short excerpts when useful. Do not reproduce the full transcript in the response unless the user explicitly requests it and doing so is permitted.

### 5. Add Clickable Time Footnotes

Add a clickable timestamp footnote after a result sentence when the user would benefit from locating the speaker's original words. Prioritize summary conclusions, organized viewpoints, direct answers, disputed claims, numbers, price levels, forecasts, stated positions, and actions. Do not attach a link mechanically to every sentence.

Use this inline Markdown form:

```markdown
The speaker argues that demand is slowing as financing costs and weak income growth weigh on spending. ([00:33](https://www.youtube.com/watch?v=VIDEO_ID&t=33s))
```

Normalize links to:

```text
https://www.youtube.com/watch?v=VIDEO_ID&t=SECONDSs
```

Select evidence and supporting segments from the JSON's original floating-point timestamps. Convert to integer seconds only when constructing the YouTube `t=SECONDSs` URL and its visible human-readable label. Use the start of the supporting subtitle segment, or a few seconds earlier when necessary to preserve context. When one sentence depends on multiple distant passages, append multiple timestamp links. Keep the visible label human-readable, such as `[00:51]` or `[01:12:34]`.

These links support source navigation; they are not independent fact-check citations. State separately whether any external verification was performed.

### 6. Deliver the Result

Include the video title, channel, verified upload/publication date when available, and clickable YouTube URL, followed by the summary, organization, extraction, grounded answer, comparison, or analysis requested by the user. When the date is not verified, use `title date` or `date unknown` in the response language according to the rules above rather than presenting an estimate. Add timestamp footnotes where they materially improve traceability. Mention uncertainty caused by automatic captions, translation, missing context, or unclear wording, using the JSON transcript-track metadata rather than guessing the caption type.

Keep transcripts in `tmp/youtube-analysis/` for the active task and follow-up questions. Move them and any durable analysis into `research/youtube/<YYYY-MM-DD_topic>/` only when the user asks to retain the work or when the task explicitly calls for a durable research deliverable.
