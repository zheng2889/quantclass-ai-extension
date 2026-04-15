# BBS 精华帖子抓取插件 - 需求分析

## 1. 功能概述

Chrome 插件扩展功能：在 bbs.quantclass.cn 论坛自动抓取精华帖子列表，保存到后台 SQLite 数据库，并自动进行 AI 分析。
后台提供管理页面查看抓取结果和 AI 分析结果。

## 2. 核心流程

```
用户点击插件按钮 → 检查登录状态 → 未登录提示 → 已登录则：

  步骤1：列表页抓取
    1.1 点击"精华"筛选按钮
    1.2 点击"按日期查看"按钮，自动填入近一个月日期范围
    1.3 自动滚动列表（每2-3秒加载下一页，5秒无新数据停止）
    1.4 抓取每个帖子的基本信息（帖子ID、链接、标题、作者）

  步骤2：首次数据保存
    2.1 对每条帖子，检查数据库是否已存在（根据 post_id 判断）
    2.2 已存在则跳过，不处理
    2.3 不存在则插入数据库，状态默认 "pending"
    2.4 保存：post_id、url、author_id、author_name、title、status

  步骤3：详细页处理（批量）
    3.1 查询数据库，获取所有 status 为 "pending"、"failed" 或为空的记录
    3.2 循环处理每条记录：
        3.2.1 打开帖子链接，等待页面加载
        3.2.2 判断是否有权限（无权限：标记 status="no_permission"）
        3.2.3 将帖子页面转为 MD 格式（保留格式、图片、代码块），保存到：
             {数据目录}/BBS/{帖子ID}/{帖子ID}.md
        3.2.4 检查是否有附件，有则下载到：
             {数据目录}/BBS/{帖子ID}/attachments/
        3.2.5 从页面提取：发布时间、编辑时间、是否精华
        3.2.6 更新数据库对应记录
        3.2.7 处理下一条

  步骤4：AI 分析（异步批量处理）
    4.1 对所有 status="success" 的记录，调用 AI 分析接口
    4.2 生成 AI 分析结果 MD 文件，保存到：
         {数据目录}/BBS/{帖子ID}/AI-{帖子ID}-{随机数}.md
    4.3 更新数据库：has_ai_result=1, ai_result_path（保留最新记录）
```

## 3. 配置项

### 插件端配置

存储在 `chrome.storage.local` 中：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| api_key | 后台 API 认证 Key | 用户配置 |

### 后台配置

- 数据存储目录由后台统一管理，插件不负责配置

## 4. 登录检测

### 未登录

页面有 `button.el-button` 包含文本"登录"

```html
<div data-v-157ef578="">
  <button data-v-157ef578="" type="button" class="el-button h-button h-button1 el-button--default el-button--small">
    <span>登录</span>
  </button>
  <button data-v-157ef578="" type="button" class="el-button h-button h-button2 el-button--default el-button--small">
    <span>注册</span>
  </button>
</div>
```

判断逻辑：`button.el-button` 包含文本"登录"

### 已登录

页面有 `div.flex` 下包含 `a[href^="/user/"]` 和 `a[href="/my/profile"]`

```html
<div data-v-157ef578="" class="flex">
  <div data-v-6f90f895="" data-v-157ef578="" class="">
    <a data-v-6f90f895="" href="/user/27506" class="avatar-a avatar-size-35">
      <img ... alt="Zheng2889">
    </a>
  </div>
  <a data-v-157ef578="" href="/user/27506" class="menu-item user-name text-hidden">Zheng2889</a>
  <a data-v-157ef578="" href="/my/notice" class="menu-item notice-btn">消息</a>
  <a data-v-157ef578="" href="/my/profile" class="menu-item">个人中心</a>
  <div data-v-157ef578="" class="menu-item">退出登录</div>
</div>
```

判断逻辑：`div.flex > a[href^="/user/"]` 且存在 `a[href="/my/profile"]`

## 5. 选择器汇总

### 列表页选择器

| 字段 | 选择器 | 提取方式 |
|------|--------|----------|
| 帖子ID | `a.title[href]` | 从 URL `/thread/{id}` 提取 |
| 链接 | `a.title` | 获取 href 属性 |
| 标题 | `a.title span:not(.el-tag)` | 获取文本内容，过滤标签元素 |
| 作者ID | `.top-user-info a[href^="/user/"]` | 从 URL 提取数字部分 |
| 作者名称 | `.user-name` | 获取文本 |

