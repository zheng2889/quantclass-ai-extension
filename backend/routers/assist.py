"""Assist router - AI assistance features."""

import re
from typing import Literal, List
from fastapi import APIRouter
from models import (
    success, llm_error, param_error,
    PolishRequest, FormatRequest, CheckCodeRequest,
    AssistResponse, CheckCodeResponse, CheckCodeIssue,
    CompareRequest,
)
from llm.adapter import llm_adapter
from llm.prompts import get_prompt, POLISH_PROMPT, CHECK_CODE_PROMPT, COMPARE_PROMPT
from llm.base import LLMMessage

router = APIRouter(tags=["Assist"])


@router.post("/polish")
async def polish_text(request: PolishRequest):
    """Polish/rewrite text in different styles."""
    try:
        llm = llm_adapter.get_llm()
        
        length_instruction = "- Keep similar length to original" if request.keep_length else "- Optimize for clarity"
        
        prompt = get_prompt(
            POLISH_PROMPT,
            text=request.text,
            style=request.style,
            length_instruction=length_instruction
        )
        
        messages = [LLMMessage(role="user", content=prompt)]
        response = await llm.chat(messages, temperature=0.5)
        
        return success({
            "result": response.content,
            "original_length": len(request.text),
            "result_length": len(response.content),
            "style": request.style
        })
    except Exception as e:
        return llm_error(str(e))


@router.post("/format")
async def format_text(request: FormatRequest):
    """Format text in various formats."""
    try:
        llm = llm_adapter.get_llm()
        
        format_prompts = {
            "markdown": "Format the following as proper Markdown. Fix formatting issues:\n\n{text}",
            "json": "Format and validate as proper JSON. Fix syntax errors:\n\n{text}",
            "sql": "Format the following SQL with proper indentation:\n\n{text}",
            "python": "Format the following Python code (PEP 8 style):\n\n{text}"
        }
        
        prompt_template = format_prompts.get(
            request.format_type, 
            format_prompts["markdown"]
        )
        
        prompt = prompt_template.format(text=request.text)
        messages = [LLMMessage(role="user", content=prompt)]
        
        response = await llm.chat(messages, temperature=0.1)
        
        return success({
            "result": response.content,
            "original_length": len(request.text),
            "result_length": len(response.content),
            "format": request.format_type
        })
    except Exception as e:
        return llm_error(str(e))


@router.post("/check-code")
async def check_code(request: CheckCodeRequest):
    """Check code for issues and suggest fixes."""
    try:
        llm = llm_adapter.get_llm()
        
        language = request.language or "auto-detect"
        
        prompt = get_prompt(
            CHECK_CODE_PROMPT,
            code=request.code,
            language=language
        )
        
        messages = [LLMMessage(role="user", content=prompt)]
        response = await llm.chat(messages, temperature=0.2)
        
        # Parse issues from response
        content = response.content
        issues = []

        # Simple parsing - look for line references
        line_pattern = r'(?:Line|行)\s*(\d+)[:\s]*(?:\[(\w+)\]|(\w+))\s*[:-]?\s*(.+?)(?=\n|$)'
        matches = re.findall(line_pattern, content, re.IGNORECASE)
        
        for match in matches:
            line_num = int(match[0])
            severity = match[1] or match[2] or "warning"
            message = match[3].strip()
            
            # Map severity
            severity_map = {
                "error": "error",
                "err": "error",
                "警告": "warning",
                "warning": "warning",
                "warn": "warning",
                "info": "info",
                "建议": "info"
            }
            
            issues.append({
                "line": line_num,
                "column": None,
                "severity": severity_map.get(severity.lower(), "warning"),
                "message": message,
                "suggestion": None
            })
        
        # If no structured issues found, use the whole response as summary
        summary = "Code review completed." if issues else content[:200]
        
        return success({
            "issues": issues,
            "summary": summary,
            "fixed_code": None  # Could be extracted if LLM provides it
        })
    except Exception as e:
        return llm_error(str(e))


@router.post("/compare")
async def compare_bookmarks(request: CompareRequest):
    """Compare multiple bookmarks and generate a comparison table."""
    try:
        llm = llm_adapter.get_llm()

        # Build items text
        items_text = "\n\n".join(
            f"【帖子{i+1}】{item.title}\n{item.summary}"
            for i, item in enumerate(request.items)
        )

        focus_instruction = f"请重点关注：{request.focus}" if request.focus else "请全面对比。"

        prompt = COMPARE_PROMPT.format(
            count=len(request.items),
            items_text=items_text,
            focus_instruction=focus_instruction
        )

        messages = [LLMMessage(role="user", content=prompt)]
        response = await llm.chat(messages, temperature=0.4)

        content = response.content

        # Parse structured output
        table_match = re.search(r"<TABLE>(.*?)</TABLE>", content, re.DOTALL)
        summary_match = re.search(r"<SUMMARY>(.*?)</SUMMARY>", content, re.DOTALL)
        rec_match = re.search(r"<RECOMMENDATION>(.*?)</RECOMMENDATION>", content, re.DOTALL)

        table = table_match.group(1).strip() if table_match else content
        summary = summary_match.group(1).strip() if summary_match else content[:200]
        recommendation = rec_match.group(1).strip() if rec_match else None

        return success({
            "table": table,
            "summary": summary,
            "recommendation": recommendation
        })
    except Exception as e:
        return llm_error(str(e))
