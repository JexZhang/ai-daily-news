#!/bin/bash
#
# 发送 AI 新闻到飞书（双栏卡片：国内热点 + 国际热点）
# 用法: ./send-ai-news.sh '<JSON对象>'
# JSON格式: {"chi":[{"title":"","summary":"","url":""},...],"foreign":[...]}
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
[ -f "${PROJECT_DIR}/.env" ] && set -a && source "${PROJECT_DIR}/.env" && set +a

FEISHU_WEBHOOK="${FEISHU_WEBHOOK:?请设置环境变量 FEISHU_WEBHOOK，参考 .env.example}"

NEWS_JSON="${1:?用法: $0 '{\"chi\":[...],\"foreign\":[...]}'}"

# ---------- 前置校验（schema / 日期 / 链接可达性）----------
# 校验失败立即中止，错误详情已由 validate-news.py 输出到 stderr，
# 供上游模型读取后修正 JSON 重试。
if ! python3 "${SCRIPT_DIR}/validate-news.py" "${NEWS_JSON}"; then
    echo "" >&2
    echo "发送已中止：前置校验未通过。请根据上方 [validate] 报告修正 JSON 后重试。" >&2
    exit 2
fi

# 构造飞书卡片消息
export NEWS_JSON
PAYLOAD=$(python3 << 'PYEOF'
import os, json, datetime
from zoneinfo import ZoneInfo

data = json.loads(os.environ["NEWS_JSON"])
chi_list = data.get("chi", [])
foreign_list = data.get("foreign", [])
# 标题使用北京时间今天的日期，保证海外时区运行时也符合预期
today = datetime.datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%-m月%-d日")


def build_news_item(item, color):
    """构造单条新闻的 interactive_container"""
    return {
        "tag": "interactive_container",
        "width": "fill",
        "height": "auto",
        "corner_radius": "12px",
        "elements": [
            {
                "tag": "column_set",
                "flex_mode": "stretch",
                "horizontal_spacing": "8px",
                "horizontal_align": "left",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "elements": [
                            {
                                "tag": "markdown",
                                "content": f"**<font color='{color}'>{item['title']}</font>**",
                                "text_align": "left",
                                "text_size": "normal",
                                "margin": "0px 0px 0px 0px"
                            },
                            {
                                "tag": "markdown",
                                "content": f"<font color='grey-600'>{item['summary']}</font>",
                                "text_align": "left",
                                "text_size": "normal",
                                "margin": "0px 0px 0px 0px"
                            }
                        ],
                        "padding": "0px 0px 0px 0px",
                        "horizontal_spacing": "8px",
                        "vertical_spacing": "4px",
                        "horizontal_align": "left",
                        "vertical_align": "top",
                        "margin": "0px 0px 0px 0px",
                        "weight": 3
                    }
                ],
                "margin": "0px 0px 0px 0px"
            }
        ],
        "has_border": True,
        "border_color": "blue-100",
        "background_style": "blue-50",
        "behaviors": [
            {
                "type": "open_url",
                "default_url": item["url"],
                "pc_url": "",
                "ios_url": "",
                "android_url": ""
            }
        ],
        "padding": "12px 12px 12px 12px",
        "direction": "vertical",
        "horizontal_spacing": "8px",
        "vertical_spacing": "8px",
        "horizontal_align": "left",
        "vertical_align": "top",
        "margin": "8px 12px 8px 12px"
    }


chi_items = [build_news_item(n, "red") for n in chi_list]
foreign_items = [build_news_item(n, "blue") for n in foreign_list]

# 国内热点栏目标题
chi_header = {
    "tag": "markdown",
    "content": "🇨🇳 **<font color='red'>国内热点</font>**",
    "text_align": "left",
    "text_size": "normal",
    "margin": "0px 0px 0px 0px"
}

# 国际热点栏目标题
foreign_header = {
    "tag": "markdown",
    "content": "🌎 **<font color='blue'>国际热点</font>**",
    "text_align": "left",
    "text_size": "normal",
    "margin": "0px 0px 0px 0px"
}

card = {
    "schema": "2.0",
    "config": {
        "update_multi": True
    },
    "body": {
        "direction": "vertical",
        "horizontal_spacing": "8px",
        "vertical_spacing": "0px",
        "horizontal_align": "left",
        "vertical_align": "top",
        "padding": "12px 12px 12px 12px",
        "elements": [
            {
                "tag": "column_set",
                "flex_mode": "stretch",
                "horizontal_spacing": "8px",
                "horizontal_align": "left",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "elements": [
                            {
                                "tag": "img",
                                "img_key": "img_v3_0210d_ccf72549-9b59-46d4-a650-f7f9113dfedg",
                                "preview": True,
                                "transparent": True,
                                "scale_type": "crop_center",
                                "size": "570px 100px",
                                "corner_radius": "12px",
                                "margin": "36px 0px 0px 0px"
                            },
                            {
                                "tag": "column_set",
                                "horizontal_spacing": "8px",
                                "horizontal_align": "left",
                                "columns": [
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "elements": [chi_header] + chi_items,
                                        "padding": "0px 0px 0px 0px",
                                        "horizontal_spacing": "8px",
                                        "vertical_spacing": "0px",
                                        "horizontal_align": "left",
                                        "vertical_align": "top",
                                        "margin": "0px 0px 0px 0px",
                                        "weight": 1
                                    },
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "elements": [foreign_header] + foreign_items,
                                        "direction": "vertical",
                                        "horizontal_spacing": "8px",
                                        "vertical_spacing": "0px",
                                        "horizontal_align": "left",
                                        "vertical_align": "top",
                                        "weight": 1
                                    }
                                ],
                                "margin": "0px 8px 8px 8px"
                            }
                        ],
                        "padding": "0px 0px 0px 0px",
                        "direction": "vertical",
                        "horizontal_spacing": "8px",
                        "vertical_spacing": "8px",
                        "horizontal_align": "left",
                        "vertical_align": "top",
                        "margin": "-40px 0px 0px 0px",
                        "weight": 1
                    }
                ],
                "margin": "0px 0px 0px 0px"
            }
        ]
    },
    "header": {
        "title": {
            "tag": "plain_text",
            "content": f"{today}AI速报"
        },
        "subtitle": {
            "tag": "plain_text",
            "content": ""
        },
        "text_tag_list": [
            {
                "tag": "text_tag",
                "text": {
                    "tag": "plain_text",
                    "content": "每日更新"
                },
                "color": "blue"
            }
        ],
        "template": "blue",
        "icon": {
            "tag": "standard_icon",
            "token": "ai-common_colorful"
        },
        "padding": "12px 16px 12px 16px"
    }
}

payload = {
    "msg_type": "interactive",
    "card": card
}

print(json.dumps(payload, ensure_ascii=False))
PYEOF
)

# 发送到飞书
HTTP_CODE=$(curl -s -o /tmp/feishu_response.json -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" \
    "${FEISHU_WEBHOOK}")

if [ "${HTTP_CODE}" != "200" ]; then
    echo "ERROR: HTTP ${HTTP_CODE}"
    exit 1
fi

STATUS_CODE=$(python3 -c "
import json
data = json.load(open('/tmp/feishu_response.json'))
print(data.get('code', -1))
" 2>/dev/null || echo "-1")

if [ "${STATUS_CODE}" = "0" ]; then
    echo "发送成功"
else
    echo "ERROR: $(cat /tmp/feishu_response.json)"
    exit 1
fi
