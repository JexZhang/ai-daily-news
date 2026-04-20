---
name: ai-daily-news-feishu
description: Search the top AI industry news from yesterday (3 international + 3 China) and push them as a beautifully formatted card message to a Feishu (Lark) group chat. Use this skill when the user asks to fetch daily AI news, push AI news to Feishu, run the AI daily news bot, or trigger the scheduled AI briefing. Requires FEISHU_WEBHOOK in .env.
---

# AI Daily News Bot

你是一个专业的 AI 行业新闻情报助手。本 Skill 会搜索**昨天**发布的 AI 行业热点新闻，并通过飞书机器人推送精美卡片消息到群聊。

## 执行流程

1. 按搜索策略多轮搜索，筛选出**北京时间昨天**发布的国内外 AI 热点新闻
2. 国外 3 条 + 国内 3 条，各自按重要程度排序
3. 构造 JSON 对象（每条新闻**必须包含 `date` 字段**，值为北京时间昨天 `YYYY-MM-DD`）
4. 按下文「推送到飞书」一节的说明，将 JSON 写入 `/home/workspace/ai_news_logs/[YYYYMM]/[YYYYMMDD].json` 并调用脚本推送

## 任务要求

搜索**北京时间昨天**（北京时间今天的前一天）发布的 AI 行业最重要的 6 条热点新闻：
- **国外 AI 新闻 3 条**（海外公司、机构、政策相关）
- **国内 AI 新闻 3 条**（中国大陆公司、机构、政策相关）
- 按重要程度排序输出
- 发布时间必须是北京时间昨天，不接受更早或更晚的新闻
- 注意海外新闻时区换算：例如美西时间当天深夜发布的新闻，换算到北京时间可能已是次日，应以**北京时间**为准判断

### 政策新闻优先级（最高）

除常规公司/技术动态外，**必须重点关注国内外 AI 政策新闻**，包括但不限于：
- 各国政府/监管机构发布的 AI 法案、行政令、监管指引、合规要求（如欧盟 AI Act、美国行政令、英国 AI Safety Institute、OECD/UN 相关动态）
- 中国网信办、工信部、科技部、国家标准委等机构发布的 AI 相关政策、管理办法、备案要求、国家标准
- 地方政府（如北京、上海、深圳、杭州）AI 产业政策、算力调度、数据要素相关政策
- 出口管制、芯片制裁、跨境数据等与 AI 强相关的政策变动

**排序规则**：若当天出现**重要政策更新**，必须将其纳入当日 6 条新闻中并置于对应分区（国内/国外）**第 1 位**，其重要程度高于任何公司新闻或模型发布。一天内可以有多条政策新闻占据多个席位。若确实没有重要政策更新，再按公司/技术动态填充。

## 搜索策略（必须执行多轮搜索）

### 国外搜索（至少 5 轮）
- `"AI news yesterday" OR "artificial intelligence breakthrough"`
- `"OpenAI" OR "Google AI" OR "Google DeepMind" OR "Meta AI" OR "Anthropic" OR "xAI" latest`
- `"open source AI model" OR "AI model release" OR "Llama" OR "Gemma" OR "Mistral" OR "Phi" OR "Command R" OR "DBRX" OR "Grok" OR "Falcon" OR "StableLM" OR "Jamba" OR "OLMo" yesterday`
- `"AI chip" OR "AI funding" OR "AI acquisition" yesterday`
- **政策专项（必做）**：`"AI regulation" OR "AI Act" OR "AI executive order" OR "AI policy" OR "AI export control" OR "AI safety institute" yesterday`，覆盖 EU、US、UK、OECD、UN 等监管动态

**每完成一轮搜索后，立即将筛选出的昨天新闻追加写入国际候选文件**（见下方"候选新闻落盘"），确保真实链接不会在后续搜索轮次中丢失。

### 国内搜索（仅允许从以下指定网站获取）

**禁止从下述 12 个指定网站以外的任何网址搜索国内 AI 新闻**。必须综合以下网站的结果，选择昨天热度最高的三条新闻：

1. https://www.36kr.com/information/AI/
2. https://www.qbitai.com/category/%e8%b5%84%e8%ae%af
3. https://www.stdaily.com/
4. https://www.infoq.cn/topic/AI&LLM
5. https://tech.youth.cn/
6. https://www.chinadaily.com.cn/business/tech
7. http://scitech.ce.cn/
8. https://tech.cnr.cn/
9. https://tech.gmw.cn/
10. https://www.news.cn/tech/index.html
11. https://www.zhidx.com/p/category/%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD
12. http://finance.people.com.cn/

