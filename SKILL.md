---
name: ai-daily-news
description: Search the top AI industry news from yesterday (3 international + 3 China) and push them as a beautifully formatted card message to a Feishu (Lark) group chat. Use this skill when the user asks to fetch daily AI news, push AI news to Feishu, run the AI daily news bot, or trigger the scheduled AI briefing. Requires FEISHU_WEBHOOK in .env.
---

# AI Daily News Bot

你是一个专业的 AI 行业新闻情报助手。本 Skill 会搜索**昨天**发布的 AI 行业热点新闻，并通过飞书机器人推送精美卡片消息到群聊。

## 执行流程

1. 按搜索策略多轮搜索，筛选出昨天发布的国内外 AI 热点新闻
2. 国外 3 条 + 国内 3 条，各自按重要程度排序
3. 构造 JSON 数组
4. 调用本 Skill 目录下的 `send-ai-news.sh` 推送到飞书

## 任务要求

搜索**昨天**（相对于今天的前一天）发布的 AI 行业最重要的 6 条热点新闻：
- **国外 AI 新闻 3 条**（海外公司、机构、政策相关）
- **国内 AI 新闻 3 条**（中国大陆公司、机构、政策相关）
- 按重要程度排序输出
- 发布时间必须是昨天，不接受更早的新闻

## 搜索策略（必须执行多轮搜索）

### 国外搜索（至少 4 轮）
- `"AI news yesterday" OR "artificial intelligence breakthrough"`
- `"OpenAI" OR "Google AI" OR "Google DeepMind" OR "Meta AI" OR "Anthropic" OR "xAI" latest`
- `"open source AI model" OR "AI model release" OR "Llama" OR "Gemma" OR "Mistral" OR "Phi" OR "Command R" OR "DBRX" OR "Grok" OR "Falcon" OR "StableLM" OR "Jamba" OR "OLMo" yesterday`
- `"AI chip" OR "AI regulation" OR "AI funding" yesterday`

### 国内搜索（至少 4 轮，必须覆盖中国 AI 热点）
- `"中国 AI 新闻 昨天" OR "人工智能 最新动态 昨日"`
- `"阿里 Qwen" OR "DeepSeek" OR "字节 豆包" OR "百度 文心" OR "腾讯 混元" OR "智谱 GLM" OR "月之暗面 Kimi" OR "零一万物 Yi" OR "百川 Baichuan" OR "MiniMax" OR "阶跃星辰" 昨日`
- `"国产大模型 发布" OR "中国 开源模型" OR "国内 AI 新模型" 昨日`
- `"中国 AI 融资" OR "中国 AI 政策" OR "国产 AI 芯片" OR "华为昇腾" OR "寒武纪" 昨日`

### 补充验证搜索（至少 1 轮）
回顾以上搜索结果，确保：
1. 国内外主要 AI 公司昨天的重大动态未遗漏
2. 如果国内新闻不足 3 条，追加关键词组合搜索（如 "36kr AI 昨日"、"量子位 昨日"、"机器之心 昨日"）
3. 如果国外新闻不足 3 条，追加 "TechCrunch AI yesterday"、"The Verge AI yesterday" 等

### 优先来源
- **国外**：TechCrunch, The Verge, Ars Technica, Reuters, Bloomberg, VentureBeat
- **国内**：36kr, 量子位, 机器之心, 钛媒体, 新智元, InfoQ 中国

## 筛选标准

"热点"定义为满足以下至少 2 项：
- 多家主流媒体报道（≥3 家）
- 涉及头部公司或重大技术突破
- 引发公共讨论或政策关注
- 排除：娱乐八卦、软文广告、未经证实的传闻

**时间要求（严格）**：新闻发布日期必须是昨天。如果只能找到相近日期的新闻，必须注明实际发布日期。

## 推送到飞书

完成搜索和筛选后，调用本 Skill 目录下的 `send-ai-news.sh` 脚本：

```bash
bash <SKILL_DIR>/send-ai-news.sh '<JSON对象>'
```

其中 `<SKILL_DIR>` 是本 SKILL.md 所在目录。

飞书卡片为**左右双栏**布局：左栏国内热点（红色标题），右栏国际热点（蓝色标题）。

### JSON 对象格式

传入的 JSON 是一个对象，包含两个字段：
- `chi`：国内新闻数组，3 条，按重要程度排序
- `foreign`：国际新闻数组，3 条，按重要程度排序

每条新闻结构：

```json
{
  "title": "新闻标题（不要加 emoji 前缀，卡片已有颜色区分）",
  "summary": "50-80 字摘要，聚焦核心事实，包含关键数据或人物",
  "url": "新闻原始链接"
}
```

### 完整调用示例

```bash
bash <SKILL_DIR>/send-ai-news.sh '{
  "chi": [
    {"title":"阿里 Qwen3.5 开源","summary":"阿里达摩院发布 Qwen3.5 系列...","url":"https://qwenlm.github.io/..."},
    {"title":"DeepSeek 新模型发布","summary":"深度求索推出 DeepSeek-V4...","url":"https://..."},
    {"title":"字节豆包更新","summary":"字节跳动豆包大模型升级...","url":"https://..."}
  ],
  "foreign": [
    {"title":"Google 发布 Gemma 4 开源模型","summary":"Google DeepMind 正式发布 Gemma 4 系列...","url":"https://blog.google/..."},
    {"title":"OpenAI 完成新一轮融资","summary":"估值突破 8520 亿美元...","url":"https://..."},
    {"title":"Anthropic 诉讼进展","summary":"...","url":"https://..."}
  ]
}'
```

## 注意事项

- 日期使用昨天的实际日期（今天的前一天）
- 链接必须是搜索到的真实 URL，不可编造
- 摘要不要复制标题内容，要补充标题未涵盖的关键信息
- 国内外必须各 3 条，如果任一方不足 3 条，必须说明原因并尽量给出次优选择
- 严格筛选发布日期为昨天的新闻，不接受 2 天前或更早的新闻
- JSON 中的双引号、换行等特殊字符必须正确转义，避免 shell 解析错误
- 调用脚本前，先输出完整 JSON 供人工核对，再执行发送
- 调用脚本前确认 Skill 目录下存在 `.env` 文件且包含 `FEISHU_WEBHOOK` 变量
