(()=>{
  var chrome_api = chrome;
  function markInstalled() {
    document.documentElement.setAttribute("installed", "yes");
    document.documentElement.setAttribute("data", JSON.stringify({version: chrome_api.runtime.getManifest().version}));
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
  
  onReady(markInstalled);
})();
