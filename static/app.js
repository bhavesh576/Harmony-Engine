/**
 * The Harmony Engine — Frontend Application
 * ==========================================
 * Interactive visualization of the knowledge graph and discoveries.
 * Uses D3.js for force-directed graph rendering.
 */

const App = {
    data: {
        discoveries: [],
        graphData: null,
        diseases: [],
        stats: null,
    },
    simulation: null,
    svg: null,
    g: null,
    zoom: null,
    tooltip: null,
    showLabels: true,
    showPredicted: true,
    paused: false,

    // ── Initialization ─────────────────────────────────────────────

    async init() {
        console.log("Initializing Harmony Engine...");

        // Create tooltip
        this.tooltip = d3.select("body").append("div")
            .attr("class", "node-tooltip")
            .style("opacity", 0);

        // Setup event listeners FIRST — before any async work
        this.setupListeners();

        try {
            // Load stats IMMEDIATELY (fast endpoint, shows numbers right away)
            this.fetchJSON("/api/stats").then(stats => {
                if (stats) {
                    this.data.stats = stats;
                    this.updateStats(stats);
                }
            });

            // Load source status and set toggle
            this.fetchJSON("/api/source-status").then(status => {
                if (status) {
                    const toggle = document.getElementById("apiToggle");
                    if (toggle) toggle.checked = status.use_api;
                    const label = document.getElementById("source-label");
                    if (label) label.textContent = status.use_api ? "API Data" : "CSV Only";
                }
            });

            // Load lite mode preference from localStorage
            const litePref = localStorage.getItem("harmony_lite_mode") === "true";
            if (litePref) {
                fetch("/api/lite-mode", {method: "POST", headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({enabled: true})});
            }
            const liteToggle = document.getElementById("lite-mode-toggle");
            if (liteToggle) liteToggle.checked = litePref;

            // Load the rest in parallel (may be slow due to literature checks)
            const [discoveries, diseases, graphData] = await Promise.all([
                this.fetchJSON("/api/discoveries?n=30"),
                this.fetchJSON("/api/diseases"),
                this.fetchJSON("/api/graph"),
            ]);

            this.data.discoveries = discoveries;
            this.data.diseases = diseases;
            this.data.graphData = graphData;

            // Populate disease selector
            if (diseases) this.populateDiseaseSelect(diseases);

            // Render discoveries
            if (discoveries) this.renderDiscoveries(discoveries);

            // Load discoveries with literature check (async, doesn't block init)
            this.loadDiscoveries();

            // Render graph
            if (graphData) this.renderGraph(graphData);

            // Retry: if graph is empty after 2s, reload it
            setTimeout(() => {
                const svgNodes = d3.select("#graph-svg").selectAll("circle").size();
                if (svgNodes === 0 && graphData) {
                    console.warn("Graph has 0 nodes after 2s, retrying...");
                    this.renderGraph(graphData);
                }
            }, 2000);

            console.log("Ready.");
        } catch (e) {
            console.error("Init error:", e);
        } finally {
            // Always hide loading screen
            document.getElementById("loading").classList.add("hidden");
        }
    },

    async fetchJSON(url) {
        try {
            const resp = await fetch(url);
            return await resp.json();
        } catch (e) {
            console.error(`Failed to fetch ${url}:`, e);
            return null;
        }
    },

    updateStats(stats) {
        if (!stats) return;
        document.getElementById("stat-diseases").textContent = stats.n_diseases;
        document.getElementById("stat-genes").textContent = stats.n_genes;
        document.getElementById("stat-symptoms").textContent = stats.n_symptoms;
        document.getElementById("stat-discoveries").textContent = stats.n_discoveries;
    },

    populateDiseaseSelect(diseases) {
        const select = document.getElementById("focus-select");
        diseases.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.id;
            opt.textContent = `${d.name} (${d.category})`;
            select.appendChild(opt);
        });
    },

    setupListeners() {
        console.log("Setting up listeners...");

        // Disease focus
        const focusSelect = document.getElementById("focus-select");
        if (focusSelect) {
            focusSelect.addEventListener("change", async (e) => {
                const focusId = e.target.value;
                const url = focusId ? `/api/graph?focus=${focusId}` : "/api/graph";
                const data = await this.fetchJSON(url);
                if (data) {
                    this.data.graphData = data;
                    this.renderGraph(data);
                }
                if (focusId) {
                    const disc = await this.fetchJSON(`/api/discoveries/${focusId}`);
                    if (disc) this.renderDiscoveries(disc);
                } else {
                    this.loadDiscoveries();
                }
            });
        }

        // Metric filter
        const metricFilter = document.getElementById("metric-filter");
        if (metricFilter) {
            metricFilter.addEventListener("change", async (e) => {
                this.loadDiscoveries();
            });
        }

        // Novel filter
        const novelFilter = document.getElementById("novel-filter");
        if (novelFilter) {
            novelFilter.addEventListener("change", () => this.loadDiscoveries());
        }

        // Reset view (top bar button) — fully destroy and reinitialize graph
        this._bind("btn-reset", "click", () => this._reinitializeGraph());

        // Modal close
        this._bind("modal-close", "click", () => {
            document.getElementById("modal-overlay").classList.add("hidden");
        });
        const overlay = document.getElementById("modal-overlay");
        if (overlay) {
            overlay.addEventListener("click", (e) => {
                if (e.target.id === "modal-overlay") {
                    document.getElementById("modal-overlay").classList.add("hidden");
                }
            });
        }

        // ── Zoom Controls ──
        this._bind("btn-zoom-in", "click", () => { console.log("Zoom in"); this.zoomBy(1.4); });
        this._bind("btn-zoom-out", "click", () => { console.log("Zoom out"); this.zoomBy(0.7); });
        this._bind("btn-reset-zoom", "click", () => { console.log("Reset zoom"); this.resetZoom(); });
        this._bind("btn-fit", "click", () => { console.log("Fit view"); this.fitToView(); });

        // ── Graph Options ──
        this._bind("btn-fullscreen", "click", () => { console.log("Fullscreen"); this.toggleFullscreen(); });
        this._bind("btn-pause-sim", "click", () => { console.log("Pause"); this.togglePause(); });
        this._bind("btn-show-labels", "click", () => { console.log("Toggle labels"); this.toggleLabels(); });
        this._bind("btn-show-predicted", "click", () => { console.log("Toggle predicted"); this.togglePredicted(); });

        // ── Header Buttons ──
        this._bind("btn-settings", "click", () => Settings.open());
        this._bind("btn-upload", "click", () => Settings.open());
        this._bind("btn-reload-graph", "click", () => this._reinitializeGraph());
        this._bind("btn-report", "click", () => this._downloadReport());
        this._bind("btn-copy-ai", "click", () => this._copyReportForAI());

        // ── Source Toggle ──
        const apiToggle = document.getElementById("apiToggle");
        if (apiToggle) {
            apiToggle.addEventListener("change", (e) => this._toggleSource(e.target.checked));
        }


        // ── Keyboard Shortcuts ──
        document.addEventListener("keydown", (e) => {
            if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;

            switch (e.key) {
                case "+": case "=": e.preventDefault(); this.zoomBy(1.4); break;
                case "-": case "_": e.preventDefault(); this.zoomBy(0.7); break;
                case "0": e.preventDefault(); this.resetZoom(); break;
                case "f": case "F": e.preventDefault(); this.fitToView(); break;
                case "p": case "P": e.preventDefault(); this.togglePause(); break;
                case "l": case "L": e.preventDefault(); this.toggleLabels(); break;
                case "e": case "E": e.preventDefault(); this.togglePredicted(); break;
                case "Escape":
                    document.getElementById("modal-overlay").classList.add("hidden");
                    break;
            }
        });

        console.log("Listeners ready.");
    },

    // Helper: safely bind event to element by ID
    _bind(id, event, handler) {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener(event, handler);
        } else {
            console.warn(`Element #${id} not found`);
        }
    },

    // ── Graph Visualization ────────────────────────────────────────

    renderGraph(data) {
        if (!data) return;

        const container = document.getElementById("graph-container");
        const width = container.clientWidth;
        const height = container.clientHeight;

        // If container has zero dimensions, retry up to 10 times with 100ms delay
        if (width === 0 || height === 0) {
            this._graphRetryCount = (this._graphRetryCount || 0) + 1;
            if (this._graphRetryCount <= 10) {
                console.warn(`Graph container has zero dimensions (attempt ${this._graphRetryCount}/10), retrying in 100ms...`);
                setTimeout(() => this.renderGraph(data), 100);
            } else {
                console.error("Graph container still has zero dimensions after 10 retries.");
                this._graphRetryCount = 0;
            }
            return;
        }
        this._graphRetryCount = 0;

        // Clear previous — fully destroy existing SVG content and simulation
        this._destroyGraph();

        this.svg = d3.select("#graph-svg")
            .attr("width", width)
            .attr("height", height);

        // Create main group with zoom
        this.g = this.svg.append("g");

        // Node color by type
        const colorMap = {
            disease: "#d4a853",
            symptom: "#50c070",
            gene: "#5080e0",
            pathway: "#9060e0",
        };

        // Node radius by type
        const radiusMap = {
            disease: 8,
            symptom: 3,
            gene: 4,
            pathway: 5,
        };

        // Prepare nodes with random initial positions spread across container
        const nodeMap = {};
        data.nodes.forEach(n => {
            nodeMap[n.id] = n;
            n.radius = radiusMap[n.type] || 4;
            n.x = Math.random() * width;
            n.y = Math.random() * height;
        });

        // Filter edges for performance — keep disease-disease and predicted
        const visibleEdges = data.edges.filter(e =>
            [
               "similar",
               "presents",
               "linked_gene",
               "participates",
               "in_pathway",
               "co_occurs",
               "interacts"
            ].includes(e.type)
        );

        // Add predicted edges
        const predictedEdges = (data.predicted_edges || []).map(e => ({
            ...e,
            type: "predicted",
            isPredicted: true,
        }));

        const allEdges = [...visibleEdges, ...predictedEdges];

        // Only include nodes that have edges
        const connectedNodes = new Set();
        allEdges.forEach(e => {
            connectedNodes.add(e.source);
            connectedNodes.add(e.target);
        });

        const visibleNodes = data.nodes.filter(n => connectedNodes.has(n.id));

        // Create simulation — lightweight for slow laptops
        this.simulation = d3.forceSimulation(visibleNodes)
            .force("link", d3.forceLink(allEdges)
                .id(d => d.id)
                .distance(d => d.isPredicted ? 100 : 60)
                .strength(d => d.isPredicted ? 0.1 : 0.3))
            .force("charge", d3.forceManyBody()
                .strength(-100))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .alphaDecay(0.05)     // Fast settling
            .velocityDecay(0.6);  // High friction, stops quickly

        // Freeze simulation completely after 5 seconds
        this._simFreezeTimer = setTimeout(() => {
            if (this.simulation) {
                this.simulation.stop();
                this._simFrozen = true;
            }
        }, 5000);
        this._simFrozen = false;

        // Auto fit-to-view after simulation has time to position nodes
        this._fitTimer = setTimeout(() => {
            this.fitToView();
        }, 1000);

        // Zoom-based visibility: hide small nodes when zoomed out
        const self = this;
        const allNodeEls = visibleNodes;
        const originalZoom = this.zoom;

        this.zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => {
                self.g.attr("transform", event.transform);
                self.updateZoomLevel(event.transform);

                // When zoomed out below 30%, hide symptoms and pathways
                const k = event.transform.k;
                const hideSmall = k < 0.3;
                d3.selectAll(".node-circle")
                    .style("display", d => {
                        if (hideSmall && (d.type === "symptom" || d.type === "pathway")) {
                            return "none";
                        }
                        return "block";
                    });
                d3.selectAll(".node-label")
                    .style("display", d => {
                        if (hideSmall) return "none";
                        return self.showLabels ? "block" : "none";
                    });
                d3.selectAll(".edge-line")
                    .style("opacity", hideSmall ? 0.05 : null);
            });

        this.svg.call(this.zoom);

        // Draw edges
        const edgeGroup = this.g.append("g").attr("class", "edges");

        const links = edgeGroup.selectAll("line")
            .data(allEdges)
            .enter().append("line")
            .attr("class", d => `edge-line ${d.type}`)
            .attr("stroke-width", d => d.isPredicted ? 1.5 : 0.5)
            .style("display", d => (d.isPredicted && !this.showPredicted) ? "none" : "block")
            .attr("stroke", d => {
                if (d.isPredicted) return "#d4a853";
                const colorMap = {
                    similar: "#d4a853",
                    co_occurs: "#50c070",
                    interacts: "#5080e0",
                    participates: "#9060e0",
                };
                return colorMap[d.type] || "#444";
            });

        // Draw nodes
        const nodeGroup = this.g.append("g").attr("class", "nodes");

        const nodes = nodeGroup.selectAll("circle")
            .data(visibleNodes)
            .enter().append("circle")
            .attr("class", "node-circle")
            .attr("r", d => d.radius)
            .attr("fill", d => colorMap[d.type] || "#666")
            .attr("stroke", d => {
                const c = d3.color(colorMap[d.type] || "#666");
                return c ? c.darker(0.5) : "#333";
            })
            .on("mouseover", (event, d) => this.showTooltip(event, d))
            .on("mouseout", () => this.hideTooltip())
            .on("click", (event, d) => this.onNodeClick(d))
            .call(d3.drag()
                .on("start", (event, d) => {
                    // Restart simulation if it was frozen
                    if (this._simFrozen) {
                        this.simulation.alpha(0.3).restart();
                        this._simFrozen = false;
                    } else if (!event.active) {
                        this.simulation.alphaTarget(0.3).restart();
                    }
                    d.fx = d.x;
                    d.fy = d.y;
                })
                .on("drag", (event, d) => {
                    d.fx = event.x;
                    d.fy = event.y;
                })
                .on("end", (event, d) => {
                    if (!event.active) this.simulation.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                    // Re-freeze after 3 seconds of inactivity
                    clearTimeout(this._simFreezeTimer);
                    this._simFreezeTimer = setTimeout(() => {
                        if (this.simulation) {
                            this.simulation.stop();
                            this._simFrozen = true;
                        }
                    }, 3000);
                }));

        // Labels for disease nodes only
        const labelGroup = this.g.append("g").attr("class", "labels");

        const labels = labelGroup.selectAll("text")
            .data(visibleNodes.filter(n => n.type === "disease"))
            .enter().append("text")
            .attr("class", "node-label")
            .text(d => d.name.length > 20 ? d.name.substring(0, 18) + "…" : d.name)
            .attr("dy", d => d.radius + 12)
            .style("font-size", "8px")
            .style("display", this.showLabels ? "block" : "none");

        // Simulation tick
        this.simulation.on("tick", () => {
            links
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            nodes
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);

            labels
                .attr("x", d => d.x)
                .attr("y", d => d.y);
        });

        // Highlight predicted edges with animation
        this.animatePredictions(links);
    },

    animatePredictions(links) {
        // Pulse the predicted edges
        function pulse() {
            links.filter(d => d.isPredicted)
                .transition()
                .duration(2000)
                .attr("stroke-opacity", 0.6)
                .attr("stroke-width", 2.5)
                .transition()
                .duration(2000)
                .attr("stroke-opacity", 0.2)
                .attr("stroke-width", 1)
                .on("end", pulse);
        }
        pulse();
    },

    // ── Graph Destruction ─────────────────────────────────────────────

    _destroyGraph() {
        // Stop simulation
        if (this.simulation) {
            this.simulation.stop();
            this.simulation = null;
        }
        // Clear all timers
        clearTimeout(this._simFreezeTimer);
        clearTimeout(this._fitTimer);
        this._simFrozen = false;
        this.paused = false;
        // Disconnect any resize observer
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        // Remove all SVG content
        d3.select("#graph-svg").selectAll("*").remove();
        // Clear references
        this.svg = null;
        this.g = null;
        this.zoom = null;
    },

    async _reinitializeGraph() {
        // Fully destroy and rebuild the graph from scratch
        this._destroyGraph();
        if (this.data.graphData) {
            this.renderGraph(this.data.graphData);
        } else {
            const data = await this.fetchJSON("/api/graph");
            if (data) {
                this.data.graphData = data;
                this.renderGraph(data);
            }
        }
    },

    // ── Source Toggle ─────────────────────────────────────────────────

    async _toggleSource(useApi) {
        const label = document.getElementById("source-label");
        if (label) label.textContent = useApi ? "API Data" : "CSV Only";

        try {
            const resp = await fetch("/api/toggle-source", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({use_api: useApi}),
            });
            const data = await resp.json();
            if (data.error) {
                alert("Error: " + data.error);
                return;
            }
            // Update stats
            if (data.diseases !== undefined) document.getElementById("stat-diseases").textContent = data.diseases;
            if (data.genes !== undefined) document.getElementById("stat-genes").textContent = data.genes;
            if (data.symptoms !== undefined) document.getElementById("stat-symptoms").textContent = data.symptoms;

            // Reload graph
            const graphData = await this.fetchJSON("/api/graph");
            if (graphData) {
                this.data.graphData = graphData;
                this._destroyGraph();
                this.renderGraph(graphData);
            }
            this.loadDiscoveries();

            // Show notification
            this._showNotification(useApi ? "Switched to API Mode" : "Switched to CSV Only Mode");
        } catch (e) {
            alert("Toggle failed: " + e.message);
        }
    },

    _showNotification(msg) {
        const el = document.createElement("div");
        el.className = "notification-toast";
        el.textContent = msg;
        document.body.appendChild(el);
        setTimeout(() => el.classList.add("show"), 10);
        setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 300); }, 2500);
    },

    // ── Report Download ───────────────────────────────────────────────

    async _downloadReport() {
        try {
            const resp = await fetch("/api/export-report");
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "harmony_report.txt";
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            alert("Failed to download report: " + e.message);
        }
    },

    async _copyReportForAI() {
        try {
            const resp = await fetch("/api/export-report");
            const text = await resp.text();
            await navigator.clipboard.writeText(text);
            this._showNotification("Copied! Paste into ChatGPT or Gemini");
        } catch (e) {
            alert("Failed to copy: " + e.message);
        }
    },

    // ── Zoom Helpers ──────────────────────────────────────────────────

    zoomBy(factor) {
        if (!this.svg || !this.zoom) { console.warn("Zoom not ready"); return; }
        this.svg.transition().duration(300)
            .call(this.zoom.scaleBy, factor);
    },

    resetZoom() {
        if (!this.svg || !this.zoom) { console.warn("Zoom not ready"); return; }
        this.svg.transition().duration(500)
            .call(this.zoom.transform, d3.zoomIdentity);
        this.updateZoomLevel({ k: 1 });
    },

    fitToView() {
        if (!this.svg || !this.zoom || !this.g) { console.warn("Graph not ready"); return; }
        const container = document.getElementById("graph-container");
        if (!container) return;
        const width = container.clientWidth;
        const height = container.clientHeight;
        if (width === 0 || height === 0) return;

        const bounds = this.g.node().getBBox();
        if (bounds.width === 0 || bounds.height === 0) return;

        const padding = 40;
        const scale = Math.min(
            (width - padding * 2) / bounds.width,
            (height - padding * 2) / bounds.height,
            2
        );
        const tx = width / 2 - scale * (bounds.x + bounds.width / 2);
        const ty = height / 2 - scale * (bounds.y + bounds.height / 2);

        this.svg.transition().duration(500)
            .call(this.zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
    },

    updateZoomLevel(transform) {
        const pct = Math.round((transform?.k || 1) * 100);
        const el = document.getElementById("zoom-level");
        if (el) el.textContent = pct + "%";
    },

    // ── Toggle Controls ───────────────────────────────────────────────

    toggleFullscreen() {
        const el = document.getElementById("graph-container");
        const btn = document.getElementById("btn-fullscreen");
        if (!el) return;
        if (!document.fullscreenElement) {
            el.requestFullscreen().then(() => {
                if (btn) { btn.textContent = "⊡"; btn.title = "Exit fullscreen (Esc)"; }
                this._createFullscreenChat();
            }).catch(err => console.warn("Fullscreen failed:", err));
        } else {
            document.exitFullscreen().then(() => {
                if (btn) { btn.textContent = "⛶"; btn.title = "Fullscreen (Esc to exit)"; }
                this._removeFullscreenChat();
            });
        }
    },

    // ── Fullscreen Chat Bubble ─────────────────────────────────────────

    _createFullscreenChat() {
        // Remove existing if any
        this._removeFullscreenChat();

        const container = document.getElementById("graph-container");
        if (!container) return;

        const bubble = document.createElement("div");
        bubble.id = "fs-chat-bubble";
        bubble.innerHTML = `
            <button id="fs-chat-icon" title="Ask AI">💬</button>
            <div id="fs-chat-body" style="display:none;">
                <div class="fs-chat-header">
                    <span>🔬 AI</span>
                    <button id="fs-chat-close">−</button>
                </div>
                <div id="fs-chat-messages"></div>
                <div class="fs-chat-input-row">
                    <input type="text" id="fs-chat-input" placeholder="Ask about a discovery...">
                    <button id="fs-chat-send">➤</button>
                </div>
            </div>
        `;
        container.appendChild(bubble);

        // Style the bubble
        Object.assign(bubble.style, {
            position: "fixed",
            bottom: "20px",
            right: "20px",
            zIndex: "9999",
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
        });

        const icon = document.getElementById("fs-chat-icon");
        Object.assign(icon.style, {
            width: "44px",
            height: "44px",
            borderRadius: "50%",
            background: "rgba(212, 168, 83, 0.9)",
            border: "none",
            fontSize: "20px",
            cursor: "pointer",
            boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
            backdropFilter: "blur(8px)",
        });

        const body = document.getElementById("fs-chat-body");
        Object.assign(body.style, {
            width: "320px",
            height: "360px",
            background: "rgba(18, 18, 26, 0.92)",
            border: "1px solid rgba(42, 42, 58, 0.8)",
            borderRadius: "10px",
            marginBottom: "8px",
            display: "none",
            flexDirection: "column",
            overflow: "hidden",
            boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
            backdropFilter: "blur(12px)",
        });

        // Event handlers
        icon.addEventListener("click", () => {
            body.style.display = body.style.display === "none" ? "flex" : "none";
            if (body.style.display === "flex") {
                document.getElementById("fs-chat-input").focus();
            }
        });

        document.getElementById("fs-chat-close").addEventListener("click", () => {
            body.style.display = "none";
        });

        document.getElementById("fs-chat-send").addEventListener("click", () => this._fsChatSend());

        document.getElementById("fs-chat-input").addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                this._fsChatSend();
            }
        });

        // Listen for fullscreen exit
        this._fsHandler = () => {
            if (!document.fullscreenElement) {
                this._removeFullscreenChat();
            }
        };
        document.addEventListener("fullscreenchange", this._fsHandler);
    },

    _removeFullscreenChat() {
        const bubble = document.getElementById("fs-chat-bubble");
        if (bubble) bubble.remove();
        if (this._fsHandler) {
            document.removeEventListener("fullscreenchange", this._fsHandler);
            this._fsHandler = null;
        }
    },

    async _fsChatSend() {
        const input = document.getElementById("fs-chat-input");
        const msgs = document.getElementById("fs-chat-messages");
        if (!input || !msgs) return;

        const text = input.value.trim();
        if (!text) return;

        const provider = Settings.getProvider();
        const apiKey = Settings.getApiKey();
        if (!apiKey) {
            msgs.innerHTML += `<div style="color:#e05050;font-size:11px;text-align:center;padding:8px;">Set API key in Settings first</div>`;
            return;
        }

        // User message
        msgs.innerHTML += `<div style="align-self:flex-end;background:rgba(160,128,48,0.3);color:#fff;padding:6px 10px;border-radius:8px;font-size:12px;max-width:85%;margin:4px 0;">${this.escapeHtml(text)}</div>`;
        input.value = "";

        // Typing indicator
        const typing = document.createElement("div");
        typing.style.cssText = "color:#888;font-size:11px;font-style:italic;padding:6px;";
        typing.textContent = "Thinking...";
        msgs.appendChild(typing);
        msgs.scrollTop = msgs.scrollHeight;

        try {
            const resp = await fetch("/api/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    message: text,
                    provider: provider,
                    api_key: apiKey,
                    model: Settings.getModel(),
                    endpoint: Settings.getEndpoint(),
                }),
            });
            const data = await resp.json();
            typing.remove();

            if (data.error) {
                msgs.innerHTML += `<div style="color:#e05050;font-size:11px;padding:6px;">${data.error}</div>`;
            } else {
                msgs.innerHTML += `<div style="background:rgba(26,26,37,0.8);color:#e0e0e8;padding:6px 10px;border-radius:8px;font-size:12px;max-width:85%;margin:4px 0;border:1px solid rgba(42,42,58,0.5);">${this.formatReply(data.reply)}</div>`;
            }
        } catch (e) {
            typing.remove();
            msgs.innerHTML += `<div style="color:#e05050;font-size:11px;padding:6px;">Error: ${e.message}</div>`;
        }

        msgs.scrollTop = msgs.scrollHeight;
    },

    togglePause() {
        const btn = document.getElementById("btn-pause-sim");
        if (!this.simulation) { console.warn("Simulation not ready"); return; }
        this.paused = !this.paused;
        if (this.paused) {
            this.simulation.stop();
            if (btn) { btn.textContent = "▶"; btn.title = "Resume simulation (P)"; btn.classList.add("active"); }
        } else {
            this.simulation.restart();
            if (btn) { btn.textContent = "⏸"; btn.title = "Pause simulation (P)"; btn.classList.remove("active"); }
        }
    },

    toggleLabels() {
        this.showLabels = !this.showLabels;
        const btn = document.getElementById("btn-show-labels");
        d3.selectAll(".node-label").style("display", this.showLabels ? "block" : "none");
        if (btn) btn.classList.toggle("active", this.showLabels);
    },

    togglePredicted() {
        this.showPredicted = !this.showPredicted;
        const btn = document.getElementById("btn-show-predicted");
        d3.selectAll(".edge-line.predicted").style("display", this.showPredicted ? "block" : "none");
        if (btn) btn.classList.toggle("active", this.showPredicted);
    },

    showTooltip(event, d) {
        this.tooltip
            .style("opacity", 1)
            .style("left", (event.pageX + 12) + "px")
            .style("top", (event.pageY - 20) + "px")
            .html(`
                <div class="tooltip-name">${d.name}</div>
                <div class="tooltip-type">${d.type}${d.category ? " · " + d.category : ""}</div>
            `);
    },

    hideTooltip() {
        this.tooltip.style("opacity", 0);
    },

    onNodeClick(d) {
        if (d.type === "disease") {
            document.getElementById("focus-select").value = d.id;
            document.getElementById("focus-select").dispatchEvent(new Event("change"));
        }
    },

    // ── Discovery Loading ──────────────────────────────────────────

    async loadDiscoveries() {
        const metric = document.getElementById("metric-filter")?.value || "";
        const novel = document.getElementById("novel-filter")?.checked || false;

        let url = "/api/discoveries?n=30";
        if (metric) url += `&metric=${metric}`;
        if (novel) url += `&novel=true`;

        const disc = await this.fetchJSON(url);
        if (disc) this.renderDiscoveries(disc);
    },

    // ── Discovery Rendering ────────────────────────────────────────

    renderDiscoveries(discoveries) {
        const container = document.getElementById("discovery-list");
        container.innerHTML = "";

        if (!discoveries || discoveries.length === 0) {
            container.innerHTML = '<p style="color: var(--text-dim); padding: 16px;">No discoveries found.</p>';
            return;
        }

        discoveries.forEach((disc, index) => {
            const card = document.createElement("div");
            card.className = "discovery-card";
            card.addEventListener("click", () => this.showDiscoveryDetail(disc));

            // Metric bars
            const metricBars = this.renderMetricBars(disc.components);

            // Novelty badge
            const papers = disc.literature_evidence;
            const noveltyBadge = papers === 0
                ? '<span class="card-novelty novel">🔬 NOVEL</span>'
                : papers > 0
                    ? `<span class="card-novelty studied">${papers} paper${papers !== 1 ? 's' : ''}</span>`
                    : '';

            card.innerHTML = `
                <div class="card-header">
                    <span class="card-title">#${index + 1}</span>
                    <span>${noveltyBadge}</span>
                    <span class="card-score">${disc.composite_score.toFixed(3)}</span>
                </div>
                <div class="card-entities">
                    <span class="entity-tag ${disc.entity1_type}">${disc.entity1_name}</span>
                    <span class="connector">—</span>
                    <span class="entity-tag ${disc.entity2_type}">${disc.entity2_name}</span>
                </div>
                <div class="card-metrics">${metricBars}</div>
            `;

            container.appendChild(card);
        });
    },

    renderMetricBars(components) {
        const metrics = [
            { key: "sds", label: "SDS" },
            { key: "hds", label: "HDS" },
            { key: "cis", label: "CIS" },
            { key: "crs", label: "CRS" },
        ];

        return metrics.map(m => {
            const val = components[m.key] || 0;
            const pct = Math.round(val * 100);
            return `
                <div class="metric-bar">
                    <span>${m.label}</span>
                    <div class="bar-track">
                        <div class="bar-fill ${m.key}" style="width: ${pct}%"></div>
                    </div>
                </div>
            `;
        }).join("");
    },

    // ── Discovery Detail Modal ─────────────────────────────────────

    showDiscoveryDetail(disc) {
        const modal = document.getElementById("modal-content");

        // Build evidence HTML
        const evidenceHTML = (disc.explanation?.evidence || disc.evidence || []).map(e => {
            const metricClass = e.metric.includes("Symmetry") ? "sds" :
                               e.metric.includes("Harmonic") ? "hds" :
                               e.metric.includes("Compositional") ? "cis" : "crs";
            return `
                <div class="evidence-item">
                    <div class="evidence-metric ${metricClass}">${e.metric}</div>
                    <div class="evidence-detail">${e.detail}</div>
                </div>
            `;
        }).join("");

        // Build scores HTML
        const components = disc.components || {};
        const scoresHTML = Object.entries(components).map(([key, val]) => {
            const labels = { sds: "Symmetry Defect", hds: "Harmonic Dissonance",
                           cis: "Compositional Gap", crs: "Curvature Defect" };
            return `
                <div class="score-card">
                    <div class="score-label">${labels[key] || key}</div>
                    <div class="score-value ${key}">${(val * 100).toFixed(0)}%</div>
                </div>
            `;
        }).join("");

        modal.innerHTML = `
            <div class="modal-title">${disc.explanation?.title || "Discovery"}</div>
            <div class="modal-summary">${disc.explanation?.summary || ""}</div>
            <div class="modal-story">${disc.explanation?.story || ""}</div>

            <div class="modal-section-title">Evidence</div>
            ${evidenceHTML || '<p style="color: var(--text-dim);">No detailed evidence available.</p>'}

            <div class="modal-section-title">Harmony Scores</div>
            <div class="modal-scores">${scoresHTML}</div>
        `;

        document.getElementById("modal-overlay").classList.remove("hidden");
    },
};