### 详细页选择器

| 字段 | 选择器 | 说明 |
|------|--------|------|
| 发布时间 | `.publish-time span:contains("发布于")` | 提取文本中的日期，如 "2025-09-20 18:29" |
| 编辑时间 | `.publish-time span:contains("编辑于")` | 提取文本中的日期，如 "2025-10-13 02:13" |
| 是否精华 | `div.thread-tags span.el-tag--danger:contains("精华帖")` | 存在则标记为 1 |
| 是否独创 | `div.thread-tags span:contains("独家原创")` | 存在则标记为 1 |
| 是否有附件 | `div.container-attachment` | 存在则标记为 1 |
| 附件列表 | `div.container-attachment div.attachment-item` | 遍历每个附件 |
| 附件名称 | `div.container-attachment div.attachment-item div.info span.file-name` | 获取文件名 |
| 下载按钮 | `div.container-attachment div.attachment-item span.download` | 点击触发下载 |
| 无权限 | `div.hide-content-tip:contains("剩余内容已隐藏")` | 存在则标记无权限 |

### 无权限检测

```html
<div data-v-675aac18="" class="hide-content-tip">
  <p data-v-675aac18="" class="mb-2 text-muted">(剩余内容已隐藏)</p>
  <div data-v-675aac18="" class="text-primary mb-3">本版块为邢不行-B圈基础课程课程同学专属...</div>
  <button data-v-675aac18="" type="button" class="el-button el-button--default el-button--small is-plain">
    <span>立即报名</span>
  </button>
</div>
```

选择器：`div.hide-content-tip:contains("剩余内容已隐藏")`

## 6. 数据库表 BBS_LIST（新建）

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

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| post_id | TEXT | 帖子原始ID（唯一标识） |
| url | TEXT | 帖子完整链接 |
| title | TEXT | 帖子标题 |
| author_id | TEXT | 作者ID（从 URL 提取） |
| author_name | TEXT | 作者显示名称 |
| publish_time | DATETIME | 发布时间（从详细页获取） |
| modify_time | DATETIME | 编辑时间（从详细页获取） |
| is_digest | INTEGER | 是否精华：0/1（从详细页获取） |
| is_original | INTEGER | 是否独创：0/1（从详细页获取） |
| has_attachment | INTEGER | 是否有附件：0/1 |
| md_file_path | TEXT | 帖子原文 MD 文件完整路径 |
| attachment_dir | TEXT | 附件存储目录 |
| crawled_at | DATETIME | 抓取时间 |
| status | TEXT | pending/success/no_permission/failed |
| has_ai_result | INTEGER | 是否已有 AI 分析结果：0/1 |
| ai_result_path | TEXT | AI 分析结果 MD 文件路径（仅保留最新） |
| error_message | TEXT | 错误信息（失败时记录） |

### 状态流转

```
新插入 → pending
  ↓
详细页处理成功 → success
详细页处理无权限 → no_permission
详细页处理失败 → failed

success 状态可触发 AI 分析
```

## 7. 文件存储路径格式

### 基础目录

数据存储目录（后台配置）：`{后台配置的数据目录}/`

### 帖子原文 MD

```
{数据目录}/BBS/{帖子ID}/{帖子ID}.md
```

示例：`D:/quantclass/BBS/77883/77883.md`

### 图片存储

帖子中的图片在转换为 MD 时一并下载保存：
```
{数据目录}/BBS/{帖子ID}/images/
```

### 附件目录

```
{数据目录}/BBS/{帖子ID}/attachments/
```

示例：`D:/quantclass/BBS/77883/attachments/`

### AI 分析结果 MD

```
{数据目录}/BBS/{帖子ID}/AI-{帖子ID}-{随机4位数字}.md
```

示例：`D:/quantclass/BBS/77883/AI-77883-a3b2.md`

## 8. API 接口

### 同步帖子数据

- **地址**：`POST /api/bbs/sync`
- **认证**：API Key（存储在 chrome.storage.local 中）
- **功能**：插入或更新帖子数据（根据 post_id 判断）

#### 请求格式

