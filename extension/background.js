// ローカル実行のためのバックグラウンドスクリプト
(()=>{
  // 拡張機能のバックグラウンド処理
  // MINTOtchaサーバーへのアクセスは完全に削除
  
  console.log('Local extension background loaded');
  
  // ローカルストレージの基本設定
  const DEFAULT_SETTINGS = {
    version: 1,
    enabled: true,
    key: "",
    hcaptcha_auto_solve: true,
  };
  
  // 設定取得
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'getSettings') {
      chrome.storage.local.get('settings', (result) => {
        const settings = result.settings || DEFAULT_SETTINGS;
        sendResponse(settings);
      });
      return true;
    }
    
    if (request.action === 'updateSettings') {
      chrome.storage.local.set({ settings: request.settings }, () => {
        sendResponse({ ok: true });
      });
      return true;
    }
    
    sendResponse(null);
  });
  
  // コンテンツスクリプトの登録
  if (chrome.scripting) {
    chrome.scripting.getRegisteredContentScripts().catch(() => {
      // コンテンツスクリプトが登録されていない場合
      console.log('Content scripts not yet registered');
    });
  }
})();
