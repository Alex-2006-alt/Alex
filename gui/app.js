/* ========================================================
   A.L.E.X — JARVIS Interface: App Logic
   Connects to the Python backend via REST API when available.
   Falls back to demo mode when running standalone.
   ======================================================== */

// ============ STATE ============
const state = {
    isListening: false,
    isThinking: false,
    isSpeaking: false,
    sessionMessages: 0,
    startTime: Date.now(),
    waveformAnimId: null,
    backendConnected: false,
    apiBase: '', // Empty = same origin (Flask serves GUI)
};

// ============ DOM REFS ============
const $ = (id) => document.getElementById(id);

const dom = {
    aiCore: $('aiCore'),
    orb: $('orb'),
    orbIcon: $('orbIcon'),
    orbPulse: $('orbPulse'),
    statusText: $('statusText'),
    chatContainer: $('chatContainer'),
    chatMessages: $('chatMessages'),
    chatInput: $('chatInput'),
    sendBtn: $('sendBtn'),
    currentTime: $('currentTime'),
    systemStatus: $('systemStatus'),
    cpuBar: $('cpuBar'),
    cpuValue: $('cpuValue'),
    ramBar: $('ramBar'),
    ramValue: $('ramValue'),
    ramUsed: $('ramUsed'),
    ramTotal: $('ramTotal'),
    diskBar: $('diskBar'),
    diskValue: $('diskValue'),
    diskFree: $('diskFree'),
    batteryBar: $('batteryBar'),
    batteryValue: $('batteryValue'),
    batteryStatus: $('batteryStatus'),
    networkStatus: $('networkStatus'),
    uptime: $('uptime'),
    sessionMsgs: $('sessionMsgs'),
    waveformCanvas: $('waveformCanvas'),
    particles: $('particles'),
    btnListen: $('btnListen'),
};

function scrollChatToBottom() {
    if (dom.chatContainer) {
        dom.chatContainer.scrollTop = dom.chatContainer.scrollHeight;
    }
    if (dom.chatMessages) {
        dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    }
}

// ============ INITIALIZATION ============
document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initParticles();
    initWaveform();
    initKeyboardShortcuts();
    initWebSpeech();
    checkBackendConnection();
    bootSequence();
});

// ============ BACKEND API ============
// Consecutive transport failures before we admit the backend is gone. One
// blip shouldn't flip the HUD; a stopped server should.
let _apiFailureStreak = 0;
const API_FAILURES_BEFORE_OFFLINE = 3;

// Only announce a reconnection if we actually reported a disconnection first —
// otherwise the very first successful poll on page load reads as a "reconnect".
let _reportedOffline = false;

function markBackendOffline() {
    if (!state.backendConnected) return;
    state.backendConnected = false;
    _reportedOffline = true;
    if (dom.systemStatus) {
        dom.systemStatus.textContent = 'OFFLINE';
        dom.systemStatus.className = 'hud-value status-offline';
    }
    setState('standby');
    addMessage('SYSTEM', 'Lost contact with the backend. Restart with: python server.py', 'error-msg');
    simulateSystemStats();
}

function markBackendOnline() {
    _apiFailureStreak = 0;
    if (!_reportedOffline) return;   // startup is handled by checkBackendConnection
    _reportedOffline = false;
    state.backendConnected = true;
    stopSimulatedStats();
    if (dom.systemStatus) {
        dom.systemStatus.textContent = 'ONLINE';
        dom.systemStatus.className = 'hud-value status-online';
    }
    addMessage('SYSTEM', 'Backend reconnected.', 'system-msg');
    fetchRealStats();
}

async function apiCall(endpoint, method = 'GET', body = null) {
    try {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) opts.body = JSON.stringify(body);

        const res = await fetch(`${state.apiBase}${endpoint}`, opts);

        // The server sends a useful JSON body on 4xx/5xx too — for /api/chat it
        // carries the message meant for the user. Throwing it away turned a
        // real error into a useless "No response from backend."
        let data = null;
        try { data = await res.json(); } catch (_) { /* empty or non-JSON body */ }

        markBackendOnline();

        if (!res.ok) {
            console.warn(`API ${endpoint} → HTTP ${res.status}`);
            return data && (data.response || data.error)
                ? data
                : { error: `HTTP ${res.status}` };
        }
        return data;
    } catch (err) {
        // Transport-level failure: server down, DNS, CORS
        _apiFailureStreak++;
        if (_apiFailureStreak === API_FAILURES_BEFORE_OFFLINE) {
            console.warn(`API unreachable (${endpoint}): ${err.message}`);
            markBackendOffline();
        }
        return null;
    }
}


async function fetchRealStats() {
    const stats = await apiCall('/api/stats');
    if (!stats || stats.error) return;

    // CPU
    dom.cpuBar.style.width = `${stats.cpu}%`;
    dom.cpuValue.textContent = Math.round(stats.cpu);

    // RAM
    dom.ramBar.style.width = `${stats.ram_percent}%`;
    dom.ramValue.textContent = Math.round(stats.ram_percent);
    dom.ramUsed.textContent = stats.ram_used;
    dom.ramTotal.textContent = stats.ram_total;

    // Disk
    dom.diskBar.style.width = `${stats.disk_percent}%`;
    dom.diskValue.textContent = stats.disk_percent;
    dom.diskFree.textContent = stats.disk_free;

    // Battery
    dom.batteryBar.style.width = `${stats.battery_percent}%`;
    dom.batteryValue.textContent = stats.battery_percent;
    dom.batteryStatus.textContent = stats.battery_status;

    // Network
    dom.networkStatus.textContent = `Connected — ${stats.network_ip}`;

    // Uptime
    dom.uptime.textContent = stats.uptime;
}

// ============ BOOT SEQUENCE ============
function bootSequence() {
    const steps = [
        { delay: 300,  text: 'Initializing neural cores...', status: 'BOOTING' },
        { delay: 800,  text: 'Loading Whisper STT engine...', status: 'LOADING STT' },
        { delay: 1200, text: 'Connecting to LLM provider...', status: 'CONNECTING' },
        { delay: 1800, text: 'Scanning action modules — 15 loaded.', status: 'LOADING ACTIONS' },
        { delay: 2200, text: 'Tool registry — web ✓ files ✓ system ✓ code ✓ data ✓ notifications ✓', status: 'LOADING TOOLS' },
        { delay: 2800, text: 'All systems nominal. ALEX is online.', status: 'STANDBY' },
    ];

    steps.forEach(({ delay, text, status }) => {
        setTimeout(() => {
            addMessage('SYSTEM', text, 'system-msg');
            dom.statusText.textContent = status;
        }, delay);
    });

    // Final ready state
    setTimeout(() => {
        dom.aiCore.classList.remove('listening', 'thinking', 'speaking');
        dom.statusText.textContent = 'STANDBY';
        dom.orbIcon.textContent = '◆';
    }, 3000);
}

