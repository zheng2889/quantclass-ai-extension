# BBS 精华帖子抓取插件 - 技术方案

## 一、开发限制

1. **不删除现有代码** - 新增功能不能影响或删除现有的 GitHub 仓库中的代码
2. **复用现有函数** - 后台开发尽量复用现有的函数和服务，避免重复代码
3. **向后兼容** - 新增的 API 和数据库表要确保与现有系统兼容

---

## 二、数据库设计

### 2.1 新建表 BBS_LIST

```sql
CREATE TABLE IF NOT EXISTS bbs_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    author_id TEXT,
    author_name TEXT,
    publish_time DATETIME,
    modify_time DATETIME,
    is_digest INTEGER,
    is_original INTEGER,
    has_attachment INTEGER DEFAULT 0,
    md_file_path TEXT,
    attachment_dir TEXT,
    crawled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending',
    has_ai_result INTEGER DEFAULT 0,
    ai_result_path TEXT,
    error_message TEXT
);
```

### 2.2 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| post_id | TEXT | 帖子原始ID（唯一标识） |
| url | TEXT | 帖子完整链接 |
| title | TEXT | 帖子标题 |
| author_id | TEXT | 作者ID |
| author_name | TEXT | 作者名称 |
| publish_time | DATETIME | 发布时间 |
| modify_time | DATETIME | 编辑时间 |
| is_digest | INTEGER | 是否精华：0/1 |
| is_original | INTEGER | 是否独创：0/1 |
| has_attachment | INTEGER | 是否有附件：0/1 |
| md_file_path | TEXT | 帖子原文 MD 文件路径 |
| attachment_dir | TEXT | 附件存储目录 |
| crawled_at | DATETIME | 抓取时间 |
| status | TEXT | pending/success/no_permission/failed |
| has_ai_result | INTEGER | 是否有AI分析结果：0/1 |
| ai_result_path | TEXT | AI分析结果MD路径 |
| error_message | TEXT | 错误信息 |

### 2.3 状态流转

```
新插入 → pending
  ↓
详细页处理成功 → success
详细页处理无权限 → no_permission
详细页处理失败 → failed
```

---

## 三、API 接口设计

### 3.1 同步帖子数据

| 项目 | 内容 |
|------|------|
| URL | `POST /api/bbs/sync` |
| 认证 | Header: `X-API-Key` |
| 功能 | 插入或更新帖子数据（根据 post_id 判断） |

**请求**：
```json
{
  "post_id": "77883",
  "url": "https://bbs.quantclass.cn/thread/77883",
  "title": "帖子标题",
  "author_id": "52084",
  "author_name": "elikong",
  "status": "pending"
}
```

**响应**：
```json
{
  "success": true,
  "message": "数据同步成功",
  "data": {
    "id": 1,
    "post_id": "77883"
  }
}
```

### 3.2 AI 分析

| 项目 | 内容 |
|------|------|
| URL | `POST /api/bbs/analyze` |
| 认证 | Header: `X-API-Key` |
| 功能 | 异步处理AI分析 |

**请求**：
```json
{
  "post_id": "77883",
  "md_file_path": "/data/BBS/77883/77883.md"
}
```

**响应**：
```json
{
  "success": true,
  "task_id": "uuid-xxx",
  "message": "任务已加入队列"
}
```

### 3.3 查询列表

| 项目 | 内容 |
|------|------|
| URL | `GET /api/bbs/list` |
| 参数 | `page`, `page_size`, `publish_start`, `publish_end`, `keyword`, `is_digest`, `has_ai_result` |

### 3.4 获取明细

| 项目 | 内容 |
|------|------|
| URL | `GET /api/bbs/detail/{post_id}` |

### 3.5 重新AI分析

| 项目 | 内容 |
|------|------|
| URL | `POST /api/bbs/reanalyze` |
| 功能 | 手动触发重新AI分析 |

---

## 四、插件端实现

### 4.1 文件结构