// ── Report Functions (global, called from HTML) ───────────────────

function downloadReport() {
    window.open('/api/export-report', '_blank');
}

async function copyForAI() {
    try {
        const resp = await fetch('/api/export-report');
        const text = await resp.text();
        await navigator.clipboard.writeText(text);
        alert('Copied! Paste into ChatGPT or Gemini.');
    } catch (e) {
        alert('Failed to copy: ' + e.message);
    }
}

// ── Source Toggle (global) ─────────────────────────────────────────

let apiEnabled = true;

async function toggleSource() {
    apiEnabled = !apiEnabled;
    const knob = document.getElementById('toggleKnob');
    const tog = document.getElementById('sourceToggle');
    if (knob) knob.style.left = apiEnabled ? '20px' : '2px';
    if (tog) tog.style.background = apiEnabled ? '#d4af37' : '#30363d';
    await fetch('/api/toggle-source', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({use_api: apiEnabled})
    });
    location.reload();
}

// ── Bootstrap ──────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    App.init();
    Chat.init();
    Settings.init();

    // Check source status on load
    fetch('/api/source-status').then(r => r.json()).then(d => {
        apiEnabled = d.use_api;
        const knob = document.getElementById('toggleKnob');
        const tog = document.getElementById('sourceToggle');
        const label = document.getElementById('source-label');
        if (knob) knob.style.left = apiEnabled ? '20px' : '2px';
        if (tog) tog.style.background = apiEnabled ? '#d4af37' : '#30363d';
        if (label) label.textContent = apiEnabled ? 'API Data' : 'CSV Only';
    });
    // Safety: hide loading screen after 20s no matter what
    setTimeout(() => {
        const loading = document.getElementById("loading");
        if (loading && !loading.classList.contains("hidden")) {
            console.warn("Loading timeout — forcing hide after 20s");
            loading.classList.add("hidden");
        }
    }, 20000);
});


