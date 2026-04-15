"""Agent service — manage agent personas and run multi-agent discussions."""

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

import yaml

from config import get_data_dir
from llm.adapter import llm_adapter
from llm.base import LLMMessage

logger = logging.getLogger(__name__)

AGENTS_DIR = "agents"

# Default agents created on first startup
DEFAULT_AGENTS = [
    {
        "id": "student",
        "name": "学员小白",
        "icon": "🐣",
        "description": "提出初学者视角的好问题",
        "enabled": True,
        "order": 1,
        "prompt": """你是一个初学者。你的任务是：
- 对文章中不明白的术语提出疑问
- 从新手角度提出"为什么"类的问题
- 用简单的语言复述你对内容的理解
- 如果某些假设看起来不合理，大胆质疑

回复风格：好奇、谦虚、简短（3-5句话）。用中文回复。""",
    },
    {
        "id": "teacher",
        "name": "老师",
        "icon": "👨‍🏫",
        "description": "用类比和例子把概念讲透",
        "enabled": True,
        "order": 2,
        "prompt": """你是一位资深教师。你的任务是：
- 用通俗的类比和生活化的例子解释文章中的概念
- 把复杂的逻辑拆解成易懂的步骤
- 纠正常见的误解
- 给出进一步学习的方向

回复风格：耐心、清晰、循序渐进（5-8句话）。用中文回复。""",
    },
    {
        "id": "expert",
        "name": "领域专家",
        "icon": "🧠",
        "description": "结合行业背景深度解读",
        "enabled": True,
        "order": 3,
        "prompt": """你是该领域深耕多年的资深专家。你的任务是：
- 补充行业背景知识和最新进展
- 指出文章的独到之处和创新点
- 客观评价方法的局限性
- 与业界其他方案做对比

回复风格：专业、深入、有洞察力（5-10句话）。用中文回复。""",
    },
    {
        "id": "engineer",
        "name": "工程师",
        "icon": "🔧",
        "description": "从实战落地角度提出追问",
        "enabled": True,
        "order": 4,
        "prompt": """你是一位实战经验丰富的工程师。你的任务是：
- 关注方案的可实现性和工程细节
- 提出性能、可靠性、可维护性方面的考量
- 分享相关的踩坑经验和最佳实践
- 给出具体的技术建议

回复风格：务实、直接、注重细节（5-8句话）。用中文回复。""",
    },
    {
        "id": "reviewer",
        "name": "审查者",
        "icon": "🧐",
        "description": "评价讨论质量、纠偏补漏",
        "enabled": True,
        "order": 5,
        "prompt": """你是一位严谨的审查者。你的任务是：
- 汇总前面所有角色的观点
- 指出讨论中的遗漏、矛盾或偏见
- 评价各观点的论证质量
- 提出需要进一步探讨的问题

回复风格：客观、全面、有批判性（5-8句话）。用中文回复。""",
    },
]


def _agents_path() -> Path:
    return get_data_dir() / AGENTS_DIR


def ensure_agents_dir() -> Path:
    p = _agents_path()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parse_agent_md(filepath: Path) -> Optional[Dict[str, Any]]:
    """Parse an agent .md file (YAML frontmatter + prompt body)."""
    try:
        text = filepath.read_text(encoding="utf-8")
        # Split YAML frontmatter from body
        match = re.match(r'^---\n(.*?)\n---\n(.*)', text, re.DOTALL)
        if not match:
            return None
        meta = yaml.safe_load(match.group(1))
        prompt = match.group(2).strip()
        return {**meta, "prompt": prompt}
    except Exception as e:
        logger.warning(f"Failed to parse agent {filepath}: {e}")
        return None


def _write_agent_md(agent_id: str, data: Dict[str, Any]) -> None:
    """Write an agent .md file."""
    path = _agents_path() / f"{agent_id}.md"
    meta = {
        "id": agent_id,
        "name": data.get("name", agent_id),
        "icon": data.get("icon", "🤖"),
        "description": data.get("description", ""),
        "enabled": data.get("enabled", True),
        "order": data.get("order", 99),
    }
    prompt = data.get("prompt", "")
    content = f"---\n{yaml.dump(meta, allow_unicode=True, default_flow_style=False)}---\n{prompt}\n"
    path.write_text(content, encoding="utf-8")


def ensure_default_agents() -> None:
    """Create default agent .md files if they don't exist."""
    ensure_agents_dir()
    for agent in DEFAULT_AGENTS:
        path = _agents_path() / f"{agent['id']}.md"
        if not path.exists():
            _write_agent_md(agent["id"], agent)
            logger.info(f"Created default agent: {agent['name']}")


def list_agents() -> List[Dict[str, Any]]:
    """List all agents from the agents/ directory."""
    agents = []
    for f in sorted(_agents_path().glob("*.md")):
        agent = _parse_agent_md(f)
        if agent:
            agents.append(agent)
    agents.sort(key=lambda a: a.get("order", 99))
    return agents


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    path = _agents_path() / f"{agent_id}.md"
    if not path.exists():
        return None
    return _parse_agent_md(path)


