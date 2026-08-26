(function () {
  'use strict';
  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const set = (selector, text, root = document) => { const node = q(selector, root); if (node && node.textContent !== text) node.textContent = text; };
  const setMany = (selector, values, root = document) => qa(selector, root).forEach((node, index) => { if (values[index] !== undefined && node.textContent !== values[index]) node.textContent = values[index]; });
  const replaceTextNodes = (element, value, leading) => {
    if (!element) return;
    const textNodes = [...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE);
    const current = leading ? textNodes[0] : textNodes[textNodes.length - 1];
    textNodes.filter(node => node !== current).forEach(node => node.remove());
    if (current) {
      if (current.nodeValue !== value) current.nodeValue = value;
    } else {
      const text = document.createTextNode(value);
      if (leading) element.insertBefore(text, element.firstChild);
      else element.appendChild(text);
    }
  };
  const setLeadingText = (element, value) => replaceTextNodes(element, value, true);
  const setTrailingText = (element, value) => replaceTextNodes(element, value, false);

  function normalizeLogin() {
    const login = q('.production-login'); if (!login) return;
    const image = q('.production-login-brand img', login); if (image) image.alt = '\u4e2d\u56fd\u4e1c\u65b9\u822a\u7a7a';
    const labels = qa('.production-login-form label', login);
    setLeadingText(labels[0], '\u7528\u6237\u540d');
    setLeadingText(labels[1], '\u5bc6\u7801');
    const button = q('.production-login-form button', login);
    if (button && /^\?+$/.test(button.textContent.trim())) button.textContent = '\u767b\u5f55\u5e73\u53f0';
  }

  function normalizeNavigation() {
    setTrailingText(q('[data-view="imports"]'), '\u6570\u636e\u63a5\u5165');
    setTrailingText(q('[data-view="models"]'), '\u6a21\u578b\u914d\u7f6e');
    setTrailingText(q('[data-view="tenants"]'), '\u79df\u6237\u4e0e\u7528\u6237');
  }

  function normalizeImports() {
    const page = q('#imports'); if (!page) return;
    set('.page-head h1', '\u6570\u636e\u63a5\u5165', page);
    set('.page-head p', '\u6309\u79df\u6237\u5bfc\u5165\u5ba2\u6237\u3001\u5ba2\u7fa4\u3001\u822a\u7ebf\u3001\u4ea7\u54c1\u5305\u3001\u6d3b\u52a8\u3001\u6e20\u9053\u4e0e\u7ed3\u679c\u5173\u7cfb', page);
    setMany('.panel-head h2', ['\u65b0\u5efa\u5bfc\u5165\u6279\u6b21', '\u63a5\u5165\u6cbb\u7406\u89c4\u5219', '\u5bfc\u5165\u5386\u53f2'], page);
    setMany('.production-upload b', ['\u5b9e\u4f53\u6570\u636e', '\u5173\u7cfb\u6570\u636e'], page);
    setMany('[data-production-import]', ['\u6821\u9a8c\u5e76\u5bfc\u5165\u5b9e\u4f53', '\u6821\u9a8c\u5e76\u5bfc\u5165\u5173\u7cfb'], page);
    setMany('.control-item b', ['\u79df\u6237\u5f52\u5c5e', '\u5b9e\u4f53\u66f4\u65b0', '\u9519\u8bef\u9694\u79bb'], page);
    setMany('.control-item span', ['\u5b9e\u4f53\u3001\u5173\u7cfb\u548c\u6279\u6b21\u81ea\u52a8\u7ed1\u5b9a\u5f53\u524d\u79df\u6237', '\u6309 external_id \u65b0\u589e\u6216\u66f4\u65b0', '\u9519\u8bef\u884c\u4fdd\u7559\u884c\u53f7\u3001\u539f\u56e0\u4e0e\u6570\u636e\u6458\u8981'], page);
    setMany('#importTable th', ['\u6587\u4ef6', '\u7c7b\u578b', '\u603b\u884c\u6570', '\u6210\u529f', '\u5931\u8d25', '\u72b6\u6001', '\u65f6\u95f4'], page);
  }

  function normalizeModels() {
    const page = q('#models'); if (!page) return;
    set('.page-head h1', '\u6a21\u578b\u914d\u7f6e', page);
    set('.page-head p', '\u4e3a\u5f53\u524d\u79df\u6237\u914d\u7f6e\u53ef\u66ff\u6362\u7684\u5927\u6a21\u578b\u670d\u52a1\uff0c\u667a\u80fd\u57df\u8fd0\u884c\u6309\u79df\u6237\u9009\u62e9\u6a21\u578b', page);
    setMany('.panel-head h2', ['\u6a21\u578b\u670d\u52a1\u6e05\u5355', '\u65b0\u589e\u6a21\u578b\u670d\u52a1'], page);
    setMany('#modelTable th', ['\u540d\u79f0', '\u7c7b\u578b', '\u6a21\u578b', '\u72b6\u6001', '\u9ed8\u8ba4', '\u64cd\u4f5c'], page);
    const labels = qa('#modelForm label', page);
    ['\u914d\u7f6e\u540d\u79f0','\u670d\u52a1\u7c7b\u578b','\u670d\u52a1\u5730\u5740','\u6a21\u578b\u540d\u79f0','API Key'].forEach((value,index)=>setLeadingText(labels[index],value));
    set('#modelForm button', '\u4fdd\u5b58\u6a21\u578b\u914d\u7f6e', page);
  }

  function normalizeTenants() {
    const page = q('#tenants'); if (!page) return;
    set('.page-head h1', '\u79df\u6237\u4e0e\u7528\u6237', page);
    set('.page-head p', '\u7ba1\u7406\u72ec\u7acb\u8425\u9500\u8fd0\u8425\u7ec4\u7ec7\u3001\u8d26\u53f7\u3001\u89d2\u8272\u548c\u6570\u636e\u8fb9\u754c', page);
    setMany('.panel-head h2', ['\u79df\u6237\u6e05\u5355', '\u65b0\u5efa\u8fd0\u8425\u79df\u6237', '\u7528\u6237\u4e0e\u79df\u6237\u6388\u6743'], page);
    setMany('#tenantTable th', ['\u7f16\u7801', '\u79df\u6237\u540d\u79f0', '\u89d2\u8272'], page);
    setMany('#userTable th', ['\u7528\u6237', '\u7528\u6237\u540d', '\u79df\u6237\u6388\u6743', '\u5e73\u53f0\u89d2\u8272'], page);
    const labels = qa('#tenantForm label', page); setLeadingText(labels[0], '\u79df\u6237\u7f16\u7801'); setLeadingText(labels[1], '\u79df\u6237\u540d\u79f0');
    set('#tenantForm button', '\u521b\u5efa\u79df\u6237', page);
  }

  function normalizeCampaignTables() {
    setMany('#campaigns .table tr:first-child th', ['\u6d3b\u52a8\u7f16\u53f7','\u6d3b\u52a8\u540d\u79f0','\u5f53\u524d\u8282\u70b9','\u5f53\u524d\u7248\u672c','\u8d1f\u8d23\u4eba','\u6700\u8fd1\u53d8\u66f4','\u72b6\u6001','\u64cd\u4f5c']);
    qa('#campaigns .table tr').slice(1).forEach(row => { const cells = qa('td', row); if(cells[5] && /^\?+$/.test(cells[5].textContent)) cells[5].textContent='\u521a\u521a'; if(cells[7] && cells[7].textContent !== '\u8fdb\u5165\u6d3b\u52a8') cells[7].textContent='\u8fdb\u5165\u6d3b\u52a8'; });
    setMany('#overview .table tr:first-child th', ['\u6d3b\u52a8','\u5f53\u524d\u8282\u70b9','\u8d1f\u8d23\u4eba','\u7248\u672c','\u72b6\u6001','\u64cd\u4f5c']);
    qa('#overview .table tr').slice(1).forEach(row => { const cells=qa('td',row); if(cells[5] && cells[5].textContent !== '\u67e5\u770b') cells[5].textContent='\u67e5\u770b'; });
  }

  function normalizeWorkspace() {
    const modal=q('.production-modal'); if(!modal) return;
    set('.production-modal-head b','\u5207\u6362\u8425\u9500\u5de5\u4f5c\u7a7a\u95f4',modal);
    set('[data-close]','\u5173\u95ed',modal); set('[data-logout]','\u9000\u51fa\u767b\u5f55',modal);
    qa('.workspace-option em',modal).forEach(node=>{const value=node.closest('.active')?'\u5f53\u524d':'\u5207\u6362';if(node.textContent!==value)node.textContent=value;});
  }

  function normalize() { normalizeLogin(); normalizeNavigation(); normalizeImports(); normalizeModels(); normalizeTenants(); normalizeCampaignTables(); normalizeWorkspace(); }
  let scheduled = false;
  let normalizing = false;
  const observer = new MutationObserver(() => {
    if (normalizing || scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      normalizing = true;
      observer.disconnect();
      try { normalize(); } finally {
        normalizing = false;
        observer.observe(document.documentElement, { subtree: true, childList: true });
      }
    });
  });
  const runNormalize = () => {
    normalizing = true;
    observer.disconnect();
    try { normalize(); } finally {
      normalizing = false;
      observer.observe(document.documentElement, { subtree: true, childList: true });
    }
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',runNormalize);else runNormalize();
})();
