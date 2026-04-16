"""BBS (quantclass) router."""

import html
from functools import lru_cache
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from models import success, not_found, param_error
from services.bbs_service import BBSService
from routers.auth import require_admin
import subprocess
from pathlib import Path

router = APIRouter(tags=["BBS"])
page_router = APIRouter(tags=["BBS Pages"])

BBS_DETAIL_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>帖子详情 - %(post_id)s</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }}
    .header {{ background: #001529; color: white; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }}
    .header h1 {{ font-size: 18px; }}
    .header a {{ color: #40a9ff; text-decoration: none; }}
    .card {{ background: white; padding: 20px; border-radius: 8px; max-width: 800px; margin: 16px auto; }}
    .meta {{ display: grid; grid-template-columns: auto 1fr; gap: 8px 16px; margin-bottom: 16px; }}
    .meta dt {{ color: #666; font-size: 14px; }}
    .meta dd {{ font-size: 14px; }}
    .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px; }}
    .tag.digest {{ background: #f6ffed; color: #52c41a; }}
    .tag.ai {{ background: #e6f7ff; color: #1890ff; }}
    .tag.status {{ background: #fffbe6; color: #d4b106; }}
    .tag.success {{ background: #f6ffed; color: #52c41a; }}
    .tag.failed {{ background: #fff1f0; color: #ff4d4f; }}
    .actions {{ margin: 16px 0; display: flex; gap: 12px; }}
    .btn {{ padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }}
    .btn-primary {{ background: #1890ff; color: white; }}
    .btn-primary:hover {{ background: #40a9ff; }}
    .ai-result {{ background: #fafafa; padding: 16px; border-radius: 4px; border: 1px solid #e8e8e8; }}
    .ai-result h3 {{ font-size: 16px; margin-bottom: 12px; }}
    .ai-result .md-content {{ font-size: 14px; line-height: 1.6; }}
    .ai-result .md-content h4 {{ font-size: 15px; margin: 12px 0 8px; }}
    .ai-result .md-content p {{ margin: 8px 0; }}
    .ai-result .md-content ul {{ padding-left: 20px; }}
    .empty {{ text-align: center; color: #999; padding: 32px; }}
    .error {{ color: #ff4d4f; }}
    .loading {{ text-align: center; padding: 32px; color: #999; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>BBS 帖子详情</h1>
    <a href="/bbs">返回列表</a>
  </div>
  <div id="loading" class="loading">加载中...</div>
  <div id="content" style="display:none;">
    <div class="card">
      <div class="meta">
        <dt>标题</dt><dd id="title"></dd>
        <dt>作者</dt><dd id="author"></dd>
        <dt>发布时间</dt><dd id="publish_time"></dd>
        <dt>链接</dt><dd id="url"></dd>
        <dt>状态</dt><dd id="status_tags"></dd>
      </div>
      <div class="actions" id="actions"></div>
    </div>
    <div class="card" id="ai_section" style="display:none;">
      <div class="ai-result">
        <h3>AI 分析结果</h3>
        <div class="md-content" id="ai_content"></div>
      </div>
    </div>
  </div>
  <div id="error_msg" class="card empty" style="display:none;">
    <p class="error">帖子不存在或加载失败</p>
  </div>
  <script>
    const POST_ID = '%(post_id)s';

    async function loadDetail() {
      try {
        const resp = await fetch('/api/bbs/detail/' + POST_ID);
        const data = await resp.json();
        if (!data.success || !data.data) {
          document.getElementById('loading').style.display = 'none';
          document.getElementById('error_msg').style.display = 'block';
          return;
        }
        const post = data.data;
        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';

        document.getElementById('title').textContent = post.title || '未知标题';
        document.getElementById('author').textContent = post.author_name || '未知作者';
        document.getElementById('publish_time').textContent = post.publish_time || '-';

        const urlLink = document.getElementById('url');
        if (post.url) {
          urlLink.innerHTML = '<a href="' + esc(post.url) + '" target="_blank">' + esc(post.url) + '</a>';
        } else {
          urlLink.textContent = '-';
        }

        let tags = '';
        if (post.is_digest) tags += '<span class="tag digest">精华</span>';
        if (post.has_ai_result) tags += '<span class="tag ai">有AI分析</span>';
        const s = post.status || 'pending';
        tags += '<span class="tag status ' + esc(s) + '">' + esc(s) + '</span>';
        document.getElementById('status_tags').innerHTML = tags;

        // Actions
        const actions = document.getElementById('actions');
        if (post.status === 'success' && !post.has_ai_result) {
          actions.innerHTML = '<button class="btn btn-primary" onclick="triggerAnalysis()">触发AI分析</button>';
        } else if (post.has_ai_result) {
          actions.innerHTML = '<button class="btn btn-primary" onclick="triggerAnalysis()">重新分析</button>';
        }

        // AI result
        if (post.ai_result_content) {
          document.getElementById('ai_section').style.display = 'block';
          document.getElementById('ai_content').innerHTML = simpleMd(esc(post.ai_result_content));
        }
        if (post.md_content) {
          const mdSection = document.createElement('div');
          mdSection.className = 'card';
          mdSection.innerHTML = '<div class="ai-result"><h3>原始内容</h3><div class="md-content"></div></div>';
          mdSection.querySelector('.md-content').innerHTML = simpleMd(esc(post.md_content));
          document.getElementById('content').appendChild(mdSection);
        }
      } catch (e) {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('error_msg').style.display = 'block';
        console.error(e);
      }
    }

    async function triggerAnalysis() {
      // Write endpoints require admin auth (JWT Bearer token)
      const token = localStorage.getItem('quantclass_token');
      if (!token) {
        alert('需要登录后才能触发AI分析。请先通过API获取登录token。');
        return;
      }
      try {
        const resp = await fetch('/api/bbs/analyze', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + token
          },
          body: JSON.stringify({ post_id: POST_ID })
        });
        if (resp.status === 401 || resp.status === 403) {
          alert('认证失败，请重新登录获取token。');
          return;
        }
        const data = await resp.json();
        if (data.success) {
          alert('AI分析已完成，正在刷新页面...');
          loadDetail();
        } else {
          alert('分析失败: ' + (data.message || '未知错误'));
        }
      } catch (e) {
        alert('请求失败: ' + e.message);
      }
    }

    function esc(str) {
      if (!str) return '';
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }

    function simpleMd(text) {
      let html = text
        .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        .replace(/^# (.+)$/gm, '<h2>$1</h2>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^\- (.+)$/gm, '<li>$1</li>')
        .replace(/^\* (.+)$/gm, '<li>$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');
      return '<p>' + html + '</p>';
    }

    loadDetail();
  </script>
</body>
</html>"""

# 获取Git版本信息
@lru_cache(maxsize=1)
def _get_git_info():
    """获取Git版本信息（缓存结果）"""
    try:
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=backend_dir,
            capture_output=True,
            text=True
        )
        commit = result.stdout.strip() if result.returncode == 0 else 'unknown'

        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=backend_dir,
            capture_output=True,
            text=True
        )
        branch = result.stdout.strip() if result.returncode == 0 else 'main'

        result = subprocess.run(
            ['git', 'log', '-1', '--format=%ci'],
            cwd=backend_dir,
            capture_output=True,
            text=True
        )
        date = result.stdout.strip() if result.returncode == 0 else ''

        return {
            'commit': commit,
            'branch': branch,
            'date': date[:19] if date else ''
        }
    except Exception:
        return {'commit': 'unknown', 'branch': 'unknown', 'date': ''}


def get_version_info():
    """获取版本信息"""
    git_info = _get_git_info()
    return {
        'version': '0.2.4',
        'branch': git_info.get('branch', 'main'),
        'date': git_info.get('date', '').split()[0] if git_info.get('date') else ''
    }


BBS_LIST_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BBS 帖子管理</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }
    .header { background: #001529; color: white; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
    .header h1 { font-size: 18px; }
    .version { font-size: 12px; opacity: 0.7; }
    .toolbar { background: white; padding: 16px 24px; border-bottom: 1px solid #e8e8e8; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
    .toolbar input, .toolbar select { padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 4px; font-size: 14px; }
    .toolbar button { padding: 8px 16px; background: #1890ff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
    .toolbar button:hover { background: #40a9ff; }
    .table-container { background: white; margin: 16px 24px; border-radius: 4px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #e8e8e8; font-size: 14px; }
    th { background: #fafafa; font-weight: 500; color: #333; }
    td a { color: #1890ff; text-decoration: none; }
    td a:hover { text-decoration: underline; }
    .status { padding: 4px 8px; border-radius: 4px; font-size: 12px; }
    .status.pending { background: #fffbe6; color: #d4b106; }
    .status.success { background: #f6ffed; color: #52c41a; }
    .status.failed { background: #fff1f0; color: #ff4d4f; }
    .status.no_permission { background: #f0f5ff; color: #1890ff; }
    .pagination { padding: 16px; display: flex; justify-content: center; gap: 8px; align-items: center; }
    .pagination button { padding: 6px 12px; border: 1px solid #d9d9d9; background: white; cursor: pointer; }
    .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
    .pagination span { font-size: 14px; }
    .empty { padding: 48px; text-align: center; color: #999; }
  </style>
</head>
<body>
  <div class="header">
    <h1>BBS 精华帖管理</h1>
    <span class="version">v%(version)s | %(branch)s | %(date)s</span>
  </div>
  <div class="toolbar">
    <input type="text" id="keyword" placeholder="搜索标题..." />
    <select id="is_digest">
      <option value="">是否精华</option>
      <option value="1">是</option>
      <option value="0">否</option>
    </select>
    <select id="has_ai_result">
      <option value="">AI分析</option>
      <option value="1">有</option>
      <option value="0">无</option>
    </select>
    <select id="status">
      <option value="">状态</option>
      <option value="pending">待处理</option>
      <option value="success">成功</option>
      <option value="failed">失败</option>
      <option value="no_permission">无权限</option>
    </select>
    <button onclick="loadData(1)">搜索</button>
  </div>
  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th>帖子ID</th>
          <th>标题</th>
          <th>作者</th>
          <th>发布时间</th>
          <th>是否精华</th>
          <th>AI分析</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody id="table-body"></tbody>
    </table>
  </div>
  <div class="pagination">
    <button id="prev-btn" onclick="changePage(-1)">上一页</button>
    <span id="page-info"></span>
    <button id="next-btn" onclick="changePage(1)">下一页</button>
  </div>
  <script>
    let currentPage = 1;
    let total = 0;

    async function loadData(page = 1) {
      const keyword = document.getElementById('keyword').value;
      const is_digest = document.getElementById('is_digest').value;
      const has_ai_result = document.getElementById('has_ai_result').value;
      const status = document.getElementById('status').value;

      const params = new URLSearchParams({
        page, page_size: 20,
        ...(keyword && {keyword}),
        ...(is_digest && {is_digest}),
        ...(has_ai_result && {has_ai_result}),
        ...(status && {status})
      });

      try {
        const resp = await fetch('/api/bbs/list?' + params);
        const data = await resp.json();

        if (data.success) {
          renderTable(data.data.items);
          total = data.data.total;
          currentPage = data.data.page;
          updatePagination();
        }
      } catch (e) {
        console.error(e);
      }
    }

    function renderTable(items) {
      const tbody = document.getElementById('table-body');
      if (!items || items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">暂无数据</td></tr>';
        return;
      }

      tbody.innerHTML = items.map(item => `
        <tr>
          <td>${esc(item.post_id)}</td>
          <td><a href="/bbs/detail/${esc(item.post_id)}" target="_blank">${esc(item.title) || '-'}</a></td>
          <td>${esc(item.author_name) || '-'}</td>
          <td>${esc(item.publish_time) || '-'}</td>
          <td>${item.is_digest ? '✓' : '-'}</td>
          <td>${item.has_ai_result ? '✓' : '-'}</td>
          <td><span class="status ${esc(item.status) || 'pending'}">${esc(item.status) || 'pending'}</span></td>
        </tr>
      `).join('');
    }

    function esc(str) {
      if (!str) return '';
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }

    function updatePagination() {
      const totalPages = Math.ceil(total / 20) || 1;
      document.getElementById('page-info').textContent = `第 ${currentPage} / ${totalPages} 页 (共 ${total} 条)`;
      document.getElementById('prev-btn').disabled = currentPage <= 1;
      document.getElementById('next-btn').disabled = currentPage >= totalPages;
    }

    function changePage(delta) {
      loadData(currentPage + delta);
    }

    loadData();
  </script>
</body>
</html>"""


@page_router.get("/bbs")
async def bbs_list_page():
    """BBS列表页面"""
    version_info = get_version_info()
    safe_version = {
        'version': html.escape(str(version_info.get('version', ''))),
        'branch': html.escape(str(version_info.get('branch', ''))),
        'date': html.escape(str(version_info.get('date', '')))
    }
    html_content = BBS_LIST_PAGE % safe_version
    return HTMLResponse(content=html_content)


@page_router.get("/bbs/detail/{post_id}")
async def bbs_detail_page(post_id: str):
    """BBS详情页面"""
    safe_post_id = html.escape(post_id)
    html_content = BBS_DETAIL_PAGE % {'post_id': safe_post_id}
    return HTMLResponse(content=html_content)


# API endpoints
@router.post("/sync")
async def sync_post(request: dict, _admin=Depends(require_admin)):
    """Sync BBS post to database (insert or update)."""
    post_id = request.get("post_id")
    url = request.get("url")
    if not post_id or not url:
        return param_error("post_id 和 url 为必填项")
    try:
        result = await BBSService.sync_post(
            post_id=post_id,
            url=url,
            title=request.get("title"),
            author_id=request.get("author_id"),
            author_name=request.get("author_name"),
            status=request.get("status", "pending")
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))


@router.post("/analyze")
async def analyze_post(request: dict, _admin=Depends(require_admin)):
    """Trigger AI analysis for a post."""
    post_id = request.get("post_id")
    if not post_id:
        return param_error("post_id 为必填项")
    try:
        result = await BBSService.trigger_analysis(
            post_id=post_id,
            md_file_path=request.get("md_file_path")
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))


@router.get("/list")
async def list_posts(
    publish_start: Optional[str] = None,
    publish_end: Optional[str] = None,
    keyword: Optional[str] = None,
    is_digest: Optional[int] = None,
    has_ai_result: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """List BBS posts with filtering."""
    try:
        result = await BBSService.list_posts(
            publish_start=publish_start,
            publish_end=publish_end,
            keyword=keyword,
            is_digest=is_digest,
            has_ai_result=has_ai_result,
            status=status,
            page=page,
            page_size=page_size
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))


@router.get("/detail/{post_id}")
async def get_post_detail(post_id: str):
    """Get BBS post detail."""
    try:
        result = await BBSService.get_post_detail(post_id)
        if result:
            return success(result)
        return not_found("帖子不存在")
    except Exception as e:
        return param_error(str(e))


@router.post("/reanalyze")
async def reanalyze_post(request: dict, _admin=Depends(require_admin)):
    """Re-trigger AI analysis for a post."""
    post_id = request.get("post_id")
    if not post_id:
        return param_error("post_id 为必填项")
    try:
        result = await BBSService.reanalyze_post(
            post_id=post_id
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))


@router.post("/batch-analyze")
async def batch_analyze(_admin=Depends(require_admin)):
    """Batch trigger AI analysis for all posts with status=success and no AI result."""
    try:
        result = await BBSService.batch_analyze()
        return success(result)
    except Exception as e:
        return param_error(str(e))