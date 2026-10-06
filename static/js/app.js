// CoGNETs Edge Arena Live Dashboard Controller

let profitChart = null;
let ws = null;
let roundsData = [];
const botColors = {
    "edge_agent_smart_04": { border: "#18191C", bg: "#18191C", name: "CognitiveSwarmBot" },
    "node_random_01": { border: "#9CA3AF", bg: "#9CA3AF", name: "RandomBot" },
    "node_greedy_02": { border: "#EF4444", bg: "#EF4444", name: "GreedyBot" },
    "node_static_03": { border: "#8B5CF6", bg: "#8B5CF6", name: "StaticBot" }
};

// Initialize Chart.js matching Reference Mockup Aesthetics
function initChart() {
    const ctx = document.getElementById('profitChart').getContext('2d');
    profitChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: Object.keys(botColors).map(botId => ({
                label: botColors[botId].name,
                data: [],
                backgroundColor: botColors[botId].bg,
                borderColor: botColors[botId].border,
                borderRadius: 8,
                borderSkipped: false,
                barPercentage: 0.65,
                categoryPercentage: 0.75
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 350 },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#4B5563', font: { family: 'Outfit', size: 11, weight: '600' } }
                },
                tooltip: {
                    backgroundColor: '#18191C',
                    titleColor: '#FFFFFF',
                    bodyColor: '#E5E7EB',
                    cornerRadius: 8,
                    padding: 10,
                    titleFont: { family: 'Outfit', size: 12, weight: '700' },
                    bodyFont: { family: 'JetBrains Mono', size: 11 }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#8E929B', font: { family: 'Outfit', size: 11, weight: '600' } }
                },
                y: {
                    grid: { color: 'rgba(0, 0, 0, 0.04)' },
                    ticks: {
                        color: '#8E929B',
                        font: { family: 'Outfit', size: 11 },
                        callback: val => '€' + Number(val).toFixed(1)
                    }
                }
            }
        }
    });

    // Chart mode switcher listeners
    document.getElementById('btnChartBars')?.addEventListener('click', (e) => {
        document.getElementById('btnChartBars')?.classList.add('active');
        document.getElementById('btnChartLines')?.classList.remove('active');
        profitChart.config.type = 'bar';
        profitChart.data.datasets.forEach(ds => {
            ds.borderRadius = 8;
            ds.tension = 0;
            ds.fill = false;
        });
        profitChart.update();
    });

    document.getElementById('btnChartLines')?.addEventListener('click', (e) => {
        document.getElementById('btnChartLines')?.classList.add('active');
        document.getElementById('btnChartBars')?.classList.remove('active');
        profitChart.config.type = 'line';
        profitChart.data.datasets.forEach(ds => {
            ds.borderRadius = 0;
            ds.tension = 0.35;
            ds.fill = ds.label.includes('Cognitive');
            ds.backgroundColor = ds.label.includes('Cognitive') ? 'rgba(24, 25, 28, 0.06)' : 'transparent';
        });
        profitChart.update();
    });
}

// WebSocket Connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/arena`;
    const statusElem = document.getElementById('connectionStatus');

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        statusElem.querySelector('.status-dot').className = 'status-dot green';
        statusElem.querySelector('.status-text').textContent = 'Live WS Connected';
    };

    ws.onclose = () => {
        statusElem.querySelector('.status-dot').className = 'status-dot yellow';
        statusElem.querySelector('.status-text').textContent = 'Reconnecting...';
        setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = () => {
        ws.close();
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWsMessage(msg);
        } catch (e) {
            console.error("WS parse error:", e);
        }
    };
}

let currentNodes = [];

function handleWsMessage(msg) {
    switch (msg.type) {
        case "INIT_STATE":
            currentNodes = msg.data.nodes || [];
            if (msg.data.leaderboard) renderLeaderboard(msg.data.leaderboard);
            if (msg.data.active_auction) renderActiveAuction(msg.data.active_auction);
            if (msg.data.history && msg.data.history.length > 0) {
                // Find latest history item with deliberation steps
                const lastWithTrace = [...msg.data.history].reverse().find(h => h.deliberation_steps || h.reasoning_trace);
                if (lastWithTrace) renderDeliberationStream(lastWithTrace);
            }
            renderTopologyGrid(currentNodes, {}, null);
            break;

        case "SHOWCASE_TRIGGERED":
            const badge = document.getElementById('auctionStatusBadge');
            badge.textContent = '⭐ GOLDEN DEMO ACTIVE';
            badge.style.borderColor = 'var(--gold)';
            badge.style.color = 'var(--gold)';
            break;

        case "AUCTION_OPENED":
            renderActiveAuction(msg.data);
            break;

        case "BID_RECEIVED":
            renderIncomingBid(msg.data);
            if (msg.data.deliberation_steps || msg.data.reasoning_trace) {
                renderDeliberationStream(msg.data);
            }
            break;

        case "AUCTION_CLEARED":
            handleAuctionCleared(msg.data);
            break;

        case "SIMULATION_RESET":
            resetClientState();
            break;
    }
}

