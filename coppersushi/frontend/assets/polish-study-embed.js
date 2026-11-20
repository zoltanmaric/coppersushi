// Include this script immediately after the study iframe in the article's HTML card.
(() => {
  const frame = document.currentScript.previousElementSibling;
  if (!(frame instanceof HTMLIFrameElement)) return;
  const origin = new URL(frame.src).origin;
  window.addEventListener('message', event => {
    if (event.origin !== origin || event.source !== frame.contentWindow) return;
    const message = event.data;
    if (message?.type === 'polish-study-height' && Number.isSafeInteger(message.height) && message.height > 0) {
      frame.style.height = message.height + 'px';
    }
  });
  frame.contentWindow.postMessage('request-polish-study-height', '*');
})();
