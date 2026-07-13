const ArtworkViewer = {
    scale: 1,
    minScale: 0.25,
    maxScale: 8,
    isDragging: false,
    startX: 0,
    startY: 0,
    translateX: 0,
    translateY: 0,

    open(url) {
        const viewer = document.getElementById('imageViewer');
        const img = document.getElementById('viewerImage');
        img.src = url;
        this.resetZoom();
        viewer.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        this._bindEvents();
    },

    close() {
        document.getElementById('imageViewer').style.display = 'none';
        document.body.style.overflow = '';
        this._unbindEvents();
    },

    zoomIn() {
        this.scale = Math.min(this.maxScale, this.scale * 1.25);
        this._applyTransform();
    },

    zoomOut() {
        this.scale = Math.max(this.minScale, this.scale / 1.25);
        this._applyTransform();
    },

    resetZoom() {
        this.scale = 1;
        this.translateX = 0;
        this.translateY = 0;
        this._applyTransform();
    },

    _applyTransform() {
        const img = document.getElementById('viewerImage');
        img.style.transform = `translate(${this.translateX}px, ${this.translateY}px) scale(${this.scale})`;
    },

    _bindEvents() {
        const canvas = document.getElementById('viewerCanvas');
        this._wheelHandler = (e) => {
            e.preventDefault();
            if (e.deltaY < 0) this.zoomIn();
            else this.zoomOut();
        };
        this._mousedownHandler = (e) => {
            this.isDragging = true;
            this.startX = e.clientX - this.translateX;
            this.startY = e.clientY - this.translateY;
            canvas.style.cursor = 'grabbing';
        };
        this._mousemoveHandler = (e) => {
            if (!this.isDragging) return;
            this.translateX = e.clientX - this.startX;
            this.translateY = e.clientY - this.startY;
            this._applyTransform();
        };
        this._mouseupHandler = () => {
            this.isDragging = false;
            canvas.style.cursor = 'grab';
        };
        this._keydownHandler = (e) => {
            if (e.key === 'Escape') this.close();
        };
        canvas.addEventListener('wheel', this._wheelHandler, { passive: false });
        canvas.addEventListener('mousedown', this._mousedownHandler);
        document.addEventListener('mousemove', this._mousemoveHandler);
        document.addEventListener('mouseup', this._mouseupHandler);
        document.addEventListener('keydown', this._keydownHandler);
    },

    _unbindEvents() {
        const canvas = document.getElementById('viewerCanvas');
        if (this._wheelHandler) canvas.removeEventListener('wheel', this._wheelHandler);
        if (this._mousedownHandler) canvas.removeEventListener('mousedown', this._mousedownHandler);
        if (this._mousemoveHandler) document.removeEventListener('mousemove', this._mousemoveHandler);
        if (this._mouseupHandler) document.removeEventListener('mouseup', this._mouseupHandler);
        if (this._keydownHandler) document.removeEventListener('keydown', this._keydownHandler);
    },
};

function openImagePreview(url) {
    ArtworkViewer.open(url);
}
