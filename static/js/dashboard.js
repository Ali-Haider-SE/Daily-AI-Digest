/* Interactive Dashboard Client Logic (Search, Filter, HCI Feedback) */
/* eslint-disable no-console */

document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('search-input');
  const searchClear = document.getElementById('search-clear');
  const credFilter = document.getElementById('cred-filter');
  const remoteFilter = document.getElementById('remote-filter');
  const noneFound = document.getElementById('search-none-found');

  /* ─── Toast Notification System ─── */
  function showToast(message, type = 'info', duration = 4500) {
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.id = 'toast-container';
      toastContainer.style.cssText = [
        'position:fixed', 'bottom:24px', 'right:24px', 'z-index:9999',
        'display:flex', 'flex-direction:column', 'gap:10px',
        'max-width:360px', 'pointer-events:none'
      ].join(';');
      document.body.appendChild(toastContainer);
    }

    const colors = {
      info:    { bg: '#1e40af', border: '#3b82f6', icon: 'ℹ️' },
      success: { bg: '#065f46', border: '#10b981', icon: '✅' },
      warning: { bg: '#92400e', border: '#f59e0b', icon: '⚠️' },
      error:   { bg: '#7f1d1d', border: '#ef4444', icon: '❌' }
    };
    const c = colors[type] || colors.info;

    const toast = document.createElement('div');
    toast.style.cssText = [
      `background:${c.bg}`, `border:1px solid ${c.border}`,
      'color:#f1f5f9', 'padding:14px 16px', 'border-radius:10px',
      'font-size:13px', 'line-height:1.5', 'pointer-events:auto',
      'box-shadow:0 8px 24px rgba(0,0,0,0.5)',
      'animation:slideIn 0.25s ease', 'cursor:pointer'
    ].join(';');
    toast.innerHTML = `<span style="margin-right:8px">${c.icon}</span>${message}`;
    toast.title = 'Click to dismiss';
    toast.addEventListener('click', () => toast.remove());

    // Inject animation if not already done
    if (!document.getElementById('toast-anim-style')) {
      const s = document.createElement('style');
      s.id = 'toast-anim-style';
      s.textContent = '@keyframes slideIn{from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:translateX(0)}}';
      document.head.appendChild(s);
    }

    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.4s';
      setTimeout(() => toast.remove(), 400);
    }, duration);
  }

  /* ─── Client-side Search & Filter ─── */
  function applyFilters() {
    const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
    const credVal = credFilter ? credFilter.value : 'all';
    const remoteVal = remoteFilter ? remoteFilter.value : 'all';
    let anyVisible = false;

    document.querySelectorAll('.intel-card:not(.job-card)').forEach(card => {
      const title = card.getAttribute('data-title') || '';
      const source = card.getAttribute('data-source') || '';
      const cred = card.getAttribute('data-credibility') || '';
      const textContent = card.innerText.toLowerCase();

      const matchesSearch = !query || textContent.includes(query) || title.includes(query) || source.includes(query);
      const matchesCred = credVal === 'all' || cred === credVal;

      if (matchesSearch && matchesCred) {
        card.classList.remove('hidden');
        anyVisible = true;
      } else {
        card.classList.add('hidden');
      }
    });

    document.querySelectorAll('.job-card').forEach(card => {
      const title = card.getAttribute('data-title') || '';
      const company = card.getAttribute('data-company') || '';
      const remote = card.getAttribute('data-remote') || '';
      const textContent = card.innerText.toLowerCase();

      const matchesSearch = !query || textContent.includes(query) || title.includes(query) || company.includes(query);
      const matchesRemote = remoteVal === 'all' || remote === remoteVal;

      if (matchesSearch && matchesRemote) {
        card.classList.remove('hidden');
        anyVisible = true;
      } else {
        card.classList.add('hidden');
      }
    });

    if (noneFound) {
      noneFound.classList.toggle('hidden', anyVisible);
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      if (searchClear) searchClear.classList.toggle('hidden', !searchInput.value);
      applyFilters();
    });
  }
  if (searchClear) {
    searchClear.addEventListener('click', () => {
      searchInput.value = '';
      searchClear.classList.add('hidden');
      applyFilters();
      searchInput.focus();
    });
  }
  if (credFilter) credFilter.addEventListener('change', applyFilters);
  if (remoteFilter) remoteFilter.addEventListener('change', applyFilters);

  /* ─── Highlight item from URL hash/query ─── */
  const urlParams = new URLSearchParams(window.location.search);
  const targetItem = urlParams.get('item');
  if (targetItem) {
    const targetCard = document.querySelector(`[data-hash="${targetItem}"]`);
    if (targetCard) {
      targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
      targetCard.style.outline = '2px solid #38bdf8';
      targetCard.style.boxShadow = '0 0 20px rgba(56, 189, 248, 0.5)';
    }
  }
});
