"""LLM prompts for various tasks."""

from typing import Dict


SUMMARY_PROMPT = """你是一位量化金融领域的专业分析师。请阅读以下帖子并生成结构化摘要。

标题：{title}

正文：
{content}

请用 **{language}** 回复，输出格式为 Markdown，包含：
1. **核心观点**（2-3 句话概括主旨）
2. **关键要点**（用列表列出 3-5 个关键结论或发现）
3. **适用场景**（这篇内容对谁最有价值，一句话）

摘要："""


TAG_SUGGESTION_PROMPT = """You are a content categorization expert. Analyze the following content and suggest relevant tags.

Content:
{content}

Existing tags selected: {existing_tags}

Available system tags: 量化策略, 因子分析, 回测, 数据分析, Python, 机器学习, 重要, 待读

Please suggest up to {max_suggestions} relevant tags. Return only the tag names as a comma-separated list.

Suggested tags:"""


POLISH_PROMPT = """You are a writing assistant. Polish the following text to make it more {style}.

Original text:
{text}

Requirements:
{length_instruction}
- Maintain the original meaning
- Improve clarity and flow
- Fix any grammar or style issues

Polished text:"""


FORMAT_MARKDOWN_PROMPT = """Format the following text as proper Markdown. Fix any formatting issues while preserving the content.

Text:
{text}

Formatted Markdown:"""


FORMAT_JSON_PROMPT = """Format and validate the following as proper JSON. Fix any syntax errors if possible.

Content:
{text}

Formatted JSON:"""


FORMAT_SQL_PROMPT = """Format the following SQL query with proper indentation and style.

SQL:
{code}

Formatted SQL:"""


FORMAT_PYTHON_PROMPT = """Format the following Python code according to PEP 8 standards.

Code:
{code}

Formatted Python code:"""


CHECK_CODE_PROMPT = """You are a code review expert. Analyze the following code and identify any issues.

```{language}
{code}
```

Please identify:
1. Syntax errors
2. Potential bugs or logic issues
3. Performance concerns
4. Style violations
5. Security issues

Return your findings in this format:
- Line X: [severity] Description (suggestion)

If no issues found, say "No issues found."

Analysis:"""


SYSTEM_PROMPTS: Dict[str, str] = {
    "summary": "You are an expert at summarizing technical conversations. Provide clear, concise summaries.",
    "tag_suggestion": "You are a content categorization expert. Suggest relevant, specific tags.",
    "polish": "You are a professional writing assistant. Improve text while maintaining original meaning.",
    "format": "You are a code and text formatting expert. Apply consistent formatting.",
    "code_check": "You are a senior software engineer. Review code thoroughly and provide actionable feedback.",
    "chat": "You are a helpful assistant for quantitative finance and programming topics.",
}


def get_prompt(template: str, **kwargs) -> str:
    """Get formatted prompt with variables substituted."""
    return template.format(**kwargs)


# ── Memory System Prompts ──

STRATEGY_EXTRACT_PROMPT = """你是量化策略分析专家。请从以下帖子中提取策略信息。

标题：{title}

正文：
{content}

请提取并输出**严格 JSON 格式**（不要输出任何其他文本），包含以下字段：

```json
{{
  "name": "策略名称",
  "strategy_type": "trend_following|mean_reversion|momentum|statistical_arbitrage|ml_based|factor|other",
  "asset_class": "a_shares|futures|options|crypto|multi_asset",
  "factors": ["因子1", "因子2"],
  "signals": ["入场信号描述", "出场信号描述"],
  "params": {{
    "lookback_period": "回看周期",
    "rebalance_freq": "调仓频率",
    "position_sizing": "仓位管理方式",
    "stop_loss": "止损条件",
    "take_profit": "止盈条件"
  }},
  "backtest": {{
    "period": "回测区间",
    "annual_return": "年化收益",
    "sharpe_ratio": null,
    "max_drawdown": "最大回撤",
    "win_rate": null
  }},
  "framework": "backtrader|vnpy|quantclass|custom|unknown",
  "key_logic": "用1-2句话描述核心策略逻辑",
  "confidence": 0.7
}}
```

如果帖子不包含明确的策略信息，返回：
```json
{{"name": null, "confidence": 0.0}}
```"""


MEMORY_EXTRACT_PROMPT = """分析以下对话，提取值得长期记住的用户信息。

对话内容：
{conversation}

请提取并输出**严格 JSON 数组**，每个元素是一条记忆：

```json
[
  {{
    "memory_type": "user_fact|strategy_insight|preference|skill_observation",
    "content": "一句话描述这条记忆",
    "importance": 3
  }}
]
```

提取规则：
- user_fact: 用户的背景信息（职业、经验年限、资金规模等）
- strategy_insight: 用户对策略的理解或发现
- preference: 用户的偏好（框架选择、语言偏好、风格）
- skill_observation: 观察到的用户技能水平
- importance 1-5: 1=琐碎 3=有用 5=关键

如果没有值得记住的信息，返回空数组 `[]`。
最多提取 3 条记忆。"""


PROFILE_INFER_PROMPT = """根据以下用户的交互历史，推断其画像信息。

最近阅读的帖子标题：
{recent_reads}

最近的对话主题：
{recent_topics}

收藏的帖子标签分布：
{tag_distribution}

现有画像：
{existing_profile}

请输出更新后的用户画像（严格 JSON，不要其他文本）：

```json
{{
  "skill_level": "beginner|intermediate|advanced|expert",
  "primary_interests": ["兴趣1", "兴趣2", "兴趣3"],
  "preferred_frameworks": ["框架1"],
  "asset_focus": ["A股", "期货"],
  "learning_goals": ["目标1"],
  "active_research": "当前正在研究的主题"
}}
```"""


SESSION_SUMMARY_PROMPT = """用一到两句中文概括以下对话的主题和结论：

{conversation}

摘要："""


COMPARE_PROMPT = """你是量化投资领域的专业分析师。请对比以下 {count} 篇量化研究帖子：

{items_text}

{focus_instruction}

请输出：
1. 一个 Markdown 对比表格，列出各帖的策略类型、核心指标、优点、局限性
2. 100字以内的自然语言总结
3. 建议优先阅读哪篇（并说明原因，30字以内）

格式要求：
- 先输出 <TABLE> 标签，包裹 Markdown 表格
- 再输出 <SUMMARY> 标签，包裹总结文字
- 最后输出 <RECOMMENDATION> 标签，包裹阅读建议
"""