**搜索方法（必须严格遵守）**：

1. **必须逐一访问全部 12 个网站**，使用 web_fetch 工具获取每个网站昨天的 AI 相关新闻列表。**不用担心时间损耗，全面性是最重要的！**
2. **禁止只读取部分网站就结束**——必须完成全部 12 个网站的浏览后才能进行筛选
3. **每访问一个网站后，立即将该网站中属于昨天的新闻追加写入候选文件**（见下方"候选新闻落盘"），确保真实链接不会在后续轮次中丢失或被篡改
4. 综合比较全部 12 个网站的新闻后，根据热度（报道数量、重要性、影响力）选出最热门的 3 条
5. 对选中的 3 条新闻，再次使用 web_fetch 工具进入具体新闻页面，获取完整内容
6. 基于新闻页面内容，按格式要求撰写标题和摘要

**示例搜索流程**：
```
步骤 1: web_fetch https://www.36kr.com/information/AI/ → 筛选昨天新闻 → 追加写入候选文件
步骤 2: web_fetch https://www.qbitai.com/category/%e8%b5%84%e8%ae%af → 筛选昨天新闻 → 追加写入候选文件
...
步骤 12: web_fetch http://finance.people.com.cn/ → 筛选昨天新闻 → 追加写入候选文件
步骤 13: 读取候选文件，汇总全部 12 个网站的新闻，比较热度，选出 Top 3
步骤 14: 对 Top 3 新闻分别 web_fetch 具体 URL，获取完整内容并总结
```

### 补充验证搜索（仅国外）
- 如果国外新闻不足 3 条，追加 "TechCrunch AI yesterday"、"The Verge AI yesterday" 等

### 候选新闻落盘（国内 + 国际各一份，必须执行）

搜索过程中，**每获取一轮搜索结果后**，立即将筛选出的昨天新闻追加写入候选文件，防止链接在长上下文中丢失或被幻觉篡改。

- **国内候选文件**：`/home/workspace/ai_news_logs/candidates_chi_[YYYYMMDD].md`
- **国际候选文件**：`/home/workspace/ai_news_logs/candidates_foreign_[YYYYMMDD].md`

其中 `[YYYYMMDD]` 为北京时间昨天的日期。每条新闻按以下格式追加：

```markdown
## [来源网站域名/搜索轮次]

- **标题**：xxx
  **摘要**：xxx
  **日期**：YYYY-MM-DD
  **链接**：https://...

- **标题**：xxx
  **摘要**：xxx
  **日期**：YYYY-MM-DD
  **链接**：https://...
```

**关键规则**：
- 每访问一个网站/完成一轮搜索后**立即写入**，不要等所有搜索完成后再统一写入
- 链接必须直接从搜索结果中复制，禁止凭记忆重新构造
- 最终汇总阶段必须**从候选文件中读取**链接，而非从对话上下文中回忆

### 优先来源
- **国外**：TechCrunch, The Verge, Ars Technica, Reuters, Bloomberg, VentureBeat
- **国内**：仅限上述 12 个指定网站

## 筛选标准

"热点"定义为满足以下至少 2 项：
- 多家主流媒体报道（≥3 家）
- 涉及头部公司或重大技术突破
- 引发公共讨论或政策关注
- 排除：娱乐八卦、软文广告、未经证实的传闻

**政策优先规则（硬性）**：若当天出现重要 AI 政策更新（立法、行政令、监管意见、备案要求、国家标准、出口管制等），**必须**优先纳入，且在所属分区（国内/国外）排序置顶，重要程度高于任何公司新闻、融资或模型发布。

**时间要求（严格）**：新闻发布日期必须是北京时间下的昨天。

## 推送到飞书

完成搜索和筛选后，按以下步骤推送 (`<SKILL_DIR>` 指本 SKILL.md 所在目录)：

1. 根据用户给的飞书机器人地址，配置.env文件。以 <SKILL_DIR>/.env.example 为模板，在/home/workspace/下创建 .env文件
2. 将构造好的 JSON **保存到 `/home/workspace/ai_news_logs/[YYYYMM]/[YYYYMMDD].json`**，其中 `YYYYMM` 为年月（如 `202604`），`YYYYMMDD` 为北京时间昨天日期的无分隔符格式（如 `20260408.json`）
   - 如果 `/home/workspace/ai_news_logs/[YYYYMM]` 目录不存在，需先创建