// ═══════════════════════════════════════════════════════════════════
// AI CHAT MODULE
// ═══════════════════════════════════════════════════════════════════

const Chat = {
    panel: null,
    body: null,
    messages: null,
    input: null,

    init() {
        this.panel = document.getElementById("chat-panel");
        this.body = document.getElementById("chat-body");
        this.messages = document.getElementById("chat-messages");
        this.input = document.getElementById("chat-input");

        // Toggle open/close
        document.getElementById("chat-toggle").addEventListener("click", () => {
            this.panel.classList.toggle("chat-collapsed");
            if (!this.panel.classList.contains("chat-collapsed")) {
                this.input.focus();
            }
        });

        // Minimize
        document.getElementById("chat-minimize").addEventListener("click", () => {
            this.panel.classList.add("chat-collapsed");
        });

        // Settings button
        document.getElementById("chat-settings-btn").addEventListener("click", () => {
            Settings.open();
        });

        // Send
        document.getElementById("chat-send").addEventListener("click", () => this.send());

        // Enter to send (Shift+Enter for newline)
        this.input.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                this.send();
            }
        });

        // Keyboard shortcut: C to toggle chat
        document.addEventListener("keydown", (e) => {
            if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
            if (e.key === "c" || e.key === "C") {
                e.preventDefault();
                this.panel.classList.toggle("chat-collapsed");
                if (!this.panel.classList.contains("chat-collapsed")) {
                    this.input.focus();
                }
            }
        });
    },

    addMessage(text, type) {
        const div = document.createElement("div");
        div.className = `chat-msg ${type}`;
        div.innerHTML = `<div class="chat-msg-text">${text}</div>`;
        this.messages.appendChild(div);
        this.messages.scrollTop = this.messages.scrollHeight;
        return div;
    },

    async send() {
        const text = this.input.value.trim();
        if (!text) return;

        // Get settings
        const provider = Settings.getProvider();
        const apiKey = Settings.getApiKey();

        if (!apiKey) {
            this.addMessage("Please configure your API key in Settings (⚙).", "error");
            return;
        }

        // Show user message
        this.addMessage(this.escapeHtml(text), "user");
        this.input.value = "";

        // Show typing indicator
        const typing = this.addMessage("Thinking...", "typing");

        try {
            const resp = await fetch("/api/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    message: text,
                    provider: provider,
                    api_key: apiKey,
                    model: Settings.getModel(),
                    endpoint: Settings.getEndpoint(),
                }),
            });

            const data = await resp.json();

            // Remove typing indicator
            typing.remove();

            if (data.error) {
                this.addMessage(`Error: ${data.error}`, "error");
            } else {
                this.addMessage(this.formatReply(data.reply), "bot");
            }
        } catch (e) {
            typing.remove();
            this.addMessage(`Network error: ${e.message}`, "error");
        }
    },

    escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    },

    formatReply(text) {
        // Basic markdown-like formatting
        return text
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>")
            .replace(/`(.*?)`/g, "<code>$1</code>")
            .replace(/\n/g, "<br>");
    },
};


