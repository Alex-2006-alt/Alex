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
async function apiCall(endpoint, method = 'GET', body = null) {
    try {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) opts.body = JSON.stringify(body);

        const res = await fetch(`${state.apiBase}${endpoint}`, opts);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (err) {
        console.warn(`API call failed (${endpoint}):`, err.message);
        return null;
    }
}

async function checkBackendConnection() {
    const data = await apiCall('/api/status');
    if (data && data.status === 'online') {
        state.backendConnected = true;
        dom.systemStatus.textContent = 'ONLINE';
        dom.systemStatus.className = 'hud-value status-online';
        addMessage('SYSTEM', `Backend connected — ${data.assistant_name} is running with ${data.llm_provider}.`, 'system-msg');

        // Update HUD with real info
        if (data.llm_model) $('llmProvider').textContent = data.llm_model.toUpperCase();
        if (data.stt_engine) $('sttEngine').textContent = data.stt_engine;
        if (data.tts_engine) $('ttsEngine').textContent = data.tts_engine;

        // Start polling real system stats
        fetchRealStats();
        setInterval(fetchRealStats, 5000);
    } else {
        state.backendConnected = false;
        addMessage('SYSTEM', 'Running in demo mode — no backend connected. Launch with: python main.py --server', 'system-msg');
        simulateSystemStats();
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
    const ctx = canvas.getContext('2d');

    // High-DPI support
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;
    let phase = 0;

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
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;

    state.sessionMessages++;
    dom.sessionMsgs.textContent = `${state.sessionMessages} MSGS`;
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
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
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
    card.innerHTML = `
        <div class="msg-header">
            <span class="msg-sender">⚠ CONFIRMATION REQUIRED</span>
            <span class="msg-time" data-countdown>${item.expires_in}s</span>
        </div>
        <div class="msg-body">
            A.L.E.X wants to run <strong>${escapeHtml(item.tool)}</strong>
            <pre class="confirm-params">${escapeHtml(JSON.stringify(item.params, null, 2))}</pre>
        </div>
        <div class="confirm-actions">
            <button class="confirm-btn confirm-deny">DENY</button>
            <button class="confirm-btn confirm-approve">APPROVE</button>
        </div>
    `;

    card.querySelector('.confirm-approve').addEventListener('click', () => answerConfirmation(item.id, true));
    card.querySelector('.confirm-deny').addEventListener('click', () => answerConfirmation(item.id, false));

    dom.chatMessages.appendChild(card);
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
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
    if (!('speechSynthesis' in window)) return;
    try {
        window.speechSynthesis.cancel();
        const cleanText = text.replace(/[*_~`#]/g, '').trim();
        if (!cleanText) return;

        const utterance = new SpeechSynthesisUtterance(cleanText);
        utterance.rate = 1.05;

        utterance.onstart = () => setState('speaking');
        utterance.onend = () => setState('standby');
        utterance.onerror = () => setState('standby');

        window.speechSynthesis.speak(utterance);
    } catch (e) {
        console.warn("SpeechSynthesis error:", e);
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
            } catch (err) {
                console.warn("Recognition start failed:", err);
                setState('listening');
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
function simulateSystemStats() {
    function updateStats() {
        const cpu = 15 + Math.floor(Math.random() * 60);
        dom.cpuBar.style.width = `${cpu}%`;
        dom.cpuValue.textContent = cpu;

        const ram = 50 + Math.floor(Math.random() * 30);
        const total = 16;
        const used = (total * ram / 100).toFixed(1);
        dom.ramBar.style.width = `${ram}%`;
        dom.ramValue.textContent = ram;
        dom.ramUsed.textContent = used;
        dom.ramTotal.textContent = total.toFixed(1);

        const disk = 40 + Math.floor(Math.random() * 15);
        const free = Math.floor(256 * (1 - disk / 100));
        dom.diskBar.style.width = `${disk}%`;
        dom.diskValue.textContent = disk;
        dom.diskFree.textContent = free;

        const battery = 70 + Math.floor(Math.random() * 25);
        dom.batteryBar.style.width = `${battery}%`;
        dom.batteryValue.textContent = battery;
        dom.batteryStatus.textContent = battery > 95 ? 'Full' : 'Charging';
    }

    updateStats();
    setInterval(updateStats, 5000);
}

// ============ KEYBOARD SHORTCUTS ============
function initKeyboardShortcuts() {
    dom.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'l') { e.preventDefault(); dom.chatInput.focus(); }
        if (e.ctrlKey && e.key === 'm') { e.preventDefault(); toggleListening(); }
        if (e.ctrlKey && e.key === 'k') { e.preventDefault(); toggleSidePanel(); }
        if (e.key === 'Escape') { setState('standby'); closePlanDrawer(); }
    });
}

// ============ PLAN VIEWER ============
function renderPlan(plan) {
    if (!plan || !plan.steps || plan.steps.length === 0) return;

    const drawer = document.getElementById('planDrawer');
    const goalText = document.getElementById('planGoalText');
    const planSteps = document.getElementById('planSteps');
    const planSummary = document.getElementById('planSummary');

    goalText.textContent = plan.goal ? plan.goal.substring(0, 60) : 'ACTIVE PLAN';
    planSummary.textContent = plan.summary || `${plan.steps.length} steps`;

    const statusEmoji = { done: '✅', running: '🔄', failed: '❌', pending: '⏳', skipped: '➡️' };
    const statusClass = { done: 'step-done', running: 'step-running', failed: 'step-failed', pending: 'step-pending', skipped: 'step-skipped' };

    planSteps.innerHTML = plan.steps.map(step => `
        <div class="plan-step ${statusClass[step.status] || 'step-pending'}" id="step-${step.id}">
            <div class="step-header">
                <span class="step-status-icon">${statusEmoji[step.status] || '⏳'}</span>
                <span class="step-num">STEP ${step.id}</span>
                <span class="step-action">${step.action}</span>
                ${step.duration ? `<span class="step-duration">${step.duration}s</span>` : ''}
            </div>
            <div class="step-desc">${step.description || ''}</div>
            ${step.result ? `<div class="step-result">${escapeHtml(String(step.result).substring(0, 120))}</div>` : ''}
            ${step.error ? `<div class="step-error">⚠️ ${escapeHtml(step.error)}</div>` : ''}
        </div>
    `).join('');

    drawer.classList.add('active');
}

function closePlanDrawer() {
    const drawer = document.getElementById('planDrawer');
    if (drawer) drawer.classList.remove('active');
}

function togglePlanDrawer() {
    const drawer = document.getElementById('planDrawer');
    if (drawer) drawer.classList.toggle('active');
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
                    <button class="fact-delete-btn" onclick="deleteFact('${escapeHtml(f.key)}')" title="Forget this">✕</button>
                </div>
            `).join('')}
        </div>
    `).join('');
}

async function deleteFact(key) {
    await apiCall(`/api/memory/${encodeURIComponent(key)}`, 'DELETE');
    refreshMemory();
}

// ============ TASKS PANEL ============
async function refreshTasks() {
    const data = await apiCall('/api/tasks');
    if (!data) return;

    const tasksList = document.getElementById('tasksList');
    const tasks = data.tasks || [];

    if (tasks.length === 0) {
        tasksList.innerHTML = '<div class="tasks-empty">No background tasks running.</div>';
        return;
    }

    const statusEmoji = { running: '🔄', pending: '⏳', done: '✅', failed: '❌', cancelled: '🚫' };

    tasksList.innerHTML = tasks.map(t => `
        <div class="task-item task-${t.status}">
            <div class="task-header">
                <span class="task-status-icon">${statusEmoji[t.status] || '?'}</span>
                <span class="task-name">${escapeHtml(t.name)}</span>
                <button class="task-cancel-btn" onclick="cancelTask('${t.id}')" title="Cancel">✕</button>
            </div>
            ${t.progress ? `<div class="task-progress">${escapeHtml(t.progress)}</div>` : ''}
            ${t.is_recurring && t.next_run ? `<div class="task-next">Next: ${new Date(t.next_run * 1000).toLocaleTimeString()}</div>` : ''}
        </div>
    `).join('');
}

async function cancelTask(taskId) {
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
        panel.classList.add('open');
        icon.textContent = '✕';
        refreshSideContent();
    } else {
        panel.classList.remove('open');
        icon.textContent = '💾';
    }
}

function switchSideTab(tab) {
    _currentTab = tab;
    document.querySelectorAll('.side-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.side-content').forEach(c => c.classList.remove('active'));

    document.getElementById(`tab${tab.charAt(0).toUpperCase() + tab.slice(1)}`).classList.add('active');
    document.getElementById(`content${tab.charAt(0).toUpperCase() + tab.slice(1)}`).classList.add('active');
    refreshSideContent();
}

function refreshSideContent() {
    if (_currentTab === 'memory') refreshMemory();
    else if (_currentTab === 'tasks') refreshTasks();
    else if (_currentTab === 'history') refreshHistory();
}

// ============ POLLING (when backend connected) ============
function startPolling() {
    // Confirmations are blocking a request while they sit unanswered, so
    // they get their own faster loop.
    setInterval(pollConfirmations, 1500);

    // Poll tasks and plan every 3 seconds
    setInterval(async () => {
        if (!state.backendConnected) return;



        // Refresh side panel if open
        if (_sidePanelOpen) {
            refreshSideContent();
        }

        // Update agent mode chip
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
            // Update tool count in footer and HUD
            if (statusData.tools) {
                const actionCountEl = document.getElementById('actionCount');
                if (actionCountEl) actionCountEl.textContent = `${statusData.tools} TOOLS`;
                const toolCountEl = document.getElementById('toolCount');
                if (toolCountEl) toolCountEl.textContent = `${statusData.tools} LOADED`;
            }
        }
    }, 3000);
}

// Start polling after backend connection confirmed
const _origCheckBackend = checkBackendConnection;
async function checkBackendConnection() {
    const data = await apiCall('/api/status');
    if (data && data.status === 'online') {
        state.backendConnected = true;
        dom.systemStatus.textContent = 'ONLINE';
        dom.systemStatus.className = 'hud-value status-online';
        addMessage('SYSTEM', `Backend connected — ${data.assistant_name} is online (Agent Mode: ${data.agent_mode !== false ? 'ON' : 'OFF'}).`, 'system-msg');

        if (data.llm_model) $('llmProvider').textContent = data.llm_model.toUpperCase();
        if (data.stt_engine) $('sttEngine').textContent = data.stt_engine;
        if (data.tts_engine) $('ttsEngine').textContent = data.tts_engine;

        fetchRealStats();
        setInterval(fetchRealStats, 5000);
        startPolling();
    } else {
        state.backendConnected = false;
        addMessage('SYSTEM', 'Running in demo mode — no backend connected. Launch with: python server.py', 'system-msg');
        simulateSystemStats();
    }
}
