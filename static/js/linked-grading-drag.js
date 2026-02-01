document.addEventListener('DOMContentLoaded', function() {
    loadHierarchy();
    
    document.getElementById('save-hierarchy-btn').addEventListener('click', saveHierarchy);
});

let hierarchyData = { diseases: [], links: [] };
let draggedItem = null;

function loadHierarchy() {
    fetch('/admin/api/linked-disease-gradings/hierarchy')
        .then(response => response.json())
        .then(data => {
            hierarchyData = data;
            renderUI();
        })
        .catch(err => {
            console.error('Failed to load hierarchy', err);
            alert('Failed to load hierarchy data.');
        });
}

function renderUI() {
    const poolList = document.getElementById('pool-list');
    const hierarchyRoot = document.getElementById('hierarchy-root');
    poolList.innerHTML = '';
    hierarchyRoot.innerHTML = '';
    
    // 1. Build Adjacency Map: Parent -> [Children]
    // Note: The API returns links sorted by display_order, so array order is correct.
    const childrenMap = {};
    const parentSet = new Set(); // Set of IDs that ARE children (have parents)
    
    hierarchyData.links.forEach(link => {
        if (!childrenMap[link.parent_id]) childrenMap[link.parent_id] = [];
        childrenMap[link.parent_id].push(link.child_id);
        parentSet.add(link.child_id);
    });
    
    // 2. Identify Roots and Pool Items
    const linkedIDs = new Set();
    hierarchyData.links.forEach(l => {
        linkedIDs.add(l.parent_id);
        linkedIDs.add(l.child_id);
    });
    
    const roots = []; // Items that are part of hierarchy but have no parent
    const pool = [];  // Items completely unlinked
    
    hierarchyData.diseases.forEach(d => {
        if (!linkedIDs.has(d.id)) {
            pool.push(d);
        } else if (!parentSet.has(d.id)) {
            roots.push(d);
        }
    });
    
    // 3. Helper to create DOM elements recursively
    function createItem(diseaseId) {
        const disease = hierarchyData.diseases.find(d => d.id === diseaseId);
        if (!disease) return null;
        
        const template = document.getElementById('disease-item-template');
        const clone = template.content.cloneNode(true);
        const el = clone.querySelector('.disease-item');
        
        el.dataset.id = diseaseId;
        el.querySelector('.disease-name').textContent = disease.name;
        el.querySelector('.disease-id').textContent = diseaseId;
        
        const container = el.querySelector('.nested-container');
        
        // Find children
        const childrenIds = childrenMap[diseaseId] || [];
        childrenIds.forEach(childId => {
            const childEl = createItem(childId);
            if (childEl) container.appendChild(childEl);
        });
        
        return el;
    }
    
    // 4. Render lists
    pool.forEach(d => {
        const item = createItem(d.id);
        if (item) poolList.appendChild(item);
    });
    
    roots.forEach(d => {
        const item = createItem(d.id);
        if (item) hierarchyRoot.appendChild(item);
    });
    
    setupDragAndDrop();
}

function setupDragAndDrop() {
    const items = document.querySelectorAll('.disease-item');
    const containers = document.querySelectorAll('.drop-zone, .nested-container');
    
    items.forEach(item => {
        item.addEventListener('dragstart', handleDragStart);
        item.addEventListener('dragend', handleDragEnd);
        // Prevent drag events from bubbling up to parent items
        item.addEventListener('dragover', (e) => e.stopPropagation());
    });
    
    containers.forEach(container => {
        container.addEventListener('dragover', handleDragOver);
        container.addEventListener('dragenter', handleDragEnter);
        container.addEventListener('dragleave', handleDragLeave);
        container.addEventListener('drop', handleDrop);
    });
}

function handleDragStart(e) {
    draggedItem = this;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', this.dataset.id);
    this.classList.add('opacity-50');
    
    // We need to re-query containers because dynamic DOM changes might affect listeners?
    // No, listeners are attached to elements. But if we created new elements, we'd need to attach.
    // Here we assume static set after render.
}

function handleDragEnd(e) {
    this.classList.remove('opacity-50');
    draggedItem = null;
    document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
}

function handleDragOver(e) {
    e.preventDefault(); // Necessary to allow dropping
    e.dataTransfer.dropEffect = 'move';
    return false;
}

function handleDragEnter(e) {
    e.preventDefault();
    this.classList.add('drag-over');
}

function handleDragLeave(e) {
    this.classList.remove('drag-over');
}

function handleDrop(e) {
    e.stopPropagation(); // Stop bubbling
    e.preventDefault();
    this.classList.remove('drag-over');
    
    if (draggedItem === this) return; // Dropped on self (shouldn't happen due to hierarchy but safety)
    
    // Cycle Check: Cannot drop a parent into its own child
    if (this.closest(`.disease-item[data-id="${draggedItem.dataset.id}"]`)) {
        alert("Cannot move an item into its own descendant!");
        return;
    }
    
    // Move DOM element
    this.appendChild(draggedItem);
    
    // Clean up empty containers or styles if needed
}

function saveHierarchy() {
    const links = [];
    
    // Traverse the hierarchy-root to build links
    const rootContainer = document.getElementById('hierarchy-root');
    
    function traverse(container) {
        // Direct children of this container are .disease-item elements
        // Use :scope > .disease-item to get direct children
        const items = Array.from(container.children).filter(el => el.classList.contains('disease-item'));
        
        items.forEach(item => {
            const parentId = item.parentElement.closest('.disease-item')?.dataset.id;
            const childId = item.dataset.id;
            
            if (parentId) {
                links.push({
                    parent_id: parseInt(parentId),
                    child_id: parseInt(childId)
                });
            }
            
            // Recurse into this item's nested container
            const nested = item.querySelector('.nested-container');
            if (nested) traverse(nested);
        });
    }
    
    traverse(rootContainer);
    
    // Send to API
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    
    fetch('/admin/api/linked-disease-gradings/hierarchy', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ links: links })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Use global toast/flash utility if available, or reload
            // Reloading is safest to sync state
            window.location.reload(); 
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Save failed', err);
        alert('Save failed: ' + err);
    });
}
