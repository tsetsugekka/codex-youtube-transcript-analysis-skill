# YouTube Transcript Analysis Skill for Codex

[![Codex Skill](https://img.shields.io/badge/Codex-Skill-111827)](skills/analyze-youtube-video/SKILL.md)
[![YouTube Captions](https://img.shields.io/badge/YouTube-Captions-FF0000)](skills/analyze-youtube-video/scripts/extract_transcript.py)
[![Public Safe](https://img.shields.io/badge/Public--safe-No%20secrets-15803D)](#security-rules)

Languages: **English** | [简体中文](README.zh-CN.md)

A reusable Codex skill that finds YouTube videos, extracts accessible captions into metadata-rich JSON, and answers the user's actual question with clickable source timestamps.

## What This Is

This repository packages one Codex skill for subtitle-first YouTube analysis. It turns captions into compact text before model analysis, which is generally more token-efficient than processing full video, audio, or sampled frames.

The transcript is a grounded source, not a fixed analysis template. Codex can summarize, organize viewpoints, extract structured facts, build timelines, compare videos, fact-check claims with external sources, or answer questions from the transcript as a RAG corpus.

## Skill

| Skill | Purpose |
| --- | --- |
| [`analyze-youtube-video`](skills/analyze-youtube-video/SKILL.md) | Resolve a video URL, bootstrap an isolated Python environment, extract captions and metadata, then perform prompt-driven analysis with timestamp links. |

## Example Prompts

```text
Use $analyze-youtube-video to summarize this video and link each major conclusion to the supporting timestamp: YOUTUBE_URL
```

```text
Use $analyze-youtube-video to find the latest completed public upload from CHANNEL_NAME and organize the speaker's claims, evidence, forecasts, and caveats.
```

```text
Use $analyze-youtube-video to treat this video's transcript as a RAG corpus and answer: What reasons does the speaker give for the expected change in demand?
```

## Features

- Processes the complete video by default, even when the supplied URL contains `t=`, `start=`, or a timestamp fragment.
- Saves structured JSON first, preserving raw floating-point start times, durations, caption language, and manual/automatic track type.
- Generates a separate readable transcript with human-friendly timestamps.
- Resolves metadata in a fixed order: YouTube video page, YouTube oEmbed, then current search results when Codex still needs missing fields.
- Never infers upload dates. It labels a date found only in the title as `title date`, and otherwise reports `date unknown`.
- Adds selective links such as `https://www.youtube.com/watch?v=VIDEO_ID&t=51s` so readers can jump to supporting speech.
- Keeps analysis prompt-driven instead of forcing a generic summary or viewpoint template.

## Recommended Layout

```text
skills/
  analyze-youtube-video/
    SKILL.md
    requirements.txt
    agents/openai.yaml
    scripts/extract_transcript.py
    tests/test_extract_transcript.py
```

## Installation and Usage

Copy the skill folder into your Codex skills directory:

```bash
git clone https://github.com/tsetsugekka/codex-youtube-transcript-analysis-skill.git
mkdir -p ~/.codex/skills
cp -R codex-youtube-transcript-analysis-skill/skills/analyze-youtube-video ~/.codex/skills/
```

Restart or refresh Codex skill discovery, then invoke `$analyze-youtube-video` in your prompt.

The skill requires Python 3.9 or newer and installs Python packages only into its own `.venv`. If Python itself is missing, the instructions require Codex to explain the proposed installation and obtain user permission before installing Python or system-level components.

To run the bundled regression tests from the skill directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
env PYTHONPYCACHEPREFIX=/tmp/youtube-skill-pycache \
  .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

## Security Rules

- Do not place API keys, cookies, browser profiles, account data, or private logs in the skill package.
- Use the isolated skill virtual environment; do not install dependencies globally or with `sudo pip`.
- Treat private, members-only, age-restricted, region-blocked, or authentication-gated captions as inaccessible unless the user explicitly authorizes a separate authenticated workflow.
- Metadata lookup failures must not be hidden, and repeated requests must stop when YouTube appears rate-limited.

## Disclaimer

This workflow analyzes available captions, not the complete audiovisual work. It is unsuitable by itself when the answer depends on frames, charts, gestures, on-screen text omitted from captions, music, sound effects, tone, or editing. Videos without accessible captions are outside the default workflow; audio transcription or multimodal video analysis requires a separate user-approved process.

Automatic captions may contain recognition errors. Timestamp links provide navigation to the source speech, not independent verification of the speaker's claims.
