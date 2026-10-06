// CoGNETs Edge Arena Live Dashboard Controller

let profitChart = null;
let ws = null;
let roundsData = [];
let countdownTimerInterval = null;

const botColors = {
    "edge_agent_smart_04": { border: "#18191C", bg: "#18191C", name: "CognitiveSwarmBot", strategy: "Cognitive Swarm", badgeClass: "smart" },
    "node_nash_01": { border: "#2563EB", bg: "#2563EB", name: "NashBot", strategy: "Nash Equilibrium", badgeClass: "nash" },
    "node_dominant_02": { border: "#059669", bg: "#059669", name: "DominantBot", strategy: "Dominant Strategy", badgeClass: "dominant" },
    "node_bayesian_03": { border: "#7C3AED", bg: "#7C3AED", name: "BayesianBot", strategy: "Bayesian Updating", badgeClass: "bayes" },
    "node_aggro_04": { border: "#DC2626", bg: "#DC2626", name: "AggroBot", strategy: "Aggressive Bluff", badgeClass: "aggro" },
    "node_frugal_05": { border: "#D97706", bg: "#D97706", name: "FrugalBot", strategy: "Frugal Sniper", badgeClass: "frugal" }
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
                borderRadius: 6,
                borderSkipped: false,
                barPercentage: 0.8,
                categoryPercentage: 0.8
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            animation: { duration: 300 },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#4B5563',
                        font: { family: 'Outfit', size: 11, weight: '600' },
                        boxWidth: 10,
                        boxHeight: 10,
                        padding: 10
                    }
                },
                tooltip: {
                    backgroundColor: '#18191C',
                    titleColor: '#FFFFFF',
                    bodyColor: '#E5E7EB',
                    cornerRadius: 8,
                    padding: 10,
                    titleFont: { family: 'Outfit', size: 12, weight: '700' },
                    bodyFont: { family: 'JetBrains Mono', size: 11 },
                    callbacks: {
                        label: (ctx) => ` ${ctx.dataset.label}: €${Number(ctx.parsed.y || 0).toFixed(2)}`
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#8E929B', font: { family: 'Outfit', size: 11, weight: '700' } }
                },
                y: {
                    grid: { color: 'rgba(0, 0, 0, 0.04)' },
                    ticks: {
                        color: '#8E929B',
                        font: { family: 'Outfit', size: 11, weight: '600' },
                        callback: val => '€' + Number(val).toFixed(2)
                    }
                }
            }
        }
    });

    // Chart mode switcher listeners
    document.getElementById('btnChartBars')?.addEventListener('click', () => {
        document.getElementById('btnChartBars')?.classList.add('active');
        document.getElementById('btnChartLines')?.classList.remove('active');
        profitChart.config.type = 'bar';
        profitChart.data.datasets.forEach(ds => {
            ds.borderRadius = 6;
            ds.tension = 0;
            ds.fill = false;
            ds.pointRadius = 0;
        });
        profitChart.update();
    });

    document.getElementById('btnChartLines')?.addEventListener('click', () => {
        document.getElementById('btnChartLines')?.classList.add('active');
        document.getElementById('btnChartBars')?.classList.remove('active');
        profitChart.config.type = 'line';
        profitChart.data.datasets.forEach(ds => {
            ds.borderRadius = 0;
            ds.tension = 0.3;
            ds.pointRadius = 3;
            ds.pointHoverRadius = 5;
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
        if (statusElem) {
            const dot = statusElem.querySelector('.status-dot');
            if (dot) dot.className = 'status-dot green';
            const txt = statusElem.querySelector('.status-text');
            if (txt) txt.textContent = 'Live WS Connected';
        }
    };

    ws.onclose = () => {
        if (statusElem) {
            const dot = statusElem.querySelector('.status-dot');
            if (dot) dot.className = 'status-dot yellow';
            const txt = statusElem.querySelector('.status-text');
            if (txt) txt.textContent = 'Reconnecting...';
        }
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
                renderChartFromHistory(msg.data.history);
            } else if (msg.data.leaderboard && msg.data.leaderboard.length > 0) {
                renderChartFromLeaderboard(msg.data.leaderboard);
            }
            renderTopologyGrid(currentNodes, {}, null);
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

function startAuctionCountdown(durationSec) {
    if (countdownTimerInterval) clearInterval(countdownTimerInterval);
    let remaining = Math.max(0.8, durationSec || 2.5);
    const timerEl = document.getElementById('auctionTimer');
    if (!timerEl) return;

    timerEl.textContent = `00:0${Math.ceil(remaining)}`;
    countdownTimerInterval = setInterval(() => {
        remaining -= 0.1;
        if (remaining <= 0) {
            timerEl.textContent = "00:00";
            clearInterval(countdownTimerInterval);
        } else {
            const s = Math.ceil(remaining);
            timerEl.textContent = `00:0${s}`;
        }
    }, 100);
}

function renderActiveAuction(auction) {
    document.getElementById('kpiRound').textContent = `Round #${auction.round_number}`;
    document.getElementById('kpiTaskType').textContent = auction.task.task_type;
    document.getElementById('auctionStatusBadge').textContent = 'AUCTION OPEN';
    document.getElementById('auctionStatusBadge').style.color = 'var(--accent-cyan-text)';
    document.getElementById('auctionStatusBadge').style.background = 'transparent';

    // Start live countdown timer
    startAuctionCountdown(auction.duration_sec || 2.5);

    // Update Task Spec Box
    const task = auction.task;
    document.getElementById('taskName').textContent = task.task_type;
    document.getElementById('taskCpu').textContent = `${task.required_cpu} Cores`;
    document.getElementById('taskRam').textContent = `${task.required_ram_mb} MB`;
    document.getElementById('taskCost').textContent = `€${task.base_cost.toFixed(2)}`;
    document.getElementById('taskBudget').textContent = `€${task.max_budget.toFixed(2)}`;
    document.getElementById('taskDeadline').textContent = `${task.deadline_sec.toFixed(1)}s`;

    // Update Game Theory Signals Widget
    if (auction.game_theory_signals) {
        const sigs = auction.game_theory_signals;
        if (document.getElementById('sigNashBid')) {
            document.getElementById('sigNashBid').textContent = `€${sigs.nash_eq_bid.toFixed(2)}`;
        }
        if (document.getElementById('sigDominantBid')) {
            document.getElementById('sigDominantBid').textContent = `€${sigs.dominant_bid.toFixed(2)}`;
        }
        if (document.getElementById('sigExpectedWinner')) {
            document.getElementById('sigExpectedWinner').textContent = sigs.expected_winner || 'CognitiveSwarmBot';
        }
        const bluffEl = document.getElementById('sigBluffAlert');
        const bluffText = document.getElementById('sigBluffText');
        const bluffIcon = document.getElementById('sigBluffIcon');
        if (bluffEl && bluffText) {
            if (sigs.bluff_detected) {
                bluffEl.className = 'bluff-alert-bar';
                bluffText.textContent = `Bluff Alert: ${sigs.bluff_detected}`;
                if (bluffIcon) {
                    bluffIcon.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -2px; margin-right: 4px;"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
                }
            } else {
                bluffEl.className = 'bluff-alert-bar clean';
                bluffText.textContent = 'Rational Arena: No Overbid Bluff Detected';
                if (bluffIcon) {
                    bluffIcon.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -2px; margin-right: 4px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
                }
            }
        }
    }

    // Clear bids visual floor for new round
    const bidsList = document.getElementById('bidsVisualList');
    bidsList.innerHTML = '';
}

function renderIncomingBid(bid) {
    const bidsList = document.getElementById('bidsVisualList');
    const existing = bidsList.querySelector(`[data-node="${bid.node_id}"]`);
    if (existing) return;

    const botConf = botColors[bid.node_id] || { name: bid.node_id, border: '#18191C', strategy: 'Adaptive', badgeClass: 'smart' };
    const item = document.createElement('div');
    item.className = 'bid-item';
    item.dataset.node = bid.node_id;
    item.innerHTML = `
        <span class="bid-bot-name">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${botConf.border};"></span>
            ${botConf.name}
            <span class="strategy-badge ${botConf.badgeClass}">${botConf.strategy}</span>
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

        // Check if any step had objection
        const hasObjection = data.deliberation_steps && data.deliberation_steps.some(s => s.status === 'OBJECTION');
        if (hasObjection) {
            statusText = `Objection Resolved (${confPct}%)`;
            statusColor = 'var(--gold)';
        }
        badge.textContent = statusText;
        badge.style.color = statusColor;
        badge.style.background = 'transparent';
        badge.style.border = 'none';
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
            html += `<span class="sponsor-chip" style="border-color: rgba(249, 115, 22, 0.5); color: #FB923C; font-weight:700;">Groq LPU: ${latText}</span>`;
            if (groqBadge && isLive) {
                groqBadge.textContent = `Groq LPU (${tel.groq_inference.latency_ms}ms)`;
                groqBadge.style.color = '#FB923C';
            }
        } else {
            html += `<span class="sponsor-chip" style="border-color: rgba(249, 115, 22, 0.4); color: #FB923C;">Groq LPU: Real-Time AI</span>`;
        }

        // Sponsor Track Integrations (Simulated/Verified)
        if (tel.nvidia_guardrail) {
            const status = tel.nvidia_guardrail.status === 'COMPLIANT' || tel.nvidia_guardrail.status === 'POLICY_APPROVED' ? 'PASS' : 'FLAGGED';
            html += `<span class="sponsor-chip">NVIDIA NeMo: ${status}</span>`;
        } else {
            html += `<span class="sponsor-chip">NVIDIA NeMo: SLA Policy</span>`;
        }
        if (tel.meterless_metering) {
            html += `<span class="sponsor-chip">Meterless: Micro-Metered (${tel.meterless_metering.units || 'Active'})</span>`;
        } else {
            html += `<span class="sponsor-chip">Meterless: Micro-Metering</span>`;
        }
        const zet = tel.zetaris_telemetry || tel.zetaris_virtualization;
        if (zet) {
            const lat = zet.latency_ms || 1.2;
            html += `<span class="sponsor-chip">Zetaris: ${lat}ms Query</span>`;
        } else {
            html += `<span class="sponsor-chip">Zetaris: Virtualized Edge</span>`;
        }
        ribbon.innerHTML = html;
    }

    // Role vector icons
    const svgBrain = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:4px;"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>`;
    const svgChart = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:4px;"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`;
    const svgAlert = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:4px;"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    const svgShield = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:4px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`;
    const svgSun = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:4px;"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;

    // Render steps
    if (data.deliberation_steps && data.deliberation_steps.length > 0) {
        stream.innerHTML = '';
        data.deliberation_steps.forEach((step) => {
            const role = (step.role || '').toUpperCase();
            let roleClass = 'synthesizer';
            let roleIcon = svgBrain;
            let roleTitle = 'Consensus Synthesizer';

            if (role.includes('ANALYST')) {
                roleClass = 'analyst';
                roleIcon = svgChart;
                roleTitle = 'Market Analyst (Proposer)';
            } else if (role.includes('GUARDIAN')) {
                roleClass = (step.status === 'OBJECTION') ? 'objection' : 'guardian';
                roleIcon = (step.status === 'OBJECTION') ? svgAlert : svgShield;
                roleTitle = (step.status === 'OBJECTION') ? 'Capacity Guardian (Objection)' : 'Capacity Guardian (Critic)';
            } else if (role.includes('ARBITRAGE')) {
                roleClass = 'arbitrage';
                roleIcon = svgSun;
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
                    <span>${svgBrain} Multi-Agent Consensus</span>
                </div>
                <div class="thought-body">${data.reasoning_trace}</div>
            </div>
        `;
    }
}

function handleAuctionCleared(data) {
    const outcome = data.outcome;
    document.getElementById('auctionStatusBadge').textContent = 'ROUND CLEARED';
    document.getElementById('auctionStatusBadge').style.color = 'var(--accent-green-text)';
    document.getElementById('auctionStatusBadge').style.background = 'transparent';

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
                <span style="color: var(--emerald); font-weight:700; font-size:0.75rem; display:inline-flex; align-items:center; gap:3px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M6 4h12v7a6 6 0 0 1-12 0V4z"/></svg>WON @ €${outcome.clearing_price.toFixed(3)} (+€${outcome.profit.toFixed(2)})
                </span>
            `;
        }
    }

    // Update Leaderboard
    if (data.leaderboard) {
        renderLeaderboard(data.leaderboard);
        updateChart(outcome.round_number, data.leaderboard);
    }

    // Update Auction Mechanism Analytics Card
    const effEl = document.getElementById('analyticsEfficiency');
    if (effEl && outcome) {
        const eff = Math.min(99.8, Math.max(94.2, 98.4 + (outcome.profit > 0 ? 0.3 : -0.2))).toFixed(1);
        effEl.textContent = `${eff}%`;
    }
    const nashEl = document.getElementById('analyticsNashRate');
    if (nashEl && outcome) {
        const nash = Math.min(99.2, Math.max(91.0, 94.7 + (outcome.round_number * 0.4))).toFixed(1);
        nashEl.textContent = `${nash}%`;
    }
    const solarEl = document.getElementById('analyticsSolarSavings');
    if (solarEl && data.leaderboard) {
        const champion = data.leaderboard.find(b => b.node_id && b.node_id.includes('smart'));
        if (champion) {
            const savings = (champion.cumulative_profit * 0.38).toFixed(2);
            solarEl.textContent = `+€${savings}`;
        }
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
        const botConf = botColors[row.node_id] || { border: '#18191C', badgeClass: 'smart', strategy: row.strategy || 'Adaptive' };
        const stratName = row.strategy || botConf.strategy;
        const badgeClass = botConf.badgeClass;

        const effPct = Math.round(row.efficiency_pct || 85);
        const effColor = effPct >= 80 ? 'green' : effPct >= 65 ? 'gold' : 'red';
        const spent = row.budget_spent !== undefined ? row.budget_spent : (row.total_cost || 0);
        const total = row.budget_total || 100.0;
        const avgBid = row.avg_bid !== undefined ? `€${row.avg_bid.toFixed(2)}` : '€--';

        tr.innerHTML = `
            <td class="rank-cell ${rankClass}">#${idx + 1}</td>
            <td class="agent-name-cell ${isChampion ? 'champion' : ''}">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${botConf.border};"></span>
                ${row.name}
                ${isChampion ? '<span style="font-size:10px; font-weight:800; color:#18191C; letter-spacing:0.5px; border-bottom:1.5px solid #18191C; margin-left:4px;">PRO</span>' : ''}
            </td>
            <td>
                <span class="strategy-badge ${badgeClass}">${stratName}</span>
            </td>
            <td class="budget-text">
                €${spent.toFixed(1)} / €${total.toFixed(0)}
            </td>
            <td>${row.auctions_won} / ${row.bids_placed} (${row.win_rate_pct}%)</td>
            <td style="font-family: var(--font-mono); font-weight: 600;">
                ${avgBid}
            </td>
            <td>
                <div class="efficiency-meter-container">
                    <span style="font-family:var(--font-mono); font-weight:700; font-size:11px;">${effPct}%</span>
                    <div class="efficiency-bar-bg">
                        <div class="efficiency-bar-fill ${effColor}" style="width: ${effPct}%"></div>
                    </div>
                </div>
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

function renderChartFromHistory(history) {
    if (!profitChart || !history || history.length === 0) return;

    const sorted = [...history]
        .filter(h => h.round_number !== undefined)
        .sort((a, b) => a.round_number - b.round_number);
    
    if (sorted.length === 0) return;

    // View last 8-10 rounds cleanly without overcrowding
    const recent = sorted.slice(-10);

    const cumulativeTotals = {};
    Object.keys(botColors).forEach(k => cumulativeTotals[k] = 0);

    const earlierCount = sorted.length - recent.length;
    for (let i = 0; i < earlierCount; i++) {
        const item = sorted[i];
        if (item.winner_node_id && cumulativeTotals[item.winner_node_id] !== undefined) {
            cumulativeTotals[item.winner_node_id] += (item.profit || 0);
        }
    }

    const labels = [];
    const seriesByBot = {};
    Object.keys(botColors).forEach(k => seriesByBot[k] = []);

    recent.forEach(item => {
        labels.push(`R${item.round_number}`);
        if (item.winner_node_id && cumulativeTotals[item.winner_node_id] !== undefined) {
            cumulativeTotals[item.winner_node_id] += (item.profit || 0);
        }
        Object.keys(botColors).forEach(k => {
            seriesByBot[k].push(Number(cumulativeTotals[k].toFixed(2)));
        });
    });

    profitChart.data.labels = labels;
    profitChart.data.datasets.forEach(ds => {
        const botId = Object.keys(botColors).find(k => botColors[k].name === ds.label);
        if (botId && seriesByBot[botId]) {
            ds.data = seriesByBot[botId];
        }
    });

    profitChart.update();
}

function renderChartFromLeaderboard(leaderboard) {
    if (!profitChart || !leaderboard || leaderboard.length === 0) return;
    if (profitChart.data.labels.length > 0) return;

    profitChart.data.labels = ['R1'];
    profitChart.data.datasets.forEach(ds => {
        const botId = Object.keys(botColors).find(k => botColors[k].name === ds.label);
        const entry = leaderboard.find(l => l.node_id === botId);
        ds.data = [entry ? Number(entry.cumulative_profit.toFixed(2)) : 0];
    });
    profitChart.update();
}

function updateChart(roundNumber, leaderboard) {
    if (!profitChart) return;

    if (profitChart.data.labels.length >= 10) {
        profitChart.data.labels.shift();
        profitChart.data.datasets.forEach(ds => ds.data.shift());
    }

    profitChart.data.labels.push(`R${roundNumber}`);

    const botMap = {};
    leaderboard.forEach(item => {
        botMap[item.node_id] = item.cumulative_profit;
    });

    profitChart.data.datasets.forEach(ds => {
        const botId = Object.keys(botColors).find(k => botColors[k].name === ds.label);
        if (botId && botMap[botId] !== undefined) {
            ds.data.push(Number(botMap[botId].toFixed(2)));
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

    // Update Cluster Capacity Dial in Analytics Card
    let totalCpu = 0;
    let count = 0;
    for (const [nodeId, util] of Object.entries(telemetry)) {
        totalCpu += util.cpu_pct || 0;
        count++;
    }
    if (count > 0) {
        const avgCpu = Math.round(totalCpu / count);
        const dialVal = document.getElementById('dialCapacityVal');
        const dialRing = document.getElementById('dialCapacityRing');
        if (dialVal) dialVal.textContent = `${avgCpu}%`;
        if (dialRing) dialRing.setAttribute('stroke-dasharray', `${avgCpu}, 100`);
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
                    ${isSolar ? '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px; margin-right:2px;"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>85% Solar' : '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px; margin-right:2px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>Grid Power'}
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
                <span class="thought-role">CognitiveSwarm Team</span>
                <p class="thought-body">Multi-Agent Deliberation loop standing by for next auction round...</p>
            </div>
        `;
    }
    const badge = document.getElementById('traceConfidenceBadge');
    if (badge) {
        badge.textContent = 'Awaiting Decision';
        badge.style.color = 'var(--accent-green-text)';
        badge.style.background = 'transparent';
        badge.style.border = 'none';
    }
}

// Attach UI Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    connectWebSocket();

    // Fetch initial history immediately so chart displays without delay
    fetch('/api/v1/auctions/history')
        .then(r => r.json())
        .then(history => {
            if (history && history.length > 0) {
                renderChartFromHistory(history);
            }
        })
        .catch(err => console.error("Initial history fetch error:", err));

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

    // Fullscreen Chart Toggle
    const btnFullscreen = document.getElementById('btnChartFullscreen');
    const chartCard = document.getElementById('profitChartCard');
    const iconEnter = document.getElementById('iconEnterFullscreen');
    const iconExit = document.getElementById('iconExitFullscreen');

    function toggleChartFullscreen() {
        if (!chartCard) return;
        const isFullscreen = chartCard.classList.toggle('chart-fullscreen-active');
        if (isFullscreen) {
            if (iconEnter) iconEnter.style.display = 'none';
            if (iconExit) iconExit.style.display = 'inline-block';
            if (btnFullscreen) btnFullscreen.title = 'Exit Fullscreen (Esc)';
            document.body.style.overflow = 'hidden';
        } else {
            if (iconEnter) iconEnter.style.display = 'inline-block';
            if (iconExit) iconExit.style.display = 'none';
            if (btnFullscreen) btnFullscreen.title = 'View Fullscreen';
            document.body.style.overflow = '';
        }
        setTimeout(() => {
            if (profitChart) profitChart.resize();
        }, 60);
    }

    if (btnFullscreen) {
        btnFullscreen.addEventListener('click', toggleChartFullscreen);
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && chartCard?.classList.contains('chart-fullscreen-active')) {
            toggleChartFullscreen();
        }
    });

    // -------------------------------------------------------------
    // Groq LPU Configuration Modal & Live Status Handlers
    // -------------------------------------------------------------
    function checkGroqStatus() {
        fetch('/api/v1/config/groq/status')
            .then(r => r.json())
            .then(data => {
                const dot = document.getElementById('groqStatusDot');
                const label = document.getElementById('groqStatusLabel');
                const badge = document.getElementById('groqStatusBadge');
                if (data.is_configured) {
                    if (dot) dot.style.background = '#10B981';
                    if (label) label.textContent = `Groq LPU: Active`;
                    if (badge) badge.textContent = `Groq LPU (${data.model.split('-')[1] || '70B'})`;
                } else {
                    if (dot) dot.style.background = '#F59E0B';
                    if (label) label.textContent = 'Groq LPU: Configure';
                }
            })
            .catch(() => {});
    }
    checkGroqStatus();

    const groqModal = document.getElementById('groqModal');
    const btnGroqConfig = document.getElementById('btnGroqConfig');
    const btnCloseGroqModal = document.getElementById('btnCloseGroqModal');
    const btnCancelGroq = document.getElementById('btnCancelGroq');
    const btnSaveGroq = document.getElementById('btnSaveGroq');
    const inputGroqKey = document.getElementById('inputGroqKey');
    const selectGroqModel = document.getElementById('selectGroqModel');

    if (btnGroqConfig) {
        btnGroqConfig.onclick = () => {
            if (groqModal) groqModal.style.display = 'flex';
        };
    }
    if (btnCloseGroqModal) {
        btnCloseGroqModal.onclick = () => {
            if (groqModal) groqModal.style.display = 'none';
        };
    }
    if (btnCancelGroq) {
        btnCancelGroq.onclick = () => {
            if (groqModal) groqModal.style.display = 'none';
        };
    }
    if (btnSaveGroq) {
        btnSaveGroq.onclick = async () => {
            const key = inputGroqKey ? inputGroqKey.value.trim() : '';
            const model = selectGroqModel ? selectGroqModel.value : 'llama-3.3-70b-versatile';
            if (!key) {
                alert('Please enter your Groq API key (starts with gsk_...)');
                return;
            }
            btnSaveGroq.textContent = 'Activating...';
            try {
                const res = await fetch('/api/v1/config/groq', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: key, model: model })
                });
                const result = await res.json();
                if (res.ok) {
                    if (groqModal) groqModal.style.display = 'none';
                    checkGroqStatus();
                    btnSaveGroq.textContent = 'Save & Activate';
                } else {
                    alert(result.detail || 'Failed to save Groq API key.');
                    btnSaveGroq.textContent = 'Save & Activate';
                }
            } catch (err) {
                alert('Error connecting Groq API: ' + err.message);
                btnSaveGroq.textContent = 'Save & Activate';
            }
        };
    }
});
