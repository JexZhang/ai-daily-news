# ai-daily-news (Claude Code Skill)

一个 Claude Code Skill —— 每日自动搜索 AI 行业热点新闻（国内外各 3 条），通过飞书机器人推送精美卡片消息到群聊。

## 工作原理

本项目是一个 [Claude Code Skill](https://docs.anthropic.com/en/docs/claude-code/skills)，打包了：

1. **SKILL.md** — 搜索策略、筛选标准、输出要求的完整提示词
2. **send-ai-news.sh** — 把新闻 JSON 转成飞书卡片并推送

触发 Skill 后，Claude 会按策略多轮搜索昨天的 AI 新闻，筛选出国内外各 3 条热点，然后调用 `send-ai-news.sh` 推送到飞书群聊。

```
Claude (触发 Skill) → 多轮搜索 → JSON → send-ai-news.sh → 飞书卡片
```

## 安装

### 1. 克隆到 Skills 目录

```bash
# 用户级别（所有项目可用）
git clone https://github.com/<your-username>/ai-daily-news-bot.git ~/.claude/skills/ai-daily-news

# 或项目级别（仅当前项目可用）
git clone https://github.com/<your-username>/ai-daily-news-bot.git .claude/skills/ai-daily-news
```

### 2. 配置飞书 Webhook

在飞书群聊中添加自定义机器人获取 Webhook 地址，然后：

```bash
cd ~/.claude/skills/ai-daily-news
cp .env.example .env
# 编辑 .env，填入你的 FEISHU_WEBHOOK 地址
```

### 3. 确保脚本可执行

```bash
chmod +x send-ai-news.sh
```

## 使用方式

### 手动触发

在 Claude Code 中直接说：

> 帮我执行 ai-daily-news skill，推送今天的 AI 新闻到飞书

Claude 会自动加载 Skill 并执行完整流程。

### 定时触发（推荐）

使用 Claude Code 的 **Remote Schedule** 功能，设置工作日早 9 点触发：

```
执行 ai-daily-news skill
```

这样即使你的电脑关机，定时任务也会在云端执行并推送。

### 测试发送脚本

```bash
./send-ai-news.sh '{
  "chi": [
    {"title":"国内测试","summary":"测试摘要","url":"https://example.com"}
  ],
  "foreign": [
    {"title":"国际测试","summary":"测试摘要","url":"https://example.com"}
  ]
}'
```

## 文件结构

```
.
├── SKILL.md          # Skill 定义（frontmatter + 搜索/筛选策略）
├── send-ai-news.sh   # 发送脚本，接收 JSON 生成飞书卡片
├── .env.example      # 环境变量模板
├── .env              # 实际配置（不会提交）
├── .gitignore
├── LICENSE
└── README.md
```

## 数据格式

`send-ai-news.sh` 接收 JSON 对象作为参数，包含国内 `chi` 和国际 `foreign` 两个数组，各 3 条新闻：

```json
{
  "chi": [
    {"title": "标题", "summary": "50-80 字摘要", "url": "https://..."}
  ],
  "foreign": [
    {"title": "Title", "summary": "50-80 字摘要", "url": "https://..."}
  ]
}
```

## 飞书卡片效果

- 标题自动显示当天日期（如 "4月8日AI速报"）
- **左右双栏布局**：左栏国内热点（红色），右栏国际热点（蓝色）
- 每条新闻以卡片展示，含标题与摘要
- 点击卡片可跳转到新闻原文

## 环境要求

- macOS / Linux
- Python 3.6+
- curl
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)

## License

MIT
