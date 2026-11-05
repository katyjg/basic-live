/*!
 * Based on Color mode toggler for Bootstrap's docs (https://getbootstrap.com/)
 * Copyright 2011-2025 The Bootstrap Authors
 * Licensed under the Creative Commons Attribution 3.0 Unported License.
 */

(() => {
  'use strict'

  const getStoredTheme = () => localStorage.getItem('theme')
  const setStoredTheme = theme => localStorage.setItem('theme', theme)
  const getStoredAccent = () => localStorage.getItem('accent')
  const setStoredAccent = accent => localStorage.setItem('accent', accent)

  const getPreferredTheme = () => {
    const storedTheme = getStoredTheme()

    if (storedTheme) {
      return storedTheme
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }

  const getPreferredAccent = () => {
    const storedAccent = getStoredAccent()
    if (storedAccent) {
      return storedAccent
    }
    return 'user'
  }

  const setTheme = theme => {
    if (theme === 'auto') {
      theme = (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    }
    document.documentElement.setAttribute('data-bs-theme', theme)
  }
  const setAccent = accent => {
    document.documentElement.setAttribute('data-bl-accent', accent)
  }

  setTheme(getPreferredTheme())
  setAccent(getPreferredAccent())

  const showActiveTheme = (theme) => {
    const btnToActive = document.querySelector(`[data-bs-theme-value="${theme}"]`)
    if (btnToActive) {
      document.querySelectorAll('[data-bs-theme-value]').forEach(element => {
        element.classList.remove('selected')
        element.setAttribute('aria-pressed', 'false')
      })
      btnToActive.classList.add('selected')
      btnToActive.setAttribute('aria-pressed', 'true')
    }
  }

  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const storedTheme = getStoredTheme()
    if (storedTheme !== 'light' && storedTheme !== 'dark') {
      setTheme(getPreferredTheme())
    }
  })

  window.addEventListener('DOMContentLoaded', () => {
    showActiveTheme(getPreferredTheme())

    document.querySelectorAll('[data-bs-theme-value]')
      .forEach(toggle => {
        toggle.addEventListener('click', () => {
          const theme = toggle.getAttribute('data-bs-theme-value')
          setStoredTheme(theme)
          setTheme(theme)
          showActiveTheme(theme)
          console.log(theme)
        })
      })
  })
})()

// Ajax Progress
function setupAjaxProgress() {
    const $body = $("body");

    // Handle Spinner for all ajax calls
    $(document).ajaxStart(function (xhr) {
        $(document).data('xhrProgress', 0);
        $(document).data('xhrCount', 0);
        $(document).data('xhrPercent', 0);
        $body.css({
            '--bl-progress-percent': 0,
            '--bl-progress-opacity': 1,
        });
    }).ajaxStop(function () {
        setTimeout(function () {
            $("body").css({
                '--bl-progress-opacity': 0
            });
        }, 500);
    });

    // Handle XHR Progress
    let origOpen = XMLHttpRequest.prototype.open;
    $(document).data('xhrCount', $(document).data('xhrCount') || 0);
    $(document).data('xhrProgress', $(document).data('xhrProgress') || 0);
    $(document).data('xhrPercent', $(document).data('xhrPercent') || 0);

    XMLHttpRequest.prototype.open = function () {
        $(document).data('xhrCount', $(document).data('xhrCount') + 1);
        this.addEventListener('load', function () {
            $(document).data('xhrProgress', $(document).data('xhrProgress') + 1);
            $(document).data('xhrCount', $(document).data('xhrCount') - 1);
            if ($(document).data('xhrCount') === 0) {
                $(document).data('xhrPercent', 100)
                $("body").css({
                    '--bl-progress-percent': $(document).data('xhrPercent'),
                });
            } else {
                let percentComplete = 100 * $(document).data('xhrProgress') / $(document).data('xhrCount');
                $(document).data('xhrPercent', Math.max($(document).data('xhrPercent'), percentComplete));
                $("body").css({
                    '--bl-progress-percent': $(document).data('xhrPercent'),
                });
            }
        });
        origOpen.apply(this, arguments);
    };
}