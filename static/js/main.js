// AI Research Lab - Client Scripts

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add('open');
    const firstInput = modal.querySelector('input:not([type=hidden]), textarea');
    if (firstInput) firstInput.focus();
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('open');
  }
}

// Close modal on backdrop click or ESC
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop.open').forEach(m => m.classList.remove('open'));
  }
});

document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.classList.remove('open');
  }
});
