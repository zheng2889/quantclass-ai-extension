// BBS 抓取按钮事件绑定
// 不修改 popup.js，单独绑定按钮事件
document.addEventListener('DOMContentLoaded', function() {
  const btn = document.getElementById('btn-capture-digest');
  if (btn) {
    btn.addEventListener('click', async function() {
      // 获取当前活动标签页
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      if (!tab || !tab.url || !tab.url.includes('bbs.quantclass.cn')) {
        alert('请在 bbs.quantclass.cn 论坛页面使用此功能');
        return;
      }

      // 禁用按钮，显示处理中
      btn.disabled = true;
      btn.textContent = '处理中...';

      // 发送消息到 content script
      chrome.tabs.sendMessage(tab.id, { type: 'BBS_CAPTURE_START' }, function(response) {
        btn.disabled = false;
        btn.textContent = '抓取精华帖';

        if (response && response.success) {
          alert('抓取完成: ' + response.message);
        } else {
          alert('抓取失败: ' + (response?.error || '未知错误'));
        }
      });
    });
  }
});