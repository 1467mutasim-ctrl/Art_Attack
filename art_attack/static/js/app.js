document.addEventListener('DOMContentLoaded', () => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  document.querySelectorAll('form[method="post"], form[method="POST"]').forEach((form) => {
    if (token && !form.querySelector('input[name="csrf_token"]')) {
      const input = document.createElement('input');
      input.type = 'hidden'; input.name = 'csrf_token'; input.value = token;
      form.prepend(input);
    }
  });

  document.querySelector('[data-menu-toggle]')?.addEventListener('click', () => {
    document.querySelector('[data-menu]')?.classList.toggle('open');
  });

  document.querySelectorAll('[data-confirm]').forEach((button) => {
    button.addEventListener('click', (event) => {
      if (!window.confirm(button.dataset.confirm || 'Continue?')) event.preventDefault();
    });
  });

  document.querySelectorAll('[data-modal-open]').forEach((button) => {
    button.addEventListener('click', () => document.querySelector(button.dataset.modalOpen)?.classList.add('open'));
  });
  document.querySelectorAll('[data-modal-close]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.modal')?.classList.remove('open'));
  });
  document.querySelectorAll('.modal').forEach((modal) => {
    modal.addEventListener('click', (event) => { if (event.target === modal) modal.classList.remove('open'); });
  });

  document.querySelectorAll('[data-flash-close]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });
  window.setTimeout(() => document.querySelectorAll('.flash').forEach((node) => node.remove()), 6500);

  const previewInput = document.querySelector('[data-image-input]');
  const preview = document.querySelector('[data-image-preview]');
  previewInput?.addEventListener('change', () => {
    const file = previewInput.files?.[0];
    if (file && preview) { preview.src = URL.createObjectURL(file); preview.hidden = false; }
  });
});