```json
{
  "post_id": "77883",
  "url": "https://bbs.quantclass.cn/thread/77883",
  "title": "让100个策略断点续传跑回测",
  "author_id": "52084",
  "author_name": "elikong",
  "status": "pending"
}
```

#### 响应格式

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

### AI 分析接口（异步）

- **地址**：`POST /api/bbs/analyze`
- **认证**：API Key
- **返回**：异步返回任务 ID，后续通过轮询或 WebSocket 获取结果

#### 请求格式

```json
{
  "post_id": "77883",
  "md_file_path": "D:/quantclass/BBS/77883/77883.md"
}
```

#### 响应格式

```json
{
  "success": true,
  "task_id": "uuid-xxx",
  "message": "任务已加入队列"
}
```

## 9. 后台管理页面

### Git 版本功能

#### 版本显示

- 在页面 footer 或 header 显示当前代码版本信息
- 显示内容：Git commit hash、分支名称、最后更新时间
- 格式示例：`v1.0.0 | main | 2025-04-14 10:30`

#### 代码更新

- 提供"检查更新"按钮，点击后执行 `git pull`
- 显示更新结果（成功/失败）
- 如果有本地修改未提交，应提示用户先处理

### 列表页面

#### 筛选功能

| 筛选条件 | 类型 | 说明 |
|----------|------|------|
| 发布日期范围 | 日期范围选择器 | 开始日期 ~ 结束日期 |
| 关键字 | 文本输入 | 对帖子 title 进行模糊匹配 |
| 是否精华 | 下拉选择 | 全部 / 是 / 否 |
| AI 分析结果 | 下拉选择 | 全部 / 有 / 无 |

#### 列表字段

| 字段 | 说明 | 可排序 |
|------|------|--------|
| 帖子ID | post_id | 否 |
| 标题 | title（可点击跳转） | 否 |
| 作者 | author_name | 否 |
| 发布时间 | publish_time | 是（默认倒序） |
| 是否精华 | is_digest 显示图标 | 否 |
| AI 分析 | has_ai_result 显示状态 | 否 |
| 状态 | status 显示状态 | 否 |

#### 排序功能

- 默认按发布时间倒序（最新的在前）
- 点击发布时间表头可切换升序/降序
- 支持其他字段的排序扩展

#### 分页

- 每页显示 20/50/100 条
- 支持跳转页码

### 明细页面

#### 显示内容

| 内容 | 说明 |
|------|------|
| 帖子标题 | title |
| 原文链接 | 点击跳转新窗口打开原帖子 |
| 原文 MD 内容 | 渲染后的 HTML（MD 转 HTML） |
| 附件列表 | 显示附件名称和下载链接 |
| AI 分析结果 | 显示最新 AI 分析结果（MD 转 HTML） |
| 基本信息 | 作者、发布时间、编辑时间、是否精华、是否独创 |

#### 操作按钮

| 按钮 | 功能 | 说明 |
|------|------|------|
| 重新 AI 分析 | 触发 AI 分析 | 调用 API 分析原文 MD，生成 AI 分析文件 |

#### 重新 AI 分析功能

1. 点击"重新 AI 分析"按钮
2. 调用 AI 分析接口 `POST /api/bbs/analyze`
3. 请求参数：
   ```json
   {
     "post_id": "77883",
     "md_file_path": "D:/quantclass/BBS/77883/77883.md"
   }
   ```
4. 生成 AI 分析结果文件：`AI-{帖子ID}-{随机4位数字}.md`
5. 更新数据库记录：
   - `has_ai_result = 1`
   - `ai_result_path = {新生成的AI结果文件路径}`
6. 刷新页面显示新的 AI 分析结果

#### MD 转 HTML

- 加载 MD 文件后转换为 HTML 渲染
- 图片使用本地存储路径

## 10. 日志功能

### 插件端日志

抓取过程中产生的日志发送到后台存储：
- 进度信息
- 错误信息
- 操作记录

### 后台日志

- **存储方式**：每天一个日志文件
- **文件格式**：`bbs_crawl_YYYY-MM-DD.log`
- **日志内容**：记录当天所有插件抓取帖子内容的活动

## 11. 处理逻辑详解

### 步骤2：首次数据保存