function renderActiveAuction(auction) {
    document.getElementById('kpiRound').textContent = `Round #${auction.round_number}`;
    document.getElementById('kpiTaskType').textContent = auction.task.task_type;
    document.getElementById('auctionStatusBadge').textContent = 'AUCTION OPEN';
    document.getElementById('auctionStatusBadge').style.borderColor = 'var(--cyan)';

    // Update Task Spec Box
    const task = auction.task;
    document.getElementById('taskName').textContent = task.task_type;
    document.getElementById('taskCpu').textContent = `${task.required_cpu} Cores`;
    document.getElementById('taskRam').textContent = `${task.required_ram_mb} MB`;
    document.getElementById('taskCost').textContent = `€${task.base_cost.toFixed(2)}`;
    document.getElementById('taskBudget').textContent = `€${task.max_budget.toFixed(2)}`;
    document.getElementById('taskDeadline').textContent = `${task.deadline_sec.toFixed(1)}s`;

    // Clear bids visual floor for new round
    const bidsList = document.getElementById('bidsVisualList');
    bidsList.innerHTML = '';
}

function renderIncomingBid(bid) {
    const bidsList = document.getElementById('bidsVisualList');
    const existing = bidsList.querySelector(`[data-node="${bid.node_id}"]`);
    if (existing) return;

    const botConf = botColors[bid.node_id] || { name: bid.node_id, border: '#FFF' };
    const item = document.createElement('div');
    item.className = 'bid-item';
    item.dataset.node = bid.node_id;
    item.innerHTML = `
        <span class="bid-bot-name">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${botConf.border};"></span>
            ${botConf.name}
        </span>
        <span class="bid-price-tag" style="color: ${botConf.border}">€${bid.bid_price.toFixed(3)}</span>
    `;
    bidsList.appendChild(item);
}

