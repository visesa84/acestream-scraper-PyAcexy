/**
 * PyAcexy integration functionality for Acestream Scraper - Robust Version
 */

async function checkAcexyStatus(showLoadingIndicator = false) {
    const acexyCheckEnabled = localStorage.getItem('enableAcexyCheck') !== 'false';
    const acexyStatusElement = document.getElementById('acexyStatus');
    const acexyStreamsElement = document.getElementById('acexyStreams');

    if (!acexyCheckEnabled) {
        if (acexyStatusElement) {
            acexyStatusElement.className = 'badge bg-secondary';
            acexyStatusElement.textContent = 'Check disabled';
        }
        if (acexyStreamsElement) acexyStreamsElement.classList.add('d-none');
        return;
    }

    try {
        if (showLoadingIndicator) showLoading();
        
        const response = await fetch('/api/config/acexy_status');
        
        // Validar que la respuesta sea exitosa (Status 200)
        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status}`);
        }

        // Leer el JSON (ahora es seguro porque validamos response.ok)
        const data = await response.json();
        
        if (acexyStatusElement) {
            if (data.enabled) {
                if (data.available) {
                    acexyStatusElement.className = 'badge bg-success';
                    acexyStatusElement.textContent = 'Online';
                    if (acexyStreamsElement) {
                        acexyStreamsElement.classList.remove('d-none');
                        const streamCount = acexyStreamsElement.querySelector('.fw-bold');
                        if (streamCount) streamCount.textContent = data.active_streams;
							// --- LISTA DE IDS DEBAJO DEL CONTADOR ---
							let listContainer = document.getElementById('acexyIdsList');
							if (!listContainer) {
								listContainer = document.createElement('div');
								listContainer.id = 'acexyIdsList';
								// mt-1: margen superior | d-block: asegura que baje a la siguiente línea
								// text-muted: color gris | small: letra pequeña
								listContainer.className = 'mt-1 d-block small text-muted font-monospace border-top pt-1';
								listContainer.style.fontSize = '0.7rem';
								acexyStreamsElement.appendChild(listContainer);
							}

							// Rellenamos con los IDs formateados
							if (data.streams_list && data.streams_list.length > 0) {
								listContainer.innerHTML = data.streams_list
									.map(stream => `
										<div class="text-truncate py-1 w-100" 
											 title="Acestream ID: ${stream.id}" 
											 style="cursor: help !important; border-bottom: 1px solid rgba(0,0,0,0.05); display: block;">
											<i class="fas fa-play-circle me-1 text-success" style="font-size: 0.7rem; pointer-events: none;"></i>
											<span class="fw-bold" style="font-size: 0.85rem; pointer-events: none;">
												${stream.nombre}
											</span>
										</div>
									`)
									.join('');
							} else {
								listContainer.innerHTML = '';
							}
                    }
                } else {
					// Limpiar lista si Acexy está offline
                    const listContainer = document.getElementById('acexyIdsList');
                    if (listContainer) listContainer.innerHTML = '';
					
                    acexyStatusElement.innerHTML = '<span class="badge bg-danger">Offline</span>';
                    if (acexyStreamsElement) acexyStreamsElement.classList.add('d-none');
                }
            } else {
				// Limpiar lista si Acexy está Disabled
				const listContainer = document.getElementById('acexyIdsList');
				if (listContainer) listContainer.innerHTML = '';

                acexyStatusElement.innerHTML = '<span class="badge bg-secondary">Disabled</span>';
                if (acexyStreamsElement) acexyStreamsElement.classList.add('d-none');
            }
        }
        
        // Actualizar visibilidad de componentes dependientes de Acexy
        const acexyElements = document.querySelectorAll('.acexy-feature');
        acexyElements.forEach(el => {
            if (data.enabled) el.classList.remove('d-none');
            else el.classList.add('d-none');
        });
        
        return data;

    } catch (error) {
        // Este bloque captura el SyntaxError de JSON y errores 500
        console.error('Error checking Acexy status:', error.message);
        
        if (acexyStatusElement) {
			const listContainer = document.getElementById('acexyIdsList');
			if (listContainer) listContainer.innerHTML = '';

			acexyStatusElement.className = 'badge bg-warning';
            acexyStatusElement.textContent = 'Error';
        }
        if (acexyStreamsElement) {
			const listContainer = document.getElementById('acexyIdsList');
			if (listContainer) listContainer.innerHTML = '';

            acexyStreamsElement.classList.add('d-none');
        }
        return { enabled: true, available: false };
    } finally {
        if (showLoadingIndicator) hideLoading();
    }
}

// Inicialización corregida
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('acexyStatus')) {
        checkAcexyStatus().catch(err => console.error("Acexy Init Error:", err));
    }
});