```
extension/
├── build/
│   ├── popup.html      # 在现有基础上添加新按钮
│   ├── popup.js        # 在现有基础上添加新逻辑
│   └── content.js      # 在现有基础上添加页面操作脚本
├── manifest.json       # 可能需要更新权限
```

### 4.2 插件按钮设计

**设计原则**：
- 不修改现有按钮的功能和逻辑
- 新功能通过添加独立按钮实现
- 按钮展示在插件 Popup 界面的右侧区域

**按钮布局**：
```
+-----------------------------------+
| 现有功能区域     |   新功能区域    |
| [AI聊天] [知识库]  | [抓取精华帖] |
+-----------------------------------+
```

**功能按钮**：
| 按钮 | 功能 | 位置 |
|------|------|------|
| 抓取精华帖 | 点击触发 BBS 抓取流程 | Popup 右侧新增 |

### 4.2 主要函数

| 函数 | 功能 | 说明 |
|------|------|------|
| `checkLoginStatus()` | 检查登录状态 | 新增 |
| `scrollAndLoad()` | 模拟人工滚动加载 | 新增 |
| `extractPostList()` | 提取列表页帖子信息 | 新增 |
| `openAndExtract()` | 打开详情页提取信息 | 新增 |
| `convertToMarkdown()` | 页面转MD | 新增 |
| `saveToBackend()` | 调用后台API | 新增 |
| `downloadAttachment()` | 下载附件 | 新增 |

### 4.3 实现约束

**代码组织**：
- 新功能代码独立于原有功能
- 不修改 `popup.js` 中原有按钮的点击事件
- 新增按钮的事件处理独立实现

**代码示例**：

```javascript
// popup.js 中新增部分
// 不修改原有代码，只是在现有基础上添加

// 新增：抓取精华帖按钮的事件处理
const handleDigestCapture = async () => {
  // 1. 检查登录状态
  const isLoggedIn = await bbsModule.checkLoginStatus();
  if (!isLoggedIn) {
    showMessage('请先登录论坛', 'warning');
    return;
  }

  // 2. 抓取流程
  await bbsModule.startCapture();
};

// 现有的原有功能代码保持不变
// const handleOriginalFunction = () => { ... }

// 新增按钮绑定
document.getElementById('btn-capture-digest')?.addEventListener('click', handleDigestCapture);
```

### 4.4 附件下载处理

#### 方案A：使用 setDownloadPath（推荐）

```javascript
// 设置下载目录
await page.setDownloadDirectory(targetDir);

// 点击下载按钮
await page.click('span.download');
```

#### 方案B：浏览器限制时的处理

如果浏览器无法指定下载目录：

```javascript
// 方案B：检测到浏览器限制时
// 1. 监听下载，使用临时目录
// 2. 下载完成后，根据文件名和时间找到文件
// 3. 移动文件到目标目录

async function downloadWithMove(page, downloadBtnSelector, targetDir) {
  // 创建临时下载监听
  const downloadPath = await new Promise(resolve => {
    page.on('download', (download) => {
      resolve(download.suggestedFilename());
    });
  });

  // 点击下载按钮
  await page.click(downloadBtnSelector);

  // 使用 fs 根据时间找到最新下载的文件
  const latestFile = getLatestDownloadFile();

  // 移动到目标目录
  fs.move(latestFile.path, targetDir + '/' + downloadPath);
}
```

---

## 五、后台实现

### 5.1 目录结构

```
backend/
├── routers/
│   └── bbs.py              # 新增 BBS 相关路由
├── services/
│   └── bbs_service.py      # 新增 BBS 服务
└── templates/
    └── bbs/                # 后台页面模板
        ├── list.html       # 列表页
        └── detail.html    # 明细页
```

### 5.2 复用现有组件

| 现有组件 | 复用方式 |
|----------|----------|
| `database/connection.py` | 使用现有 DatabaseManager |
| `services/knowledge_service.py` | 参考MD转换逻辑 |
| `routers/admin.py` | 参考管理页面结构 |
| `models/schemas.py` | 添加 BBS 相关 schema |

