(function () {
  // widget.js'in kendi <script> etiketi (defer ile calisirken currentScript gecerli).
  const CURRENT_SCRIPT = document.currentScript;

  function initBFLWidget() {
    // 1. Stil Kurallarını Enjekte Et
    const style = document.createElement('style');
    style.innerHTML = `
      .bf-widget-container {
        position: fixed;
        bottom: 20px;
        left: 20px;
        z-index: 999999;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .bf-widget-button {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: #537286;
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s, background-color 0.2s;
      }
      .bf-widget-button:hover { 
        background: #425b6b;
        transform: scale(1.05); 
      }
      .bf-widget-button svg { transition: transform 0.3s; }
      
      .bf-iframe-container {
        position: fixed;
        bottom: 90px;
        left: 20px;

        width: 400px;
        height: 600px;

        border-radius: 16px;
        box-shadow: 0 5px 40px rgba(0,0,0,0.16);
        overflow: hidden;

        opacity: 0;
        pointer-events: none;
        z-index: 999998;

        /*
        * Sol alt köşeden küçülsün.
        * Değer JavaScript tarafından hesaplanacak.
        */
        --bf-widget-scale: 1;
        transform-origin: left bottom;
        transform:
          translateY(20px)
          scale(var(--bf-widget-scale));

        transition:
          opacity 0.3s,
          transform 0.3s;
      }
      .bf-iframe-container.open {
        opacity: 1;
        pointer-events: auto;

        transform:
          translateY(0)
          scale(var(--bf-widget-scale));
      }
      .bf-chat-iframe {
        width: 100%;
        height: 100%;
        border: none;
      }
      @media (max-width: 480px) {
      .bf-widget-container {
        bottom: 12px;
        left: 12px;
      }

      .bf-iframe-container {
        bottom: 82px;
        left: 12px;
      }
    }
    `;
    document.head.appendChild(style);

    // Robot İkonu Tanımı
    const robotIconHtml = `
      <svg id="bf-icon-open" viewBox="0 0 24 24" style="width: 32px; height: 32px;">
        <circle cx="12" cy="3" r="1.5" fill="#E23E3E"/>
        <line x1="12" y1="4.5" x2="12" y2="7" stroke="#fff" stroke-width="1.8"/>
        <rect x="4" y="7" width="16" height="11" rx="4" fill="none" stroke="#fff" stroke-width="2"/>
        <rect x="1.5" y="10" width="2" height="5" rx="1" fill="#fff"/>
        <rect x="20.5" y="10" width="2" height="5" rx="1" fill="#fff"/>
        <circle cx="9" cy="12.5" r="1.5" fill="#E23E3E"/>
        <circle cx="15" cy="12.5" r="1.5" fill="#E23E3E"/>
        <path d="M10 15.5 h4" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    `;

    // Kapatma (X) İkonu Tanımı
    const closeIconHtml = `
      <svg viewBox="0 0 24 24" style="width: 28px; height: 28px;">
        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" fill="#fff"/>
      </svg>
    `;

    // 2. HTML Yapısını Oluştur
    const container = document.createElement('div');
    container.className = 'bf-widget-container';

    const iframeContainer = document.createElement('div');
    iframeContainer.className = 'bf-iframe-container';

    function updateWidgetScale() {
      const originalWidth = 400;
      const originalHeight = 600;

      /*
      * Ekranın kenarlarında bırakılacak alanlar:
      * - yatayda toplam 40px
      * - dikeyde chatbot butonu ve boşluklar için 130px
      */
      const availableWidth = Math.max(window.innerWidth - 40, 240);
      const availableHeight = Math.max(window.innerHeight - 130, 360);

      const widthScale = availableWidth / originalWidth;
      const heightScale = availableHeight / originalHeight;

      /*
      * 1'in üzerine çıkmaz; sadece gerektiğinde küçülür.
      * Genişlik ve yükseklikten küçük olan değer seçildiği için
      * 400×600 oranı korunur.
      */
      const scale = Math.min(
        1,
        widthScale,
        heightScale
      );

      iframeContainer.style.setProperty(
        '--bf-widget-scale',
        scale.toFixed(4)
      );
    }

    updateWidgetScale();

    window.addEventListener(
      'resize',
      updateWidgetScale,
      { passive: true }
    );

    // Tenant + API origin'i kendi <script> etiketimizden turet.
    // Ornek gomme:
    //   <script src="https://api.host/static/widget.js" data-tenant="kfz" defer></script>
    const ds = (CURRENT_SCRIPT && CURRENT_SCRIPT.dataset) || {};
    const tenant = ds.tenant || 'bfl';
    const scriptSrc = (CURRENT_SCRIPT && CURRENT_SCRIPT.src) || '';

    let chatHtmlUrl = '/static/chat.html';   // ayni-domain fallback
    let apiOrigin = '';
    try {
      const u = new URL(scriptSrc);
      apiOrigin = u.origin;                                  // ornek: https://api.host
      chatHtmlUrl = scriptSrc.replace(/widget\.js(\?.*)?$/, 'chat.html');
    } catch (e) { /* scriptSrc parse edilemezse ayni-domain kullan */ }

    // data-api-base verildiyse onu, yoksa script'in origin'ini kullan.
    const apiBase = (ds.apiBase || apiOrigin || '').replace(/\/+$/, '');

    const params = new URLSearchParams({ tenant_id: tenant });
    if (apiBase) params.set('api_base', apiBase);

    const iframeSrc = `${chatHtmlUrl}?${params.toString()}`;
    iframeContainer.innerHTML =
      `<iframe src="${iframeSrc}" class="bf-chat-iframe"></iframe>`;

    const button = document.createElement('div');
    button.className = 'bf-widget-button';
    button.innerHTML = robotIconHtml;

    container.appendChild(iframeContainer);
    container.appendChild(button);
    document.body.appendChild(container);

    // 3. Tıklama Olayını Yönet
    let isOpen = false;
    button.addEventListener('click', () => {
      isOpen = !isOpen;
      if (isOpen) {
        iframeContainer.classList.add('open');
        button.innerHTML = closeIconHtml;
      } else {
        iframeContainer.classList.remove('open');
        button.innerHTML = robotIconHtml;
      }
    });
  }

  // DOM kontrolü ve güvenli yükleme
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBFLWidget);
  } else {
    initBFLWidget();
  }
})();