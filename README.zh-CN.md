# Codex YouTube 字幕分析 Skill

[![Codex Skill](https://img.shields.io/badge/Codex-Skill-111827)](skills/analyze-youtube-video/SKILL.md)
[![YouTube 字幕](https://img.shields.io/badge/YouTube-%E5%AD%97%E5%B9%95-FF0000)](skills/analyze-youtube-video/scripts/extract_transcript.py)
[![公开安全](https://img.shields.io/badge/%E5%85%AC%E5%BC%80%E5%AE%89%E5%85%A8-%E4%B8%8D%E5%90%AB%E7%A7%98%E5%AF%86-15803D)](#安全规则)

语言：[English](README.md) | **简体中文**

一个可复用的 Codex Skill：把可访问的 YouTube 字幕转换成紧凑、可追溯的分析语料，不要求 Codex 处理完整视频，也不把直接读取播放页作为唯一前提。

## 它解决什么问题

Agent 分析 YouTube 视频时经常遇到四类问题：

| 问题 | 本 Skill 的处理方式 |
| --- | --- |
| YouTube 播放页是动态页面，还可能出现自动请求限制、限流或解析失败，Codex 不一定能稳定读取。 | 不把“Codex 必须直接理解播放页”作为硬依赖，而是单独获取可访问的字幕轨道；视频页失败时，元数据再依次回退到 YouTube oEmbed 和搜索结果。 |
| 直接输入完整视频、音频或大量采样帧，通常会占用远高于口述内容分析所需的模型上下文。 | 主要分析输入是紧凑的字幕文本，token 消耗主要随口述文本长度变化，而不是随视频分辨率、帧数和音频数据量变化。 |
| 普通复制的字幕会丢失字幕类型、精确时间和来源信息。 | 默认先保存 JSON，保留原始浮点时间、持续时间、语言以及人工/自动字幕轨道类型。 |
| 只有摘要而没有原文位置，用户很难复核。 | 在重要结论后添加可点击时间链接，直接定位到视频中的对应原话。 |

它特别适合回答“视频里说了什么”：摘要、观点整理、提纲、时间线、结构化信息提取、视频比较，或者把字幕作为 RAG 语料回答具体问题。

## 为什么只分析字幕

进入模型主要工作上下文的是口述文本和少量元数据。默认流程不上传视频画面、不解码完整音轨，也不抽取大量视频帧。对于长视频，这通常可以显著降低 token 和处理成本，同时保留完整的口述顺序。

字幕是语料，不是固定分析模板。Codex 可以根据用户提示词进行摘要、整理观点与依据、检索相关段落回答问题，或者另外调用外部来源做事实核查；分析形式由用户问题决定。

## 播放页受限时为什么仍可能工作

字幕获取与 Codex 直接读取 YouTube 播放页不是同一个步骤。因此，当播放页无法稳定解析、但字幕轨道仍可访问时，Skill 仍可能取得字幕并继续分析。

这里所说的“绕开”，是绕开“必须让 Codex 直接读取和理解播放页”这一依赖，不是绕过 YouTube 的访问控制。它不能突破登录、会员、年龄、地区限制、关闭字幕或请求限流；如果字幕接口同样不可访问，字幕工作流就会停止并明确报告原因。

## 能力边界

| 默认支持 | 默认不支持 |
| --- | --- |
| 存在可访问人工字幕或自动字幕的公开视频 | 无字幕、字幕被关闭，或者字幕请求被 YouTube 阻止的视频 |
| 与口述内容有关的问题：摘要、观点、论据、数字、时间线、比较、信息提取和基于字幕的问答 | 依赖图表、演示动作、人物画面身份、字幕未记录的屏幕文字、音乐、音效、语气或剪辑的问题 |
| 用时间链接定位支撑结论的原话 | 自动证明讲者的主张真实可靠 |
| 尽力获取标题、频道和日期，并明确记录来源与不确定性 | 根据标题、频道更新规律、搜索上下文或当前日期猜测上传日期 |
| 根据字幕轨道信息提示自动字幕和不清晰措辞的风险 | 静默修正不确定字幕，或者根据标题、缩略图、评论和搜索摘要猜测视频内容 |

字幕失败时，Skill 不会自动下载视频或转录音频。音频转录和多模态视频分析是另外的、可能成本更高的工作流，需要用户明确同意。

## 这是什么

本仓库包含一个 Codex Skill 和配套字幕提取器。它把可用字幕转换成包含完整元数据的 JSON，另外生成便于阅读的时间戳文本，再由 Codex 根据用户提示词分析，并按需添加原话链接。

## Skill

| Skill | 用途 |
| --- | --- |
| [`analyze-youtube-video`](skills/analyze-youtube-video/SKILL.md) | 确认视频 URL、配置隔离的 Python 环境、提取字幕与元数据，再按用户提示词分析并添加时间链接。 |

## 示例提示词

```text
使用 $analyze-youtube-video 总结这个视频，并在每项主要结论后连接到对应原话时间：YOUTUBE_URL
```

```text
使用 $analyze-youtube-video 找到 CHANNEL_NAME 最新一期已经完成的公开视频，整理讲者的观点、依据、预测和保留条件。
```

```text
使用 $analyze-youtube-video 把这个视频的字幕作为 RAG 语料回答：讲者认为需求将发生变化的原因是什么？
```

## 功能特点

- 即使 URL 含有 `t=`、`start=` 或时间片段，默认仍处理完整视频。
- 默认先保存结构化 JSON，保留原始浮点开始时间、持续时间、字幕语言和人工/自动轨道类型。
- 另外生成带可读时间戳的文本，方便人工查看。
- 元数据固定按视频页、YouTube oEmbed、当前搜索结果的顺序回退。
- 不推断上传日期。只能从标题得到日期时标注“标题日期”，仍无法确认时标注“日期未知”。
- 按需添加 `https://www.youtube.com/watch?v=VIDEO_ID&t=51s` 形式的原话定位链接。
- 分析方式取决于用户提示词，不强制套用通用总结或观点模板。

## 推荐目录

```text
skills/
  analyze-youtube-video/
    SKILL.md
    requirements.txt
    agents/openai.yaml
    scripts/extract_transcript.py
    tests/test_extract_transcript.py
```

## 安装与使用

把 Skill 文件夹复制到 Codex Skills 目录：

```bash
git clone https://github.com/tsetsugekka/codex-youtube-transcript-analysis-skill.git
mkdir -p ~/.codex/skills
cp -R codex-youtube-transcript-analysis-skill/skills/analyze-youtube-video ~/.codex/skills/
```

重新启动或刷新 Codex 的 Skill 发现，然后在提示词中调用 `$analyze-youtube-video`。

本 Skill 需要 Python 3.9 或更高版本，Python 包只安装到 Skill 自己的 `.venv`。如果系统缺少 Python，Skill 要求 Codex 先说明拟采用的安装方式并取得用户许可，才能安装 Python 或系统级组件。

在 Skill 目录运行回归测试：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
env PYTHONPYCACHEPREFIX=/tmp/youtube-skill-pycache \
  .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

## 安全规则

- 不要把 API 密钥、Cookie、浏览器配置、账户数据或私有日志放进 Skill。
- 使用 Skill 自己的虚拟环境；不要全局安装依赖，也不要运行 `sudo pip`。
- 私密、会员、年龄限制、地区限制或需要登录的字幕默认视为不可访问，除非用户明确授权另外的认证流程。
- 不隐藏元数据抓取失败；YouTube 疑似限流时停止增加请求频率。

## 免责声明

这个工作流分析的是可用字幕，而不是完整视听内容。降低 token 消耗是设计优势，不代表固定比例的节省；字幕长度、用户要求的分析深度以及是否需要外部核查仍会影响上下文用量。

自动字幕可能存在识别错误。时间链接用于定位讲者原话，并不等于对讲者主张进行了独立事实核查。
