document.addEventListener('DOMContentLoaded', function() {
    // Canvas and context
    const canvas = document.getElementById('imageCanvas');
    const ctx = canvas.getContext('2d');
    
    // Image and editing state
    let img = new Image();
    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;
    let currentTool = 'brush';
    let brushSize = 10;
    let brushColor = '#000000';
    let history = [];
    let historyIndex = -1;
    
    // DOM elements
    const brushSizeSlider = document.getElementById('brush-size');
    const brushSizeValue = document.getElementById('brush-size-value');
    const brushColorPicker = document.getElementById('brush-color');
    const clearCanvasBtn = document.getElementById('clear-canvas');
    const undoBtn = document.getElementById('undo');
    const redoBtn = document.getElementById('redo');
    const saveImageBtn = document.getElementById('save-image');
    
    // Load the image
    img.onload = function() {
        // Set canvas dimensions to match image
        canvas.width = img.width;
        canvas.height = img.height;
        // Draw the image on canvas
        ctx.drawImage(img, 0, 0);
        // Save initial state
        saveState();
    };
    
    // Use the validated image URL passed from the route
    img.src = "{{ image_url }}";
    
    // Tool selection
    document.querySelectorAll('input[name="tool"]').forEach(radio => {
        radio.addEventListener('change', function() {
            currentTool = this.value;
            updateCursor();
        });
    });
    
    // Brush size
    brushSizeSlider.addEventListener('input', function() {
        brushSize = parseInt(this.value);
        brushSizeValue.textContent = brushSize + 'px';
        updateCursor();
    });
    
    // Brush color (default to black)
    brushColorPicker.addEventListener('input', function() {
        brushColor = this.value;
    });
    
    // Update cursor based on tool and brush size
    function updateCursor() {
        if (currentTool === 'brush' || currentTool === 'eraser') {
            // Create a cursor based on brush size
            const cursorSize = Math.max(brushSize, 10);
            canvas.style.cursor = `url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='${cursorSize}' height='${cursorSize}' viewBox='0 0 ${cursorSize} ${cursorSize}'><circle cx='${cursorSize/2}' cy='${cursorSize/2}' r='${cursorSize/2}' fill='rgba(0,0,0,0.5)' stroke='black' stroke-width='1'/></svg>") ${cursorSize/2} ${cursorSize/2}, auto`;
        } else {
            canvas.style.cursor = 'move';
        }
    }
    
    // Save canvas state for undo/redo
    function saveState() {
        historyIndex++;
        history.splice(historyIndex);
        history.push(canvas.toDataURL());
        updateUndoRedoButtons();
    }
    
    // Update undo/redo button states
    function updateUndoRedoButtons() {
        undoBtn.disabled = historyIndex <= 0;
        redoBtn.disabled = historyIndex >= history.length - 1;
    }
    
    // Undo
    undoBtn.addEventListener('click', function() {
        if (historyIndex > 0) {
            historyIndex--;
            const imgData = new Image();
            imgData.onload = function() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(imgData, 0, 0);
                updateUndoRedoButtons();
            };
            imgData.src = history[historyIndex];
        }
    });
    
    // Redo
    redoBtn.addEventListener('click', function() {
        if (historyIndex < history.length - 1) {
            historyIndex++;
            const imgData = new Image();
            imgData.onload = function() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(imgData, 0, 0);
                updateUndoRedoButtons();
            };
            imgData.src = history[historyIndex];
        }
    });
    
    // Clear canvas
    clearCanvasBtn.addEventListener('click', function() {
        if (confirm('Are you sure you want to clear all edits?')) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0);
            saveState();
        }
    });
    
    // Save image
    saveImageBtn.addEventListener('click', function() {
        // Get the edited image data
        const imageData = canvas.toDataURL();
        
        // Log the data for debugging
        console.log('Image data length:', imageData.length);
        console.log('Image data preview:', imageData.substring(0, 100));
        
        // Send the image data to the server
        fetch('{{ url_for("direct_uploads.save_edited_image", upload_id=upload.id) }}', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': '{{ csrf_token() }}'
            },
            body: JSON.stringify({
                image_data: imageData
            })
        })
        .then(response => {
            console.log('Response status:', response.status);
            return response.json();
        })
        .then(data => {
            if (data.error) {
                alert('Error saving image: ' + data.error);
            } else {
                alert('Image saved successfully!');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while saving the image.');
        });
    });
    
    // Drawing functions
    function startDrawing(e) {
        isDrawing = true;
        [lastX, lastY] = [e.offsetX, e.offsetY];
    }
    
    function draw(e) {
        if (!isDrawing) return;
        
        ctx.beginPath();
        ctx.moveTo(lastX, lastY);
        ctx.lineTo(e.offsetX, e.offsetY);
        
        if (currentTool === 'brush') {
            ctx.strokeStyle = brushColor;
            ctx.lineWidth = brushSize;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.stroke();
        } else if (currentTool === 'eraser') {
            ctx.strokeStyle = 'rgba(0,0,0,0)';
            ctx.lineWidth = brushSize;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.globalCompositeOperation = 'destination-out';
            ctx.stroke();
            ctx.globalCompositeOperation = 'source-over';
        }
        
        [lastX, lastY] = [e.offsetX, e.offsetY];
    }
    
    function stopDrawing() {
        if (isDrawing) {
            isDrawing = false;
            saveState();
        }
    }
    
    // Event listeners for drawing
    canvas.addEventListener('mousedown', startDrawing);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stopDrawing);
    canvas.addEventListener('mouseout', stopDrawing);
    
    // Update cursor initially
    updateCursor();
});