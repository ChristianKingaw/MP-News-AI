/**
 * Mountain Province Disaster Alert — Admin Dashboard JavaScript
 * Vanilla JS — no framework dependencies
 */

(function () {
  'use strict';

  /* ==========================================================
     Utility helpers
     ========================================================== */

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => Array.from((ctx || document).querySelectorAll(sel));

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  async function apiFetch(url, options = {}) {
    const token = getAccessToken();
    const res = await fetch(url, {
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: 'Bearer ' + token } : {}),
        ...options.headers,
      },
      ...options,
    });

    if (res.status === 401) {
      window.location.href = '/admin/login';
      throw new Error('Unauthorized');
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }

    return res.json();
  }

  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function getAccessToken() {
    const match = document.cookie.match(/(?:^|;\s*)access_token=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  function isLoggedIn() {
    return !!getAccessToken();
  }

  /* ==========================================================
     Toast notifications
     ========================================================== */

  const Toast = {
    _container: null,

    _ensureContainer() {
      if (!this._container) {
        this._container = document.createElement('div');
        this._container.className = 'toast-container';
        this._container.setAttribute('role', 'status');
        this._container.setAttribute('aria-live', 'polite');
        this._container.setAttribute('aria-atomic', 'true');
        document.body.appendChild(this._container);
      }
      return this._container;
    },

    show(message, type = 'info', duration = 4000) {
      const container = this._ensureContainer();
      const toast = document.createElement('div');
      toast.className = 'toast toast--' + type;
      toast.setAttribute('role', 'alert');
      toast.innerHTML =
        '<span>' +
        escapeHtml(message) +
        '</span>' +
        '<button class="toast-close" aria-label="Dismiss">&times;</button>';

      const closeBtn = $('.toast-close', toast);
      closeBtn.addEventListener('click', () => this._dismiss(toast));

      container.appendChild(toast);

      if (duration > 0) {
        setTimeout(() => this._dismiss(toast), duration);
      }
    },

    _dismiss(toast) {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(16px)';
      toast.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 200);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 6000); },
    info(msg) { this.show(msg, 'info'); },
  };

  /* ==========================================================
     Confirm Dialog
     ========================================================== */

  function confirmDialog({ title, message, confirmLabel = 'Confirm', variant = 'primary' }) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'dialog-overlay';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.setAttribute('aria-labelledby', 'dialog-title');

      const btnClass = variant === 'danger' ? 'btn-danger' : 'btn-primary';

      overlay.innerHTML =
        '<div class="dialog">' +
        '<h2 class="dialog-title" id="dialog-title">' + escapeHtml(title) + '</h2>' +
        '<p class="dialog-body">' + escapeHtml(message) + '</p>' +
        '<div class="dialog-actions">' +
        '<button class="btn btn-outline" data-action="cancel">Cancel</button>' +
        '<button class="btn ' + btnClass + '" data-action="confirm" autofocus>' + escapeHtml(confirmLabel) + '</button>' +
        '</div>' +
        '</div>';

      document.body.appendChild(overlay);

      const confirmBtn = $('[data-action="confirm"]', overlay);
      const cancelBtn = $('[data-action="cancel"]', overlay);

      function close(result) {
        overlay.style.opacity = '0';
        overlay.style.transition = 'opacity 0.15s ease';
        setTimeout(() => {
          if (overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
          }
          resolve(result);
        }, 150);
      }

      confirmBtn.addEventListener('click', () => close(true));
      cancelBtn.addEventListener('click', () => close(false));

      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close(false);
      });

      document.addEventListener('keydown', function onKey(e) {
        if (e.key === 'Escape') {
          close(false);
          document.removeEventListener('keydown', onKey);
        }
      });

      confirmBtn.focus();
    });
  }

  /* ==========================================================
     Mobile Navigation Toggle
     ========================================================== */

  function initMobileNav() {
    const toggle = $('#nav-toggle');
    const nav = $('#navbar-nav');

    if (!toggle || !nav) return;

    toggle.addEventListener('click', () => {
      const isOpen = nav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(isOpen));
    });

    document.addEventListener('click', (e) => {
      if (!toggle.contains(e.target) && !nav.contains(e.target)) {
        nav.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && nav.classList.contains('is-open')) {
        nav.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.focus();
      }
    });
  }

  /* ==========================================================
     Logout
     ========================================================== */

  function initLogout() {
    const btn = $('#btn-logout');
    if (!btn) return;

    btn.addEventListener('click', () => {
      document.cookie =
        'access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC; SameSite=Strict';
      window.location.href = '/admin/login';
    });
  }

  /* ==========================================================
     Post Actions (Approve / Reject)
     ========================================================== */

  function initPostActions() {
    $$('[data-action="approve-post"]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const postId = btn.getAttribute('data-post-id');
        const row = btn.closest('tr');

        const confirmed = await confirmDialog({
          title: 'Approve Post',
          message: 'This post will be approved and queued for publishing.',
          confirmLabel: 'Approve',
          variant: 'primary',
        });

        if (!confirmed) return;

        btn.classList.add('btn-loading');
        btn.disabled = true;

        try {
          await apiFetch('/posts/' + postId + '/approve', { method: 'POST' });
          updatePostRow(row, 'approved');
          Toast.success('Post approved successfully.');
        } catch (err) {
          Toast.error(err.message);
        } finally {
          btn.classList.remove('btn-loading');
          btn.disabled = false;
        }
      });
    });

    $$('[data-action="reject-post"]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const postId = btn.getAttribute('data-post-id');
        const row = btn.closest('tr');

        const confirmed = await confirmDialog({
          title: 'Reject Post',
          message: 'This post will be rejected and will not be published.',
          confirmLabel: 'Reject',
          variant: 'danger',
        });

        if (!confirmed) return;

        btn.classList.add('btn-loading');
        btn.disabled = true;

        try {
          await apiFetch('/posts/' + postId + '/reject', { method: 'POST' });
          updatePostRow(row, 'rejected');
          Toast.success('Post rejected.');
        } catch (err) {
          Toast.error(err.message);
        } finally {
          btn.classList.remove('btn-loading');
          btn.disabled = false;
        }
      });
    });
  }

  function updatePostRow(row, newStatus) {
    const statusCell = row.querySelector('[data-label="Status"] .badge');
    if (statusCell) {
      const badgeMap = {
        approved: 'badge-primary',
        rejected: 'badge-danger',
      };
      const labelMap = {
        approved: 'APPROVED',
        rejected: 'REJECTED',
      };
      statusCell.className = 'badge ' + (badgeMap[newStatus] || 'badge-neutral');
      statusCell.textContent = labelMap[newStatus] || newStatus;
    }

    const actionsCell = row.querySelector('.cell-actions');
    if (actionsCell) {
      actionsCell.innerHTML =
        '<span class="text-muted text-sm">' +
        (newStatus === 'approved' ? 'Approved' : 'Rejected') +
        '</span>';
    }
  }

  /* ==========================================================
     Login Form
     ========================================================== */

  function initLoginForm() {
    const form = $('#login-form');
    if (!form) return;

    const errorEl = $('#login-error');
    const submitBtn = $('#login-submit');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const username = $('#login-username').value.trim();
      const password = $('#login-password').value;

      if (!username || !password) {
        errorEl.textContent = 'Please enter both username and password.';
        errorEl.classList.add('is-visible');
        return;
      }

      errorEl.classList.remove('is-visible');
      submitBtn.classList.add('btn-loading');
      submitBtn.disabled = true;

      try {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const res = await fetch('/auth/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: formData.toString(),
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || 'Invalid username or password.');
        }

        const data = await res.json();
        const maxAge = 60 * 60 * 24; // 24 hours
        document.cookie =
          'access_token=' +
          encodeURIComponent(data.access_token) +
          '; path=/; max-age=' +
          maxAge +
          '; SameSite=Strict';

        const redirect = new URLSearchParams(window.location.search).get('next') || '/admin';
        window.location.href = redirect;
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.add('is-visible');
        $('#login-password').value = '';
        $('#login-password').focus();
      } finally {
        submitBtn.classList.remove('btn-loading');
        submitBtn.disabled = false;
      }
    });
  }

  /* ==========================================================
     Init
     ========================================================== */

  document.addEventListener('DOMContentLoaded', () => {
    initMobileNav();
    initLogout();
    initPostActions();
    initLoginForm();
  });
})();