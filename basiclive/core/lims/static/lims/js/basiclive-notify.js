class Notify {
  static DEFAULTS = {
    theme: 'light',          // 'light' or 'dark'
    color: 'light',          // Bootstrap bg color: 'light', 'primary', 'secondary', 'success', 'danger', 'warning', 'info'
    title: '',               // optional header title
    message: 'This is a toast message',
    delay: 3000,             // delay in milliseconds
    autohide: true,          // automatically hide the toast after delay
    animation: true,         // apply Bootstrap fade transition
    position: 'bottom-0 end-0',
    containerId: 'toast-container',
  };

  constructor(defaults = {}) {
    this.defaults = { ...Notify.DEFAULTS, ...defaults };
  }

  createToastElement(html) {
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    return template.content.firstElementChild;
  }

  #getContainer() {
    let container = document.getElementById(this.defaults.containerId);
    if (!container) {
      container = document.createElement('div');
      container.id = this.defaults.containerId;
      container.className = `toast-container position-fixed ${this.defaults.position} p-3`;
      document.body.appendChild(container);
    }
    return container;
  }

  #resolveOptions(params = {}, preset = {}) {
    const normalized = typeof params === 'string' ? { message: params } : params;
    return { ...this.defaults, ...preset, ...normalized };
  }

  show(params = {}) {
    const options = this.#resolveOptions(params);
    const toastContainer = this.#getContainer();
    const colorClass = options.color ? `text-bg-${options.color}` : '';

    let closeBtn =
      '<button type="button" class="btn-close ms-auto me-1" data-bs-dismiss="toast" aria-label="Close"></button>';
    let titleHtml = '';

    if (options.title) {
      titleHtml = `
        <div class="toast-header d-flex flex-row bg-transparent">
          <strong>${options.title}</strong>${closeBtn}
        </div>
      `;
      closeBtn = '';
    }

    const html = `
      <div data-bs-theme="${options.theme}"
        class="toast d-flex flex-column align-items-stretch ${colorClass} border-0"
        role="alert" aria-live="assertive" aria-atomic="true">
        ${titleHtml}
        <div class="toast-body d-flex align-items-center">
          <div>${options.message}</div>${closeBtn}
        </div>
      </div>
    `;

    const toastElement = this.createToastElement(html);
    toastContainer.appendChild(toastElement);

    const toast = new bootstrap.Toast(toastElement, {
      delay: options.delay,
      autohide: options.autohide,
      animation: options.animation,
    });

    toastElement.addEventListener(
      'hidden.bs.toast',
      () => {
        toast.dispose();
        toastElement.remove();
      },
      { once: true }
    );

    toast.show();
    return toast;
  }

  error(params = {}) {
    return this.show(
      this.#resolveOptions(params, {
        theme: 'dark',
        color: 'danger',
        textColor: 'white',
      })
    );
  }

  success(params = {}) {
    return this.show(
      this.#resolveOptions(params, {
        theme: 'dark',
        color: 'success',
        textColor: 'white',
      })
    );
  }

  info(params = {}) {
    return this.show(
      this.#resolveOptions(params, {
        theme: 'dark',
        color: 'info',
        textColor: 'white',
      })
    );
  }

  warning(params = {}) {
    return this.show(
      this.#resolveOptions(params, {
        theme: 'dark',
        color: 'warning',
        textColor: 'white',
      })
    );
  }
}