(() => {
  const $ = (id) => document.getElementById(id);
  const authScreen = $("authScreen"), appScreen = $("appScreen");
  let registerMode = false, busy = false, recognition = null;
  const messages = $("messages"), canvas = $("orbCanvas"), ctx = canvas.getContext("2d");
  let particles = [], pointer = { x: 0, y: 0, active: false, down: false }, orbState = "idle";
  let toastTimer;

  function toast(text) {
    const el = $("toast"); el.textContent = text; el.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 2800);
  }
  async function api(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }
  function setAuthMode(isRegister) {
    registerMode = isRegister;
    $("authTitle").textContent = isRegister ? "Begin your own universe." : "A space of your own.";
    $("authSubtitle").textContent = isRegister ? "Создай аккаунт и познакомься с Aether." : "Войди в своё пространство или создай аккаунт.";
    $("emailLabel").classList.toggle("hidden", !isRegister);
    $("loginField").previousElementSibling.textContent = isRegister ? "Никнейм" : "Никнейм или почта";
    $("loginField").placeholder = isRegister ? "your.name" : "your.name";
    $("loginField").autocomplete = isRegister ? "username" : "username";
    $("emailField").required = isRegister;
    $("authSubmit").innerHTML = isRegister ? 'Создать аккаунт <span>↗</span>' : 'Войти <span>↗</span>';
    $("switchText").textContent = isRegister ? "Уже есть аккаунт?" : "Впервые здесь?";
    $("switchMode").textContent = isRegister ? "Войти" : "Создать аккаунт";
    $("authError").textContent = "";
  }
  $("switchMode").addEventListener("click", () => setAuthMode(!registerMode));
  $("authForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = $("authSubmit"); submit.disabled = true; $("authError").textContent = "";
    try {
      const payload = registerMode
        ? { username: $("loginField").value.trim(), email: $("emailField").value.trim(), password: $("passwordField").value }
        : { login: $("loginField").value.trim(), password: $("passwordField").value };
      const data = await api(registerMode ? "/api/auth/register" : "/api/auth/login", { method: "POST", body: JSON.stringify(payload) });
      showApp(data.user.username);
    } catch (error) { $("authError").textContent = error.message; }
    finally { submit.disabled = false; }
  });
  async function showApp(username) {
    $("userName").textContent = username;
    $("topLogout").textContent = username.slice(0,1).toUpperCase();
    authScreen.classList.add("hidden"); appScreen.classList.remove("hidden");
    initOrb();
    try {
      const data = await api("/api/chat/history");
      messages.innerHTML = "";
      data.messages.forEach(m => addMessage(m.role, m.content, false));
      if (data.messages.length) $("welcomeBlock").classList.add("hidden");
    } catch (e) { if (e.message.includes("sign in")) doLogout(); }
  }
  async function doLogout() {
    try { await api("/api/auth/logout", { method: "POST", body: "{}" }); } catch {}
    appScreen.classList.add("hidden"); authScreen.classList.remove("hidden");
    $("passwordField").value = ""; messages.innerHTML = ""; $("welcomeBlock").classList.remove("hidden");
    setAuthMode(false);
  }
  $("logoutBtn").addEventListener("click", doLogout);
  $("topLogout").addEventListener("click", doLogout);
  $("newChat").addEventListener("click", () => {
    messages.innerHTML = ""; $("welcomeBlock").classList.remove("hidden");
    toast("Новый диалог начат. История аккаунта сохранена.");
  });
  $("futureEarth").addEventListener("click", () => toast("Интерактивная Земля Cesium появится на следующем этапе."));
  $("futureFiles").addEventListener("click", () => toast("Генератор файлов и инструменты разработчика добавим следующим этапом."));
  document.querySelectorAll("[data-prompt]").forEach(btn => btn.addEventListener("click", () => {
    $("messageInput").value = btn.dataset.prompt; sendMessage();
  }));
  $("chatForm").addEventListener("submit", e => { e.preventDefault(); sendMessage(); });
  $("messageInput").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  $("messageInput").addEventListener("input", e => {
    e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 150) + "px";
  });
  function addMessage(role, content, scroll = true) {
    $("welcomeBlock").classList.add("hidden");
    const row = document.createElement("div"); row.className = `message ${role === "user" ? "user" : "assistant"}`;
    const avatar = document.createElement("div"); avatar.className = "message-avatar"; avatar.textContent = role === "user" ? "Y" : "✳";
    const body = document.createElement("div"); body.className = "message-body"; body.textContent = content;
    row.append(avatar, body); messages.appendChild(row);
    if (scroll) $("conversation").scrollTop = $("conversation").scrollHeight;
    return row;
  }
  async function sendMessage(text) {
    if (busy) return;
    const input = $("messageInput"); const message = (text || input.value).trim();
    if (!message) return;
    busy = true; $("sendButton").disabled = true; input.value = ""; input.style.height = "auto";
    addMessage("user", message);
    const pending = addMessage("assistant", "Aether is thinking…");
    orbState = "thinking";
    try {
      const data = await api("/api/chat", { method: "POST", body: JSON.stringify({ message }) });
      pending.querySelector(".message-body").textContent = data.reply;
      orbState = "idle";
      if (window.speechSynthesis && localStorage.getItem("aether_voice") === "on") speak(data.reply);
    } catch (error) {
      pending.querySelector(".message-body").textContent = `Не удалось отправить сообщение: ${error.message}`;
      orbState = "idle";
    } finally { busy = false; $("sendButton").disabled = false; $("conversation").scrollTop = $("conversation").scrollHeight; }
  }
  function speak(text) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.slice(0, 3500));
    utterance.lang = "ru-RU"; utterance.rate = 1.0;
    utterance.onstart = () => orbState = "speaking"; utterance.onend = () => orbState = "idle";
    speechSynthesis.speak(utterance);
  }
  function voiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { toast("Распознавание речи не поддерживается этим браузером. Можно использовать диктовку клавиатуры."); return; }
    if (recognition) { recognition.stop(); return; }
    recognition = new SpeechRecognition(); recognition.lang = "ru-RU"; recognition.interimResults = true; recognition.continuous = false;
    $("voiceButton").classList.add("listening"); $("orbLabel").textContent = "LISTENING…"; orbState = "listening";
    let finalText = "";
    recognition.onresult = event => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) finalText += event.results[i][0].transcript;
        else interim += event.results[i][0].transcript;
      }
      $("messageInput").value = (finalText + " " + interim).trim();
    };
    recognition.onerror = () => toast("Не удалось распознать речь. Проверь разрешение микрофона.");
    recognition.onend = () => {
      $("voiceButton").classList.remove("listening"); $("orbLabel").textContent = "TOUCH TO CONNECT";
      recognition = null; orbState = "idle";
      if (finalText.trim()) sendMessage(finalText.trim());
    };
    recognition.start();
  }
  $("voiceButton").addEventListener("click", voiceInput);
  $("orbStage").addEventListener("click", () => {
    if (recognition) recognition.stop(); else voiceInput();
  });

  function initOrb() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.round(rect.width * dpr); canvas.height = Math.round(rect.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = rect.width, h = rect.height, count = Math.round(Math.min(1000, Math.max(420, w * h / 100)));
    particles = Array.from({length: count}, (_, i) => {
      const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * .78;
      return {a, r, speed:(Math.random()-.5)*.003, size:Math.random()*1.7+.35, phase:Math.random()*6.28, hue:Math.random(), seed:i};
    });
    const draw = (time) => {
      if (appScreen.classList.contains("hidden")) { requestAnimationFrame(draw); return; }
      const rectNow = canvas.getBoundingClientRect(), W = rectNow.width, H = rectNow.height;
      ctx.clearRect(0, 0, W, H);
      const cx = W/2, cy = H/2, radius = Math.min(W,H)*.39;
      const glow = ctx.createRadialGradient(cx,cy,radius*.12,cx,cy,radius*1.18);
      glow.addColorStop(0,"rgba(95,70,194,.10)"); glow.addColorStop(.6,"rgba(79,105,218,.07)"); glow.addColorStop(1,"rgba(20,28,70,0)");
      ctx.fillStyle=glow;ctx.fillRect(0,0,W,H);
      // Layered, deforming cloud fields make the orb feel fluid without an external 3D dependency.
      for(let layer=0;layer<5;layer++){
        const rr=radius*(.42+layer*.105);
        ctx.beginPath();
        for(let i=0;i<=180;i++){
          const a=i/180*Math.PI*2;
          const noise=Math.sin(a*3+time*.0005+layer)*.035+Math.sin(a*7-time*.0007+layer*2)*.018+Math.cos(a*2+time*.0003)*.022;
          const pull=pointer.active?Math.max(0,1-Math.hypot(pointer.x-cx,pointer.y-cy)/radius)*.035:0;
          const r=rr*(1+noise+pull);
          const x=cx+Math.cos(a)*r, y=cy+Math.sin(a)*r*.94;
          if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
        }
        ctx.closePath();
        const hue=(250+layer*17+Math.sin(time*.0005+layer)*20)%360;
        ctx.fillStyle=`hsla(${hue},85%,${18+layer*4}%,${.13+layer*.025})`;
        ctx.fill();ctx.strokeStyle=`hsla(${hue+25},90%,${65+layer*3}%,${.08+layer*.012})`;ctx.lineWidth=1;ctx.stroke();
      }
      ctx.save();ctx.beginPath();ctx.ellipse(cx,cy,radius*.76,radius*.73,0,0,Math.PI*2);ctx.clip();
      const core=ctx.createRadialGradient(cx-radius*.24,cy-radius*.28,2,cx,cy,radius);
      core.addColorStop(0,"rgba(220,208,255,.96)");core.addColorStop(.12,"rgba(145,119,245,.9)");core.addColorStop(.36,"rgba(75,70,169,.82)");core.addColorStop(.65,"rgba(28,69,121,.78)");core.addColorStop(1,"rgba(7,12,31,.92)");
      ctx.fillStyle=core;ctx.fillRect(cx-radius,cy-radius,radius*2,radius*2);
      ctx.globalCompositeOperation="screen";
      for(let cloud=0;cloud<8;cloud++){
        const x=cx+Math.sin(time*.00025+cloud*2.1)*radius*.42;
        const y=cy+Math.cos(time*.00031+cloud*1.6)*radius*.4;
        const cr=ctx.createRadialGradient(x,y,0,x,y,radius*(.16+cloud%3*.06));
        cr.addColorStop(0,`hsla(${255+cloud*13},100%,75%,.22)`);cr.addColorStop(1,"rgba(70,100,230,0)");
        ctx.fillStyle=cr;ctx.fillRect(cx-radius,cy-radius,radius*2,radius*2);
      }
      for(const p of particles){
        p.a+=p.speed*(orbState==="thinking"?4:1);
        const wobble=Math.sin(time*.0008+p.phase)*.035;
        let x=cx+Math.cos(p.a)*(p.r+wobble)*radius;
        let y=cy+Math.sin(p.a)*(p.r+wobble)*radius*.93;
        if(pointer.active){const dx=x-pointer.x,dy=y-pointer.y,dist=Math.hypot(dx,dy);if(dist<radius*.42){const f=(1-dist/(radius*.42))*.24;x+=dx*f;y+=dy*f;}}
        const hue=245+p.hue*90+Math.sin(time*.001+p.phase)*15;
        ctx.fillStyle=`hsla(${hue},100%,${66+p.hue*25}%,${.22+p.r*.62})`;
        ctx.beginPath();ctx.arc(x,y,p.size*(orbState==="thinking"?1.45:1),0,Math.PI*2);ctx.fill();
      }
      ctx.restore();
      const rim=ctx.createRadialGradient(cx-radius*.4,cy-radius*.45,radius*.4,cx,cy,radius);
      rim.addColorStop(.82,"rgba(190,174,255,0)");rim.addColorStop(.96,orbState==="listening"?"rgba(255,140,198,.55)":"rgba(155,160,255,.27)");rim.addColorStop(1,"rgba(94,205,240,0)");
      ctx.fillStyle=rim;ctx.beginPath();ctx.ellipse(cx,cy,radius*.78,radius*.75,0,0,Math.PI*2);ctx.fill();
      requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
  }
  function updatePointer(event) {
    const r=canvas.getBoundingClientRect();pointer.x=event.clientX-r.left;pointer.y=event.clientY-r.top;pointer.active=true;
  }
  canvas.addEventListener("pointermove",updatePointer);
  canvas.addEventListener("pointerleave",()=>pointer.active=false);
  canvas.addEventListener("pointerdown",e=>{updatePointer(e);pointer.down=true;});
  canvas.addEventListener("pointerup",()=>pointer.down=false);
  window.addEventListener("resize",()=>{if(!appScreen.classList.contains("hidden"))initOrb();});
  (async function boot(){
    try { const data = await api("/api/auth/me"); showApp(data.user.username); }
    catch { setAuthMode(false); }
  })();
})();
