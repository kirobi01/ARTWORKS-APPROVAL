const CHUNK_SIZE = 2 * 1024 * 1024; // 2 MB

const ChunkUploader = {
    async uploadFile(file, artworkNo, options = {}) {
        const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
        const uploadId = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;

        for (let i = 0; i < totalChunks; i++) {
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, file.size);
            const chunk = file.slice(start, end);

            const formData = new FormData();
            formData.append('chunk', chunk);
            formData.append('chunk_index', i);
            formData.append('total_chunks', totalChunks);
            formData.append('upload_id', uploadId);
            formData.append('filename', file.name);
            formData.append('description', options.description || '');
            formData.append('is_primary', options.isPrimary ? 'true' : 'false');

            const response = await fetch(`/artwork/${artworkNo}/upload-chunk/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken },
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Upload failed');
            }

            const progress = ((i + 1) / totalChunks) * 100;
            if (options.onProgress) options.onProgress(progress);
        }
    },

    initDropZone(zoneEl, artworkNo, fileListEl, onComplete) {
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.accept = '.jpg,.jpeg,.png,.pdf,.ai,.eps,.tiff,.tif,.svg';
        input.style.display = 'none';
        zoneEl.appendChild(input);

        zoneEl.addEventListener('click', () => input.click());
        zoneEl.addEventListener('dragover', (e) => { e.preventDefault(); zoneEl.classList.add('dragover'); });
        zoneEl.addEventListener('dragleave', () => zoneEl.classList.remove('dragover'));
        zoneEl.addEventListener('drop', (e) => {
            e.preventDefault();
            zoneEl.classList.remove('dragover');
            this._handleFiles(e.dataTransfer.files, artworkNo, fileListEl, onComplete);
        });
        input.addEventListener('change', () => {
            this._handleFiles(input.files, artworkNo, fileListEl, onComplete);
            input.value = '';
        });
    },

    async _handleFiles(files, artworkNo, fileListEl, onComplete) {
        for (const file of files) {
            const itemEl = document.createElement('div');
            itemEl.className = 'file-item';
            itemEl.innerHTML = `
                <span>${file.name}</span>
                <div class="upload-progress"><div class="upload-progress-bar"></div></div>
                <span class="upload-status">Uploading...</span>
            `;
            fileListEl.appendChild(itemEl);
            const bar = itemEl.querySelector('.upload-progress-bar');
            const status = itemEl.querySelector('.upload-status');

            try {
                const isFirst = fileListEl.querySelectorAll('.file-item').length === 1;
                await this.uploadFile(file, artworkNo, {
                    isPrimary: isFirst,
                    onProgress: (pct) => { bar.style.width = pct + '%'; },
                });
                status.textContent = 'Done';
                status.style.color = '#28a745';
            } catch (err) {
                status.textContent = err.message;
                status.style.color = '#dc3545';
            }
        }
        if (onComplete) onComplete();
    },
};

async function submitApproval(action) {
    const comments = document.getElementById('approvalComments').value.trim();
    if (!comments) {
        alert('Comments are required before approving or rejecting.');
        return;
    }
    if (action === 'rejected' && !confirm('Are you sure? This will send the artwork back to Design for revision.')) {
        return;
    }
    const formData = new FormData();
    formData.append('comments', comments);
    formData.append('action', action);
    formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

    const response = await fetch(window.location.href, {
        method: 'POST',
        headers: { 'X-CSRFToken': formData.get('csrfmiddlewaretoken') },
        body: formData,
    });
    const data = await response.json();
    if (data.success) {
        window.location.href = data.redirect || '/artwork/pending/';
    } else {
        alert(data.message || 'Action failed.');
    }
}