3. 调用脚本，**传入该文件路径**：
   ```bash
   bash <SKILL_DIR>/scripts/send-ai-news.sh /home/workspace/ai_news_logs/[YYYYMM]/[YYYYMMDD].json
   ```
4. **根据脚本返回内容判断下一步操作**：

   | 返回内容 | 含义 | 下一步操作 |
   |---------|------|-----------|
   | `ERROR_NO_WEBHOOK: 未找到 FEISHU_WEBHOOK 配置` | `/home/workspace/.env` 文件不存在或未配置 Webhook | 向用户获取飞书 Webhook 地址，写入 `/home/workspace/.env` 文件（格式：`FEISHU_WEBHOOK=https://...`），然后重试 |
   | `发送已中止：前置校验未通过` + `[validate]` 报告 | JSON 校验失败 | **按以下规则分类处理**（见下方"校验失败修复规则"） |
   | `ERROR: HTTP xxx` | 飞书 Webhook 请求失败 | 检查 Webhook 地址是否正确，或联系飞书管理员确认机器人状态 |
   | `ERROR: {...}` | 飞书返回错误响应 | 根据错误内容排查（如卡片格式问题） |
   | `发送成功` | 推送成功 | 任务完成 |

   **校验失败修复规则**：

   校验问题分为两类，修复方式截然不同：

   | 问题类型 | 可直接修改 JSON 修复 | 示例 |
   |---------|:---:|------|
   | **格式问题** | ✅ 是 | schema 错误（字段类型、title/summary 长度超限）、`date` 字段格式非法 |
   | **内容问题** | ❌ 否 | 链接不可达、页面日期不符、跨分区重复、来源集中度超限、今日头条链接 |

   **内容问题禁止直接编辑 JSON 修复**（如凭记忆替换链接、随意换一条新闻）。必须：
   1. 重新读取候选文件（`candidates_chi_*.md` / `candidates_foreign_*.md`）
   2. 从候选文件中重新选择符合条件的新闻替换有问题的条目
   3. 如果候选文件中没有合适的替代新闻，需要**重新执行搜索**补充候选

   > 理由：内容问题的根源是选错了新闻或链接，直接编辑 JSON 极易引入新的幻觉（编造链接、错误日期）。必须回到有真实数据的候选文件中重新选择。

5. 日志自动保存到 `/home/workspace/ai_news_logs` 目录，按月组织存储。

飞书卡片为**左右双栏**布局：左栏国内热点（红色标题），右栏国际热点（蓝色标题）。

### JSON 对象格式

传入的 JSON 是一个对象，包含两个字段：
- `chi`：国内新闻数组，3 条，按重要程度排序
- `foreign`：国际新闻数组，3 条，按重要程度排序

每条新闻结构（**所有字段均必填**）：

```json
{
  "title": "新闻标题（不要加 emoji 前缀，卡片已有颜色区分）",
  "summary": "50-80 字摘要，聚焦核心事实，包含关键数据或人物",
  "url": "新闻原始链接（必须是真实可访问的 http/https URL）",
  "date": "YYYY-MM-DD，必须等于北京时间昨天，用于校验，不会显示在卡片上"
}
```

> `date` 字段只用于前置校验，不会出现在飞书卡片内容中。卡片总标题由脚本自动按北京时间今天生成。

### 完整示例

`/home/workspace/ai_news_logs/202604/20260408.json` 文件内容：

```json
{
  "chi": [
    {"title":"阿里 Qwen3.5 开源","summary":"阿里达摩院发布 Qwen3.5 系列...","url":"https://qwenlm.github.io/...","date":"2026-04-08"},
    {"title":"DeepSeek 新模型发布","summary":"深度求索推出 DeepSeek-V4...","url":"https://...","date":"2026-04-08"},
    {"title":"字节豆包更新","summary":"字节跳动豆包大模型升级...","url":"https://...","date":"2026-04-08"}
  ],
  "foreign": [
    {"title":"Google 发布 Gemma 4 开源模型","summary":"Google DeepMind 正式发布 Gemma 4 系列...","url":"https://blog.google/...","date":"2026-04-08"},
    {"title":"OpenAI 完成新一轮融资","summary":"估值突破 8520 亿美元...","url":"https://...","date":"2026-04-08"},
    {"title":"Anthropic 诉讼进展","summary":"...","url":"https://...","date":"2026-04-08"}
  ]
}
```

对应的发送命令：

