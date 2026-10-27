(function(){
  "use strict";
  if (window.__BFL_WIDGET__) return; window.__BFL_WIDGET__ = true;

  // --- kendi <script> etiketinden tenant + kaynak origin türet ---
  var me = document.currentScript;
  if (!me) { var ss = document.getElementsByTagName('script'); me = ss[ss.length-1]; }
  var TENANT = (me && me.getAttribute('data-tenant')) || 'bfl';
  var SIDE   = ((me && me.getAttribute('data-side')) || 'left').toLowerCase(); // left | right
  var srcUrl;
  try { srcUrl = new URL(me.src, location.href); } catch(e){ srcUrl = null; }
  var ORIGIN = srcUrl ? srcUrl.origin : location.origin;
  // data-api-base verilmişse onu, yoksa script'in origin'ini kullan
  var API_BASE = ((me && me.getAttribute('data-api-base')) || ORIGIN).replace(/\/+$/,'');
  // chat.html, widget.js ile aynı klasörde: .../widget.js -> .../chat.html
  var CHAT_BASE = srcUrl ? srcUrl.href.replace(/widget\.js(\?.*)?$/, 'chat.html') : '/static/chat.html';
  var CHAT_URL = CHAT_BASE + '?tenant_id=' + encodeURIComponent(TENANT) +
                 '&api_base=' + encodeURIComponent(API_BASE);
  var CONFIG_URL = API_BASE + '/api/' + encodeURIComponent(TENANT) + '/config';

  var POS = (SIDE === 'right') ? 'right:26px;' : 'left:26px;';
  var CHATPOS = (SIDE === 'right') ? 'right:26px;' : 'left:26px;';

  var MASCOT = '<div class="bflw-bot3d">' +
    '<div class="bflw-ant-stick"></div><div class="bflw-ant-ball"></div>' +
    '<div class="bflw-ear l"></div><div class="bflw-ear r"></div>' +
    '<div class="bflw-head"></div>' +
    '<div class="bflw-face"><div class="bflw-eye l"></div><div class="bflw-eye r"></div><div class="bflw-smile"></div></div>' +
    '<div class="bflw-neck"></div><div class="bflw-torso"></div><div class="bflw-chest"></div>' +
    '<div class="bflw-arm l"><div class="bflw-fist"></div></div>' +
    '<div class="bflw-arm r"><div class="bflw-fist"></div>' +
      '<div class="bflw-palm"><i></i><i></i><i></i><i></i><b></b></div></div>' +
    '</div>';

  var CSS = [
  '.bflw-root{--navy:#092e62;--blue:#0968d8;--cyan:#66e6ff;position:fixed;bottom:24px;'+POS+'z-index:2147483000;}',
  '.bflw-launcher{position:relative;width:58px;height:66px;background:none;border:0;padding:0;cursor:pointer;'+
    '-webkit-tap-highlight-color:transparent;animation:bflw-float 5s ease-in-out infinite;transition:opacity .25s;}',
  '.bflw-launcher:focus{outline:0;}',
  '.bflw-root.open .bflw-launcher{opacity:0;animation:none;transform:scale(.6);pointer-events:none;}',

  /* hello nudge */
  '.bflw-hello{position:absolute;bottom:30px;'+ (SIDE==='right'?'right:58px;':'left:58px;') +'z-index:30;'+
    'background:#fff;color:#223247;font:600 12.5px/1.3 Inter,-apple-system,Segoe UI,sans-serif;'+
    'padding:9px 13px;border-radius:'+(SIDE==='right'?'14px 14px 4px 14px':'14px 14px 14px 4px')+';'+
    'box-shadow:0 10px 26px rgba(9,46,98,.22);white-space:nowrap;opacity:0;transform:translateY(6px) scale(.96);'+
    'transition:.28s cubic-bezier(.2,.8,.2,1);pointer-events:none;}',
  '.bflw-root.nudge .bflw-hello,.bflw-launcher:hover .bflw-hello{opacity:1;transform:translateY(0) scale(1);}',
  '.bflw-root.open .bflw-hello{opacity:0!important;}',

  /* ---- 3D CSS maskot ---- */
  '.bflw-bot3d{position:absolute;left:2px;bottom:0;width:104px;height:116px;transform-origin:0% 100%;transition:transform .3s;transform:scale(.50);}',
  '.bflw-launcher:hover .bflw-bot3d{transform:scale(.50) translateY(-3px) rotate(-2deg);}',
  '.bflw-ant-stick{position:absolute;z-index:2;left:49px;top:3px;width:7px;height:18px;border-radius:7px;background:linear-gradient(90deg,#083d86,#1681eb,#073675);}',
  '.bflw-ant-ball{position:absolute;z-index:3;left:43px;top:-7px;width:20px;height:20px;border-radius:50%;background:radial-gradient(circle at 34% 28%,#8feeff 0 7%,#1496f4 25%,#0069d9 62%,#064496 100%);box-shadow:inset -2px -3px 4px rgba(0,31,91,.28),0 2px 5px rgba(0,64,130,.25);animation:bflw-glow 3s ease-in-out infinite;}',
  '.bflw-head{position:absolute;z-index:5;left:9px;top:16px;width:86px;height:68px;border-radius:33px 32px 29px 31px;background:radial-gradient(circle at 32% 19%,#fff 0 13%,transparent 14%),linear-gradient(145deg,#fff,#fbfdff 46%,#e4edf5 75%,#cbdbe7 100%);box-shadow:inset 2px 3px 5px rgba(255,255,255,.95),inset -3px -5px 8px rgba(65,101,132,.16),0 6px 11px rgba(13,48,78,.16);}',
  '.bflw-face{position:absolute;z-index:7;left:18px;top:27px;width:68px;height:44px;border-radius:24px;background:radial-gradient(circle at 35% 15%,rgba(82,157,255,.5),transparent 28%),linear-gradient(160deg,#114c9b,#06285d 65%,#031d47);border:2px solid rgba(5,55,119,.85);box-shadow:inset 0 1px 2px rgba(113,190,255,.6),inset 0 -7px 14px rgba(0,13,48,.26);animation:bflw-blink 5.4s infinite;}',
  '.bflw-eye{position:absolute;top:13px;width:11px;height:11px;border-radius:50%;background:#fff;box-shadow:0 0 5px rgba(255,255,255,.45);transform-origin:center;transform:scaleY(var(--blink,1));}',
  '.bflw-eye.l{left:16px;} .bflw-eye.r{right:16px;}',
  /* hover: sağ göz göz kırpar (çizgi) */
  '.bflw-launcher:hover .bflw-eye.r{height:3px;border-radius:3px;top:17px;transform:none;}',
  '.bflw-smile{position:absolute;left:24px;top:26px;width:13px;height:7px;border:3px solid #fff;border-top:0;border-left-color:transparent;border-right-color:transparent;border-radius:0 0 14px 14px;}',
  '.bflw-ear{position:absolute;z-index:4;top:38px;width:17px;height:32px;border-radius:50%;background:linear-gradient(90deg,#064897,#087ce6 58%,#00dfff);box-shadow:inset -3px 0 4px rgba(0,31,92,.35);}',
  '.bflw-ear.l{left:1px;transform:rotate(4deg);} .bflw-ear.r{right:1px;transform:rotate(-4deg) scaleX(-1);}',
  '.bflw-neck{position:absolute;z-index:3;left:39px;top:77px;width:28px;height:11px;border-radius:50%;background:linear-gradient(#082d68,#041d48);}',
  '.bflw-torso{position:absolute;z-index:4;left:27px;top:79px;width:52px;height:34px;border-radius:50% 50% 42% 42%;background:radial-gradient(circle at 35% 20%,#fff 0 19%,transparent 20%),linear-gradient(145deg,#fff,#edf3f8 64%,#cad9e5);}',
  '.bflw-chest{position:absolute;z-index:6;left:43px;top:86px;width:22px;height:12px;border-radius:5px 5px 10px 10px;background:linear-gradient(#0b438d,#072c68);}',
  '.bflw-chest:after{content:"";position:absolute;left:5px;top:4px;width:12px;height:4px;border-radius:8px;background:#72edff;box-shadow:0 0 7px #43d9ff;}',

  /* kollar */
  '.bflw-arm{position:absolute;z-index:8;top:80px;width:16px;height:30px;border-radius:12px;background:linear-gradient(135deg,#fff,#e1ebf2);box-shadow:inset -2px -2px 4px rgba(65,101,132,.18);}',
  '.bflw-arm.l{left:19px;transform:rotate(22deg);transform-origin:50% 10%;}',
  '.bflw-arm.r{right:19px;transform:rotate(-16deg);transform-origin:50% 10%;transition:transform .35s cubic-bezier(.2,.8,.2,1);}',
  '.bflw-fist{position:absolute;left:1px;bottom:-4px;width:14px;height:14px;border-radius:50%;background:radial-gradient(circle at 34% 28%,#ff8178 0 18%,#e23b34 62%,#c02a23);box-shadow:inset -1px -2px 3px rgba(120,10,10,.3);}',
  '.bflw-palm{position:absolute;left:0;bottom:-15px;width:16px;height:13px;opacity:0;transition:opacity .2s;border-radius:7px 7px 4px 4px;background:linear-gradient(#e8463d,#c92b24);box-shadow:inset -1px -1px 2px rgba(120,10,10,.28);}',
  '.bflw-palm i{position:absolute;top:100%;width:4px;height:11px;border-radius:0 0 4px 4px;background:linear-gradient(#e8463d,#c92b24);}',
  '.bflw-palm i:nth-child(1){left:0;height:9px;transform:rotate(-8deg);transform-origin:top;} .bflw-palm i:nth-child(2){left:4px;} .bflw-palm i:nth-child(3){left:8px;} .bflw-palm i:nth-child(4){left:12px;height:9px;transform:rotate(8deg);transform-origin:top;}',
  '.bflw-palm b{position:absolute;left:100%;top:4px;width:8px;height:6px;border-radius:5px;background:linear-gradient(#e8463d,#c92b24);transform:rotate(26deg);transform-origin:left center;margin-left:-3px;}',
  /* hover: sağ kol kalkar + sallanır, yumruk → açık el */
  '.bflw-launcher:hover .bflw-arm.r{animation:bflw-wave .7s ease-in-out infinite;}',
  '.bflw-launcher:hover .bflw-arm.r .bflw-fist{opacity:0;}',
  '.bflw-launcher:hover .bflw-arm.r .bflw-palm{opacity:1;}',

  /* ---- chat kabuğu (iframe) ---- */
  '.bflw-chat{position:fixed;bottom:100px;'+CHATPOS+'width:405px;height:630px;max-width:calc(100vw - 32px);max-height:calc(100vh - 120px);'+
    'border:0;border-radius:24px;box-shadow:0 24px 70px rgba(9,46,98,.30);background:#fff;overflow:hidden;z-index:2147483000;'+
    'opacity:0;visibility:hidden;transform:translateY(16px) scale(.98);transform-origin:bottom '+(SIDE==='right'?'right':'left')+';'+
    'transition:opacity .32s cubic-bezier(.2,.8,.2,1),transform .32s cubic-bezier(.2,.8,.2,1),visibility 0s linear .32s;pointer-events:none;}',
  '.bflw-root.open .bflw-chat{opacity:1;visibility:visible;transform:translateY(0) scale(1);pointer-events:auto;transition:opacity .32s cubic-bezier(.2,.8,.2,1),transform .32s cubic-bezier(.2,.8,.2,1),visibility 0s;}',
  '.bflw-badge{position:absolute;top:-3px;'+(SIDE==='right'?'left:-3px;':'right:-3px;')+'min-width:20px;height:20px;border-radius:12px;background:#ef4444;color:#fff;'+
    'font:700 11px/20px Inter,sans-serif;text-align:center;padding:0 5px;box-shadow:0 2px 6px rgba(239,68,68,.5);z-index:9;}',

  '@keyframes bflw-float{0%,100%{transform:translateY(0);}50%{transform:translateY(-7px);}}',
  '@keyframes bflw-glow{0%,100%{filter:brightness(1);}50%{filter:brightness(1.25);}}',
  '@property --blink{syntax:"<number>";inherits:true;initial-value:1;}',
  '@keyframes bflw-blink{0%,45%,48%,100%{--blink:1;}46.5%{--blink:.08;}}',
  '.bflw-launcher:hover .bflw-face{animation:none;--blink:1;}',
  '@keyframes bflw-wave{0%,100%{transform:rotate(-104deg);}50%{transform:rotate(-128deg);}}',
  '@media (max-width:520px){.bflw-chat{width:100vw;height:100dvh;max-width:100vw;max-height:100dvh;bottom:0;left:0;right:0;border-radius:0;}'+
    '.bflw-root{bottom:18px;'+ (SIDE==='right'?'right:16px;':'left:16px;') +'}.bflw-launcher{width:58px;height:66px;}.bflw-bot3d{transform:scale(.50);transform-origin:0% 100%;}}',
  '@media (prefers-reduced-motion:reduce){.bflw-launcher{animation:none;}.bflw-eye{animation:none;}.bflw-ant-ball{animation:none;}}'
  ].join('\n');

  function boot(){
    // Google font (yoksa ekle)
    if (!document.getElementById('bflw-font')) {
      var f=document.createElement('link'); f.id='bflw-font'; f.rel='stylesheet';
      f.href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap';
      document.head.appendChild(f);
    }
    var style=document.createElement('style'); style.id='bflw-style'; style.textContent=CSS; document.head.appendChild(style);

    var root=document.createElement('div'); root.className='bflw-root';
    root.innerHTML =
      '<iframe class="bflw-chat" title="Asistan" src="about:blank" allow="clipboard-write"></iframe>' +
      '<button class="bflw-launcher" aria-label="Asistanı aç">' +
        '<span class="bflw-badge" style="display:none">1</span>' +
        '<span class="bflw-hello">Merhaba! 👋 Yardımcı olayım mı?</span>' +
        MASCOT +
      '</button>';
    document.body.appendChild(root);

    var iframe=root.querySelector('.bflw-chat'),
        launcher=root.querySelector('.bflw-launcher'),
        badge=root.querySelector('.bflw-badge'),
        loaded=false, open=false;

    function openChat(){
      if(!loaded){ iframe.src=CHAT_URL; loaded=true; }
      root.classList.add('open'); open=true; badge.style.display='none';
      launcher.setAttribute('aria-label','Asistanı kapat');
    }
    function closeChat(){ root.classList.remove('open'); open=false; launcher.setAttribute('aria-label','Asistanı aç'); }

    launcher.addEventListener('click',function(){ open?closeChat():openChat(); });
    window.addEventListener('message',function(ev){
      var d=ev.data; if(d && d.type==='bfl-widget' && d.action==='close') closeChat();
    });
    window.addEventListener('keydown',function(e){ if(e.key==='Escape' && open) closeChat(); });

    // renk: config'ten launcher temasını da güncelle (isteğe bağlı accent)
    try{
      fetch(CONFIG_URL).then(function(r){return r.json();}).then(function(cfg){
        if(cfg && cfg.color){ root.style.setProperty('--blue', cfg.color); }
      }).catch(function(){});
    }catch(_){}

    // açılışta kısa "merhaba" dürtmesi + rozet
    setTimeout(function(){
      if(open) return;
      root.classList.add('nudge'); badge.style.display='';
      setTimeout(function(){ root.classList.remove('nudge'); }, 4200);
    }, 2600);
  }

  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();