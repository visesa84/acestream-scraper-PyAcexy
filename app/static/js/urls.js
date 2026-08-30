/**
 * URL management functionality for Acestream Scraper
 */

// Toggle URL enabled/disabled status
async function toggleUrl(id, enable) {
    return await makeApiRequest(
        `/api/urls/${id}`,
        {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enable })
        },
        enable ? 'URL enabled successfully' : 'URL disabled successfully'
    );
}

// Delete URL
async function deleteUrl(id) {
    if (!confirm('Are you sure you want to delete this URL? This will also remove all associated channels.')) {
        return;
    }
    
    try {
        showLoading();
        
        const response = await fetch(`/api/urls/${id}`, {
            method: 'DELETE'
        });
        
        if (response.status === 204) {
            showAlert('success', 'URL deleted successfully');
            // Refresh the data if needed
            if (typeof refreshData === 'function') {
                await refreshData();
            }
            return true;
        }
        
        const data = await response.text();
        throw new Error(data || 'Failed to delete URL');
        
    } catch (error) {
        console.error('Error deleting URL:', error);
        showAlert('error', 'Failed to delete URL: ' + error.message);
        return false;
    } finally {
        hideLoading();
    }
}

// Refresh a single URL
async function refreshUrl(id) {
    try {
        showLoading();
        const response = await fetch(`/api/urls/${id}/refresh`, {
            method: 'POST'
        });
        
        await handleApiResponse(response, 'URL refreshed successfully');
        
        // Refresh dashboard data
        await refreshData();
    } catch (error) {
        console.error('Error refreshing URL:', error);
        showAlert('danger', 'Failed to refresh URL: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Add new URL or Channel Search
async function addUrl(url, urlType = 'regular') {
    try {
        showLoading();
        
        const cleanInput = url.trim();
        const isWebUrl = cleanInput.startsWith('http://') || 
                         cleanInput.startsWith('https://') || 
                         cleanInput.startsWith('ipfs://') || 
                         cleanInput.startsWith('zeronet://');

        // Si no es un enlace web, asignamos automáticamente el tipo 'search'
        const finalUrlType = isWebUrl ? urlType : 'search';

        const response = await fetch('/api/urls/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                url: cleanInput,
                url_type: finalUrlType
            })
        });
        
        await handleApiResponse(response, isWebUrl ? 'URL added successfully' : 'Channel search completed');
        
        // Refresh dashboard data
        await refreshData();
        return true;
    } catch (error) {
        console.error('Error adding URL or Search:', error);
        showAlert('danger', 'Failed to add URL/Search: ' + error.message);
        return false;
    } finally {
        hideLoading();
    }
}

// Refresh all URLs
async function refreshAllUrls() {
    if (!confirm('Are you sure you want to refresh all URLs? This might take a while.')) {
        return { success: false };
    }

    const { success, data } = await makeApiRequest(
        '/api/urls/refresh',
        { method: 'POST' },
        `URLs refresh started`
    );
    
    if (success) {
        alert(`${data.message}\nURLs being processed: ${data.urls.length}`);
        
        // Start polling for updates more frequently during refresh
        const pollInterval = setInterval(async () => {
            if (typeof loadConfigData === 'function') {
                await loadConfigData();
            } else if (typeof refreshData === 'function') {
                await refreshData();
            }
            
            // Check if all URLs are done processing
            const statsResponse = await fetch('/api/stats/');
            const stats = await statsResponse.json();
            const processingUrls = stats.urls.filter(u => u.status === 'processing');
            
            if (processingUrls.length === 0) {
                clearInterval(pollInterval);
                showAlert('success', 'All URLs have been processed');
            }
        }, 5000); // Poll every 5 seconds
        
        // Stop polling after 5 minutes max
        setTimeout(() => clearInterval(pollInterval), 300000);
    }
    
    return { success, data };
}
// --- LÓGICA DE LA BLACKLIST GLOBAL ---

// Abre el modal y carga la lista actualizada desde la API
async function openGlobalBlacklistModal() {
    // Inicializa y muestra el modal de Bootstrap
    const modalElement = document.getElementById('globalBlacklistModal');
    const modal = new bootstrap.Modal(modalElement);
    modal.show();
    
    // Carga los elementos
    await loadGlobalBlacklist();
}

// Carga los datos de la lista negra de la API y los renderiza
async function loadGlobalBlacklist() {
    const container = document.getElementById('blacklistContainer');
    if (!container) return;
    
    try {
        const response = await fetch('/api/blacklist/');
        if (!response.ok) throw new Error('Failed to fetch blacklist');
        const data = await response.json();
        
        if (data.length === 0) {
            container.innerHTML = `<li class="list-group-item text-muted text-center py-3">No blocked terms yet.</li>`;
            return;
        }
        
        container.innerHTML = data.map(item => `
            <li class="list-group-item d-flex justify-content-between align-items-center py-2">
                <span class="font-monospace fw-bold text-danger">🚫 ${escapeHtml(item.pattern)}</span>
                <button class="btn btn-sm btn-outline-danger py-0 px-2" onclick="deleteBlacklistPattern(${item.id})">
                    &times; Remove
                </button>
            </li>
        `).join('');
        
    } catch (error) {
        console.error('Error loading blacklist:', error);
        container.innerHTML = `<li class="list-group-item text-danger text-center">Error loading blacklist</li>`;
    }
}

// Envía un nuevo término a la base de datos
async function addBlacklistPattern() {
    const input = document.getElementById('newBlacklistPattern');
    const pattern = input.value.trim();
    
    if (!pattern) {
        showAlert('warning', 'Please enter a keyword or pattern');
        return;
    }
    
    try {
        showLoading();
        const response = await fetch('/api/blacklist/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pattern: pattern })
        });
        
        if (!response.ok) throw new Error('Error saving term');
        
        input.value = ''; // Limpiamos el input
        await loadGlobalBlacklist(); // Refrescamos la lista dentro del modal
    } catch (error) {
        console.error('Error adding term:', error);
        showAlert('danger', 'Failed to add term to blacklist');
    } finally {
        hideLoading();
    }
}

// Elimina un término de la base de datos
async function deleteBlacklistPattern(id) {
    try {
        showLoading();
        const response = await fetch(`/api/blacklist/${id}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Error deleting term');
        
        await loadGlobalBlacklist(); // Refrescamos la lista dentro del modal
    } catch (error) {
        console.error('Error deleting term:', error);
        showAlert('danger', 'Failed to delete term');
    } finally {
        hideLoading();
    }
}

// Función auxiliar para escapar texto y evitar problemas de XSS en la interfaz
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}