```javascript
for each post in listPagePosts:
    // 检查数据库是否已存在
    existing = db.query("SELECT id FROM bbs_list WHERE post_id = ?", post.id)
    if existing:
        continue  // 已存在，跳过

    // 插入新记录
    db.insert("bbs_list", {
        post_id: post.id,
        url: post.url,
        title: post.title,
        author_id: post.authorId,
        author_name: post.authorName,
        status: "pending"
    })
```

### 步骤3：详细页处理

```javascript
// 获取待处理记录
pendingPosts = db.query("SELECT * FROM bbs_list WHERE status IN ('pending', 'failed') OR status IS NULL")

for post in pendingPosts:
    // 打开帖子页面
    page = open(post.url)
    await page.waitForLoad()

    // 检查权限
    if page.hasElement("div.hide-content-tip:contains('剩余内容已隐藏')"):
        db.update("bbs_list", {status: "no_permission"}, {id: post.id})
        continue

    // 转换为 MD（保留格式、图片、代码块）并保存
    mdContent = convertToMarkdown(page, {keepFormat: true, keepImages: true, keepCodeBlock: true})
    mdPath = `${dataDir}/BBS/${post.post_id}/${post.post_id}.md`
    saveFile(mdPath, mdContent)

    // 更新 md_file_path
    db.update("bbs_list", {
        md_file_path: mdPath,
        status: "success"
    }, {id: post.id})

    // 检查附件
    attachments = page.querySelectorAll("div.container-attachment div.attachment-item")
    if attachments.length > 0:
        attachmentDir = `${dataDir}/BBS/${post.post_id}/attachments/`
        for attachment in attachments:
            fileName = attachment.querySelector("span.file-name").text
            downloadBtn = attachment.querySelector("span.download")
            downloadBtn.click()  // 触发浏览器下载
        db.update("bbs_list", {
            has_attachment: 1,
            attachment_dir: attachmentDir
        }, {id: post.id})

    // 提取页面信息
    publishTime = page.querySelector(".publish-time span:contains('发布于')").text
    editTime = page.querySelector(".publish-time span:contains('编辑于')").text
    isDigest = page.hasElement("div.thread-tags span.el-tag--danger:contains('精华帖')") ? 1 : 0
    isOriginal = page.hasElement("div.thread-tags span:contains('独家原创')") ? 1 : 0

    db.update("bbs_list", {
        publish_time: parseTime(publishTime),
        modify_time: parseTime(editTime),
        is_digest: isDigest,
        is_original: isOriginal
    }, {id: post.id})
```

### 步骤4：AI 分析（异步）

```javascript
// 后台异步处理
taskQueue = []  // 任务队列

function processAIAnalysis():
    while taskQueue is not empty:
        task = taskQueue.pop()
        result = callAIAnalysisAPI({
            post_id: task.post_id,
            md_file_path: task.md_file_path
        })

        if result.success:
            aiFileName = `AI-${task.post_id}-${random4Digits()}.md`
            aiPath = `${dataDir}/BBS/${task.post_id}/${aiFileName}`

            if result.content:
                saveFile(aiPath, result.content)

            db.update("bbs_list", {
                has_ai_result: 1,
                ai_result_path: aiPath
            }, {id: task.id})
```

## 12. 特殊情况处理

### 无权限帖子

详细页出现以下情况标记为无权限：
- `div.hide-content-tip` 存在
- 包含文本 "(剩余内容已隐藏)"

处理方式：标记 `status = "no_permission"`，不进行后续处理

### 日期筛选

- "按日期查看"按钮：`<div class="filter-btn"><i class="el-icon-date"></i>按日期查看</div>`
- 点击后会出现日期选择器
- 默认填充：当前日期往前推一个月

### 滚动加载

- 列表使用无限滚动机制
- **模拟人工操作**：使用缓慢滚动，每段滚动后等待 3-4 秒
- 滚动方式：每次滚动一小段距离（如 200px），等待 3-4 秒，再继续滚动
- 5 秒内无新数据加载则认为已到末尾
- 避免一次性滚动到底，防止触发反爬虫机制

## 13. 参考文件

- 列表页样本：`需求分析/列表页样本/量化小论坛-列表页面.html`
- 详细页样本：`需求分析/详细页面样本/翻开自由现金流的"暴跌史"：从血泪教训到心理建设 - 量化小论坛.htm`
- 无权限帖子样本：`需求分析/没有权限的帖子样本/新人小徐WEB3的被骗日记-量化小论坛.html`