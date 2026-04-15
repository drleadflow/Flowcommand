// Dr. Lead Flow Mission Control - Frontend
// Real-time dashboard for AI agent orchestration

const WS_URL = window.location.hostname === 'localhost' 
    ? 'ws://localhost:8765' 
    : 'wss://web-production-34fc38.up.railway.app:8765';

const API_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8080'
    : window.location.origin;

let ws = null;
let reconnectAttempts = 0;
let agents = {};
let activeTasks = [];

// DOM Elements
const taskModal = document.getElementById('taskModal');
const newTaskBtn = document.getElementById('newTaskBtn');
const closeModal = document.getElementById('closeModal');
const cancelTask = document.getElementById('cancelTask');
const submitTask = document.getElementById('submitTask');
const activityLog = document.getElementById('activityLog');
const connectionStatus = document.getElementById('connectionStatus');

// Initialize
function init() {
    connectWebSocket();
    setupEventListeners();
    updateSystemStats();
}

// WebSocket Connection
function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        console.log('Connected to Mission Control');
        connectionStatus.className = 'status-indicator online';
        connectionStatus.innerHTML = '<span class="dot"></span>Connected';
        reconnectAttempts = 0;
        addToActivityLog('Connected to Mission Control');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };
    
    ws.onclose = () => {
        console.log('Disconnected');
        connectionStatus.className = 'status-indicator offline';
        connectionStatus.innerHTML = '<span class="dot"></span>Disconnected';
        addToActivityLog('Connection lost');
        
        // Reconnect
        reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
        setTimeout(connectWebSocket, delay);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        addToActivityLog('Connection error');
    };
}

// Handle incoming messages
function handleMessage(data) {
    switch (data.type) {
        case 'init':
            agents = data.agents || {};
            activeTasks = data.active_tasks || [];
            renderInitialState();
            break;
            
        case 'task_started':
            addTaskCard(data.task);
            addToActivityLog(`${data.task.agent} started: ${data.task.task.substring(0, 50)}...`);
            break;
            
        case 'task_completed':
            updateTaskCard(data.task);
            addToActivityLog(`${data.task.agent} completed task (${formatDuration(data.task.duration)})`);
            break;
            
        case 'task_error':
            updateTaskCard(data.task, true);
            addToActivityLog(`${data.task.agent} error: ${data.task.error}`);
            break;
            
        case 'pong':
            break;
    }
}

// Render initial state
function renderInitialState() {
    activeTasks.forEach(task => addTaskCard(task));
}

// Add task card to lane
function addTaskCard(task) {
    const lane = document.getElementById(`lane-${task.lane}`);
    if (!lane) return;
    
    const card = createTaskCard(task);
    lane.appendChild(card);
    updateLaneCount(task.lane);
}

// Create task card HTML
function createTaskCard(task) {
    const card = document.createElement('div');
    card.className = 'task-card';
    card.id = `task-${task.id}`;
    
    const agent = agents[task.agent] || { icon: '🤖', name: task.agent };
    
    card.innerHTML = `
        <div class="task-header">
            <span class="task-icon">${agent.icon || '🤖'}</span>
            <span class="task-agent">${agent.name || task.agent}</span>
            <span class="task-status ${task.status}">${task.status}</span>
        </div>
        <div class="task-body">${escapeHtml(task.task)}</div>
        <div class="task-meta">
            <span class="task-time">${formatTime(task.start_time)}</span>
            <span class="task-duration" id="duration-${task.id}"></span>
        </div>
    `;
    
    if (task.status === 'running') {
        startDurationTimer(task.id, task.start_time);
    }
    
    return card;
}

// Update task card
function updateTaskCard(task, isError = false) {
    const card = document.getElementById(`task-${task.id}`);
    if (!card) return;
    
    const statusEl = card.querySelector('.task-status');
    statusEl.className = `task-status ${isError ? 'error' : 'done'}`;
    statusEl.textContent = isError ? 'error' : 'done';
    
    const durationEl = document.getElementById(`duration-${task.id}`);
    if (durationEl) {
        durationEl.textContent = formatDuration(task.duration);
    }
    
    stopDurationTimer(task.id);
    updateLaneCount(task.lane);
}

// Duration timers
const durationTimers = {};

function startDurationTimer(taskId, startTime) {
    const update = () => {
        const el = document.getElementById(`duration-${taskId}`);
        if (!el) {
            stopDurationTimer(taskId);
            return;
        }
        const duration = (Date.now() - new Date(startTime).getTime()) / 1000;
        el.textContent = formatDuration(duration);
    };
    update();
    durationTimers[taskId] = setInterval(update, 1000);
}

function stopDurationTimer(taskId) {
    if (durationTimers[taskId]) {
        clearInterval(durationTimers[taskId]);
        delete durationTimers[taskId];
    }
}

// Update lane count
function updateLaneCount(lane) {
    const laneEl = document.getElementById(`lane-${lane}`);
    const countEl = document.getElementById(`count-${lane}`);
    if (laneEl && countEl) {
        const count = laneEl.querySelectorAll('.task-card').length;
        countEl.textContent = count;
    }
}

// Activity Log
function addToActivityLog(message) {
    const item = document.createElement('span');
    item.className = 'log-item';
    item.textContent = `[${formatTime(new Date().toISOString())}] ${message}`;
    activityLog.appendChild(item);
    activityLog.scrollTop = activityLog.scrollHeight;
    
    // Keep only last 10 items
    while (activityLog.children.length > 10) {
        activityLog.removeChild(activityLog.firstChild);
    }
}

// Event Listeners
function setupEventListeners() {
    newTaskBtn.addEventListener('click', () => {
        taskModal.style.display = 'flex';
    });
    
    closeModal.addEventListener('click', closeTaskModal);
    cancelTask.addEventListener('click', closeTaskModal);
    
    submitTask.addEventListener('click', () => {
        const agent = document.getElementById('agentSelect').value;
        const task = document.getElementById('taskInput').value;
        const context = document.getElementById('contextInput').value;
        
        if (!task) return;
        
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'delegate',
                agent: agent,
                task: task,
                context: context
            }));
            
            addToActivityLog(`Delegated to ${agent || 'auto-route'}: ${task.substring(0, 40)}...`);
            closeTaskModal();
            
            // Clear form
            document.getElementById('taskInput').value = '';
            document.getElementById('contextInput').value = '';
        }
    });
    
    // Close modal on outside click
    taskModal.addEventListener('click', (e) => {
        if (e.target === taskModal) closeTaskModal();
    });
    
    // Ping to keep connection alive
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
        }
    }, 30000);
}

function closeTaskModal() {
    taskModal.style.display = 'none';
}

// System stats
function updateSystemStats() {
    fetch(`${API_URL}/api/health`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('tasksToday').textContent = data.system_stats?.total_tasks || 0;
            document.getElementById('activeCount').textContent = data.active_tasks || 0;
            document.getElementById('tokensToday').textContent = data.system_stats?.tokens_today || 0;
        })
        .catch(() => {
            // Ignore errors
        });
}

// Utilities
function formatTime(isoString) {
    const d = new Date(isoString);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Start
init();
