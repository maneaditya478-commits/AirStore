document.addEventListener('DOMContentLoaded', () => {
    // Navigation setup
    const navItems = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');
    const pageTitle = document.getElementById('page-title');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tab = item.getAttribute('data-tab');
            
            navItems.forEach(n => n.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            item.classList.add('active');
            document.getElementById(`tab-${tab}`).classList.add('active');
            pageTitle.textContent = item.textContent.trim();
        });
    });

    // Formatting helpers
    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    function formatDate(isoStr) {
        if (!isoStr) return '--';
        const d = new Date(isoStr);
        return d.toLocaleString();
    }

    // Refresh function
    async function loadData() {
        try {
            // Stats
            const statsResp = await fetch('/api/stats');
            if (statsResp.ok) {
                const stats = await statsResp.json();
                document.getElementById('stat-total-storage').textContent = formatBytes(stats.total_storage);
                document.getElementById('stat-avail-storage').textContent = formatBytes(stats.available_storage);
                document.getElementById('stat-used-storage').textContent = formatBytes(stats.used_storage);
                document.getElementById('stat-nodes-count').textContent = `${stats.online_nodes} / ${stats.total_nodes}`;
            }

            // Nodes
            const nodesResp = await fetch('/api/nodes');
            if (nodesResp.ok) {
                const nodes = await nodesResp.json();
                renderNodes(nodes);
            }

            // Files
            const filesResp = await fetch('/api/files');
            if (filesResp.ok) {
                const files = await filesResp.json();
                renderFiles(files);
            }

            // Transfers
            const transfersResp = await fetch('/api/transfers');
            if (transfersResp.ok) {
                const transfers = await transfersResp.json();
                renderTransfers(transfers);
            }

            // Events
            const eventsResp = await fetch('/api/events');
            if (eventsResp.ok) {
                const events = await eventsResp.json();
                renderEvents(events);
            }
        } catch (err) {
            console.error('Error fetching cluster data:', err);
        }
    }

    function renderNodes(nodes) {
        const miniContainer = document.getElementById('dash-nodes-container');
        const fullContainer = document.getElementById('nodes-full-container');
        
        let miniHtml = '';
        let fullHtml = '';

        nodes.forEach(n => {
            const used = n.total_storage - n.available_storage;
            const pct = n.total_storage > 0 ? Math.round((used / n.total_storage) * 100) : 0;
            const badgeClass = `badge-${n.status.toLowerCase()}`;

            miniHtml += `
                <div class="node-card">
                    <div class="node-card-header">
                        <span class="node-title">${n.node_id}</span>
                        <span class="badge ${badgeClass}">${n.status}</span>
                    </div>
                    <p style="font-size: 0.75rem; color: #94a3b8;">${n.ip}:${n.port}</p>
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" style="width: ${pct}%;"></div>
                    </div>
                    <span style="font-size: 0.75rem; color: #94a3b8;">Used ${formatBytes(used)} / ${formatBytes(n.total_storage)}</span>
                </div>
            `;

            fullHtml += `
                <div class="node-card">
                    <div class="node-card-header">
                        <div>
                            <h4 class="node-title">${n.node_id}</h4>
                            <span style="font-size: 0.75rem; color: #94a3b8;">Host: ${n.hostname} (${n.ip}:${n.port})</span>
                        </div>
                        <span class="badge ${badgeClass}">${n.status}</span>
                    </div>
                    <div style="margin: 0.75rem 0;">
                        <span style="font-size: 0.8rem;">Disk Capacity:</span>
                        <div class="progress-bar-container">
                            <div class="progress-bar-fill" style="width: ${pct}%;"></div>
                        </div>
                        <span style="font-size: 0.75rem; color: #94a3b8;">${formatBytes(used)} used of ${formatBytes(n.total_storage)} (${pct}%)</span>
                    </div>
                    <p style="font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.75rem;">Last Heartbeat: ${formatDate(n.last_heartbeat)}</p>
                    <button class="btn btn-secondary btn-block btn-recover" data-node-id="${n.node_id}">
                        <i class="fa-solid fa-wrench"></i> Run Auto-Recovery
                    </button>
                </div>
            `;
        });

        miniContainer.innerHTML = miniHtml || '<p style="color:#94a3b8;">No nodes registered.</p>';
        fullContainer.innerHTML = fullHtml || '<p style="color:#94a3b8;">No nodes registered.</p>';

        // Attach recovery buttons
        document.querySelectorAll('.btn-recover').forEach(btn => {
            btn.addEventListener('click', async () => {
                const nodeId = btn.getAttribute('data-node-id');
                if (confirm(`Trigger manual node recovery for '${nodeId}'?`)) {
                    const resp = await fetch(`/api/nodes/${nodeId}/recover`, { method: 'POST' });
                    if (resp.ok) {
                        alert(`Recovery finished for ${nodeId}!`);
                        loadData();
                    } else {
                        alert(`Recovery trigger failed.`);
                    }
                }
            });
        });
    }

    function renderFiles(files) {
        const tbody = document.getElementById('files-table-body');
        let html = '';

        files.forEach(f => {
            const badgeClass = `badge-${f.status.toLowerCase()}`;
            html += `
                <tr>
                    <td><strong>${f.filename}</strong></td>
                    <td>${formatBytes(f.size)}</td>
                    <td>${Math.ceil(f.size / f.chunk_size)}</td>
                    <td>${f.replication_factor}x</td>
                    <td style="font-family: monospace; font-size: 0.75rem;">${f.overall_hash.substring(0, 16)}...</td>
                    <td><span class="badge ${badgeClass}">${f.status}</span></td>
                    <td>${formatDate(f.created_at)}</td>
                    <td>
                        <button class="btn btn-secondary btn-file-info" data-file-id="${f.file_id}" title="Inspect Chunks">
                            <i class="fa-solid fa-circle-info"></i> Details
                        </button>
                        <a href="/api/files/${f.file_id}/download" class="btn btn-primary" title="Download">
                            <i class="fa-solid fa-download"></i>
                        </a>
                        <button class="btn btn-danger btn-file-delete" data-file-id="${f.file_id}" title="Delete">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html || '<tr><td colspan="8" style="text-align:center; color:#94a3b8;">No files uploaded yet.</td></tr>';

        // Details click
        document.querySelectorAll('.btn-file-info').forEach(btn => {
            btn.addEventListener('click', () => showFileDetails(btn.getAttribute('data-file-id')));
        });

        // Delete click
        document.querySelectorAll('.btn-file-delete').forEach(btn => {
            btn.addEventListener('click', async () => {
                const fileId = btn.getAttribute('data-file-id');
                if (confirm("Delete file and all its distributed chunk replicas from the network?")) {
                    await fetch(`/api/files/${fileId}`, { method: 'DELETE' });
                    loadData();
                }
            });
        });
    }

    async function showFileDetails(fileId) {
        const modal = document.getElementById('modal-file-detail');
        const container = document.getElementById('file-detail-content');
        
        try {
            const resp = await fetch(`/api/files/${fileId}`);
            if (!resp.ok) return;
            const detail = await resp.json();

            let html = `
                <div style="margin-bottom: 1.5rem;">
                    <h4>${detail.file.filename}</h4>
                    <p style="font-size:0.8rem; color:#94a3b8;">File ID: ${detail.file.file_id}</p>
                    <p style="font-size:0.8rem; color:#94a3b8;">Overall SHA-256: <code>${detail.file.overall_hash}</code></p>
                </div>
                <h5>Distributed Chunk Map</h5>
                <table class="data-table" style="margin-top: 0.5rem;">
                    <thead>
                        <tr>
                            <th>Seq</th>
                            <th>Chunk ID</th>
                            <th>Size</th>
                            <th>SHA-256 Checksum</th>
                            <th>Replica Node Locations</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            detail.chunks.forEach(c => {
                const chunkReps = detail.replicas.filter(r => r.chunk_id === c.chunk_id);
                const nodeBadges = chunkReps.map(r => {
                    const node = detail.nodes[r.node_id];
                    const nodeName = node ? `${node.node_id} (${node.ip}:${node.port})` : r.node_id;
                    const st = r.status === 'STORED' ? 'badge-stored' : 'badge-missing';
                    return `<span class="badge ${st}" style="margin-right: 4px;">${nodeName}</span>`;
                }).join(' ');

                html += `
                    <tr>
                        <td>#${c.sequence_number}</td>
                        <td style="font-family:monospace; font-size:0.75rem;">${c.chunk_id}</td>
                        <td>${formatBytes(c.size)}</td>
                        <td style="font-family:monospace; font-size:0.75rem;">${c.sha256.substring(0, 16)}...</td>
                        <td>${nodeBadges || 'No replicas'}</td>
                    </tr>
                `;
            });

            html += `</tbody></table>`;
            container.innerHTML = html;
            modal.classList.add('active');
        } catch (err) {
            console.error('Failed to load file details:', err);
        }
    }

    function renderTransfers(transfers) {
        const tbody = document.getElementById('transfers-table-body');
        let html = '';

        transfers.forEach(t => {
            const badgeClass = `badge-${t.status.toLowerCase()}`;
            html += `
                <tr>
                    <td style="font-family:monospace; font-size:0.75rem;">${t.transfer_id}</td>
                    <td><strong>${t.transfer_type}</strong></td>
                    <td style="width: 220px;">
                        <div class="progress-bar-container">
                            <div class="progress-bar-fill success" style="width: ${t.progress}%;"></div>
                        </div>
                        <span style="font-size:0.75rem;">${t.progress}%</span>
                    </td>
                    <td>${t.speed_mbps} MB/s</td>
                    <td><span class="badge ${badgeClass}">${t.status}</span></td>
                    <td>${formatDate(t.started_at)}</td>
                </tr>
            `;
        });

        tbody.innerHTML = html || '<tr><td colspan="6" style="text-align:center; color:#94a3b8;">No transfer activity.</td></tr>';
    }

    function renderEvents(events) {
        const feed = document.getElementById('dash-activity-feed');
        const tbody = document.getElementById('events-table-body');

        // Mini feed
        let miniHtml = '';
        events.slice(0, 5).forEach(e => {
            miniHtml += `
                <li class="activity-item">
                    <div><strong>${e.event_type}</strong>: ${e.message}</div>
                    <div class="activity-time">${formatDate(e.timestamp)}</div>
                </li>
            `;
        });
        feed.innerHTML = miniHtml || '<li class="activity-item">No recent events.</li>';

        // Full table
        let fullHtml = '';
        events.forEach(e => {
            fullHtml += `
                <tr>
                    <td>${formatDate(e.timestamp)}</td>
                    <td><span class="badge badge-active">${e.event_type}</span></td>
                    <td>${e.message}</td>
                    <td style="font-size:0.75rem; font-family:monospace;">${e.details ? JSON.stringify(e.details) : ''}</td>
                </tr>
            `;
        });
        tbody.innerHTML = fullHtml || '<tr><td colspan="4" style="text-align:center; color:#94a3b8;">No events logged.</td></tr>';
    }

    // Modal controls
    const uploadModal = document.getElementById('modal-upload');
    const btnQuickUpload = document.getElementById('btn-quick-upload');
    const closeUploadModal = document.getElementById('close-upload-modal');
    const closeDetailModal = document.getElementById('close-detail-modal');
    const fileDetailModal = document.getElementById('modal-file-detail');

    btnQuickUpload.addEventListener('click', () => uploadModal.classList.add('active'));
    closeUploadModal.addEventListener('click', () => uploadModal.classList.remove('active'));
    closeDetailModal.addEventListener('click', () => fileDetailModal.classList.remove('active'));

    // Dropzone & Upload form
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const selectedFileName = document.getElementById('selected-file-name');

    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            selectedFileName.textContent = `Selected: ${fileInput.files[0].name} (${formatBytes(fileInput.files[0].size)})`;
        }
    });

    document.getElementById('upload-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!fileInput.files.length) {
            alert('Please select a file to upload.');
            return;
        }

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('chunk_size', document.getElementById('chunk-size-input').value);
        formData.append('replication_factor', document.getElementById('replication-input').value);

        const btnSubmit = document.getElementById('btn-submit-upload');
        btnSubmit.disabled = true;
        btnSubmit.textContent = 'Uploading Chunks...';

        try {
            const resp = await fetch('/api/files/upload', {
                method: 'POST',
                body: formData
            });

            if (resp.ok) {
                uploadModal.classList.remove('active');
                loadData();
                alert('File uploaded successfully!');
            } else {
                const err = await resp.json();
                alert(`Upload failed: ${err.detail || 'Unknown error'}`);
            }
        } catch (err) {
            alert(`Upload error: ${err}`);
        } finally {
            btnSubmit.disabled = false;
            btnSubmit.textContent = 'Start Distributed Upload';
        }
    });

    document.getElementById('btn-refresh').addEventListener('click', loadData);

    // Initial load & periodic poll
    loadData();
    setInterval(loadData, 3000);
});