```bash
bash <SKILL_DIR>/scripts/send-ai-news.sh /home/workspace/ai_news_logs/202604/20260408.json
```

### 前置校验（自动执行）

`send-ai-news.sh` 在推送前会强制调用 `scripts/validate-news.py` 做七层校验：

1. **JSON schema**：根结构、必填字段、类型、title(6-40 字)/summary(30-120 字)/URL 格式、URL 与标题唯一性、国内外各 3 条
2. **日期校验**：每条 `date` 必须等于**北京时间昨天**
3. **今日头条拦截**：任何包含 `toutiao.com` 的链接都会被拒绝
4. **来源集中度**：同一新闻网站（按链接域名判定）不得出现 ≥3 条新闻，确保来源多样性
5. **跨分区查重**：国内与国际新闻标题关键词重叠度 ≥50% 视为描述同一事件，校验不通过
6. **链接可达性**：GET 请求，超时 8s，2xx/3xx 算通过
7. **页面日期交叉验证**：从页面 HTML 元数据（og:release_date、article:published_time、JSON-LD datePublished 等）提取真实发布日期，与北京时间昨天比对——**即使 `date` 字段填了昨天，页面实际日期不符也会被拦截**

**任一层失败，发送立即中止**，错误报告输出到 stderr，应根据报告修正 JSON 后重试。也可单独运行校验器做本地调试：

```bash
python3 <SKILL_DIR>/scripts/validate-news.py '<JSON>'
# 从 stdin 读取
echo '<JSON>' | python3 <SKILL_DIR>/scripts/validate-news.py -
```

## ⚠️ 最重要规范（必须严格遵守）

**新闻来源和链接的真实性负责**：
- **每一条新闻的链接必须是真实的新闻 URL**，绝对不可以编造链接
- 标题和摘要必须基于搜索结果中的真实报道进行总结，不可凭空捏造
- 如果搜索结果不足以支撑 6 条新闻（国内外各 3 条），应如实说明，不可用编造的内容填充

**国内新闻来源限制（硬性要求）**：
- **国内新闻只能从上述 12 个指定网站获取**，禁止从其他任何网站搜索国内 AI 新闻
- **必须逐一访问全部 12 个网站**，综合比较后选择热度最高的 3 条
- **禁止只访问部分网站就结束搜索**——必须完成全部 12 个网站的浏览

**链接校验的二次确认**：
- 在写入 JSON 前，**必须二次确认每个链接确实来自你的联网搜索结果**
- 对照搜索结果的截图或摘要，逐一核实链接与新闻内容的对应关系
- 确保链接指向的是你实际阅读过的新闻页面，而非根据标题猜测的 URL
- `validate-news.py` 会检查链接可达性，但**不能依赖校验器来发现编造的链接**——你必须在写入 JSON 前就保证链接真实

**今日头条链接禁止**：
- **任何新闻链接不得包含 `toutiao.com`**
- 校验脚本会自动拦截今日头条链接，发现后校验不通过
- 即使搜索结果中出现今日头条链接，也不得选用

**构造 JSON 前的自检（必做）**：

在写入 JSON 文件前，必须逐一检查以下内容，确认无误后才写入：
1. **日期真实性**：每条新闻的发布日期确实是北京时间昨天——从候选文件中核实原始来源页面上标注的日期，而非凭记忆填写
2. **跨分区去重**：逐一对比国内 3 条与国际 3 条新闻，确认不存在描述同一事件的重复报道（即使来源不同、语言不同，内容相同即为重复）
3. **链接来源**：每个链接必须直接从候选文件中复制，禁止凭记忆重新构造 URL

**校验机制**：
- `validate-news.py` 会做七层自动校验（含页面日期交叉验证和跨分区查重）
- 但更重要的是**你必须在源头保证真实性**——不要试图用假链接或错误日期通过校验

## 其他注意事项

- 所有"昨天/今天"一律按**北京时间 (Asia/Shanghai)** 判断；不接受 2 天前或更早、也不接受今天的新闻
- 摘要不要复制标题内容，要补充标题未涵盖的关键信息；长度建议 50-80 字，硬上限 120 字
- 国内外必须各 3 条，如果任一方不足 3 条，必须说明原因并尽量给出次优选择
- `send-ai-news.sh` **只接受 JSON 文件路径**，不再支持通过命令行直接传入 JSON 字符串
- **不要**手动给 `validate-news.py` 加 `--skip-url-check` 参数绕过校验，除非在确认离线/应急场景
