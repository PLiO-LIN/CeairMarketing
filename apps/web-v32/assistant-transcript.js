/* Text and validated A2UI surfaces share one ordered conversation stream. */
(function () {
  'use strict';
  window.createAssistantTranscript = function (host, renderer, format) {
    let active = null, text = '', lastText = '';
    function round() { if (active) { format(active, text); lastText = text; } active = null; text = ''; }
    function token(delta) {
      if (!active) { active = document.createElement('div'); active.className = 'assistant-answer assistant-inline-answer'; host.append(active); }
      text += delta; active.textContent = text;
    }
    function ui(message) { round(); renderer.accept(message); }
    function finish(answer) { if (!active && (!answer || answer === lastText)) return; if (!active) token(answer); else { text = answer; } format(active, text); }
    function restore(timeline, messages, answer) {
      timeline.forEach(item => { if (item.type === 'round') round(); if (item.type === 'text') token(item.text); if (item.type === 'ui' && messages[item.index]) ui(messages[item.index]); });
      finish(answer);
    }
    return { round, token, ui, finish, restore };
  };
})();
