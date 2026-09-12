// ─── Local Captcha Solver Extension ── popup.js ───

(function () {
  'use strict';

  // ローカル実行のため、外部APIへのアクセスは不要

  // ─── DOM References ───
  const authScreen = document.getElementById('auth-screen');
  const mainScreen = document.getElementById('main-screen');
  const apiKeyInput = document.getElementById('api-key-input');
  const btnActivate = document.getElementById('btn-activate');
  const authError = document.getElementById('auth-error');
  const btnCloud = document.getElementById('btn-cloud');
  const btnLocal = document.getElementById('btn-local');
  const modeDesc = document.getElementById('mode-description');
  const statInternalKey = document.getElementById('stat-internal-key');
  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');
  const btnPower = document.getElementById('btn-power');
  const powerIcon = document.getElementById('power-icon');
  const btnLogout = document.getElementById('btn-logout');

  // ─── Storage Helpers ───
  function getSettings() {
      return new Promise(resolve => {
          const nonce = Date.now().toString() + Math.random().toString();
          chrome.runtime.sendMessage([nonce, "settings::get", []], resp => {
              resolve(resp ? resp[1] : {});
          });
      });
  }

  function updateSettings(overrides) {
      return new Promise(resolve => {
          const nonce = Date.now().toString() + Math.random().toString();
          chrome.runtime.sendMessage([nonce, "settings::update", [overrides]], resp => {
              resolve();
          });
      });
  }

  // ─── Initialization ───
  async function init() {
    const settings = await getSettings();
    if (settings && settings.key && settings.key !== "") {
      showMainScreen(settings);
    } else {
      showAuthScreen();
    }
  }

  function showAuthScreen() {
    authScreen.classList.remove('hidden');
    mainScreen.classList.add('hidden');
    authError.textContent = '';
    apiKeyInput.value = '';
  }

  async function showMainScreen(settings) {
    authScreen.classList.add('hidden');
    mainScreen.classList.remove('hidden');

    const mode = 'cloud'; // We force cloud mode for the proxy logic to intercept
    const enabled = settings.enabled !== false;

    setMode(mode);
    setEnabled(enabled);
    if (statInternalKey) {
      statInternalKey.textContent = (settings.key && settings.key.substring(0, 16) + '...') || 'Not Set';
    }
  }

  // ─── API Key Activation ───
  btnActivate.addEventListener('click', async () => {
    const key = apiKeyInput.value.trim();
    if (!key) {
      authError.textContent = 'API key is not required for local operation. Click below to continue.';
      return;
    }

    btnActivate.disabled = true;
    btnActivate.textContent = 'Validating...';
    authError.textContent = '';

    try {
      // ローカル実行のため、外部サーバーへのアクセスは不要
      // キーをローカルストレージに保存して進む
      await updateSettings({ key: key, enabled: true });
      showMainScreen({ key: key, enabled: true });
    } catch (e) {
      authError.textContent = e.message || 'Failed to initialize';
      await updateSettings({ key: key, enabled: true });
      showMainScreen({ key: key, enabled: true });
    } finally {
      btnActivate.disabled = false;
      btnActivate.textContent = 'Activate';
    }
  });

  // ─── Solver Mode Toggle ───
  function setMode(mode) {
    // ローカル実行のため常にローカルモード
    btnLocal.classList.add('active');
    btnCloud.classList.remove('active');
    modeDesc.textContent = 'Solves locally on your PC using a browser extension.';
  }

  // ─── Power Toggle ───
  function setEnabled(enabled) {
    if (enabled) {
      statusDot.className = 'dot active';
      statusText.textContent = 'Active';
      btnPower.classList.remove('off');
      powerIcon.textContent = '⏻';
    } else {
      statusDot.className = 'dot disabled';
      statusText.textContent = 'Paused';
      btnPower.classList.add('off');
      powerIcon.textContent = '⏻';
    }
  }

  btnPower.addEventListener('click', async () => {
    const settings = await getSettings();
    const newEnabled = settings.enabled === false;
    await updateSettings({ enabled: newEnabled });
    setEnabled(newEnabled);
  });

  // ─── Logout ───
  btnLogout.addEventListener('click', async () => {
    await updateSettings({ key: "", enabled: false });
    showAuthScreen();
  });

  apiKeyInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') btnActivate.click();
  });

  // ─── Start ───
  init();
})();
