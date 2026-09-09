/* ==========================================================================
   AirStore v1.1.0 — Static Demo JavaScript
   Interactive Browser Simulation & Client-Side SHA-256 Computation
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // State management
    const state = {
        selectedFile: null,
        fileHash: null,
        nodeCount: 3,
        replicationFactor: 2,
        chunkSizeMB: 64,
        nodes: [],
        chunks: [],
        isProcessing: false,
        faultTargetNode: 'NODE-01'
    };

    // DOM Elements
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const metaBox = document.getElementById('file-meta-box');
    const fileNameEl = document.getElementById('meta-filename');
    const fileSizeEl = document.getElementById('meta-filesize');
    const fileTypeEl = document.getElementById('meta-filetype');
    
    const nodeCountInput = document.getElementById('node-count-slider');
    const nodeCountVal = document.getElementById('node-count-val');
    const replFactorInput = document.getElementById('repl-factor-select');
    const chunkSizeInput = document.getElementById('chunk-size-select');
    
    const btnDistribute = document.getElementById('btn-distribute');
    const btnSimulateFail = document.getElementById('btn-simulate-fail');
    const btnSimulateCorrupt = document.getElementById('btn-simulate-corrupt');
    const btnDemoResumable = document.getElementById('btn-demo-resumable');
    const btnResetSim = document.getElementById('btn-reset-sim');
    
    const nodesContainer = document.getElementById('nodes-container');
    const chunksContainer = document.getElementById('chunks-container');
    const faultNodeSelect = document.getElementById('fault-node-select');
    
    const originalHashEl = document.getElementById('hash-original');
    const recoveredHashEl = document.getElementById('hash-recovered');
    const hashStatusEl = document.getElementById('hash-status');
    const pipelineSteps = document.querySelectorAll('.step-card');

    // Default sample file init if none selected
    createSampleFile();
    initNodes();
    updateUI();

    // Event Listeners
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    nodeCountInput.addEventListener('input', (e) => {
        state.nodeCount = parseInt(e.target.value, 10);
        nodeCountVal.textContent = state.nodeCount;
        initNodes();
    });

    replFactorInput.addEventListener('change', (e) => {
        state.replicationFactor = parseInt(e.target.value, 10);
    });

    chunkSizeInput.addEventListener('change', (e) => {
        state.chunkSizeMB = parseInt(e.target.value, 10);
    });

    btnDistribute.addEventListener('click', runDistributionPipeline);
    btnSimulateFail.addEventListener('click', simulateNodeFailure);
    btnSimulateCorrupt.addEventListener('click', simulateChunkCorruption);
    btnDemoResumable.addEventListener('click', runResumableDemo);
    btnResetSim.addEventListener('click', resetSimulation);

    // Helpers
    function createSampleFile() {
        const dummyContent = "AirStore v1.1.0 Research Dataset Sample Payload - " + new Date().toISOString();
        const blob = new Blob([dummyContent], { type: 'application/octet-stream' });
        state.selectedFile = new File([blob], 'research_sample.dat', { type: 'application/octet-stream' });
        computeBrowserHash(state.selectedFile);
    }

    function handleFileSelect(file) {
        state.selectedFile = file;
        fileNameEl.textContent = file.name;
        fileSizeEl.textContent = formatBytes(file.size);
        fileTypeEl.textContent = file.type || 'binary/data';
        metaBox.classList.add('active');
        computeBrowserHash(file);
    }

    async function computeBrowserHash(file) {
        originalHashEl.textContent = "Computing SHA-256 in browser...";
        try {
            const arrayBuffer = await file.arrayBuffer();
            const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            state.fileHash = hashHex;
            originalHashEl.textContent = hashHex;
            recoveredHashEl.textContent = hashHex;
            hashStatusEl.innerHTML = '<span class="status-pill status-executed">✓ SHA-256 MATCH</span>';
        } catch (err) {
            // Fallback for demo Hash if crypto fails
            const mockHash = "5a7d6560ef7183e85e2b4bb7d00f681a54bfaed087d0c36b44f2b3b0d2d38561";
            state.fileHash = mockHash;
            originalHashEl.textContent = mockHash + " (Sample)";
            recoveredHashEl.textContent = mockHash;
            hashStatusEl.innerHTML = '<span class="status-pill status-executed">✓ MATCH</span>';
        }
    }

    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    function initNodes() {
        state.nodes = [];
        faultNodeSelect.innerHTML = '';
        for (let i = 1; i <= state.nodeCount; i++) {
            const id = `NODE-0${i}`;
            state.nodes.push({
                id: id,
                status: 'HEALTHY',
                chunksCount: 0,
                usedBytes: 0,
                capacityBytes: 5 * 1024 * 1024 * 1024
            });

            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = id;
            faultNodeSelect.appendChild(opt);
        }
        renderNodes();
    }

    function renderNodes() {
        nodesContainer.innerHTML = '';
        state.nodes.forEach(node => {
            const card = document.createElement('div');
            card.className = `node-card ${node.status === 'FAILED' ? 'failed' : ''}`;
            card.id = `card-${node.id}`;

            const loadPct = Math.min(Math.round((node.usedBytes / node.capacityBytes) * 100), 100);

            card.innerHTML = `
                <div class="node-card-header">
                    <span class="node-card-title"><i class="fa-solid fa-server"></i> ${node.id}</span>
                    <span class="node-card-badge ${node.status === 'FAILED' ? 'badge-failed' : 'badge-online'}">
                        ● ${node.status}
                    </span>
                </div>
                <div class="node-stat-line"><span>Stored Chunks:</span> <strong>${node.chunksCount}</strong></div>
                <div class="node-stat-line"><span>Used Storage:</span> <strong>${formatBytes(node.usedBytes)}</strong></div>
                <div class="node-stat-line"><span>Node Load:</span> <strong>${loadPct}%</strong></div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width: ${node.status === 'FAILED' ? 0 : loadPct}%"></div>
                </div>
            `;
            nodesContainer.appendChild(card);
        });
    }

    async function runDistributionPipeline() {
        if (state.isProcessing) return;
        state.isProcessing = true;
        btnDistribute.disabled = true;

        // Reset step animations
        pipelineSteps.forEach(step => {
            step.classList.remove('active', 'done');
            step.querySelector('.step-status').textContent = '⋯';
        });

        // 1. File Received
        await animateStep(0, 'Received');

        // 2. Chunking
        const totalSize = state.selectedFile ? state.selectedFile.size : 10 * 1024 * 1024;
        const chunkSize = state.chunkSizeMB * 1024 * 1024;
        const numChunks = Math.max(1, Math.ceil(totalSize / chunkSize));
        await animateStep(1, `${numChunks} Chunks`);

        // 3. SHA-256
        await animateStep(2, 'Calculated');

        // 4. Chunk Placement & 5. Replication
        state.chunks = [];
        state.nodes.forEach(n => { n.chunksCount = 0; n.usedBytes = 0; });

        for (let c = 1; c <= numChunks; c++) {
            const chunkId = `chk_${c.toString().padStart(3, '0')}`;
            const primaryNodeIdx = (c - 1) % state.nodeCount;
            const primaryNode = state.nodes[primaryNodeIdx];

            const replicaNodes = [];
            for (let r = 1; r < state.replicationFactor; r++) {
                const replIdx = (primaryNodeIdx + r) % state.nodeCount;
                replicaNodes.push(state.nodes[replIdx].id);
            }

            state.chunks.push({
                id: chunkId,
                primaryNode: primaryNode.id,
                replicas: replicaNodes,
                size: Math.min(chunkSize, totalSize - (c - 1) * chunkSize),
                sha256: state.fileHash ? state.fileHash.substring(0, 12) + `_${c}` : `sha256_chk${c}`
            });

            primaryNode.chunksCount++;
            primaryNode.usedBytes += Math.min(chunkSize, totalSize - (c - 1) * chunkSize);

            replicaNodes.forEach(rId => {
                const rNode = state.nodes.find(n => n.id === rId);
                if (rNode) {
                    rNode.chunksCount++;
                    rNode.usedBytes += Math.min(chunkSize, totalSize - (c - 1) * chunkSize);
                }
            });
        }

        await animateStep(3, 'Placed');
        await animateStep(4, `${state.replicationFactor}x Replicated`);

        // 6. Integrity Verification
        renderNodes();
        renderChunksMap();
        await animateStep(5, 'Verified ✓');

        state.isProcessing = false;
        btnDistribute.disabled = false;
    }

    function animateStep(idx, statusText) {
        return new Promise(resolve => {
            const step = pipelineSteps[idx];
            step.classList.add('active');
            step.querySelector('.step-status').textContent = '⏳';
            setTimeout(() => {
                step.classList.remove('active');
                step.classList.add('done');
                step.querySelector('.step-status').textContent = statusText;
                resolve();
            }, 400);
        });
    }

    function renderChunksMap() {
        chunksContainer.innerHTML = '';
        state.chunks.forEach(chunk => {
            const div = document.createElement('div');
            div.className = 'chunk-card';
            div.innerHTML = `
                <div class="chunk-card-title"><i class="fa-solid fa-cube"></i> ${chunk.id}</div>
                <div class="chunk-card-node">Primary: <strong>${chunk.primaryNode}</strong></div>
                <div class="chunk-card-node">Replicas: <strong>${chunk.replicas.join(', ') || 'None'}</strong></div>
                <div style="color: var(--text-dim); margin-top: 0.2rem;">${formatBytes(chunk.size)}</div>
            `;
            chunksContainer.appendChild(div);
        });
    }

    async function simulateNodeFailure() {
        const targetId = faultNodeSelect.value;
        const targetNode = state.nodes.find(n => n.id === targetId);
        if (!targetNode) return;

        targetNode.status = 'FAILED';
        renderNodes();

        const banner = document.getElementById('recovery-output-banner');
        banner.style.display = 'block';
        banner.className = 'visualizer-card';
        banner.style.borderColor = 'var(--danger)';
        banner.innerHTML = `
            <div style="color: var(--danger); font-weight: 700;">⚠ FAILURE DETECTED ON ${targetId}</div>
            <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;">
                Manager health monitor detected missing heartbeats. Initiating automatic cluster recovery from surviving replicas...
            </div>
            <div class="progress-bar-bg" style="margin-top: 1rem;"><div id="rec-prog-fill" class="progress-bar-fill" style="width: 0%; background: var(--warning);"></div></div>
        `;

        const fill = document.getElementById('rec-prog-fill');
        await animateProgressBar(fill, 0, 100, 1500);

        banner.style.borderColor = 'var(--success)';
        banner.innerHTML = `
            <div style="color: var(--success); font-weight: 700;"><i class="fa-solid fa-circle-check"></i> RECOVERY SUCCESSFUL — DATA RESTORED</div>
            <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;">
                Chunks previously on ${targetId} were automatically reconciled and re-replicated to remaining healthy nodes. SHA-256 integrity verified 100%.
            </div>
        `;

        setTimeout(() => {
            targetNode.status = 'HEALTHY';
            renderNodes();
        }, 3000);
    }

    async function simulateChunkCorruption() {
        const banner = document.getElementById('recovery-output-banner');
        banner.style.display = 'block';
        banner.className = 'visualizer-card';
        banner.style.borderColor = 'var(--warning)';
        banner.innerHTML = `
            <div style="color: var(--warning); font-weight: 700;">⚠ CHUNK CORRUPTION DETECTED</div>
            <div style="font-size: 0.85rem; font-family: var(--font-mono); color: var(--text-muted); margin-top: 0.5rem;">
                Chunk chk_001 SHA-256 Mismatch!<br>
                Expected: 5a7d6560ef71...<br>
                Actual:   99f011a842b1... (Corrupted)
            </div>
            <div class="progress-bar-bg" style="margin-top: 1rem;"><div id="rec-prog-fill" class="progress-bar-fill" style="width: 0%; background: var(--primary);"></div></div>
        `;

        const fill = document.getElementById('rec-prog-fill');
        await animateProgressBar(fill, 0, 100, 1200);

        banner.style.borderColor = 'var(--success)';
        banner.innerHTML = `
            <div style="color: var(--success); font-weight: 700;"><i class="fa-solid fa-shield-halved"></i> CORRUPTED CHUNK HEALED & RESTORED</div>
            <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;">
                AirStore identified checksum anomaly on local chunk read, fetched clean replica from Node-02, overwrote corrupted sector, and verified SHA-256 match.
            </div>
        `;
    }

    async function runResumableDemo() {
        const banner = document.getElementById('recovery-output-banner');
        banner.style.display = 'block';
        banner.className = 'visualizer-card';
        banner.style.borderColor = 'var(--primary)';
        
        banner.innerHTML = `
            <div style="color: var(--primary); font-weight: 700;">▶ RESUMABLE TRANSFER DEMONSTRATION</div>
            <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;" id="resumable-status">
                Uploading file (Chunk 1/5)...
            </div>
            <div class="progress-bar-bg" style="margin-top: 1rem;"><div id="rec-prog-fill" class="progress-bar-fill" style="width: 0%;"></div></div>
        `;

        const fill = document.getElementById('rec-prog-fill');
        const statusEl = document.getElementById('resumable-status');

        await animateProgressBar(fill, 0, 60, 1000);
        statusEl.innerHTML = `<span style="color: var(--danger); font-weight: 700;">⚠ Network connection lost at 60%! Interrupted.</span>`;
        await sleep(1000);

        statusEl.innerHTML = `<span style="color: var(--warning); font-weight: 700;">Re-connecting... Verifying existing chunks on cluster...</span>`;
        await sleep(1000);

        statusEl.innerHTML = `<span style="color: var(--success);">Skipping Chunks 1-3 (Already Verified). Resuming Chunk 4...</span>`;
        await animateProgressBar(fill, 60, 100, 1000);

        banner.style.borderColor = 'var(--success)';
        statusEl.innerHTML = `<strong style="color: var(--success);">✓ Transfer 100% Complete! Saved 60% bandwidth via resumable chunk validation.</strong>`;
    }

    function animateProgressBar(el, start, end, duration) {
        return new Promise(resolve => {
            const startTime = performance.now();
            function step(now) {
                const elapsed = now - startTime;
                const progress = Math.min(elapsed / duration, 1);
                const currentVal = start + (end - start) * progress;
                el.style.width = `${currentVal}%`;
                if (progress < 1) {
                    requestAnimationFrame(step);
                } else {
                    resolve();
                }
            }
            requestAnimationFrame(step);
        });
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function resetSimulation() {
        state.selectedFile = null;
        state.fileHash = null;
        metaBox.classList.remove('active');
        document.getElementById('recovery-output-banner').style.display = 'none';
        createSampleFile();
        initNodes();
        pipelineSteps.forEach(step => {
            step.classList.remove('active', 'done');
            step.querySelector('.step-status').textContent = '⋯';
        });
        chunksContainer.innerHTML = '<div style="color: var(--text-dim); font-size: 0.85rem;">Run simulation to view chunk distribution map.</div>';
    }

    function updateUI() {
        nodeCountVal.textContent = state.nodeCount;
    }
});
