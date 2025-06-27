    // Código para esconder o Preloader

   window.addEventListener('load', () => {

     console.log("Evento LOAD disparado!"); // Log para depuração

     const preloader = document.getElementById('preloader');

     if (preloader) {

       console.log("Preloader encontrado, adicionando classe hidden..."); // Log para depuração

       preloader.classList.add('hidden');

     } else {

       console.error("Elemento #preloader NÃO encontrado!"); // Log de erro

     }

   });
  // Scroll
  const scrollThumb = document.getElementById('scrollThumb');
  window.addEventListener('scroll', () => {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    scrollThumb.style.height = `${(scrollTop / docHeight) * 100}%`;
  });

  // Ripple effect
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

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('upload-form');
    
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const fileInput = document.querySelector('#upload-form input[type="file"]');
            const feedback = document.getElementById('upload-feedback');
            
            if (!fileInput.files[0]) {
                feedback.textContent = 'Selecione um arquivo PDF';
                feedback.style.color = 'red';
                return;
            }

            feedback.textContent = 'Processando...';
            feedback.style.color = 'blue';

            try {
                const formData = new FormData(form);
                
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                if (response.redirected) {
                    window.location.href = response.url;
                } else {
                    const data = await response.json();
                    if (data.error) {
                        feedback.textContent = data.error;
                        feedback.style.color = 'red';
                    }
                }
            } catch (error) {
                feedback.textContent = 'Erro: ' + error.message;
                feedback.style.color = 'red';
            }
        });
    }
});