### 5.3 AI 队列处理

```python
# 简单的异步队列处理
class AIQueue:
    def __init__(self, max_workers=3):
        self.queue = asyncio.Queue()
        self.max_workers = max_workers
        self.workers = []

    async def process(self):
        # 并发处理
        tasks = [self.process_one() for _ in range(self.max_workers)]
        await asyncio.gather(*tasks)

    async def process_one(self):
        while True:
            task = await self.queue.get()
            # 执行AI分析
            result = await call_ai_service(task)
            # 更新数据库
            await update_result(task, result)
```

---

## 六、前端页面（管理后台）

### 6.1 页面结构

| 页面 | 路由 | 功能 |
|------|------|------|
| BBS 列表 | `/bbs` | 筛选、分页、排序 |
| BBS 明细 | `/bbs/:post_id` | 查看详情、重新AI分析 |

### 6.2 列表页面功能

- 筛选：发布日期范围、关键字、是否精华、AI分析状态
- 排序：按发布时间排序（默认倒序）
- 分页：每页20/50/100条

### 6.3 明细页面功能

- 显示：帖子标题、原文链接、MD内容、附件、AI分析结果
- 操作：重新AI分析按钮
- Git版本显示

---

## 七、技术选型

| 模块 | 选型 | 说明 |
|------|------|------|
| 数据库 | SQLite + aiosqlite | 复用现有 |
| Web框架 | FastAPI | 复用现有 |
| 前端 | HTML + Vanilla JS | 轻量��� |
| MD处理 | python-markdown | 新增依赖 |
| 插件 | Chrome Extension | 复用现有 |

---

## 八、开发顺序

```
阶段1: 数据库 + API
  1.1 创建 bbs_list 表
  1.2 实现 /api/bbs/sync

阶段2: 插件端
  2.1 登录检测
  2.2 列表页抓取
  2.3 详情页处理 + MD转换

阶段3: 后台对接
  3.1 实现 /api/bbs/analyze
  3.2 AI队列处理

阶段4: 管理页面
  4.1 列表页
  4.2 明细页

阶段5: 测试 + 优化
```

---

## 九、风险与对策

| 风险 | 对策 |
|------|------|
| 反爬虫检测 | 模拟人工滚动，随机延迟3-4秒 |
| 附件下载 | 优先使用setDownloadPath，备选方案移动文件 |
| AI队列堆积 | 限制并发数，任务超时自动跳过 |
| 数据库锁 | 使用WAL模式，异步操作 |
| 影响现有功能 | 新功能独立实现，不修改原有代码 |

---

## 十、开发约束

### 10.1 代码隔离

- **不修改原有功能**：新增代码不能修改现有按钮的逻辑
- **独立模块**：新功能使用独立模块/函数，避免与现有代码耦合
- **按钮独立**：新增功能按钮单独添加，不影响现有按钮

### 10.2 代码组织示例

```javascript
// extension/build/popup.js

// ===== 现有代码保持不变 =====
// 原有按钮的事件绑定
document.getElementById('btn-existing-1')?.addEventListener('click', handleExisting1);
document.getElementById('btn-existing-2')?.addEventListener('click', handleExisting2);

// ===== 新增代码 =====
// BBS 抓取模块
const bbsCapture = {
  checkLoginStatus: async () => { ... },
  startCapture: async () => { ... },
  // ... 其他函数
};

// 新增按钮的事件绑定
document.getElementById('btn-capture-digest')?.addEventListener('click', () => {
  bbsCapture.startCapture();
});
```

### 10.3 HTML 结构示例

```html
<!-- popup.html -->
<div class="plugin-container">
  <!-- 现有功能区域 - 保持不变 -->
  <div class="existing-section">
    <button id="btn-existing-1">AI聊天</button>
    <button id="btn-existing-2">知识库</button>
  </div>

  <!-- 新功能区域 - 右侧新增 -->
  <div class="new-section">
    <button id="btn-capture-digest">抓取精华帖</button>
  </div>
</div>
```