// ═══════════════════════════════════════════════════════════════════
// SETTINGS MODULE
// ═══════════════════════════════════════════════════════════════════

const Settings = {
    overlay: null,
    status: null,
    _stagedFiles: [],

    init() {
        this.overlay = document.getElementById("settings-overlay");
        this.status = document.getElementById("settings-status");

        // Close
        document.getElementById("settings-close").addEventListener("click", () => this.close());
        this.overlay.addEventListener("click", (e) => {
            if (e.target === this.overlay) this.close();
        });

        // Load saved values
        const savedKey = localStorage.getItem("harmony_api_key") || "";
        const savedProvider = localStorage.getItem("harmony_provider") || "anthropic";
        const savedModel = localStorage.getItem("harmony_model") || "";
        const savedEndpoint = localStorage.getItem("harmony_endpoint") || "";
        document.getElementById("settings-api-key").value = savedKey;
        document.getElementById("settings-model").value = savedModel;
        document.getElementById("settings-endpoint").value = savedEndpoint;
        const radio = document.querySelector(`input[name="ai-provider"][value="${savedProvider}"]`);
        if (radio) radio.checked = true;
        this.updateProviderUI(savedProvider);

        // Save on change
        document.getElementById("settings-api-key").addEventListener("input", (e) => {
            localStorage.setItem("harmony_api_key", e.target.value);
        });
        document.getElementById("settings-model").addEventListener("input", (e) => {
            localStorage.setItem("harmony_model", e.target.value);
        });
        document.getElementById("settings-endpoint").addEventListener("input", (e) => {
            localStorage.setItem("harmony_endpoint", e.target.value);
        });
        document.querySelectorAll('input[name="ai-provider"]').forEach(radio => {
            radio.addEventListener("change", (e) => {
                localStorage.setItem("harmony_provider", e.target.value);
                this.updateProviderUI(e.target.value);
            });
        });

        // Stage CSV (don't upload yet)
        document.getElementById("btn-upload-csv").addEventListener("click", () => {
            document.getElementById("csv-file-input").click();
        });
        document.getElementById("csv-file-input").addEventListener("change", (e) => {
            for (const file of e.target.files) {
                this._stageFile(file);
            }
            e.target.value = ""; // reset so same file can be re-selected
        });

        // Recompute button
        document.getElementById("btn-recompute").addEventListener("click", () => this._recomputeAll());

        // Reset button
        document.getElementById("btn-reset-data").addEventListener("click", () => this._resetData());

        // Enrich genes
        document.getElementById("btn-enrich-genes").addEventListener("click", () => this.enrichGenes());

        // Lite mode toggle
        const liteToggle = document.getElementById("lite-mode-toggle");
        if (liteToggle) {
            liteToggle.addEventListener("change", (e) => {
                const enabled = e.target.checked;
                localStorage.setItem("harmony_lite_mode", enabled ? "true" : "false");
                fetch("/api/lite-mode", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({enabled}),
                }).then(() => App._reinitializeGraph());
            });
        }

        // Keyboard: Escape to close
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") this.close();
        });
    },

    open() {
        this.overlay.classList.remove("hidden");
    },

    close() {
        this.overlay.classList.add("hidden");
    },

    getProvider() {
        return localStorage.getItem("harmony_provider") || "anthropic";
    },

    getApiKey() {
        return localStorage.getItem("harmony_api_key") || "";
    },

    getModel() {
        return localStorage.getItem("harmony_model") || "";
    },

    getEndpoint() {
        return localStorage.getItem("harmony_endpoint") || "";
    },

    updateProviderUI(provider) {
        const modelSection = document.getElementById("settings-model-section");
        const endpointSection = document.getElementById("settings-endpoint-section");
        const keyHint = document.getElementById("settings-key-hint");
        const modelHint = document.getElementById("settings-model-hint");

        // Show/hide custom endpoint
        if (provider === "custom") {
            endpointSection.style.display = "block";
        } else {
            endpointSection.style.display = "none";
        }

        // Update hints
        const hints = {
            anthropic: "Get your key at console.anthropic.com",
            openai: "Get your key at platform.openai.com",
            together: "Get your key at api.together.xyz — supports Llama, Mistral, Qwen",
            groq: "Get your key at console.groq.com — ultra-fast inference",
            openrouter: "Get your key at openrouter.ai — access 100+ models",
            custom: "Leave blank if your endpoint doesn't need auth (e.g. local Ollama)",
        };
        keyHint.textContent = hints[provider] || "Stored in localStorage only.";

        const modelDefaults = {
            anthropic: "Default: claude-sonnet-4-20250514",
            openai: "Default: gpt-4o-mini",
            together: "e.g. meta-llama/Llama-3-70b-chat-hf",
            groq: "e.g. llama3-70b-8192 or mixtral-8x7b-32768",
            openrouter: "e.g. meta-llama/llama-3-70b-instruct",
            custom: "Model name for your endpoint",
        };
        modelHint.textContent = modelDefaults[provider] || "Leave blank for default model.";
    },

    showStatus(msg, type) {
        this.status.textContent = msg;
        this.status.className = `settings-status show ${type}`;
    },

    // ── CSV Staging Workflow ──────────────────────────────────────────

    _stageFile(file) {
        if (!file.name.endsWith(".csv")) {
            this.showStatus(`Skipped ${file.name} — not a .csv file`, "error");
            return;
        }
        // Check for duplicate filenames
        if (this._stagedFiles.some(f => f.name === file.name)) {
            this.showStatus(`${file.name} is already staged`, "error");
            return;
        }
        this._stagedFiles.push(file);
        this._renderPendingList();
        this.showStatus(`Staged ${file.name} — click "Recompute Discoveries" when ready`, "success");
    },

    _removeStaged(index) {
        this._stagedFiles.splice(index, 1);
        this._renderPendingList();
    },

    _renderPendingList() {
        const container = document.getElementById("pending-uploads");
        const list = document.getElementById("pending-list");
        if (!container || !list) return;

        if (this._stagedFiles.length === 0) {
            container.style.display = "none";
            return;
        }

        container.style.display = "block";
        list.innerHTML = this._stagedFiles.map((f, i) => `
            <div class="pending-item">
                <span class="pending-name">📄 ${f.name}</span>
                <button class="pending-remove" onclick="Settings._removeStaged(${i})" title="Remove">✕</button>
            </div>
        `).join("");
    },

    async _recomputeAll() {
        if (this._stagedFiles.length === 0) {
            this.showStatus("No files staged", "error");
            return;
        }

        // Show "Measuring harmony..." loading screen
        const loading = document.getElementById("loading");
        const loadingText = document.getElementById("loading-text");
        if (loading) loading.classList.remove("hidden");
        if (loadingText) loadingText.textContent = "Measuring harmony...";

        this.showStatus(`Uploading ${this._stagedFiles.length} file(s)...`, "loading");

        let totalAdded = 0;
        let totalSkipped = 0;
        let errors = [];

        for (const file of this._stagedFiles) {
            const formData = new FormData();
            formData.append("file", file);

            try {
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 60000);

                const resp = await fetch("/api/upload-csv", {
                    method: "POST",
                    body: formData,
                    signal: controller.signal,
                });
                clearTimeout(timeout);

                const data = await resp.json();
                if (data.error) {
                    errors.push(`${file.name}: ${data.error}`);
                } else {
                    totalAdded += data.added;
                    totalSkipped += data.skipped;
                }
            } catch (e) {
                errors.push(`${file.name}: ${e.message}`);
            }
        }

        this._stagedFiles = [];
        this._renderPendingList();

        if (loading) loading.classList.add("hidden");
        if (loadingText) loadingText.textContent = "Initializing The Harmony Engine...";

        if (errors.length > 0) {
            this.showStatus(`Partial: ${totalAdded} added, ${errors.length} errors: ${errors.join("; ")}`, "error");
        } else {
            this.showStatus(
                `✓ Added ${totalAdded} diseases (${totalSkipped} skipped). Reloading...`,
                "success"
            );
        }
        setTimeout(() => location.reload(), 2000);
    },

    async enrichGenes() {
        this.showStatus("Enriching gene data from Monarch Initiative...", "loading");

        try {
            const resp = await fetch("/api/enrich-genes", { method: "POST" });
            const data = await resp.json();

            if (data.error) {
                this.showStatus(`Error: ${data.error}`, "error");
            } else {
                this.showStatus(
                    `✓ Added ${data.new_gene_associations} gene-disease links ` +
                    `(${data.unique_new_genes} new unique genes). ` +
                    `Total genes: ${data.total_genes}. Page will reload.`,
                    "success"
                );
                setTimeout(() => location.reload(), 3000);
            }
        } catch (e) {
            this.showStatus(`Enrichment failed: ${e.message}`, "error");
        }
    },

    async _resetData() {
        if (!confirm("This will remove all uploaded datasets and restore the original Orphanet + Monarch data. Continue?")) {
            return;
        }

        const loading = document.getElementById("loading");
        const loadingText = document.getElementById("loading-text");
        if (loading) loading.classList.remove("hidden");
        if (loadingText) loadingText.textContent = "Measuring harmony...";

        this.showStatus("Resetting to original data...", "loading");

        try {
            const resp = await fetch("/api/reset", { method: "POST" });
            const data = await resp.json();

            if (data.error) {
                if (loading) loading.classList.add("hidden");
                if (loadingText) loadingText.textContent = "Initializing The Harmony Engine...";
                this.showStatus(`Error: ${data.error}`, "error");
            } else {
                // Update header stats immediately with reset response data
                if (data.diseases !== undefined) {
                    document.getElementById("stat-diseases").textContent = data.diseases;
                }
                if (data.genes !== undefined) {
                    document.getElementById("stat-genes").textContent = data.genes;
                }
                if (data.symptoms !== undefined) {
                    document.getElementById("stat-symptoms").textContent = data.symptoms;
                }
                if (data.discoveries !== undefined) {
                    document.getElementById("stat-discoveries").textContent = data.discoveries;
                }

                // Also fetch fresh stats to ensure accuracy
                try {
                    const statsResp = await fetch("/api/stats");
                    const stats = await statsResp.json();
                    if (stats) {
                        App.updateStats(stats);
                    }
                } catch (statsErr) {
                    console.warn("Could not fetch fresh stats after reset:", statsErr);
                }

                this.showStatus(
                    `✓ Reset complete. ${data.diseases} diseases, ${data.genes} genes, ${data.symptoms} symptoms. Reloading...`,
                    "success"
                );
                setTimeout(() => location.reload(), 2000);
            }
        } catch (e) {
            if (loading) loading.classList.add("hidden");
            if (loadingText) loadingText.textContent = "Initializing The Harmony Engine...";
            this.showStatus(`Reset failed: ${e.message}`, "error");
        }
    },
};