function renderDeliberationStream(data) {
    const stream = document.getElementById('deliberationStream');
    const badge = document.getElementById('traceConfidenceBadge');
    const ribbon = document.getElementById('sponsorTagsRibbon');
    if (!stream) return;

    // Update confidence badge
    if (badge) {
        const confPct = Math.round((data.confidence || 0.95) * 100);
        let statusText = `${confPct}% Confidence (CONSENSUS)`;
        let statusColor = 'var(--emerald)';
        let statusBg = 'rgba(16, 185, 129, 0.15)';
        let statusBorder = 'rgba(16, 185, 129, 0.3)';

        // Check if any step had objection
        const hasObjection = data.deliberation_steps && data.deliberation_steps.some(s => s.status === 'OBJECTION');
        if (hasObjection) {
            statusText = `Objection Resolved (${confPct}%)`;
            statusColor = 'var(--gold)';
            statusBg = 'rgba(245, 158, 11, 0.15)';
            statusBorder = 'rgba(245, 158, 11, 0.3)';
        }
        badge.textContent = statusText;
        badge.style.color = statusColor;
        badge.style.background = statusBg;
        badge.style.borderColor = statusBorder;
    }

    // Update sponsor tags ribbon
    if (ribbon && data.sponsor_telemetry) {
        const tel = data.sponsor_telemetry;
        let html = '';

        // Groq LPU inference tag
        const groqBadge = document.getElementById('groqStatusBadge');
        if (tel.groq_inference) {
            const isLive = tel.groq_inference.status === 'ACTIVE_LPU';
            const latText = isLive ? `${tel.groq_inference.latency_ms}ms` : 'Ready';
            html += `<span class="sponsor-chip" style="border-color: rgba(249, 115, 22, 0.5); color: #FB923C; font-weight:700;">⚡ Groq LPU: ${latText}</span>`;
            if (groqBadge && isLive) {
                groqBadge.textContent = `⚡ Groq LPU (${tel.groq_inference.latency_ms}ms)`;
                groqBadge.style.color = '#FB923C';
            }
        } else {
            html += `<span class="sponsor-chip" style="border-color: rgba(249, 115, 22, 0.4); color: #FB923C;">⚡ Groq LPU: Real-Time AI</span>`;
        }

        // Sponsor Track Integrations (Simulated/Verified)
        if (tel.nvidia_guardrail) {
            const status = tel.nvidia_guardrail.status === 'COMPLIANT' || tel.nvidia_guardrail.status === 'POLICY_APPROVED' ? 'PASS' : 'FLAGGED';
            html += `<span class="sponsor-chip">🛡️ NVIDIA NeMo: ${status}</span>`;
        } else {
            html += `<span class="sponsor-chip">🛡️ NVIDIA NeMo: SLA Policy</span>`;
        }
        if (tel.meterless_metering) {
            html += `<span class="sponsor-chip">📊 Meterless: Micro-Metered (${tel.meterless_metering.units || 'Active'})</span>`;
        } else {
            html += `<span class="sponsor-chip">📊 Meterless: Micro-Metering</span>`;
        }
        const zet = tel.zetaris_telemetry || tel.zetaris_virtualization;
        if (zet) {
            const lat = zet.latency_ms || 1.2;
            html += `<span class="sponsor-chip">🌐 Zetaris: ${lat}ms Query</span>`;
        } else {
            html += `<span class="sponsor-chip">🌐 Zetaris: Virtualized Edge</span>`;
        }
        ribbon.innerHTML = html;
    }

    // Render steps
    if (data.deliberation_steps && data.deliberation_steps.length > 0) {
        stream.innerHTML = '';
        data.deliberation_steps.forEach((step) => {
            const role = (step.role || '').toUpperCase();
            let roleClass = 'synthesizer';
            let roleIcon = '🧠';
            let roleTitle = 'Consensus Synthesizer';

            if (role.includes('ANALYST')) {
                roleClass = 'analyst';
                roleIcon = '📈';
                roleTitle = 'Market Analyst (Proposer)';
            } else if (role.includes('GUARDIAN')) {
                roleClass = (step.status === 'OBJECTION') ? 'objection' : 'guardian';
                roleIcon = (step.status === 'OBJECTION') ? '⚠️' : '🛡️';
                roleTitle = (step.status === 'OBJECTION') ? 'Capacity Guardian (Objection)' : 'Capacity Guardian (Critic)';
            } else if (role.includes('ARBITRAGE')) {
                roleClass = 'arbitrage';
                roleIcon = '☀️';
                roleTitle = 'Green Arbitrage Specialist';
            }

            const bidTag = (step.proposed_bid !== null && step.proposed_bid !== undefined)
                ? `<span style="font-family:var(--font-mono); font-weight:700; color:var(--cyan); margin-left:auto;">€${step.proposed_bid.toFixed(3)}</span>`
                : '';

            const stepEl = document.createElement('div');
            stepEl.className = `agent-thought-item ${roleClass}`;
            stepEl.innerHTML = `
                <div class="thought-role">
                    <span>${roleIcon} ${roleTitle}</span>
                    ${bidTag}
                </div>
                <div class="thought-body">${step.thought}</div>
            `;
            stream.appendChild(stepEl);
        });
        stream.scrollTop = stream.scrollHeight;
    } else if (data.reasoning_trace) {
        stream.innerHTML = `
            <div class="agent-thought-item synthesizer">
                <div class="thought-role">
                    <span>🧠 Multi-Agent Consensus</span>
                </div>
                <div class="thought-body">${data.reasoning_trace}</div>
            </div>
        `;
    }
}

function handleAuctionCleared(data) {
    const outcome = data.outcome;
    document.getElementById('auctionStatusBadge').textContent = 'ROUND CLEARED';
    document.getElementById('auctionStatusBadge').style.borderColor = 'var(--emerald)';

    // If winner has deliberation trace, keep stream aligned
    if (outcome.deliberation_steps || outcome.reasoning_trace) {
        renderDeliberationStream(outcome);
    }

    // Highlight winner in bids list
    const bidsList = document.getElementById('bidsVisualList');
    if (outcome.winner_node_id) {
        const winnerItem = bidsList.querySelector(`[data-node="${outcome.winner_node_id}"]`);
        if (winnerItem) {
            winnerItem.classList.add('winner');
            winnerItem.innerHTML += `
                <span style="color: var(--emerald); font-weight:700; font-size:0.75rem;">
                    🏆 WON @ €${outcome.clearing_price.toFixed(3)} (+€${outcome.profit.toFixed(2)})
                </span>
            `;
        }
    }

    // Update Leaderboard
    if (data.leaderboard) {
        renderLeaderboard(data.leaderboard);
        updateChart(outcome.round_number, data.leaderboard);
    }

    // Update Hardware Telemetry & Cluster Topology Grid
    if (data.nodes_utilization) {
        renderTelemetry(data.nodes_utilization);
        renderTopologyGrid(currentNodes, data.nodes_utilization, outcome.winner_node_id);
    }
}