def create_agent(agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    _write_agent_md(agent_id, data)
    return get_agent(agent_id)


def update_agent(agent_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_agent(agent_id)
    if not existing:
        return None
    merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
    _write_agent_md(agent_id, merged)
    return get_agent(agent_id)


def delete_agent(agent_id: str) -> bool:
    path = _agents_path() / f"{agent_id}.md"
    if path.exists():
        path.unlink()
        return True
    return False


def _build_agent_messages(agent: Dict, ctx_block: str, question: str, language: str):
    """Assemble the LLMMessage list for one agent turn.

    Split out so the non-streaming ``discuss`` and the streaming
    ``discuss_stream`` paths can share the prompt contract.
    """
    system = agent["prompt"]
    return [
        LLMMessage(role="user", content=f"你的角色设定：{system}"),
        LLMMessage(
            role="assistant",
            content=f"好的，我是{agent['name']}，{agent['description']}。请提供文章内容和问题。",
        ),
        LLMMessage(role="user", content=(
            f"以下是一篇文章的内容：\n\n---\n{ctx_block}\n---\n\n"
            f"用户的问题：{question}\n\n"
            f"请以你的角色（{agent['name']}）发表你的观点。用{language}回复，使用 Markdown 格式。"
        )),
    ]


async def discuss(
    question: str,
    context: str,
    agent_ids: List[str],
    language: str = "中文",
) -> List[Dict[str, Any]]:
    """Run a multi-agent discussion. Each agent responds in parallel."""
    agents = [get_agent(aid) for aid in agent_ids]
    agents = [a for a in agents if a]

    if not agents:
        return []

    llm = llm_adapter.get_llm()
    ctx_block = context[:30000] if context else ""

    async def _call_agent(agent: Dict) -> Dict[str, Any]:
        full_messages = _build_agent_messages(agent, ctx_block, question, language)
        try:
            resp = await llm.chat(full_messages, temperature=0.6)
            return {
                "agent_id": agent["id"],
                "name": agent["name"],
                "icon": agent.get("icon", "🤖"),
                "content": resp.content,
            }
        except Exception as e:
            return {
                "agent_id": agent["id"],
                "name": agent["name"],
                "icon": agent.get("icon", "🤖"),
                "content": f"⚠️ {agent['name']} 发言失败：{str(e)}",
            }

    results = await asyncio.gather(*[_call_agent(a) for a in agents])
    return list(results)


async def discuss_stream(
    question: str,
    context: str,
    agent_ids: List[str],
    language: str = "中文",
):
    """Stream a multi-agent discussion as an async iterator of events.

    Yields dict events interleaved from all agents running in parallel:
        {"type": "start",  "agent_id": ..., "name": ..., "icon": ...}
        {"type": "chunk",  "agent_id": ..., "content": "..."}
        {"type": "end",    "agent_id": ...}
        {"type": "error",  "agent_id": ..., "message": "..."}
        {"type": "done"}

    Implementation note: N worker coroutines call ``llm.chat_stream`` in
    parallel and push events onto a shared ``asyncio.Queue``. The main
    generator drains the queue and yields events in the order they land,
    giving the client interleaved output across agents. When a worker
    finishes (success or error) it pushes an ``end`` sentinel; the main
    generator terminates once it has seen ``end`` for every worker.
    """
    agents = [get_agent(aid) for aid in agent_ids]
    agents = [a for a in agents if a]

    if not agents:
        yield {"type": "done"}
        return

    llm = llm_adapter.get_llm()
    ctx_block = context[:30000] if context else ""

    queue: asyncio.Queue = asyncio.Queue()

    async def worker(agent: Dict):
        agent_id = agent["id"]
        await queue.put({
            "type": "start",
            "agent_id": agent_id,
            "name": agent["name"],
            "icon": agent.get("icon", "🤖"),
        })
        try:
            full_messages = _build_agent_messages(agent, ctx_block, question, language)
            async for chunk in llm.chat_stream(full_messages, temperature=0.6):
                if chunk:
                    await queue.put({
                        "type": "chunk",
                        "agent_id": agent_id,
                        "content": chunk,
                    })
        except Exception as e:
            await queue.put({
                "type": "error",
                "agent_id": agent_id,
                "message": str(e),
            })
        finally:
            await queue.put({"type": "end", "agent_id": agent_id})

    tasks = [asyncio.create_task(worker(a)) for a in agents]
    ended = 0
    total = len(tasks)
    try:
        while ended < total:
            event = await queue.get()
            yield event
            if event["type"] == "end":
                ended += 1
    finally:
        # Drain any exceptions from worker tasks so the event loop stays
        # clean even if the client disconnected mid-stream.
        await asyncio.gather(*tasks, return_exceptions=True)

    yield {"type": "done"}
