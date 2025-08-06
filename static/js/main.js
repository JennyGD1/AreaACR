// static/js/main.js

// 1. Preloader 
window.addEventListener('load', () => {
  const preloader = document.getElementById('preloader');
  if (preloader) preloader.classList.add('hidden');
});

// 2. Scroll 
const scrollThumb = document.getElementById('scrollThumb');
window.addEventListener('scroll', () => {
  const scrollTop = window.scrollY;
  const docHeight = document.documentElement.scrollHeight - window.innerHeight;
  scrollThumb.style.height = `${(scrollTop / docHeight) * 100}%`;
});

// 3. Ripple effect 
document.body.addEventListener("click", (e) => {
  const ripple = document.createElement("div");
  ripple.className = "ripple";
  Object.assign(ripple.style, {
    left: `${e.clientX}px`,
    top: `${e.clientY}px`
  });
  document.body.appendChild(ripple);
  setTimeout(() => ripple.remove(), 600);
});

// 4. Upload Form 
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('upload-form');
  if (!form) return; 

  const fileInput = form.querySelector('input[type="file"]');
  const fileNameText = document.getElementById('file-name');
  const processBtn = form.querySelector('button[type="submit"]');
  const feedback = document.getElementById('upload-feedback');

  // Atualiza nome do arquivo selecionado
  fileInput?.addEventListener('change', function() {
    fileNameText.textContent = this.files[0]?.name || 'Nenhum arquivo selecionado';
  });

  // Processamento do formulário
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!fileInput.files[0]) {
      showFeedback('Selecione um arquivo PDF', 'error');
      return;
    }

    showFeedback('Processando...', 'loading');
    if (processBtn) processBtn.disabled = true;

    try {
      const formData = new FormData(form);
      const response = await fetch('/upload', {
        method: 'POST',
        body: formData
      });

      if (response.redirected) {
        window.location.href = response.url; // Redireciona para /analise
      } else {
        const result = await response.json();
        showFeedback(result.message || 'Processamento concluído', result.success ? 'success' : 'error');
      }
    } catch (error) {
      showFeedback(`Erro: ${error.message}`, 'error');
    } finally {
      if (processBtn) processBtn.disabled = false;
    }
  });

  function showFeedback(message, type) {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.className = `feedback ${type}`; // Adicione classes CSS para cada tipo
  }
});