// ============ CLOCK ============
function initClock() {
    function updateTime() {
        const now = new Date();
        dom.currentTime.textContent = now.toLocaleTimeString('en-US', { hour12: false });

        // Update uptime (only if not using real stats)
        if (!state.backendConnected) {
            const elapsed = Date.now() - state.startTime;
            const h = String(Math.floor(elapsed / 3600000)).padStart(2, '0');
            const m = String(Math.floor((elapsed % 3600000) / 60000)).padStart(2, '0');
            const s = String(Math.floor((elapsed % 60000) / 1000)).padStart(2, '0');
            dom.uptime.textContent = `${h}:${m}:${s}`;
        }
    }
    updateTime();
    setInterval(updateTime, 1000);
}

// ============ PARTICLES ============
function initParticles() {
    const container = dom.particles;
    const count = 35;

    for (let i = 0; i < count; i++) {
        const p = document.createElement('div');
        p.className = 'particle';
        p.style.left = `${Math.random() * 100}%`;
        p.style.animationDuration = `${6 + Math.random() * 10}s`;
        p.style.animationDelay = `${Math.random() * 8}s`;
        p.style.width = p.style.height = `${1 + Math.random() * 2}px`;
        container.appendChild(p);
    }
}

// ============ WAVEFORM VISUALIZER ============
function initWaveform() {
    const canvas = dom.waveformCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let W = 600;
    let H = 80;
    let phase = 0;

    function resize() {
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        W = rect.width || 600;
        H = rect.height || 80;
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    resize();
    window.addEventListener('resize', resize);

    function draw() {
        ctx.clearRect(0, 0, W, H);
        phase += 0.02;

        const midY = H / 2;
        const isActive = state.isListening || state.isSpeaking;
        const baseAmp = isActive ? 18 : 4;
        const waves = isActive ? 3 : 2;

        for (let w = 0; w < waves; w++) {
            const amp = baseAmp * (1 - w * 0.3);
            const freq = 0.015 + w * 0.005;
            const speed = phase * (1 + w * 0.4);
            const alpha = 0.5 - w * 0.12;

            ctx.beginPath();
            ctx.strokeStyle = state.isListening
                ? `rgba(0, 255, 136, ${alpha})`
                : state.isSpeaking
                    ? `rgba(255, 107, 53, ${alpha})`
                    : `rgba(0, 212, 255, ${alpha * 0.5})`;
            ctx.lineWidth = 1.5;

            for (let x = 0; x <= W; x++) {
                const noise = Math.sin(x * 0.05 + speed * 2) * (isActive ? 3 : 0.5);
                const y = midY + Math.sin(x * freq + speed) * amp + noise;
                x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        // Center glow dot
        if (isActive) {
            const glowColor = state.isListening ? '0, 255, 136' : '255, 107, 53';
            ctx.beginPath();
            ctx.arc(W / 2, midY + Math.sin(phase * 2) * 4, 3, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${glowColor}, 0.8)`;
            ctx.shadowColor = `rgba(${glowColor}, 0.5)`;
            ctx.shadowBlur = 12;
            ctx.fill();
            ctx.shadowBlur = 0;
        }

        state.waveformAnimId = requestAnimationFrame(draw);
    }

    draw();
}

// ============ CHAT SYSTEM ============
function addMessage(sender, text, className = 'system-msg') {
    const msg = document.createElement('div');
    msg.className = `message ${className}`;

    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });

    msg.innerHTML = `
        <div class="msg-header">
            <span class="msg-sender">${sender}</span>
            <span class="msg-time">${time}</span>
        </div>
        <div class="msg-body">${escapeHtml(text)}</div>
    `;

    dom.chatMessages.appendChild(msg);
    scrollChatToBottom();

    state.sessionMessages++;
    if (dom.sessionMsgs) dom.sessionMsgs.textContent = `${state.sessionMessages} MSGS`;
}

function addTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message alex-msg';
    indicator.id = 'typingIndicator';
    indicator.innerHTML = `
        <div class="msg-header">
            <span class="msg-sender">A.L.E.X</span>
            <span class="msg-time">...</span>
        </div>
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    dom.chatMessages.appendChild(indicator);
    scrollChatToBottom();
}

function removeTypingIndicator() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// ============ CONFIRMATION CARDS ============
// Dangerous tools (shell_run, system_power, file_delete, process_kill,
// code_run) never run from the web UI without an explicit approval. The
// backend parks the request and we poll /api/confirmations for it.
const _confirmCards = new Map();   // confirmation_id -> card element

function renderConfirmation(item) {
    if (_confirmCards.has(item.id)) return;

    const card = document.createElement('div');
    card.className = 'message confirm-msg';
    card.dataset.confirmId = item.id;
    const bodyContent = item.summary
        ? `<strong>${escapeHtml(item.summary)}</strong>`
        : `A.L.E.X wants to run <strong>${escapeHtml(item.tool)}</strong>
           <pre class="confirm-params">${escapeHtml(JSON.stringify(item.params, null, 2))}</pre>`;

    card.innerHTML = `
        <div class="msg-header">
            <span class="msg-sender">⚠ CONFIRMATION REQUIRED</span>
            <span class="msg-time" data-countdown>${item.expires_in}s</span>
        </div>
        <div class="msg-body">
            ${bodyContent}
        </div>
        <div class="confirm-actions">
            <button class="confirm-btn confirm-deny">DENY</button>
            <button class="confirm-btn confirm-approve">APPROVE</button>
        </div>
    `;

    card.querySelector('.confirm-approve').addEventListener('click', () => answerConfirmation(item.id, true));
    card.querySelector('.confirm-deny').addEventListener('click', () => answerConfirmation(item.id, false));

    dom.chatMessages.appendChild(card);
    scrollChatToBottom();
    _confirmCards.set(item.id, card);
}

function settleConfirmation(id, label) {
    const card = _confirmCards.get(id);
    if (card) {
        const actions = card.querySelector('.confirm-actions');
        if (actions) actions.innerHTML = `<span class="confirm-result">${label}</span>`;
    }
    _confirmCards.delete(id);
}

async function answerConfirmation(id, approved) {
    settleConfirmation(id, approved ? 'APPROVED' : 'DENIED');
    await apiCall('/api/confirm', 'POST', { confirmation_id: id, approved });
}

async function pollConfirmations() {
    if (!state.backendConnected) return;

    const data = await apiCall('/api/confirmations');
    if (!data || !Array.isArray(data.pending)) return;

    const live = new Set();
    for (const item of data.pending) {
        live.add(item.id);
        renderConfirmation(item);
        const countdown = _confirmCards.get(item.id)?.querySelector('[data-countdown]');
        if (countdown) countdown.textContent = `${item.expires_in}s`;
    }

    // Anything the server dropped timed out on its own
    for (const id of [..._confirmCards.keys()]) {
        if (!live.has(id)) settleConfirmation(id, 'EXPIRED');
    }
}

// ============ COMMAND HANDLING ============
function handleSend() {
    const text = dom.chatInput.value.trim();
    if (!text) return;

    dom.chatInput.value = '';
    sendCommand(text);
}

async function sendCommand(text) {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();

    addMessage('YOU', cleanText, 'user-msg');
    updateLiveInspector(cleanText, 'Thinking...', null, null, null);
    setState('thinking');
    addTypingIndicator();

    if (state.backendConnected) {
        try {
            const data = await apiCall('/api/chat', 'POST', { message: cleanText });
            removeTypingIndicator();

            if (data && data.response) {
                addMessage('A.L.E.X', data.response, 'alex-msg');
                updateLiveInspector(cleanText, data.response, data.action, data.params, data.action_result);

                if (data.action) {
                    addMessage('SYSTEM', `Tool Executed: ${data.action}`, 'system-msg');
                }

                // Show the multi-step plan, if this was an agentic request.
                // renderPlan() existed but nothing ever called it.
                if (data.plan) renderPlan(data.plan);

                // Speak response via Web SpeechSynthesis
                speakText(data.response);


            } else if (data && data.error) {
                setState('standby');
                addMessage('SYSTEM', `Error: ${data.error}`, 'error-msg');
                updateLiveInspector(cleanText, `Error: ${data.error}`, null, null, null);
            } else {
                setState('standby');
                addMessage('SYSTEM', 'No response from backend.', 'error-msg');
                updateLiveInspector(cleanText, 'No response from backend.', null, null, null);
            }
        } catch (err) {
            removeTypingIndicator();
            setState('standby');
            addMessage('SYSTEM', `Connection error: ${err.message}`, 'error-msg');
            updateLiveInspector(cleanText, `Connection error: ${err.message}`, null, null, null);
        }
    } else {
        const response = processCommandDemo(cleanText.toLowerCase());
        setTimeout(() => {
            removeTypingIndicator();
            addMessage('A.L.E.X', response.message, 'alex-msg');
            updateLiveInspector(cleanText, response.message, response.action, null, 'DEMO');
            if (response.action) addMessage('SYSTEM', `Action: ${response.action}`, 'system-msg');
            speakText(response.message);
        }, 800);
    }
}

// ============ DEMO MODE COMMANDS ============
function processCommandDemo(text) {
    const commands = [
        {
            patterns: ['hello', 'hi', 'hey', 'howdy', 'greetings'],
            responses: [
                "Hello! All systems are operational. How can I assist you today?",
                "Greetings. I'm running at full capacity. What do you need?",
                "Hey there! ALEX is online and ready. What's on your mind?",
            ],
        },
        {
            patterns: ['time', 'what time', 'current time'],
            responses: [`The current time is ${new Date().toLocaleTimeString('en-US', { hour12: true })}.`],
        },
        {
            patterns: ['date', 'what date', 'today'],
            responses: [`Today is ${new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}.`],
        },
        {
            patterns: ['screenshot', 'capture', 'screen'],
            responses: ["Initiating screen capture... Screenshot saved to Desktop."],
            action: 'SCREENSHOT',
        },
        {
            patterns: ['open chrome', 'open browser', 'launch chrome'],
            responses: ["Launching Google Chrome..."],
            action: 'LAUNCH_APP: chrome.exe',
        },
        {
            patterns: ['open notepad', 'launch notepad'],
            responses: ["Opening Notepad..."],
            action: 'LAUNCH_APP: notepad.exe',
        },
        {
            patterns: ['volume up', 'louder', 'increase volume'],
            responses: ["Increasing system volume by 10%."],
            action: 'VOLUME_UP: +10',
        },
        {
            patterns: ['volume down', 'quieter', 'decrease volume'],
            responses: ["Decreasing system volume by 10%."],
            action: 'VOLUME_DOWN: -10',
        },
        {
            patterns: ['mute', 'silence'],
            responses: ["System volume muted."],
            action: 'MUTE_TOGGLE',
        },
        {
            patterns: ['search', 'google', 'look up', 'find'],
            responses: ["Initiating web search... Opening results in your default browser."],
            action: 'WEB_SEARCH',
        },
        {
            patterns: ['weather'],
            responses: ["Fetching weather data from OpenWeatherMap... It's currently 28°C, partly cloudy in your area."],
            action: 'TOOL: weather_get',
        },
        {
            patterns: ['remind', 'reminder', 'alarm'],
            responses: ["Reminder set! I'll alert you when it's time."],
            action: 'TOOL: reminder_set',
        },
        {
            patterns: ['email', 'send email', 'mail'],
            responses: ["Email is ready. To send, say: 'Send an email to [address] saying [message]'. Connect the backend for real email delivery."],
            action: 'TOOL: email_send',
        },
        {
            patterns: ['run code', 'execute', 'python', 'javascript'],
            responses: ["Code execution is ready. Connect the backend with `python main.py --server` to run real code."],
            action: 'TOOL: code_run',
        },
        {
            patterns: ['process', 'running', 'task manager'],
            responses: ["Scanning running processes... Found 87 active processes. Top consumers: Chrome (340MB), VSCode (280MB), ALEX (120MB)."],
            action: 'PROCESS_LIST',
        },
        {
            patterns: ['shutdown', 'power off', 'turn off'],
            responses: ["⚠️ System shutdown requested. This requires confirmation. Say 'confirm shutdown' to proceed."],
            action: 'SHUTDOWN (awaiting confirmation)',
        },
        {
            patterns: ['lock', 'lock screen', 'lock computer'],
            responses: ["Locking the workstation now..."],
            action: 'LOCK_SCREEN',
        },
        {
            patterns: ['status', 'system', 'diagnostics'],
            responses: ["All systems operational. CPU: 34%, RAM: 62%, Disk: 45% used. Network: Connected. LLM: Gemini 2.0 — Active. 34 tools registered across 6 categories."],
        },
        {
            patterns: ['who are you', 'what are you', 'introduce', 'your name'],
            responses: ["I am A.L.E.X — Advanced Linguistic Executive System. Your personal AI assistant built to listen, understand, and execute tasks on your machine. Think of me as your JARVIS."],
        },
        {
            patterns: ['thank', 'thanks'],
            responses: [
                "You're welcome. Always here when you need me.",
                "Happy to help! Need anything else?",
                "Anytime. That's what I'm here for.",
            ],
        },
        {
            patterns: ['joke', 'funny', 'laugh'],
            responses: [
                "Why do programmers prefer dark mode? Because light attracts bugs. 😄",
                "I tried to write a joke about UDP, but you might not get it.",
                "There are 10 types of people in the world: those who understand binary, and those who don't.",
            ],
        },
    ];

    for (const cmd of commands) {
        if (cmd.patterns.some(p => text.includes(p))) {
            const response = cmd.responses[Math.floor(Math.random() * cmd.responses.length)];
            return { message: response, action: cmd.action || null };
        }
    }

    // Default response
    const defaults = [
        "I understand your request. Connect the Python backend with `python main.py --server` for full AI-powered responses.",
        "Command received. Start the backend server to enable real PC control and AI conversation.",
        "Acknowledged. This is demo mode — launch `python main.py --server` for the full JARVIS experience.",
    ];

    return {
        message: defaults[Math.floor(Math.random() * defaults.length)],
        action: null,
    };
}

// ============ STATE MANAGEMENT ============
function setState(newState) {
    const core = dom.aiCore;
    core.classList.remove('listening', 'thinking', 'speaking');

    state.isListening = false;
    state.isThinking = false;
    state.isSpeaking = false;

    switch (newState) {
        case 'listening':
            core.classList.add('listening');
            state.isListening = true;
            dom.statusText.textContent = 'LISTENING';
            dom.orbIcon.textContent = '🎤';
            dom.btnListen.querySelector('.btn-label').textContent = 'STOP';
            dom.btnListen.style.borderColor = 'var(--accent)';
            break;
        case 'thinking':
            core.classList.add('thinking');
            state.isThinking = true;
            dom.statusText.textContent = 'PROCESSING';
            dom.orbIcon.textContent = '⟳';
            break;
        case 'speaking':
            core.classList.add('speaking');
            state.isSpeaking = true;
            dom.statusText.textContent = 'SPEAKING';
            dom.orbIcon.textContent = '🔊';
            break;
        default:
            dom.statusText.textContent = 'STANDBY';
            dom.orbIcon.textContent = '◆';
            dom.btnListen.querySelector('.btn-label').textContent = 'LISTEN';
            dom.btnListen.style.borderColor = '';
            break;
    }
}

// ============ WEB SPEECH API & SPEECH SYNTHESIS ============
let recognition = null;

function initWebSpeech() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.log("Web Speech API not supported in this browser context.");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
        setState('listening');
        const speechEl = document.getElementById('liveSpeechPreview');
        if (speechEl) speechEl.textContent = 'Listening... Speak now!';
        const badge = document.getElementById('inspectorStateBadge');
        if (badge) badge.textContent = 'LISTENING';
    };

    recognition.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }

        const transcript = finalTranscript || interimTranscript;
        const speechEl = document.getElementById('liveSpeechPreview');
        if (speechEl && transcript) {
            speechEl.textContent = transcript;
        }

        if (finalTranscript.trim()) {
            sendCommand(finalTranscript.trim());
        }
    };

    recognition.onerror = (event) => {
        console.warn("Speech recognition error:", event.error);
        if (event.error !== 'no-speech') {
            addMessage('SYSTEM', `Speech error: ${event.error}`, 'error-msg');
        }
        setState('standby');
    };

    recognition.onend = () => {
        if (state.isListening) {
            setState('standby');
        }
    };
}

function speakText(text) {
    // Every path must land on standby.
    if (!('speechSynthesis' in window)) { setState('standby'); return; }

    try {
        window.speechSynthesis.cancel();
        const cleanText = text.replace(/[*_~`#]/g, '').trim();
        if (!cleanText) { setState('standby'); return; }

        const utterance = new SpeechSynthesisUtterance(cleanText);
        utterance.rate = 1.05;
        utterance.lang = 'en-US';
        const voices = window.speechSynthesis.getVoices();
        if (voices && voices.length) {
            const preferred = voices.find(v => (v.lang === 'en-US' || v.lang.startsWith('en')) && (v.name.includes('Natural') || v.name.includes('David') || v.name.includes('Google') || v.name.includes('Guy') || v.name.includes('Mark')));
            if (preferred) utterance.voice = preferred;
        }

        let settled = false;
        const settle = () => { if (!settled) { settled = true; setState('standby'); } };

        utterance.onstart = () => setState('speaking');
        utterance.onend = settle;
        utterance.onerror = settle;

        window.speechSynthesis.speak(utterance);

        // Browsers block speech until the page has had a user gesture
        setTimeout(() => {
            if (!window.speechSynthesis.speaking && !window.speechSynthesis.pending) settle();
        }, 1200);
    } catch (e) {
        console.warn("SpeechSynthesis error:", e);
        setState('standby');
    }
}

function updateLiveInspector(userText, responseText, action = null, params = null, actionResult = null) {
    const speechEl = document.getElementById('liveSpeechPreview');
    const respEl = document.getElementById('liveResponsePreview');
    const badgeEl = document.getElementById('inspectorStateBadge');
    const actionInspector = document.getElementById('liveActionInspector');
    const actionNameEl = document.getElementById('inspectorActionName');
    const actionParamsEl = document.getElementById('inspectorActionParams');
    const actionStatusEl = document.getElementById('inspectorActionStatus');

    if (userText && speechEl) {
        speechEl.textContent = userText;
    }

    if (responseText && respEl) {
        respEl.textContent = responseText;
    }

    if (badgeEl) {
        badgeEl.textContent = action ? `ACTION: ${action.toUpperCase()}` : 'RESPONDED';
    }

    if (action && actionInspector) {
        actionInspector.style.display = 'block';
        if (actionNameEl) actionNameEl.textContent = `TOOL: ${action}`;
        if (actionParamsEl) {
            actionParamsEl.textContent = typeof params === 'object' ? JSON.stringify(params || {}, null, 2) : String(params);
        }
        if (actionStatusEl) {
            actionStatusEl.textContent = actionResult ? 'SUCCESS' : 'EXECUTED';
        }
    } else if (actionInspector) {
        actionInspector.style.display = 'none';
    }
}

// ============ LISTENING TOGGLE ============
function toggleListening() {
    if (state.isListening) {
        if (recognition) {
            try { recognition.stop(); } catch (e) {}
        }
        setState('standby');
        addMessage('SYSTEM', 'Microphone deactivated.', 'system-msg');
    } else {
        if (recognition) {
            try {
                recognition.start();
                setState('listening');
            } catch (err) {
                console.warn("Recognition start failed:", err);
                if (err.name === 'InvalidStateError') {
                    setState('listening');
                } else {
                    setState('standby');
                    addMessage('SYSTEM', `Microphone could not start: ${err.message || err}`, 'error-msg');
                }
            }
        } else {
            setState('listening');
            addMessage('SYSTEM', 'Microphone activated (Web Speech API unsupported on this browser).', 'system-msg');
            setTimeout(() => {
                if (state.isListening) setState('standby');
            }, 5000);
        }
    }
}

// ============ SEARCH MODAL ============
function showSearchModal() {
    const query = prompt('Enter your search query:');
    if (query && query.trim()) {
        sendCommand(`Search the web for: ${query.trim()}`);
    }
}

// ============ SYSTEM STATS SIMULATION (demo mode) ============
let _simStatsInterval = null;

function simulateSystemStats() {
    stopSimulatedStats();

    function updateStats() {
        if (state.backendConnected) {
            stopSimulatedStats();
            return;
        }
        const cpu = 15 + Math.floor(Math.random() * 60);
        if (dom.cpuBar) dom.cpuBar.style.width = `${cpu}%`;
        if (dom.cpuValue) dom.cpuValue.textContent = cpu;

        const ram = 50 + Math.floor(Math.random() * 30);
        const total = 16;
        const used = (total * ram / 100).toFixed(1);
        if (dom.ramBar) dom.ramBar.style.width = `${ram}%`;
        if (dom.ramValue) dom.ramValue.textContent = ram;
        if (dom.ramUsed) dom.ramUsed.textContent = used;
        if (dom.ramTotal) dom.ramTotal.textContent = total.toFixed(1);

        const disk = 40 + Math.floor(Math.random() * 15);
        const free = Math.floor(256 * (1 - disk / 100));
        if (dom.diskBar) dom.diskBar.style.width = `${disk}%`;
        if (dom.diskValue) dom.diskValue.textContent = disk;
        if (dom.diskFree) dom.diskFree.textContent = free;

        const battery = 70 + Math.floor(Math.random() * 25);
        if (dom.batteryBar) dom.batteryBar.style.width = `${battery}%`;
        if (dom.batteryValue) dom.batteryValue.textContent = battery;
        if (dom.batteryStatus) dom.batteryStatus.textContent = battery > 95 ? 'Full' : 'Charging';
    }

    updateStats();
    _simStatsInterval = setInterval(updateStats, 5000);
}

function stopSimulatedStats() {
    if (_simStatsInterval) {
        clearInterval(_simStatsInterval);
        _simStatsInterval = null;
    }
}

// ============ KEYBOARD SHORTCUTS ============
function initKeyboardShortcuts() {
    if (dom.chatInput) {
        dom.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
            }
        });
    }

    document.addEventListener('keydown', (e) => {
        const key = (e.key || '').toLowerCase();
        if (e.ctrlKey && key === 'l') { e.preventDefault(); if (dom.chatInput) dom.chatInput.focus(); }
        if (e.ctrlKey && key === 'm') { e.preventDefault(); toggleListening(); }
        if (e.ctrlKey && key === 'k') { e.preventDefault(); toggleSidePanel(); }
        if (e.ctrlKey && key === 'p') { e.preventDefault(); togglePlanDrawer(); }
        if (key === 'escape') { setState('standby'); closePlanDrawer(); }
    });
}

// ============ STRATEGIC PLAN MANAGER (VIEW, EDIT, MINIMIZE, BACKEND) ============
let _currentPlanData = null;
let _isPlanEditing = false;
let _isPlanMinimized = false;
let _isPlanExpanded = false;
let _planPollInterval = null;
let _allStepsFolded = false;

function renderPlan(plan) {
    if (!plan) return;
    _currentPlanData = plan;

    const drawer = document.getElementById('planDrawer');
    const goalText = document.getElementById('planGoalText');
    const planSteps = document.getElementById('planSteps');
    const planSummary = document.getElementById('planSummary');
    const minBadge = document.getElementById('planMinBadge');
    const statusBadge = document.getElementById('planStatusBadge');
    const progressContainer = document.getElementById('planProgressContainer');
    const progressBar = document.getElementById('planProgressBar');
    const dockStepCount = document.getElementById('dockStepCount');

    if (!drawer) return;

    const steps = plan.steps || [];
    const status = (plan.status || 'idle').toLowerCase();
    const summaryText = `${steps.length} STEP${steps.length !== 1 ? 'S' : ''} • ${status.toUpperCase()}`;

    if (goalText) goalText.textContent = plan.goal || 'Custom Strategic Plan';
    if (planSummary) planSummary.textContent = summaryText;
    if (minBadge) minBadge.textContent = summaryText;
    if (dockStepCount) dockStepCount.textContent = `${steps.length} STEP${steps.length !== 1 ? 'S' : ''}`;

    if (statusBadge) {
        statusBadge.textContent = status.toUpperCase();
        statusBadge.className = `plan-status-badge status-${status}`;
    }

    if (progressContainer && progressBar) {
        if (steps.length > 0) {
            const completedCount = steps.filter(s => s.status === 'done').length;
            const pct = Math.round((completedCount / steps.length) * 100);
            progressBar.style.width = `${pct}%`;
            progressContainer.style.display = 'block';
        } else {
            progressContainer.style.display = 'none';
        }
    }

    if (planSteps) {
        if (steps.length === 0) {
            planSteps.innerHTML = '<div class="plan-empty">No steps currently defined. Click ✎ EDIT to design a strategic plan.</div>';
        } else {
            const statusEmoji = { done: '✅', running: '🔄', failed: '❌', pending: '⏳', skipped: '➡️' };
            const statusClass = { done: 'step-done', running: 'step-running', failed: 'step-failed', pending: 'step-pending', skipped: 'step-skipped' };

            planSteps.innerHTML = steps.map(step => {
                const hasParams = step.params && typeof step.params === 'object' && Object.keys(step.params).length > 0;
                const paramsStr = hasParams ? JSON.stringify(step.params, null, 2) : '';

                return `
                    <div class="plan-step ${statusClass[step.status] || 'step-pending'}" id="step-${escapeHtml(String(step.id))}">
                        <div class="step-header">
                            <span class="step-status-icon">${statusEmoji[step.status] || '⏳'}</span>
                            <span class="step-num">STEP ${escapeHtml(String(step.id))}</span>
                            <span class="step-action-badge">${escapeHtml(String(step.action || 'system'))}</span>
                            ${step.duration ? `<span class="step-duration">${escapeHtml(String(step.duration))}s</span>` : ''}
                            <span class="step-fold-icon" onclick="toggleStepFold('step-${escapeHtml(String(step.id))}')" title="Fold / Unfold Step Details">▾</span>
                        </div>
                        <div class="step-desc">${escapeHtml(String(step.description || 'No description provided'))}</div>
                        ${hasParams ? `<div class="step-params-box"><strong>ARGS:</strong> ${escapeHtml(paramsStr)}</div>` : ''}
                        ${step.result ? `<div class="step-result"><strong>RESULT:</strong> ${escapeHtml(String(step.result))}</div>` : ''}
                        ${step.error ? `<div class="step-error">⚠️ <strong>ERROR:</strong> ${escapeHtml(String(step.error))}</div>` : ''}
                    </div>
                `;
            }).join('');
        }
    }

    if (!_isPlanMinimized) {
        drawer.classList.add('active');
        drawer.classList.remove('minimized');
    }
}

function minimizePlanDrawer() {
    const drawer = document.getElementById('planDrawer');
    const dockPill = document.getElementById('planDockPill');
    const toggleBtn = document.getElementById('btnTogglePlan');
    if (!drawer) return;

    _isPlanMinimized = true;
    drawer.classList.remove('active');
    drawer.classList.add('minimized');

    if (dockPill) dockPill.style.display = 'inline-flex';
    if (toggleBtn) {
        toggleBtn.classList.add('active');
        toggleBtn.textContent = `PLAN (${_currentPlanData?.steps?.length || 0})`;
    }
    if (_isPlanEditing) cancelPlanEdit();
}

function restorePlanDrawer() {
    const drawer = document.getElementById('planDrawer');
    const dockPill = document.getElementById('planDockPill');
    const toggleBtn = document.getElementById('btnTogglePlan');
    if (!drawer) return;

    _isPlanMinimized = false;
    drawer.classList.remove('minimized');
    drawer.classList.add('active');

    if (dockPill) dockPill.style.display = 'none';
    if (toggleBtn) {
        toggleBtn.classList.remove('active');
        toggleBtn.textContent = 'PLAN';
    }

    refreshPlanFromBackend();
}

function togglePlanMinimize() {
    if (_isPlanMinimized) {
        restorePlanDrawer();
    } else {
        minimizePlanDrawer();
    }
}

function closePlanDrawer() {
    const drawer = document.getElementById('planDrawer');
    const dockPill = document.getElementById('planDockPill');
    const toggleBtn = document.getElementById('btnTogglePlan');

    _isPlanMinimized = false;
    if (drawer) {
        drawer.classList.remove('active');
        drawer.classList.remove('minimized');
    }
    if (dockPill) dockPill.style.display = 'none';
    if (toggleBtn) {
        toggleBtn.classList.remove('active');
        toggleBtn.textContent = 'PLAN';
    }

    if (_planPollInterval) {
        clearInterval(_planPollInterval);
        _planPollInterval = null;
    }
}

async function togglePlanDrawer() {
    const drawer = document.getElementById('planDrawer');
    if (!drawer) return;

    if (_isPlanMinimized) {
        restorePlanDrawer();
        return;
    }

    if (drawer.classList.contains('active')) {
        minimizePlanDrawer();
    } else {
        restorePlanDrawer();
    }
}

function togglePlanExpand() {
    const drawer = document.getElementById('planDrawer');
    const expandBtn = document.getElementById('planExpandBtn');
    if (!drawer) return;

    _isPlanExpanded = !_isPlanExpanded;
    if (_isPlanExpanded) {
        drawer.classList.add('expanded');
        if (expandBtn) expandBtn.textContent = '⤢ NORM';
    } else {
        drawer.classList.remove('expanded');
        if (expandBtn) expandBtn.textContent = '⛶ WIDE';
    }
}

function handleDrawerTitleClick() {
    if (_isPlanMinimized) {
        restorePlanDrawer();
    }
}

function toggleGoalFold() {
    const card = document.getElementById('planGoalCard');
    const btn = document.getElementById('goalFoldBtn');
    if (!card) return;

    const isFolded = card.classList.toggle('folded');
    if (btn) btn.textContent = isFolded ? '▸' : '▾';
}

function toggleStepFold(stepElementId) {
    const el = document.getElementById(stepElementId);
    if (!el) return;

    const isFolded = el.classList.toggle('folded');
    const foldIcon = el.querySelector('.step-fold-icon');
    if (foldIcon) foldIcon.textContent = isFolded ? '▸' : '▾';
}

function toggleFoldAllSteps() {
    _allStepsFolded = !_allStepsFolded;
    const steps = document.querySelectorAll('.plan-step');
    const btn = document.getElementById('toggleFoldAllBtn');

    steps.forEach(s => {
        if (_allStepsFolded) {
            s.classList.add('folded');
        } else {
            s.classList.remove('folded');
        }
        const icon = s.querySelector('.step-fold-icon');
        if (icon) icon.textContent = _allStepsFolded ? '▸' : '▾';
    });

    if (btn) btn.textContent = _allStepsFolded ? '⊞ UNFOLD STEPS' : '⊟ FOLD STEPS';
}

async function refreshPlanFromBackend() {
    try {
        const data = await apiCall('/api/plan');
        if (data) {
            renderPlan(data);
        }
    } catch (e) {
        console.warn('Failed to refresh plan from backend:', e);
    }
}

function togglePlanEditMode() {
    _isPlanEditing = !_isPlanEditing;
    const viewMode = document.getElementById('planViewMode');
    const editMode = document.getElementById('planEditMode');
    const editBtn = document.getElementById('planEditBtn');

    if (_isPlanEditing) {
        if (_isPlanMinimized) togglePlanMinimize();
        if (viewMode) viewMode.style.display = 'none';
        if (editMode) editMode.style.display = 'flex';
        if (editBtn) editBtn.textContent = '👁 VIEW';

        const goalInput = document.getElementById('editPlanGoal');
        if (goalInput) goalInput.value = _currentPlanData?.goal || 'Automate and execute strategic workflow';

        const container = document.getElementById('editPlanSteps');
        if (container) {
            container.innerHTML = '';
            const existingSteps = _currentPlanData?.steps || [];
            if (existingSteps.length === 0) {
                addPlanEditStep('web_search', 'Search for necessary documentation and information', { query: 'ALEX AI system instructions' });
                addPlanEditStep('system_info', 'Retrieve current system diagnostics and resource health', {});
            } else {
                existingSteps.forEach(s => addPlanEditStep(s.action, s.description, s.params));
            }
        }
    } else {
        if (viewMode) viewMode.style.display = 'flex';
        if (editMode) editMode.style.display = 'none';
        if (editBtn) editBtn.textContent = '✎ EDIT';
    }
}

const COMMON_PLAN_ACTIONS = [
    'web_search',
    'system_info',
    'app_open',
    'shell_cmd',
    'file_read',
    'file_write',
    'screen_vision',
    'ask_user',
    'custom'
];

function addPlanEditStep(action = 'web_search', description = '', params = {}) {
    const container = document.getElementById('editPlanSteps');
    if (!container) return;

    const stepIndex = container.children.length + 1;
    const item = document.createElement('div');
    item.className = 'edit-step-item';

    const isKnownAction = COMMON_PLAN_ACTIONS.includes(action);
    const selectedAction = isKnownAction ? action : 'custom';
    const paramsJson = params && Object.keys(params).length > 0 ? JSON.stringify(params) : '';

    item.innerHTML = `
        <div class="edit-step-top-row">
            <span class="edit-step-num">STEP ${stepIndex}</span>
            <select class="edit-step-action-select" onchange="handleStepActionSelect(this)">
                ${COMMON_PLAN_ACTIONS.map(act => `<option value="${act}" ${act === selectedAction ? 'selected' : ''}>${act.toUpperCase()}</option>`).join('')}
            </select>
            <input type="text" class="edit-step-action-input" placeholder="Custom action..." value="${escapeHtml(action)}" style="${selectedAction === 'custom' ? 'display:block;' : 'display:none;'}">
            <button type="button" class="edit-step-del-btn" onclick="removePlanEditStep(this)" title="Delete Step">🗑 DEL</button>
        </div>
        <input type="text" class="edit-step-desc-input" placeholder="Step description..." value="${escapeHtml(description)}">
        <input type="text" class="edit-step-params-input" placeholder='Arguments JSON (e.g. {"query": "weather"})' value="${escapeHtml(paramsJson)}">
    `;
    container.appendChild(item);
}

function handleStepActionSelect(selectEl) {
    const row = selectEl.closest('.edit-step-top-row');
    if (!row) return;
    const customInput = row.querySelector('.edit-step-action-input');
    if (!customInput) return;

    if (selectEl.value === 'custom') {
        customInput.style.display = 'block';
        customInput.focus();
    } else {
        customInput.style.display = 'none';
        customInput.value = selectEl.value;
    }
}

function removePlanEditStep(btn) {
    const item = btn.closest('.edit-step-item');
    if (item) {
        item.remove();
        reindexPlanEditSteps();
    }
}

function reindexPlanEditSteps() {
    const container = document.getElementById('editPlanSteps');
    if (!container) return;
    const items = container.querySelectorAll('.edit-step-item');
    items.forEach((item, idx) => {
        const numEl = item.querySelector('.edit-step-num');
        if (numEl) numEl.textContent = `STEP ${idx + 1}`;
    });
}

async function savePlanToBackend() {
    const goalInput = document.getElementById('editPlanGoal');
    const container = document.getElementById('editPlanSteps');
    const saveBtn = document.getElementById('planSaveBtn');

    const goal = (goalInput ? goalInput.value.trim() : '') || 'Custom Strategic Plan';
    const stepItems = container ? container.querySelectorAll('.edit-step-item') : [];
    const steps = [];

    stepItems.forEach((item, idx) => {
        const actionSelect = item.querySelector('.edit-step-action-select');
        const customActionInput = item.querySelector('.edit-step-action-input');
        const descInput = item.querySelector('.edit-step-desc-input');
        const paramsInput = item.querySelector('.edit-step-params-input');

        let action = actionSelect?.value || 'web_search';
        if (action === 'custom' && customActionInput?.value.trim()) {
            action = customActionInput.value.trim();
        }

        const description = descInput ? descInput.value.trim() : '';
        let params = {};
        if (paramsInput && paramsInput.value.trim()) {
            try {
                params = JSON.parse(paramsInput.value.trim());
            } catch (e) {
                params = { raw: paramsInput.value.trim() };
            }
        }

        if (action || description) {
            steps.push({
                id: idx + 1,
                action: action || 'system_info',
                description: description || `Step ${idx + 1}`,
                params: params,
                status: 'pending'
            });
        }
    });

    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = '💾 SAVING...';
    }

    try {
        const res = await apiCall('/api/plan', 'POST', { goal, steps });
        if (res && res.success && res.plan) {
            _currentPlanData = res.plan;
            renderPlan(res.plan);
            togglePlanEditMode();
            addMessage('SYSTEM', `Strategic plan "${res.plan.goal}" saved to backend with ${res.plan.steps.length} step(s).`, 'system-msg');
        } else {
            addMessage('SYSTEM', `Failed to save plan: ${res?.error || 'Unknown error'}`, 'error-msg');
        }
    } catch (e) {
        addMessage('SYSTEM', `Error saving plan to backend: ${e.message}`, 'error-msg');
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = '💾 SAVE TO BACKEND';
        }
    }
}

async function executeCurrentPlan() {
    const runBtn = document.getElementById('planRunBtn');
    if (runBtn) {
        runBtn.disabled = true;
        runBtn.textContent = '⏳ RUNNING...';
    }

    try {
        const res = await apiCall('/api/plan/execute', 'POST');
        if (res && res.status === 'running') {
            addMessage('SYSTEM', 'Autonomous execution of strategic plan started.', 'system-msg');
            await refreshPlanFromBackend();

            // Poll progress every 1.5 seconds until done
            if (_planPollInterval) clearInterval(_planPollInterval);
            _planPollInterval = setInterval(async () => {
                const planData = await apiCall('/api/plan');
                if (planData) {
                    renderPlan(planData);
                    const status = (planData.status || '').toLowerCase();
                    if (status === 'completed' || status === 'failed' || status === 'idle') {
                        clearInterval(_planPollInterval);
                        _planPollInterval = null;
                        if (runBtn) {
                            runBtn.disabled = false;
                            runBtn.textContent = '▶ RUN';
                        }
                        addMessage('SYSTEM', `Strategic plan execution ended with status: ${status.toUpperCase()}.`, status === 'failed' ? 'error-msg' : 'system-msg');
                    }
                }
            }, 1500);
        } else {
            addMessage('SYSTEM', `Cannot execute plan: ${res?.error || 'No steps to run.'}`, 'error-msg');
            if (runBtn) {
                runBtn.disabled = false;
                runBtn.textContent = '▶ RUN';
            }
        }
    } catch (e) {
        addMessage('SYSTEM', `Execution error: ${e.message}`, 'error-msg');
        if (runBtn) {
            runBtn.disabled = false;
            runBtn.textContent = '▶ RUN';
        }
    }
}

function cancelPlanEdit() {
    togglePlanEditMode();
    if (_currentPlanData) {
        renderPlan(_currentPlanData);
    }
}

// ============ MEMORY PANEL ============
async function refreshMemory() {
    const data = await apiCall('/api/memory');
    if (!data) return;

    const factsList = document.getElementById('factsList');
    const factCount = document.getElementById('factCount');

    const facts = data.facts || [];
    factCount.textContent = `${facts.length} fact${facts.length !== 1 ? 's' : ''}`;

    if (facts.length === 0) {
        factsList.innerHTML = '<div class="facts-empty">No facts stored yet.</div>';
        return;
    }

    // Group by category
    const byCategory = {};
    facts.forEach(f => {
        if (!byCategory[f.category]) byCategory[f.category] = [];
        byCategory[f.category].push(f);
    });

    factsList.innerHTML = Object.entries(byCategory).map(([cat, items]) => `
        <div class="fact-category">
            <div class="fact-cat-header">${cat.toUpperCase()}</div>
            ${items.map(f => `
                <div class="fact-item">
                    <div class="fact-key">${escapeHtml(f.key.replace(/_/g, ' '))}</div>
                    <div class="fact-value">${escapeHtml(f.value)}</div>
                    <button class="fact-delete-btn" data-key="${encodeURIComponent(f.key)}" onclick="deleteFact(decodeURIComponent(this.dataset.key))" title="Forget this">✕</button>
                </div>
            `).join('')}
        </div>
    `).join('');
}

async function deleteFact(key) {
    if (!key) return;
    await apiCall(`/api/memory/${encodeURIComponent(key)}`, 'DELETE');
    refreshMemory();
}

// ============ TASKS PANEL ============
async function refreshTasks() {
    const data = await apiCall('/api/tasks');
    if (!data) return;

    const tasksList = document.getElementById('tasksList');
    if (!tasksList) return;
    const tasks = data.tasks || [];

    if (tasks.length === 0) {
        tasksList.innerHTML = '<div class="tasks-empty">No background tasks running.</div>';
        return;
    }

    const statusEmoji = { running: '🔄', pending: '⏳', done: '✅', failed: '❌', cancelled: '🚫' };

    tasksList.innerHTML = tasks.map(t => `
        <div class="task-item task-${escapeHtml(t.status)}">
            <div class="task-header">
                <span class="task-status-icon">${statusEmoji[t.status] || '?'}</span>
                <span class="task-name">${escapeHtml(t.name)}</span>
                <button class="task-cancel-btn" data-task-id="${escapeHtml(t.id)}" onclick="cancelTask(this.dataset.taskId)" title="Cancel">✕</button>
            </div>
            ${t.progress ? `<div class="task-progress">${escapeHtml(t.progress)}</div>` : ''}
            ${t.is_recurring && t.next_run ? `<div class="task-next">Next: ${new Date(t.next_run * 1000).toLocaleTimeString()}</div>` : ''}
        </div>
    `).join('');
}

async function cancelTask(taskId) {
    if (!taskId) return;
    await apiCall(`/api/tasks/${taskId}`, 'DELETE');
    refreshTasks();
}

async function cancelAllTasks() {
    const data = await apiCall('/api/tasks');
    if (data && data.tasks) {
        for (const t of data.tasks) {
            await apiCall(`/api/tasks/${t.id}`, 'DELETE');
        }
    }
    refreshTasks();
}

// ============ HISTORY PANEL ============
async function refreshHistory() {
    const data = await apiCall('/api/task-history?limit=10');
    if (!data) return;

    const historyList = document.getElementById('historyList');
    if (!historyList) return;
    const history = data.history || [];

    if (history.length === 0) {
        historyList.innerHTML = '<div class="tasks-empty">No task history yet.</div>';
        return;
    }

    const statusEmoji = { done: '✅', failed: '❌', partial: '⚠️', running: '🔄' };

    historyList.innerHTML = history.map(t => `
        <div class="history-item">
            <div class="history-header">
                <span>${statusEmoji[t.status] || '?'}</span>
                <span class="history-goal">${escapeHtml((t.goal || '').substring(0, 60))}</span>
            </div>
            ${t.result ? `<div class="history-result">${escapeHtml((t.result || '').substring(0, 100))}</div>` : ''}
            <div class="history-time">${new Date((t.created_at || 0) * 1000).toLocaleString()}</div>
        </div>
    `).join('');
}

// ============ SIDE PANEL ============
let _sidePanelOpen = false;
let _currentTab = 'memory';

function toggleSidePanel() {
    const panel = document.getElementById('sidePanel');
    const icon = document.getElementById('sidePanelIcon');
    _sidePanelOpen = !_sidePanelOpen;

    if (_sidePanelOpen) {
        if (panel) panel.classList.add('open');
        if (icon) icon.textContent = '✕';
        refreshSideContent();
    } else {
        if (panel) panel.classList.remove('open');
        if (icon) icon.textContent = '💾';
    }
}

function switchSideTab(tab) {
    _currentTab = tab;
    document.querySelectorAll('.side-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.side-content').forEach(c => c.classList.remove('active'));

    const tabEl = document.getElementById(`tab${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
    const contentEl = document.getElementById(`content${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
    if (tabEl) tabEl.classList.add('active');
    if (contentEl) contentEl.classList.add('active');
    refreshSideContent();
}

function refreshSideContent() {
    if (_currentTab === 'memory') refreshMemory();
    else if (_currentTab === 'tasks') refreshTasks();
    else if (_currentTab === 'history') refreshHistory();
}

// ============ POLLING (when backend connected) ============
let _pollIntervalStarted = false;
let _reconnectProbeId = null;

function startPolling() {
    if (_pollIntervalStarted) return;
    _pollIntervalStarted = true;

    // Confirmations poll faster since user interaction blocks execution
    setInterval(pollConfirmations, 1500);

    // Poll tasks, live plans, and assistant modules every 3 seconds
    setInterval(async () => {
        if (!state.backendConnected) return;

        // Live plan progress
        try {
            const planData = await apiCall('/api/plan');
            if (planData && planData.steps && planData.steps.length) {
                renderPlan(planData);
            }
        } catch (_) {}

        // Refresh side panel if open
        if (_sidePanelOpen) {
            refreshSideContent();
        }

        // Update assistant module chips & counts
        try {
            const statusData = await apiCall('/api/assistant-status');
            if (statusData) {
                const agentChip = document.getElementById('modACT');
                if (agentChip) {
                    agentChip.textContent = statusData.agent_mode ? 'AGENT' : 'ACT';
                    agentChip.className = statusData.agent_mode ? 'module-chip active' : 'module-chip';
                }
                const memChip = document.getElementById('modMEM');
                if (memChip && statusData.memory) {
                    memChip.className = 'module-chip active';
                    memChip.title = `${statusData.memory.facts} facts stored`;
                }
                if (statusData.tools) {
                    const actionCountEl = document.getElementById('actionCount');
                    if (actionCountEl) actionCountEl.textContent = `${statusData.tools} TOOLS`;
                    const toolCountEl = document.getElementById('toolCount');
                    if (toolCountEl) toolCountEl.textContent = `${statusData.tools} LOADED`;
                }
            }
        } catch (_) {}
    }, 3000);
}

function startReconnectProbe() {
    if (_reconnectProbeId) return;
    _reconnectProbeId = setInterval(async () => {
        if (state.backendConnected) return;
        const data = await apiCall('/api/status');
        if (data && data.status === 'online') {
            onBackendConnected(data);
        }
    }, 4000);
}

function onBackendConnected(data) {
    state.backendConnected = true;
    _reportedOffline = false;
    _apiFailureStreak = 0;
    stopSimulatedStats();

    if (dom.systemStatus) {
        dom.systemStatus.textContent = 'ONLINE';
        dom.systemStatus.className = 'hud-value status-online';
    }

    addMessage('SYSTEM', `Backend connected — ${data.assistant_name} is online (Agent Mode: ${data.agent_mode !== false ? 'ON' : 'OFF'}).`, 'system-msg');

    if (data.llm_model) {
        const p = $('llmProvider');
        if (p) p.textContent = data.llm_model.toUpperCase();
    }
    if (data.stt_engine) {
        const s = $('sttEngine');
        if (s) s.textContent = data.stt_engine;
    }
    if (data.tts_engine) {
        const t = $('ttsEngine');
        if (t) t.textContent = data.tts_engine;
    }

    fetchRealStats();
    setInterval(fetchRealStats, 5000);
    startPolling();
}

async function checkBackendConnection() {
    startReconnectProbe();
    const data = await apiCall('/api/status');
    if (data && data.status === 'online') {
        onBackendConnected(data);
    } else {
        state.backendConnected = false;
        addMessage('SYSTEM', 'Running in demo mode — no backend connected. Launch with: python server.py', 'system-msg');
        simulateSystemStats();
    }
}
