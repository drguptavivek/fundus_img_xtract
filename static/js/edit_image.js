function getCSRFToken() {
  // Prefer hidden input (Flask-WTF forms)
  const input = document.querySelector('input[name="csrf_token"]');
  if (input && input.value) return input.value;

  // Fallback to meta tag if you render one in your layout
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;

  return '';
}



document.addEventListener('DOMContentLoaded', function() {
    const canvas = document.getElementById('imageCanvas');
    const ctx = canvas.getContext('2d');
    const overlayCanvas = document.getElementById('ocrOverlayCanvas');
    const overlayCtx = overlayCanvas ? overlayCanvas.getContext('2d') : null;
    let img = new Image();

    // --- STATE ---
    let currentTool = 'brush';
    let brushSize = 10;
    let brushColor = '#000000';
    let history = [];
    let historyIndex = -1;

    // Drawing state
    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;

    // Cropping state (one non-destructive rectangular selection)
    let isCropping = false;         // actively interacting (down → move → up)
    let crop = null;                // { x, y, width, height } OR null
    let cropBase = null;            // clean pixels beneath the temporary overlay
    let cropMode = null;            // 'creating' | 'moving' | 'resizing'
    let activeHandle = null;        // 'NW' | 'NE' | 'SE' | 'SW' | null
    let cropAnchorX = 0, cropAnchorY = 0;
    let resizeAnchorX = 0, resizeAnchorY = 0;
    let dragDX = 0, dragDY = 0;     // for moving (pointer offset from top-left)

    const HANDLE_SIZE = 10;         // px
    const MIN_CROP_SIZE = 16;
    let antsOffset = 0;             // marching ants
    let antsRAF = null;

    // --- DOM ELEMENTS ---
    const brushSizeSlider = document.getElementById('brush-size');
    const brushSizeValue = document.getElementById('brush-size-value');
    const brushColorPicker = document.getElementById('brush-color');
    const clearCanvasBtn = document.getElementById('clear-canvas');
    const undoBtn = document.getElementById('undo');
    const redoBtn = document.getElementById('redo');
    const saveImageBtn = document.getElementById('save-image');
    const restoreBtn = document.getElementById('restore-original');
    const applyCropBtn = document.getElementById('apply-crop');
    const toggleOcrBtn = document.getElementById('toggle-ocr-overlay');
    const ocrStatusBadge = document.getElementById('ocr-status-badge');
    const ocrRedetectBtn = document.getElementById('ocr-redetect');

    const imageUuid = canvas.dataset.imageUuid;
    let ocrOverlayEnabled = false;
    let ocrOverlayLoaded = false;
    let ocrDetections = [];
    let ocrStatusLoaded = false;

    // --- INITIALIZATION ---
    img.onload = function() {
        // Set canvas to image pixel size (simple mode; if you need HiDPI crispness, we can add DPR scaling)
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
        if (overlayCanvas) {
            overlayCanvas.width = img.width;
            overlayCanvas.height = img.height;
        }
        saveState();
        brushColor = brushColorPicker.value; // Initialize brush color from the picker
    };
    img.src = canvas.dataset.imageUrl;

    // --- TOOL SELECTION ---
    const editingLocked = canvas.dataset.editingLocked === 'true';

    if (editingLocked) {
        canvas.style.cursor = 'not-allowed';
        canvas.style.pointerEvents = 'none';
        [clearCanvasBtn, undoBtn, redoBtn, saveImageBtn, restoreBtn, applyCropBtn, brushSizeSlider, brushColorPicker].forEach(el => {
            if (el) {
                el.disabled = true;
            }
        });
    }

    document.querySelectorAll('input[name="tool"]').forEach(radio => {
        radio.addEventListener('change', function() {
            currentTool = this.value;
            if (currentTool !== 'crop') {
                stopAnts();
                applyCropBtn.style.display = 'none';
                if (cropBase) {
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    ctx.drawImage(cropBase, 0, 0);
                }
                cropBase = null;
                crop = null;
                cropMode = null;
                activeHandle = null;
            } else {
                captureCropBase();
                applyCropBtn.style.display = 'none';
            }
            updateCursor();
        });
    });

    function updateCursor() {
        canvas.style.cursor = currentTool === 'crop' ? 'crosshair' : 'default';
    }

    function clearOcrOverlay() {
        if (!overlayCtx || !overlayCanvas) return;
        overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    }

    function setOcrStatusBadge(status, label, source) {
        if (!ocrStatusBadge) return;
        const sourceTag = source ? ` (${source})` : '';
        const text = label ? `OCR: ${label}${sourceTag}` : `OCR: ${status || 'pending'}${sourceTag}`;
        ocrStatusBadge.textContent = text;
        ocrStatusBadge.className = 'badge';
        if (status === 'detected') {
            ocrStatusBadge.classList.add('text-bg-danger');
        } else if (status === 'clear') {
            ocrStatusBadge.classList.add('text-bg-success');
        } else if (status === 'error') {
            ocrStatusBadge.classList.add('text-bg-warning');
        } else {
            ocrStatusBadge.classList.add('text-bg-secondary');
        }
    }

    function fetchOcrStatus() {
        if (ocrStatusLoaded || !imageUuid) return;
        fetch(`/api/ocr/pii/${encodeURIComponent(imageUuid)}`, {
            headers: { 'Accept': 'application/json' }
        })
            .then(response => response.json())
            .then(payload => {
                const data = payload && payload.data ? payload.data : null;
                if (!data || !data.status) return;
                ocrStatusLoaded = true;
                setOcrStatusBadge(
                    data.status,
                    data.status === 'detected' ? 'PII detected' : (data.status === 'clear' ? 'No PII' : 'OCR unavailable'),
                    data.source
                );
            })
            .catch(() => {});
    }

    function drawOcrOverlay() {
        if (!overlayCtx || !overlayCanvas) return;
        clearOcrOverlay();
        if (!ocrOverlayEnabled || !ocrDetections.length) return;
        overlayCtx.save();
        overlayCtx.lineWidth = 2;
        overlayCtx.font = '12px sans-serif';
        overlayCtx.textBaseline = 'top';
        ocrDetections.forEach(det => {
            const box = det.box || {};
            const x = box.x || 0;
            const y = box.y || 0;
            const w = box.w || 0;
            const h = box.h || 0;
            if (!w || !h) return;
            const isMatch = !!det.matches_pattern;
            const color = isMatch ? 'rgba(220, 53, 69, 0.9)' : 'rgba(13, 110, 253, 0.9)';
            overlayCtx.strokeStyle = color;
            overlayCtx.strokeRect(x, y, w, h);
            const label = `${det.text || ''} (${det.conf || 0})`;
            const padding = 2;
            const textWidth = overlayCtx.measureText(label).width;
            const labelX = x;
            const labelY = y > 14 ? y - 14 : y + 2;
            overlayCtx.fillStyle = 'rgba(255, 255, 255, 0.85)';
            overlayCtx.fillRect(labelX, labelY, textWidth + padding * 2, 14);
            overlayCtx.fillStyle = color;
            overlayCtx.fillText(label, labelX + padding, labelY + 1);
        });
        overlayCtx.restore();
    }

    function fetchOcrOverlay() {
        if (ocrOverlayLoaded || !imageUuid) return;
        fetch(`/api/ocr/pii/boxes/${encodeURIComponent(imageUuid)}`, {
            headers: { 'Accept': 'application/json' }
        })
            .then(response => response.json())
            .then(payload => {
                const data = payload && payload.data ? payload.data : null;
                if (!data || !data.detections) return;
                ocrDetections = data.detections;
                ocrOverlayLoaded = true;
                if (!ocrDetections.length) {
                    setOcrStatusBadge(data.status || 'clear', 'No OCR detections', data.source);
                } else {
                    setOcrStatusBadge(
                        data.status,
                        data.status === 'detected' ? 'PII detected' : (data.status === 'clear' ? 'No PII' : 'OCR unavailable'),
                        data.source
                    );
                }
                drawOcrOverlay();
            })
            .catch(() => {});
    }

    if (toggleOcrBtn) {
        toggleOcrBtn.addEventListener('click', () => {
            ocrOverlayEnabled = !ocrOverlayEnabled;
            toggleOcrBtn.classList.toggle('active', ocrOverlayEnabled);
            if (ocrOverlayEnabled) {
                fetchOcrOverlay();
            } else {
                clearOcrOverlay();
            }
        });
    }

    if (ocrRedetectBtn) {
        ocrRedetectBtn.addEventListener('click', () => {
            if (!imageUuid) return;
            ocrOverlayLoaded = false;
            ocrDetections = [];
            clearOcrOverlay();
            fetch(`/api/ocr/pii/${encodeURIComponent(imageUuid)}?refresh=1`, {
                headers: { 'Accept': 'application/json' }
            })
                .then(response => response.json())
                .then(payload => {
                    const data = payload && payload.data ? payload.data : null;
                    if (!data || !data.status) return;
                    ocrStatusLoaded = true;
                    setOcrStatusBadge(
                        data.status,
                        data.status === 'detected' ? 'PII detected' : (data.status === 'clear' ? 'No PII' : 'OCR unavailable'),
                        data.source
                    );
                    if (ocrOverlayEnabled) {
                        fetchOcrOverlay();
                    }
                })
                .catch(() => {});
        });
    }

    document.addEventListener('click', (event) => {
        const btn = event.target.closest('#ocr-redetect');
        if (!btn || ocrRedetectBtn) {
            return;
        }
        if (!imageUuid) return;
        ocrOverlayLoaded = false;
        ocrDetections = [];
        clearOcrOverlay();
        fetch(`/api/ocr/pii/${encodeURIComponent(imageUuid)}?refresh=1`, {
            headers: { 'Accept': 'application/json' }
        })
            .then(response => response.json())
            .then(payload => {
                const data = payload && payload.data ? payload.data : null;
                if (!data || !data.status) return;
                ocrStatusLoaded = true;
                setOcrStatusBadge(
                    data.status,
                    data.status === 'detected' ? 'PII detected' : (data.status === 'clear' ? 'No PII' : 'OCR unavailable'),
                    data.source
                );
                if (ocrOverlayEnabled) {
                    fetchOcrOverlay();
                }
            })
            .catch(() => {});
    });

    fetchOcrStatus();

    // --- BRUSH CONTROLS ---
    brushSizeSlider.addEventListener('input', () => {
        brushSize = parseInt(brushSizeSlider.value, 10);
        brushSizeValue.textContent = brushSize + 'px';
    });
    brushColorPicker.addEventListener('input', () => { brushColor = brushColorPicker.value; });

    // --- HISTORY MANAGEMENT (UNDO/REDO) ---
    function saveState() {
        historyIndex++;
        history.splice(historyIndex);
        history.push(canvas.toDataURL());
        updateUndoRedoButtons();
    }

    function updateUndoRedoButtons() {
        undoBtn.disabled = historyIndex <= 0;
        redoBtn.disabled = historyIndex >= history.length - 1;
    }

    function restoreState(index) {
        const imgData = new Image();
        imgData.onload = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(imgData, 0, 0);
        };
        imgData.src = history[index];
    }

    undoBtn.addEventListener('click', () => {
        if (historyIndex > 0) {
            historyIndex--;
            restoreState(historyIndex);
        }
    });
    redoBtn.addEventListener('click', () => {
        if (historyIndex < history.length - 1) {
            historyIndex++;
            restoreState(historyIndex);
        }
    });

    // --- ACTIONS ---
    clearCanvasBtn.addEventListener('click', () => {
        if (confirm('Are you sure you want to clear all edits?')) {
            restoreState(0); // Restore to the initial image state
            history.splice(1); // Clear all subsequent history
            historyIndex = 0;
            updateUndoRedoButtons();
        }
    });

    applyCropBtn.addEventListener('click', applyCrop);

    // --- POINTER → CANVAS COORD MAP (handles visual scaling) ---
    function getCanvasCoordinates(e) {
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;

        const clientX = (e.touches ? e.touches[0].clientX : e.clientX);
        const clientY = (e.touches ? e.touches[0].clientY : e.clientY);

        return {
            x: (clientX - rect.left) * scaleX,
            y: (clientY - rect.top) * scaleY
        };
    }

    // --- CROP HELPERS ---
    function captureCropBase() {
        cropBase = document.createElement('canvas');
        cropBase.width = canvas.width;
        cropBase.height = canvas.height;
        cropBase.getContext('2d').drawImage(canvas, 0, 0);
    }

    function pointInCrop(x, y, c) {
        return !!c && x >= c.x && x <= c.x + c.width && y >= c.y && y <= c.y + c.height;
    }

    function handlePositions(c) {
        if (!c) return [];
        return [
            { id: 'NW', x: c.x,           y: c.y },
            { id: 'NE', x: c.x + c.width, y: c.y },
            { id: 'SE', x: c.x + c.width, y: c.y + c.height },
            { id: 'SW', x: c.x,           y: c.y + c.height },
        ];
    }

    function hitTestHandle(x, y, c) {
        const hs = HANDLE_SIZE;
        for (const h of handlePositions(c)) {
            if (Math.abs(x - h.x) <= hs && Math.abs(y - h.y) <= hs) {
                return h.id;
            }
        }
        return null;
    }

    function setCropCursor(x, y) {
        if (!crop) { canvas.style.cursor = 'crosshair'; return; }
        const h = hitTestHandle(x, y, crop);
        if (h === 'NW' || h === 'SE') { canvas.style.cursor = 'nwse-resize'; return; }
        if (h === 'NE' || h === 'SW') { canvas.style.cursor = 'nesw-resize'; return; }
        if (pointInCrop(x, y, crop)) {
            canvas.style.cursor = 'move'; return;
        }
        canvas.style.cursor = 'crosshair';
    }

    function clampCropInBounds(c) {
        c.width = Math.max(MIN_CROP_SIZE, Math.min(c.width, canvas.width));
        c.height = Math.max(MIN_CROP_SIZE, Math.min(c.height, canvas.height));
        c.x = Math.max(0, Math.min(canvas.width - c.width, c.x));
        c.y = Math.max(0, Math.min(canvas.height - c.height, c.y));
    }

    // --- OVERLAY DRAW ---
    function redrawWithCropOverlay() {
        if (!cropBase) return;

        // Base
        ctx.globalCompositeOperation = 'source-over';
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(cropBase, 0, 0);

        if (!crop) return;
        const { x, y, width, height } = crop;

        // Dim outside (spotlight)
        ctx.save();
        ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
        ctx.beginPath();
        ctx.rect(0, 0, canvas.width, canvas.height);
        ctx.rect(x, y, width, height);
        ctx.fill('evenodd');
        ctx.restore();

        // Double border (white + marching ants)
        ctx.save();
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(255,255,255,0.95)';
        ctx.setLineDash([]);
        ctx.strokeRect(x, y, width, height);

        ctx.lineWidth = 2;
        ctx.strokeStyle = '#000';
        ctx.setLineDash([8, 6]);
        ctx.lineDashOffset = antsOffset;
        ctx.strokeRect(x, y, width, height);
        ctx.restore();

        // Handles
        for (const h of handlePositions(crop)) drawHandle(h.x, h.y);

        // Size label
        drawLabel(`${Math.round(width)} × ${Math.round(height)} px`, x + width / 2, y - 14);
    }

    function drawHandle(x, y) {
        const s = HANDLE_SIZE;
        ctx.save();
        ctx.fillStyle = '#fff';
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.rect(x - s/2, y - s/2, s, s);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
    }

    function drawLabel(text, x, y) {
        ctx.save();
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        const w = ctx.measureText(text).width + 12;
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(x - w/2, y - 16, w, 16);
        ctx.fillStyle = '#fff';
        ctx.fillText(text, x, y - 2);
        ctx.restore();
    }

    // --- MARCHING ANTS ---
    function tickAnts() {
        antsOffset = (antsOffset - 1) % 14;
        redrawWithCropOverlay();
        antsRAF = requestAnimationFrame(tickAnts);
    }
    function startAnts() { if (!antsRAF) antsRAF = requestAnimationFrame(tickAnts); }
    function stopAnts()  { if (antsRAF) { cancelAnimationFrame(antsRAF); antsRAF = null; } }

    // --- EVENT HANDLERS ---
    function start(e) {
        e.preventDefault();
        const { x, y } = getCanvasCoordinates(e);

        if (currentTool === 'crop') {
            isCropping = true;
            if (!cropBase) captureCropBase();

            // Decide interaction mode
            if (crop) {
                const h = hitTestHandle(x, y, crop);
                if (h) {
                    cropMode = 'resizing';
                    activeHandle = h;
                    resizeAnchorX = h.includes('W') ? crop.x + crop.width : crop.x;
                    resizeAnchorY = h.includes('N') ? crop.y + crop.height : crop.y;
                    startAnts();
                    redrawWithCropOverlay();
                    return;
                }
                if (pointInCrop(x, y, crop)) {
                    cropMode = 'moving';
                    activeHandle = null;
                    dragDX = x - crop.x;
                    dragDY = y - crop.y;
                    startAnts();
                    redrawWithCropOverlay();
                    return;
                }
            }

            // Start one new rectangle, replacing the previous selection only.
            cropMode = 'creating';
            activeHandle = null;
            cropAnchorX = x;
            cropAnchorY = y;
            crop = { x, y, width: MIN_CROP_SIZE, height: MIN_CROP_SIZE };
            startAnts();
            redrawWithCropOverlay();
            return;
        }

        // Brush/Eraser path
        isDrawing = true;
        lastX = x;
        lastY = y;
    }

    function draw(e) {
        e.preventDefault();
        const pt = getCanvasCoordinates(e);

        if (currentTool === 'crop') {
            if (!isCropping || !crop) {
                setCropCursor(pt.x, pt.y); // hover feedback
                return;
            }

            const { x, y } = pt;
            if (cropMode === 'creating') {
                crop.x = Math.min(cropAnchorX, x);
                crop.y = Math.min(cropAnchorY, y);
                crop.width = Math.max(MIN_CROP_SIZE, Math.abs(x - cropAnchorX));
                crop.height = Math.max(MIN_CROP_SIZE, Math.abs(y - cropAnchorY));
            } else if (cropMode === 'moving') {
                crop.x = x - dragDX;
                crop.y = y - dragDY;
            } else if (cropMode === 'resizing') {
                crop.x = Math.min(x, resizeAnchorX);
                crop.y = Math.min(y, resizeAnchorY);
                crop.width = Math.max(MIN_CROP_SIZE, Math.abs(x - resizeAnchorX));
                crop.height = Math.max(MIN_CROP_SIZE, Math.abs(y - resizeAnchorY));
            }
            clampCropInBounds(crop);
            redrawWithCropOverlay();
            return;
        }

        // Brush/Eraser draw
        if (isDrawing) {
            const { x: currentX, y: currentY } = pt;
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(currentX, currentY);
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.lineWidth = brushSize;

            if (currentTool === 'brush') {
                ctx.strokeStyle = brushColor;
                ctx.globalCompositeOperation = 'source-over';
            } else if (currentTool === 'eraser') {
                ctx.globalCompositeOperation = 'destination-out';
            }
            ctx.stroke();
            lastX = currentX;
            lastY = currentY;
        }
    }

    function stop() {
        if (isDrawing) {
            isDrawing = false;
            saveState();
        }
        if (isCropping) {
            isCropping = false;
            stopAnts();
            applyCropBtn.style.display = crop ? 'block' : 'none';
        }
    }

    // --- APPLY CROP ---
    function applyCrop() {
        if (!crop) return;

        const { x, y, width, height } = crop;
        const cropped = document.createElement('canvas');
        cropped.width = Math.round(width);
        cropped.height = Math.round(height);
        cropped.getContext('2d').drawImage(
            cropBase,
            Math.round(x), Math.round(y), Math.round(width), Math.round(height),
            0, 0, Math.round(width), Math.round(height)
        );

        stopAnts();
        canvas.width = cropped.width;
        canvas.height = cropped.height;
        ctx.drawImage(cropped, 0, 0);
        if (overlayCanvas) {
            overlayCanvas.width = canvas.width;
            overlayCanvas.height = canvas.height;
            clearOcrOverlay();
        }
        ocrOverlayEnabled = false;
        if (toggleOcrBtn) toggleOcrBtn.classList.remove('active');
        saveState();

        crop = null;
        cropBase = null;
        cropMode = null;
        activeHandle = null;
        applyCropBtn.style.display = 'none';
        const brushRadio = document.getElementById('brush-tool');
        if (brushRadio) brushRadio.click();
    }

    // --- EVENT LISTENERS ---
    canvas.addEventListener('mousedown', start);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stop);
    canvas.addEventListener('mouseout', stop);

    // End drag even if mouse leaves the canvas
    window.addEventListener('mouseup', stop);

    // (Optional) Basic touch support
    canvas.addEventListener('touchstart', (e) => { start(e); }, { passive: false });
    canvas.addEventListener('touchmove',  (e) => { draw(e);  }, { passive: false });
    canvas.addEventListener('touchend',   (e) => { stop();   }, { passive: false });

    // --- SAVE/RESTORE (unchanged) ---
    saveImageBtn.addEventListener('click', function() {
        const imageData = canvas.toDataURL();
        const saveUrl = saveImageBtn.dataset.saveUrl;
        const allowGradedEdit = saveImageBtn.dataset.allowGradedEdit === 'true';
        fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
            body: JSON.stringify({ image_data: imageData, allow_graded_edit: allowGradedEdit })
        })
        .then(async response => {
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.error || data.success === false) {
                throw new Error(data.error || data.message || `Save failed (${response.status})`);
            }
            return data;
        })
        .then(() => {
            alert('Image saved successfully!');
            window.location.reload();
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error saving image: ' + error.message);
        });
    });

    if (restoreBtn) {
        restoreBtn.addEventListener('click', function() {
            if (confirm('Are you sure you want to delete the edited version and restore the original? This cannot be undone.')) {
                const restoreUrl = restoreBtn.dataset.restoreUrl;
                const csrfToken = getCSRFToken();
                fetch(restoreUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) { alert('Error: ' + data.error); }
                    else {
                        if (data.redirect_url) { window.location.href = data.redirect_url; }
                        else { window.location.reload(); }
                    }
                })
                .catch(error => { console.error('Error:', error); alert('An unexpected error occurred.'); });
            }
        });
    }

    updateCursor();
});
