(() => {
    var chrome_api = chrome;
    function initSetupPage() {
        document.body.innerHTML = '';
        
        let container = document.createElement('div');
        container.style.cssText = 'padding: 40px; font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto;';
        
        let title = document.createElement('h1');
        title.textContent = 'Local Captcha Solver Setup';
        
        let desc = document.createElement('p');
        desc.textContent = 'This extension runs completely locally on your machine. No external API keys are required.';
        
        let status = document.createElement('p');
        status.style.cssText = 'color: green; font-weight: bold;';
        status.textContent = '✓ Extension is installed and ready to use.';
        
        let note = document.createElement('p');
        note.style.cssText = 'color: #666; font-size: 14px;';
        note.textContent = 'The extension will automatically solve captchas when they appear on web pages.';
        
        container.appendChild(title);
        container.appendChild(desc);
        container.appendChild(status);
        container.appendChild(note);
        
        document.body.appendChild(container);
    }
    
    function onReady(callback) {
        if (document.readyState !== "loading") {
            setTimeout(callback, 0);
        } else {
            let handler = () => {
                removeEventListener("DOMContentLoaded", handler);
                callback();
            };
            addEventListener("DOMContentLoaded", handler);
        }
    }
    
    onReady(initSetupPage);
})();
