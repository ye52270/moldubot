/* ========================================
   MolduBot – Taskpane Messages Card DOM Helpers
   ======================================== */

(function initTaskpaneMessagesCardDom(global) {
  function create(options) {
    var byId = options.byId;

    function getChatArea() {
      return byId('chatArea');
    }

    function withChatArea(render) {
      var chatArea = getChatArea();
      if (!chatArea) return null;
      return render(chatArea);
    }

    function appendAssistantCard(chatArea, messageClassName, contentClassName, innerHtml) {
      chatArea.insertAdjacentHTML(
        'beforeend',
        '<div class="message assistant ' + String(messageClassName || '') + '">' +
          '<div class="msg-content ' + String(contentClassName || '') + '">' + String(innerHtml || '') + '</div>' +
        '</div>'
      );
    }

    function removeCardsBySelector(selector) {
      var chatArea = getChatArea();
      if (!chatArea || typeof chatArea.querySelectorAll !== 'function') return;
      var nodes = chatArea.querySelectorAll(String(selector || ''));
      nodes.forEach(function (node) {
        if (node && typeof node.remove === 'function') node.remove();
      });
    }

    function disableControls(selector) {
      var chatArea = getChatArea();
      if (!chatArea || typeof chatArea.querySelectorAll !== 'function') return;
      var controls = chatArea.querySelectorAll(String(selector || ''));
      controls.forEach(function (node) {
        if (node && typeof node === 'object') node.disabled = true;
      });
    }

    return {
      getChatArea: getChatArea,
      withChatArea: withChatArea,
      appendAssistantCard: appendAssistantCard,
      removeCardsBySelector: removeCardsBySelector,
      disableControls: disableControls,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesCardDom = api;
})(typeof window !== 'undefined' ? window : globalThis);