function renderLeaderboard(leaderboard) {
    const tbody = document.getElementById('leaderboardBody');
    tbody.innerHTML = '';

    if (leaderboard.length > 0) {
        const top = leaderboard[0];
        document.getElementById('kpiLeader').textContent = top.name.split(' ')[0];
        document.getElementById('kpiLeaderProfit').textContent = `+€${top.cumulative_profit.toFixed(2)}`;
    }

    leaderboard.forEach((row, idx) => {
        const tr = document.createElement('tr');
        const rankClass = idx === 0 ? 'rank-1' : idx === 1 ? 'rank-2' : idx === 2 ? 'rank-3' : '';
        const isChampion = row.node_id.includes('smart');

        tr.innerHTML = `
            <td class="rank-cell ${rankClass}">#${idx + 1}</td>
            <td class="agent-name-cell ${isChampion ? 'champion' : ''}">
                ${row.name}
            </td>
            <td>${row.auctions_won} / ${row.bids_placed}</td>
            <td>${row.win_rate_pct}%</td>
            <td style="font-family: var(--font-mono); font-weight: 700; color: ${row.cumulative_profit >= 0 ? 'var(--emerald)' : 'var(--rose)'}">
                €${row.cumulative_profit.toFixed(2)}
            </td>
            <td>
                <span class="sla-badge ${row.sla_violations === 0 ? 'clean' : 'warning'}">
                    ${row.sla_violations === 0 ? 'NeMo Clean' : row.sla_violations + ' Flags'}
                </span>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function updateChart(roundNumber, leaderboard) {
    if (!profitChart) return;

    if (profitChart.data.labels.length > 8) {
        profitChart.data.labels.shift();
        profitChart.data.datasets.forEach(ds => ds.data.shift());
    }

    profitChart.data.labels.push(`R${roundNumber}`);

    const botMap = {};
    leaderboard.forEach(item => {
        botMap[item.node_id] = item.cumulative_profit;
    });

    profitChart.data.datasets.forEach(ds => {
        // match by bot id key
        const botId = Object.keys(botColors).find(k => botColors[k].name === ds.label);
        if (botId && botMap[botId] !== undefined) {
            ds.data.push(botMap[botId]);
        } else {
            ds.data.push(0);
        }
    });

    profitChart.update();
}

function renderTelemetry(telemetry) {
    const list = document.getElementById('telemetryList');
    list.innerHTML = '';

    for (const [nodeId, util] of Object.entries(telemetry)) {
        const botConf = botColors[nodeId] || { name: nodeId, border: '#FFF' };
        const card = document.createElement('div');
        card.className = 'node-telemetry-card';

        const cpuClass = util.cpu_pct > 80 ? 'red' : util.cpu_pct > 50 ? 'yellow' : 'green';
        const ramClass = util.ram_pct > 80 ? 'red' : util.ram_pct > 50 ? 'yellow' : 'green';

        card.innerHTML = `
            <div class="node-tel-header">
                <span style="color:${botConf.border};">${botConf.name}</span>
                <span style="color:var(--text-sub);">${util.active_tasks} Active Tasks</span>
            </div>
            <div class="meter-wrapper">
                <span>CPU (${util.cpu_used} Cores)</span>
                <div class="progress-bar">
                    <div class="progress-fill ${cpuClass}" style="width: ${util.cpu_pct}%"></div>
                </div>
                <span>${util.cpu_pct}%</span>
            </div>
            <div class="meter-wrapper">
                <span>RAM (${util.ram_used} MB)</span>
                <div class="progress-bar">
                    <div class="progress-fill ${ramClass}" style="width: ${util.ram_pct}%"></div>
                </div>
                <span>${util.ram_pct}%</span>
            </div>
        `;
        list.appendChild(card);
    }
}

function renderTopologyGrid(nodes, telemetry, winnerNodeId) {
    const grid = document.getElementById('topologyGrid');
    if (!grid) return;

    if (!nodes || nodes.length === 0) {
        // Fallback default nodes if not yet sent
        nodes = [
            { node_id: "edge_agent_smart_04", name: "CognitiveSwarmBot", cpu_cores: 8, green_energy_ratio: 0.85, location_zone: "VALENCIA-ZONE-1" },
            { node_id: "node_greedy_02", name: "GreedyBot", cpu_cores: 6, green_energy_ratio: 0.40, location_zone: "VALENCIA-ZONE-2" },
            { node_id: "node_static_03", name: "StaticBot", cpu_cores: 8, green_energy_ratio: 0.50, location_zone: "VALENCIA-ZONE-3" },
            { node_id: "node_random_01", name: "RandomBot", cpu_cores: 6, green_energy_ratio: 0.30, location_zone: "VALENCIA-ZONE-4" }
        ];
    }

    grid.innerHTML = '';

    nodes.forEach(node => {
        const util = telemetry[node.node_id] || { cpu_pct: 0, active_tasks: 0, cpu_used: 0 };
        const botConf = botColors[node.node_id] || { name: node.name, border: '#FFF' };
        const isWinner = (winnerNodeId === node.node_id);
        const isSolar = (node.green_energy_ratio >= 0.70);
        
        // 8 visual core blocks
        const totalBlocks = 8;
        const activeBlocks = Math.min(totalBlocks, Math.round((util.cpu_pct / 100) * totalBlocks));
        const isOverloaded = util.cpu_pct > 85;

        let coreBlocksHtml = '';
        for (let i = 0; i < totalBlocks; i++) {
            if (i < activeBlocks) {
                const blockClass = isOverloaded ? 'active-hot' : 'active-clean';
                coreBlocksHtml += `<div class="core-block ${blockClass}"></div>`;
            } else {
                coreBlocksHtml += `<div class="core-block"></div>`;
            }
        }

        let statusText = 'IDLE';
        let statusClass = 'idle';
        if (isOverloaded) {
            statusText = 'OVERLOADED';
            statusClass = 'overload';
        } else if (util.active_tasks > 0) {
            statusText = `${util.active_tasks} RUNNING`;
            statusClass = 'active';
        }

        const tile = document.createElement('div');
        tile.className = `node-tile ${isWinner ? 'claimed-pulse' : ''}`;
        tile.innerHTML = `
            <div class="tile-top">
                <div>
                    <div class="tile-title" style="color: ${botConf.border}">${botConf.name.split(' ')[0]}</div>
                    <div class="tile-zone">${node.location_zone || 'EU-VALENCIA'}</div>
                </div>
                <div class="tile-badge-power ${isSolar ? 'power-solar' : 'power-grid'}">
                    ${isSolar ? '☀️ 85% Solar' : '⚡ Grid Power'}
                </div>
            </div>

            <div>
                <div class="core-matrix-label">
                    <span>Cores Allocation (${util.cpu_used || 0}/${node.cpu_cores}c)</span>
                    <span>${util.cpu_pct}%</span>
                </div>
                <div class="core-matrix">
                    ${coreBlocksHtml}
                </div>
            </div>

            <div class="tile-status-bar">
                <span class="status-pill ${statusClass}">${statusText}</span>
                <span style="color: var(--text-sub);">${node.hardware_type || 'Edge Cluster'}</span>
            </div>
        `;
        grid.appendChild(tile);
    });
}

function resetClientState() {
    if (profitChart) {
        profitChart.data.labels = [];
        profitChart.data.datasets.forEach(ds => ds.data = []);
        profitChart.update();
    }
    document.getElementById('bidsVisualList').innerHTML = '<p class="empty-state">Waiting for next auction cycle...</p>';
    
    const stream = document.getElementById('deliberationStream');
    if (stream) {
        stream.innerHTML = `
            <div class="agent-thought-item placeholder-thought">
                <span class="thought-role">🤖 CognitiveSwarm Team</span>
                <p class="thought-body">Multi-Agent Deliberation loop standing by for next auction round...</p>
            </div>
        `;
    }
    const badge = document.getElementById('traceConfidenceBadge');
    if (badge) {
        badge.textContent = 'Awaiting Decision';
        badge.style.color = 'var(--emerald)';
        badge.style.background = 'rgba(16, 185, 129, 0.15)';
        badge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
    }
}

// Attach UI Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    connectWebSocket();

    const btnGolden = document.getElementById('btnGoldenDemo');
    if (btnGolden) {
        btnGolden.onclick = () => {
            fetch('/api/v1/simulation/demo-preset', { method: 'POST' });
        };
    }

    document.getElementById('btnStart').onclick = () => fetch('/api/v1/simulation/start', { method: 'POST' });
    document.getElementById('btnPause').onclick = () => fetch('/api/v1/simulation/pause', { method: 'POST' });
    document.getElementById('btnReset').onclick = () => fetch('/api/v1/simulation/reset', { method: 'POST' });

    document.querySelectorAll('.btn-speed').forEach(btn => {
        btn.onclick = (e) => {
            document.querySelectorAll('.btn-speed').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const speed = parseFloat(btn.dataset.speed);
            fetch(`/api/v1/simulation/speed?speed=${speed}`, { method: 'POST' });
        };
    });
});
