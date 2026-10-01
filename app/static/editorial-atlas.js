(function () {
  function dataSlugFromImage(img) {
    const match = img.getAttribute('src').match(/\/draft\/img\/([a-z0-9-]+)\.svg$/);
    return match ? match[1] : null;
  }

  document.querySelectorAll('[data-atlas-story] img').forEach(function (img) {
    const slug = dataSlugFromImage(img);
    if (!slug) return;
    img.loading = 'lazy';
    const tools = document.createElement('div');
    tools.className = 'chart-tools';
    tools.innerHTML = '<a href="/draft/data/' + slug + '">Explore data & method</a>' +
      '<button type="button" data-copy-analysis="' + slug + '">Copy analysis link</button>';
    const paragraph = img.closest('p');
    (paragraph || img).insertAdjacentElement('afterend', tools);
  });

  document.addEventListener('click', function (event) {
    const viewButton = event.target.closest('[data-view-button]');
    if (viewButton) {
      const view = viewButton.getAttribute('data-view-button');
      document.querySelectorAll('[data-view-button]').forEach(function (button) {
        button.setAttribute('aria-pressed', String(button === viewButton));
      });
      document.querySelectorAll('[data-view-panel]').forEach(function (panel) {
        panel.hidden = panel.getAttribute('data-view-panel') !== view;
      });
    }

    const shareSlug = event.target.closest('[data-copy-analysis]');
    const copyPage = event.target.closest('[data-copy-link]');
    if (shareSlug || copyPage) {
      const url = shareSlug
        ? window.location.origin + '/draft/data/' + shareSlug.getAttribute('data-copy-analysis')
        : window.location.href.split('#')[0];
      navigator.clipboard.writeText(url).then(function () {
        const status = document.querySelector('[data-copy-status]');
        if (status) status.textContent = 'Link copied';
        else event.target.textContent = 'Copied';
      }).catch(function () {
        window.prompt('Copy this link', url);
      });
    }
  });
})();
