/**
 * BBS Digest Post Capture Module
 * 不修改现有代码，独立实现抓取功能
 */

// BBS抓取模块
const BBSCapture = {
  // 配置
  config: {
    backendUrl: '',
    apiKey: ''
  },

  // 初始化配置
  async init() {
    const settings = await chrome.storage.local.get([
      'quantclass_backend_url',
      'quantclass_api_key'
    ]);
    this.config.backendUrl = settings.quantclass_backend_url || 'http://127.0.0.1:8701';
    this.config.apiKey = settings.quantclass_api_key || '';
  },

  // 检查登录状态
  checkLoginStatus() {
    return new Promise((resolve) => {
      // 未登录：页面有 button.el-button 包含文本"登录"
      const loginBtn = document.querySelector('button.el-button');
      const isNotLoggedIn = loginBtn && loginBtn.textContent.includes('登录');

      // 已登录：页面有 div.flex 下包含 a[href^="/user/"]
      const userLink = document.querySelector('div.flex a[href^="/user/"]');
      const hasProfile = document.querySelector('a[href="/my/profile"]');

      resolve(!isNotLoggedIn && !!userLink && !!hasProfile);
    });
  },

  // 模拟人工滚动加载
  async scrollAndLoad() {
    const delay = (ms) => new Promise(r => setTimeout(r, ms));

    let lastHeight = 0;
    let noChangeCount = 0;
    const maxNoChange = 5; // 5次滚动无新内容则停止

    while (noChangeCount < maxNoChange) {
      // 滚动一小段
      window.scrollBy(0, 300);
      await delay(3000 + Math.random() * 1000); // 3-4秒随机延迟

      const newHeight = document.body.scrollHeight;
      if (newHeight === lastHeight) {
        noChangeCount++;
      } else {
        noChangeCount = 0;
        lastHeight = newHeight;
      }
    }

    return lastHeight;
  },

  // 提取列表页帖子信息
  extractPostList() {
    const posts = [];
    const containers = document.querySelectorAll('.post-container, [data-v-0c32fec4]');

    for (const container of containers) {
      try {
        // 获取标题和链接
        const titleLink = container.querySelector('a.title, a[href*="/thread/"]');
        if (!titleLink) continue;

        const url = titleLink.href;
        const postIdMatch = url.match(/\/thread\/(\d+)/);
        if (!postIdMatch) continue;

        const postId = postIdMatch[1];
        const title = titleLink.textContent.trim();

        // 获取作者
        const authorLink = container.querySelector('a[href^="/user/"]');
        const authorIdMatch = authorLink ? authorLink.href.match(/\/user\/(\d+)/) : null;
        const authorId = authorIdMatch ? authorIdMatch[1] : '';
        const authorName = container.querySelector('.user-name')?.textContent?.trim() || '';

        posts.push({
          post_id: postId,
          url: url,
          title: title,
          author_id: authorId,
          author_name: authorName
        });
      } catch (e) {
        console.warn('Extract post error:', e);
      }
    }

    return posts;
  },

  // 调用后台API同步帖子
  async syncPost(post) {
    const headers = { 'Content-Type': 'application/json' };
    if (this.config.apiKey) {
      headers['Authorization'] = 'Bearer ' + this.config.apiKey;
    }

    const response = await fetch(`${this.config.backendUrl}/api/bbs/sync`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        post_id: post.post_id,
        url: post.url,
        title: post.title,
        author_id: post.author_id,
        author_name: post.author_name,
        status: 'pending'
      })
    });

    return response.json();
  },

  // 显示通知
  showNotification(message, type = 'info') {
    const colors = {
      info: '#1890ff',
      success: '#52c41a',
      warning: '#faad14',
      error: '#ff4d4f'
    };

    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: ${colors[type] || colors.info};
      color: white;
      padding: 12px 20px;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      z-index: 999999;
      font-size: 14px;
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  },

  // 主抓取流程
  async startCapture() {
    await this.init();
    this.showNotification('开始抓取...', 'info');

    // 1. 检查登录
    const isLoggedIn = await this.checkLoginStatus();
    if (!isLoggedIn) {
      this.showNotification('请先登录论坛', 'error');
      return;
    }

    this.showNotification('已登录，开始滚动加载...', 'info');

    // 2. 滚动加载
    await this.scrollAndLoad();
    this.showNotification('滚动完成，开始提取...', 'info');

    // 3. 提取帖子
    const posts = this.extractPostList();
    this.showNotification(`提取到 ${posts.length} 条帖子`, 'success');

    // 4. 同步到后台
    let synced = 0;
    for (const post of posts) {
      try {
        const result = await this.syncPost(post);
        if (result.code === 0) synced++;
      } catch (e) {
        console.warn('Sync error:', e);
      }
    }

    this.showNotification(`同步完成：${synced}/${posts.length}`, 'success');
  }
};

// 导出到全局
window.BBSCapture = BBSCapture;

// 监听来自 popup 的消息
if (typeof chrome !== 'undefined' && chrome.runtime) {
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'BBS_CAPTURE_START') {
      BBSCapture.init().then(async () => {
        try {
          // 检查登录
          const isLoggedIn = await BBSCapture.checkLoginStatus();
          if (!isLoggedIn) {
            sendResponse({ success: false, error: '请先登录论坛' });
            return;
          }

          // 滚动加载
          await BBSCapture.scrollAndLoad();

          // 提取帖子
          const posts = BBSCapture.extractPostList();
          sendResponse({ success: true, message: `提取到 ${posts.length} 条帖子` });

          // 同步到后台（后台异步执行）
          for (const post of posts) {
            try {
              await BBSCapture.syncPost(post);
            } catch (e) {
              console.warn('Sync error:', e);
            }
          }
        } catch (e) {
          sendResponse({ success: false, error: e.message });
        }
      });
      return true; // 异步响应
    }
  });
}