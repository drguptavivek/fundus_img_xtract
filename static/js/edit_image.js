document.addEventListener('DOMContentLoaded', function() {
    const canvas = document.getElementById('imageCanvas');
    const ctx = canvas.getContext('2d');
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

    // Cropping state
    let isCropping = false;
    let cropStart = null;
    let cropEnd = null;

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

    // --- INITIALIZATION ---
    img.onload = function() {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
        saveState();
        brushColor = brushColorPicker.value; // Initialize brushColor from the picker
    };
    img.src = canvas.dataset.imageUrl;

    // --- TOOL SELECTION ---
    document.querySelectorAll('input[name="tool"]').forEach(radio => {
        radio.addEventListener('change', function() {
            currentTool = this.value;
            applyCropBtn.style.display = (currentTool === 'crop' && cropStart) ? 'block' : 'none';
            updateCursor();
        });
    });

    function updateCursor() {
        canvas.style.cursor = currentTool === 'crop' ? 'crosshair' : 'default';
    }

    // --- BRUSH CONTROLS ---
    brushSizeSlider.addEventListener('input', () => { brushSize = parseInt(brushSizeSlider.value); brushSizeValue.textContent = brushSize + 'px'; });
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
        imgData.onload = () => { ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(imgData, 0, 0); };
        imgData.src = history[index];
    }

    undoBtn.addEventListener('click', () => { if (historyIndex > 0) { historyIndex--; restoreState(historyIndex); } });
    redoBtn.addEventListener('click', () => { if (historyIndex < history.length - 1) { historyIndex++; restoreState(historyIndex); } });

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

    // --- MAIN DRAWING LOGIC ---
    // Helper to get canvas coordinates
    function getCanvasCoordinates(e) {
        const rect = canvas.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    }

    function start(e) {
        const { x, y } = getCanvasCoordinates(e);
        if (currentTool === 'crop') {
            isCropping = true;
            cropStart = { x: x, y: y };
            cropEnd = { x: x, y: y };
        } else {
            isDrawing = true;
            lastX = x;
            lastY = y;
        }
    }

    function stop() {
        if (isDrawing) {
            isDrawing = false;
            saveState();
        }
        if (isCropping) {
            isCropping = false;
            applyCropBtn.style.display = 'block';
        }
    }

    function draw(e) {
        const { x: currentX, y: currentY } = getCanvasCoordinates(e);
        if (isCropping) {
            cropEnd = { x: currentX, y: currentY };
            redrawWithCropOverlay();
        } else if (isDrawing) {
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

    // --- CROP-SPECIFIC FUNCTIONS ---
    function redrawWithCropOverlay() {
        // Restore the last saved state to clear previous overlay
        restoreState(historyIndex);

        if (!cropStart || !cropEnd) return;

        const centerX = (cropStart.x + cropEnd.x) / 2;
        const centerY = (cropStart.y + cropEnd.y) / 2;
        const radiusX = Math.abs((cropEnd.x - cropStart.x) / 2);
        const radiusY = Math.abs((cropEnd.y - cropStart.y) / 2);

        ctx.save();
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.ellipse(centerX, centerY, radiusX, radiusY, 0, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.restore();
    }

    function applyCrop() {
        if (!cropStart || !cropEnd) return;

        const centerX = (cropStart.x + cropEnd.x) / 2;
        const centerY = (cropStart.y + cropEnd.y) / 2;
        const radiusX = Math.abs((cropEnd.x - cropStart.x) / 2);
        const radiusY = Math.abs((cropEnd.y - cropStart.y) / 2);

        // Get the current canvas content
        const currentImage = new Image();
        currentImage.onload = () => {
            // Clear the canvas
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Create a clipping mask
            ctx.save();
            ctx.beginPath();
            ctx.ellipse(centerX, centerY, radiusX, radiusY, 0, 0, 2 * Math.PI);
            ctx.clip();
            
            // Draw the image inside the clip
            ctx.drawImage(currentImage, 0, 0);
            
            // Restore context, removing the clip
            ctx.restore();
            
            // Save the new cropped state
            saveState();
            
            // Reset crop state
            cropStart = null;
            cropEnd = null;
            applyCropBtn.style.display = 'none';
            document.getElementById('brush-tool').click(); // Switch back to brush tool
        };
        currentImage.src = history[historyIndex]; // Use the last saved state
    }

    // --- EVENT LISTENERS ---
    canvas.addEventListener('mousedown', start);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stop);
    canvas.addEventListener('mouseout', stop);

    // --- SAVE/RESTORE LISTENERS (unchanged) ---
    saveImageBtn.addEventListener('click', function() {
        const imageData = canvas.toDataURL();
        const saveUrl = saveImageBtn.dataset.saveUrl;
        const csrfToken = document.getElementById('csrf_token').value;
        fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ image_data: imageData })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) { alert('Error saving image: ' + data.error); }
            else { alert('Image saved successfully!'); window.location.reload(); }
        })
        .catch(error => { console.error('Error:', error); alert('An error occurred while saving the image.'); });
    });

    if (restoreBtn) {
        restoreBtn.addEventListener('click', function() {
            if (confirm('Are you sure you want to delete the edited version and restore the original? This cannot be undone.')) {
                const restoreUrl = restoreBtn.dataset.restoreUrl;
                const csrfToken = document.getElementById('csrf_token').value;
                fetch(restoreUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) { alert('Error: ' + data.error); }
                    else { if (data.redirect_url) { window.location.href = data.redirect_url; } else { window.location.reload(); } }
                })
                .catch(error => { console.error('Error:', error); alert('An unexpected error occurred.'); });
            }
        });
    }

    updateCursor();
});