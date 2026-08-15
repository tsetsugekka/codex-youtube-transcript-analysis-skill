# Codex YouTube 字幕分析 Skill

[![Codex Skill](https://img.shields.io/badge/Codex-Skill-111827)](skills/analyze-youtube-video/SKILL.md)
[![YouTube 字幕](https://img.shields.io/badge/YouTube-%E5%AD%97%E5%B9%95-FF0000)](skills/analyze-youtube-video/scripts/extract_transcript.py)
[![公开安全](https://img.shields.io/badge/%E5%85%AC%E5%BC%80%E5%AE%89%E5%85%A8-%E4%B8%8D%E5%90%AB%E7%A7%98%E5%AF%86-15803D)](#安全规则)

语言：[English](README.md) | **简体中文**

一个可复用的 Codex Skill：查找 YouTube 视频，将可访问字幕提取为包含完整元数据的 JSON，再根据用户真正的问题进行分析，并为关键结论添加可点击的原话时间链接。

## 这是什么

本仓库包含一个字幕优先的 YouTube 分析 Skill。它先把字幕转换成紧凑文本，通常比处理完整视频、音频或大量采样画面更节省输入 token。

字幕只是分析依据，不绑定固定模板。Codex 可以根据提示词完成摘要、观点整理、结构化信息提取、时间线、视频比较、结合外部来源的事实核查，或者把字幕作为 RAG 语料回答问题。

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

这个工作流分析的是可用字幕，而不是完整视听内容。如果问题依赖画面、图表、动作、字幕未包含的屏幕文字、音乐、音效、语气或剪辑，单靠本 Skill 不能可靠回答。没有可访问字幕的视频不在默认能力范围内；音频转录或多模态视频分析需要另外取得用户同意。

自动字幕可能存在识别错误。时间链接用于定位讲者原话，并不等于对讲者主张进行了独立事实核查。
