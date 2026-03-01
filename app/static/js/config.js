/**
 * Configuration page functionality for Acestream Scraper
 */

// Load and display configuration data
async function loadConfigData() {
    showLoading();
    
    // 1. Estado de Acestream (Independiente)
    try {
        await initializeServiceStatusControls(); 
    } catch (e) {
        console.error('Error en Service Status:', e);
    }

    // 2. Bloque de Estadísticas
    try {
        const stats = await fetchStats();
        if (stats) {
            // Actualizar tabla de información del sistema
            if (document.getElementById('configBaseUrl')) 
                document.getElementById('configBaseUrl').textContent = stats.base_url || 'Not configured';
            if (document.getElementById('configAddPid'))
                document.getElementById('configAddPid').textContent = stats.addpid === true ? 'Yes' : 'No';
            if (document.getElementById('configAceEngineUrl'))
                document.getElementById('configAceEngineUrl').textContent = stats.ace_engine_url || 'Not configured';
            if (document.getElementById('configRescrapeInterval'))
                document.getElementById('configRescrapeInterval').textContent = (stats.rescrape_interval || 'N/A') + ' hours';
            
            // Actualizar texto del intervalo con el estado (Enabled/Disabled)
            if (document.getElementById('configCheckStatusInterval')) {
                const statusSuffix = stats.checkstatus_enabled ? ' (Enabled)' : ' (Disabled)';
                document.getElementById('configCheckStatusInterval').textContent = (stats.checkstatus_interval || 'N/A') + ' hours' + statusSuffix;
            }

            if (document.getElementById('configTotalUrls'))
                document.getElementById('configTotalUrls').textContent = stats.urls?.length || 0;
            if (document.getElementById('configTotalChannels'))
                document.getElementById('configTotalChannels').textContent = stats.total_channels || 0;

            // --- SINCRONIZACIÓN DEL BLOQUE "STREAMS CHECK STATUS" ---
            const checkStatusEnabledCheckbox = document.getElementById('checkStatusEnabledCheckbox');
            const checkStatusIntervalInput = document.getElementById('checkStatusIntervalInput');
            const taskBadge = document.getElementById('checkTaskStatusBadge');

            // Determinar si está habilitado (Soporta booleano puro del backend)
            const isEnabled = stats.checkstatus_enabled === true;

            // Actualizar Badge de Status (Estilo Acexy)
            if (taskBadge) {
                taskBadge.className = isEnabled ? 'badge bg-success' : 'badge bg-secondary';
                taskBadge.textContent = isEnabled ? 'Enabled' : 'Disabled';
            }

            // Actualizar Checkbox e Input de horas
            if (checkStatusEnabledCheckbox) {
                // Solo actualizamos si el usuario no está haciendo click ahora mismo
                if (document.activeElement !== checkStatusEnabledCheckbox) {
                    checkStatusEnabledCheckbox.checked = isEnabled;
                    
                    if (checkStatusIntervalInput) {
                        // Sincronizar el valor de las horas y bloquear/desbloquear
                        checkStatusIntervalInput.value = stats.checkstatus_interval || 24;
                        checkStatusIntervalInput.disabled = !isEnabled;
                    }
                }
            }
            // --- FIN SINCRONIZACIÓN ---

            const addPidCheckbox = document.getElementById('addPidCheckbox');
            if (addPidCheckbox) {
                addPidCheckbox.checked = stats.addpid === true;
            }
            
            updateStats(stats);
        } 
    } catch (error) {
        console.error('Error loading stats (API 500):', error);
        const totalUrlsEl = document.getElementById('configTotalUrls');
        if (totalUrlsEl) totalUrlsEl.textContent = 'Error';
    }

    // 3. Otros componentes independientes
    try {
        await updateWarpUI();
    } catch (e) { 
        console.error('Error en WARP:', e); 
    }

    try {
        await loadUrlsList();
    } catch (e) { 
        console.error('Error en URL List:', e); 
    }
    
    hideLoading();
}

// Initialize service status controls and check status if enabled
function initializeServiceStatusControls() {
    // Setup Acexy status check control
    const enableAcexyCheck = document.getElementById('enableAcexyCheck');
    if (enableAcexyCheck) {
        // Set checkbox state from localStorage
        const acexyCheckEnabled = localStorage.getItem('enableAcexyCheck') !== 'false';
        enableAcexyCheck.checked = acexyCheckEnabled;
        
        // Add event listener to save preference
        enableAcexyCheck.addEventListener('change', function() {
            localStorage.setItem('enableAcexyCheck', this.checked);
            if (this.checked) {
                // If re-enabled, immediately check status
                checkAcexyStatus();
            } else {
                // If disabled, update UI to reflect disabled state
                const acexyStatus = document.getElementById('acexyStatus');
                if (acexyStatus) {
                    acexyStatus.className = 'badge bg-secondary';
                    acexyStatus.textContent = 'Check disabled';
                }
            }
        });
        
        // Check status if enabled
        if (acexyCheckEnabled) {
            checkAcexyStatus();
        } else {
            const acexyStatus = document.getElementById('acexyStatus');
            if (acexyStatus) {
                acexyStatus.className = 'badge bg-secondary';
                acexyStatus.textContent = 'Check disabled';
            }
        }
    }
    
    // Setup Acestream Engine status check control
    const enableAcestreamCheck = document.getElementById('enableAcestreamCheck');
    if (enableAcestreamCheck) {
        // Set checkbox state from localStorage
        const acestreamCheckEnabled = localStorage.getItem('enableAcestreamCheck') !== 'false';
        enableAcestreamCheck.checked = acestreamCheckEnabled;
        
        // Add event listener to save preference
        enableAcestreamCheck.addEventListener('change', function() {
            localStorage.setItem('enableAcestreamCheck', this.checked);
            if (this.checked) {
                // If re-enabled, immediately check status
                updateAcestreamStatus();
            } else {
                // If disabled, update UI to reflect disabled state
                const acestreamStatus = document.getElementById('acestreamStatusConfig');
                if (acestreamStatus) {
                    acestreamStatus.className = 'badge bg-secondary';
                    acestreamStatus.textContent = 'Check disabled';
                }
                // Hide details
                const acestreamDetails = document.getElementById('acestreamDetailsConfig');
                if (acestreamDetails) {
                    acestreamDetails.classList.add('d-none');
                }
            }
        });
        
        // Check status if enabled
        if (acestreamCheckEnabled) {
            updateAcestreamStatus();
        } else {
            const acestreamStatus = document.getElementById('acestreamStatusConfig');
            if (acestreamStatus) {
                acestreamStatus.className = 'badge bg-secondary';
                acestreamStatus.textContent = 'Check disabled';
            }
        }
    }
    
    // Setup Acexy check interval control
    const acexyCheckInterval = document.getElementById('acexyCheckInterval');
    const saveAcexyIntervalBtn = document.getElementById('saveAcexyIntervalBtn');
    
    if (acexyCheckInterval) {
        // Load saved interval from localStorage or use default
        const savedInterval = localStorage.getItem('acexyCheckInterval');
        if (savedInterval) {
            acexyCheckInterval.value = savedInterval;
        }
        
        // Add event listener to save button
        if (saveAcexyIntervalBtn) {
            saveAcexyIntervalBtn.addEventListener('click', function() {
                const interval = parseInt(acexyCheckInterval.value);
                if (isNaN(interval) || interval < 5) {
                    showAlert('warning', 'Check interval must be at least 5 seconds');
                    return;
                }
                
                // Save to localStorage
                localStorage.setItem('acexyCheckInterval', interval);
                
                // Show confirmation
                showAlert('success', 'Acexy check interval updated');
                
                // Update backend configuration
                updateAcexyCheckIntervalSetting(interval);
            });
        }
    }
    
    // Setup Acestream Engine check interval control
    const acestreamCheckInterval = document.getElementById('acestreamCheckInterval');
    const saveAcestreamIntervalBtn = document.getElementById('saveAcestreamIntervalBtn');
    
    if (acestreamCheckInterval) {
        // Load saved interval from localStorage or use default
        const savedInterval = localStorage.getItem('acestreamCheckInterval');
        if (savedInterval) {
            acestreamCheckInterval.value = savedInterval;
        }
        
        // Add event listener to save button
        if (saveAcestreamIntervalBtn) {
            saveAcestreamIntervalBtn.addEventListener('click', function() {
                const interval = parseInt(acestreamCheckInterval.value);
                if (isNaN(interval) || interval < 5) {
                    showAlert('warning', 'Check interval must be at least 5 seconds');
                    return;
                }
                
                // Save to localStorage
                localStorage.setItem('acestreamCheckInterval', interval);
                
                // Show confirmation
                showAlert('success', 'Acestream Engine check interval updated');
                
                // Update backend configuration
                updateAcestreamCheckIntervalSetting(interval);
            });
        }
    }
}

// Update Acestream Engine status
async function updateAcestreamStatus() {
    // 1. Verificar si los checks están habilitados en localStorage
    const acestreamCheckEnabled = localStorage.getItem('enableAcestreamCheck') !== 'false';
    const acestreamStatusElement = document.getElementById('acestreamStatusConfig');
    const configAcestreamStatus = document.getElementById('configAcestreamEngineStatus');
    const acestreamDetailsElement = document.getElementById('acestreamDetailsConfig');

    if (!acestreamCheckEnabled) {
        if (acestreamStatusElement) {
            acestreamStatusElement.className = 'badge bg-secondary';
            acestreamStatusElement.textContent = 'Check disabled';
        }
        if (configAcestreamStatus) configAcestreamStatus.textContent = 'Check disabled';
        if (acestreamDetailsElement) acestreamDetailsElement.classList.add('d-none');
        return;
    }

    try {
        const response = await fetch('/api/config/acestream_status');
        if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
        const data = await response.json();
        
        // --- LOGICA DEL BADGE (A la izquierda en el dashboard/config) ---
        if (acestreamStatusElement) {
            if (data.available) {
                acestreamStatusElement.className = 'badge bg-success';
                acestreamStatusElement.textContent = data.is_internal ? 'Online' : 'External Online';
            } else {
                acestreamStatusElement.className = 'badge bg-danger';
                acestreamStatusElement.textContent = data.is_internal === false ? 'External Offline' : 'Offline';
            }
        }

        // --- LOGICA DE LA TABLA (El <td> que no se te llenaba) ---
        if (configAcestreamStatus) {
            if (data.available) {
                configAcestreamStatus.textContent = data.is_internal ? 
                    'Enabled and Online' : 'External Engine Online';
            } else if (data.is_internal === false && data.engine_url) {
                configAcestreamStatus.textContent = 'External Engine Offline';
            } else if (data.enabled) {
                configAcestreamStatus.textContent = 'Enabled but Offline';
            } else {
                configAcestreamStatus.textContent = 'Disabled';
            }
        }

        // --- LOGICA DE DETALLES (Versión, Plataforma, etc.) ---
        if (acestreamDetailsElement) {
            if (data.available || (data.is_internal === false && data.engine_url)) {
                acestreamDetailsElement.classList.remove('d-none');
                
                const version = document.getElementById('acestreamVersionConfig');
                const platform = document.getElementById('acestreamPlatformConfig');
                const network = document.getElementById('acestreamNetworkConfig');
                const engineUrl = document.getElementById('acestreamUrlConfig');

                if (version) version.textContent = data.version || 'Unknown';
                if (platform) platform.textContent = data.platform || 'Unknown';
                if (network) network.textContent = data.connected ? 'Connected' : 'Disconnected';
                
                if (engineUrl) {
                    if (data.is_internal) {
                        engineUrl.parentElement.classList.add('d-none');
                    } else {
                        engineUrl.parentElement.classList.remove('d-none');
                        engineUrl.textContent = data.engine_url || 'Unknown';
                    }
                }
            } else {
                acestreamDetailsElement.classList.add('d-none');
            }
        }

    } catch (error) {
        console.error('Error checking Acestream Engine status:', error);
        if (acestreamStatusElement) {
            acestreamStatusElement.className = 'badge bg-warning';
            acestreamStatusElement.textContent = 'Error';
        }
        if (configAcestreamStatus) configAcestreamStatus.textContent = 'Connection Error';
    }
}

// Check Acestream Engine status with optional loading indicator
async function checkAcestreamStatus(showLoadingIndicator = false) {
    try {
        if (showLoadingIndicator) showLoading();
        await updateAcestreamStatus();
    } finally {
        if (showLoadingIndicator) hideLoading();
    }
}

// Load URLs list for management
async function loadUrlsList() {
    // 1. Obtener el elemento y validar su existencia antes de cualquier otra cosa
    const urlsManagementList = document.getElementById('urlsManagementList');
    
    // Si no estamos en la página que tiene este elemento, salimos silenciosamente
    if (!urlsManagementList) {
        return;
    }

    try {
        // 2. Obtener los datos de la API
        const stats = await fetchStats();
        
        // 3. Validar si existen URLs en la respuesta
        if (stats && stats.urls && stats.urls.length > 0) {
            urlsManagementList.innerHTML = stats.urls.map(url => `
                <div class="list-group-item">
                    <div class="row align-items-center">
                        <div class="col-md-7">
                            <div>
                                <strong>${url.url}</strong>
                                <span class="badge bg-info ms-2">${url.url_type}</span>
                            </div>
                            <div class="small text-muted">
                                <span>ID: ${url.id}</span>
                                <span class="ms-2">Status: <span class="status-${(url.status || 'unknown').toLowerCase()}">${url.status}</span></span>
                                <span class="ms-2">Channels: ${url.channel_count}</span>
                                ${url.last_processed ? `<span class="ms-2">Last scraped: ${formatLocalDate(url.last_processed)}</span>` : ''}
                            </div>
                        </div>
                        <div class="col-md-5 text-end">
                            <button class="btn btn-sm ${url.enabled ? 'btn-warning' : 'btn-success'}" 
                                    onclick="toggleUrl('${url.id}', ${!url.enabled})">
                                ${url.enabled ? 'Disable' : 'Enable'}
                            </button>
                            <button class="btn btn-sm btn-info" 
                                    onclick="refreshUrl('${url.id}')">
                                Refresh
                            </button>
                            <button class="btn btn-sm btn-danger" 
                                    onclick="deleteUrl('${url.id}')">
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        } else {
            // Este bloque ahora es seguro porque urlsManagementList ya fue validado arriba
            urlsManagementList.innerHTML = '<div class="list-group-item text-center text-muted">No URLs found</div>';
        }
    } catch (error) {
        console.error('Error loading URLs list:', error);
        // Opcional: mostrar el error en la interfaz de forma segura
        if (urlsManagementList) {
            urlsManagementList.innerHTML = '<div class="list-group-item text-center text-danger">Error loading URLs</div>';
        }
    }
}

// Refresh a single URL
async function refreshUrl(url) {
    try {
        showLoading();
        const response = await fetch(`/api/urls/${encodeURIComponent(url)}/refresh`, {
            method: 'POST'
        });
        
        await handleApiResponse(response, 'URL refresh started');
    } catch (error) {
        console.error('Error refreshing URL:', error);
        alert('Network error while refreshing URL');
    } finally {
        hideLoading();
    }
}

// Migrate configuration from file to database
async function migrateConfigToDatabase() {
    if (!confirm('This will migrate settings from config.json to the database. Continue?')) {
        return;
    }
    
    try {
        showLoading();
        const response = await fetch('/api/config/migrate_config', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok && data.status === 'success') {
            showAlert('success', data.message);
            await loadConfigData();
        } else {
            showAlert('error', data.message || 'Failed to migrate configuration');
        }
    } catch (error) {
        console.error('Error migrating config:', error);
        showAlert('error', 'Network error while migrating configuration');
    } finally {
        hideLoading();
    }
}

// Setup event listeners for the configuration page
function setupConfigEvents() {
    // Base URL form
    const baseUrlForm = document.getElementById('baseUrlForm');
    if (baseUrlForm) {
        baseUrlForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const baseUrlInput = document.getElementById('baseUrlInput');
            const baseUrl = baseUrlInput.value;
            const addpid = document.getElementById('addPidCheckbox').checked;

            try {
                showLoading();
                
                // Update base URL
                const responseBaseUrl = await fetch('/api/config/base_url', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ base_url: baseUrl })
                });

                // Update addpid setting
                const responseAddPid = await fetch('/api/config/addpid', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ addpid: addpid })
                });

                if (await handleApiResponse(responseBaseUrl, 'Base URL updated successfully') && 
                    await handleApiResponse(responseAddPid, 'PID parameter setting updated successfully')) {
                    baseUrlInput.value = '';
                    await loadConfigData();
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Network error while updating base URL configuration');
            } finally {
                hideLoading();
            }
        });
    }

    // Save addpid when checkbox is changed (separately)
    const addPidCheckbox = document.getElementById('addPidCheckbox');
    if (addPidCheckbox) {
        addPidCheckbox.addEventListener('change', async () => {
            try {
                showLoading();
                const response = await fetch('/api/config/addpid', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ addpid: addPidCheckbox.checked })
                });

                await handleApiResponse(response, 'PID parameter setting updated successfully');
                await loadConfigData();
            } catch (error) {
                console.error('Error:', error);
                alert('Network error while updating PID parameter setting');
            } finally {
                hideLoading();
            }
        });
    }

    // Ace Engine form
    const aceEngineForm = document.getElementById('aceEngineForm');
    if (aceEngineForm) {
        aceEngineForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const aceEngineInput = document.getElementById('aceEngineInput');
            const aceEngineUrl = aceEngineInput.value;

            try {
                showLoading();
                const response = await fetch('/api/config/ace_engine_url', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ ace_engine_url: aceEngineUrl })
                });

                if (await handleApiResponse(response, 'Ace Engine URL updated successfully')) {
                    aceEngineInput.value = '';
                    await loadConfigData();
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Network error while updating Ace Engine URL');
            } finally {
                hideLoading();
            }
        });
    }

    // Rescrape interval form
    const rescrapeIntervalForm = document.getElementById('rescrapeIntervalForm');
    if (rescrapeIntervalForm) {
        rescrapeIntervalForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const hoursInput = document.getElementById('rescrapeIntervalInput');
            const hours = parseInt(hoursInput.value, 10);

            if (isNaN(hours) || hours < 1) {
                alert('Please enter a valid number of hours (minimum 1)');
                return;
            }

            try {
                showLoading();
                const response = await fetch('/api/config/rescrape_interval', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ hours: hours })
                });

                if (await handleApiResponse(response, 'Rescrape interval updated successfully')) {
                    hoursInput.value = '';
                    await loadConfigData();
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Network error while updating rescrape interval');
            } finally {
                hideLoading();
            }
        });
    }
	
	// Check Status interval form
    const CheckStatusIntervalForm = document.getElementById('checkStatusIntervalForm');
	if (CheckStatusIntervalForm) {
		CheckStatusIntervalForm.addEventListener('submit', async (e) => {
			e.preventDefault();
			
			const hoursInput = document.getElementById('checkStatusIntervalInput');
			const enabledCheckbox = document.getElementById('checkStatusEnabledCheckbox');
			
			// Validamos que el input tenga un número
			const hours = parseInt(hoursInput.value, 10);
			if (isNaN(hours) || hours < 1) {
				showAlert('warning', 'Please enter a valid number of hours');
				return;
			}

			const payload = {
				hours: hours,
				enabled: enabledCheckbox ? enabledCheckbox.checked : true
			};

			try {
				showLoading();
				const response = await fetch('/api/config/checkstatus_interval', {
					method: 'PUT',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(payload)
				});

				if (await handleApiResponse(response, 'Check status interval updated')) {
					// Forzamos la actualización de la tabla de arriba
					await loadConfigData();
				}
			} catch (error) {
				console.error('Error:', error);
				alert('Network error while updating configuration');
			} finally {
				hideLoading();
			}
		});
	}

    // Add URL form
    const addUrlForm = document.getElementById('addUrlForm');
    if (addUrlForm) {
        addUrlForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const urlInput = document.getElementById('urlInput');
            const urlTypeSelect = document.getElementById('urlTypeSelect');
            const url = urlInput.value.trim();
            const urlType = urlTypeSelect.value;

            if (!url) {
                showAlert('warning', 'Please enter a URL');
                return;
            }

            try {
                showLoading();
                const success = await addUrl(url, urlType);
                if (success) {
                    urlInput.value = '';
                    await loadUrlsList();
                }
            } finally {
                hideLoading();
            }
        });
    }

	// --- Streams Check Status Configuration ---
    const checkStatusIntervalForm = document.getElementById('CheckStatusIntervalForm');
    const checkStatusEnabledCheckbox = document.getElementById('checkStatusEnabledCheckbox');
    const checkStatusIntervalInput = document.getElementById('CheckStatusIntervalInput');

    if (CheckStatusIntervalForm) {
        CheckStatusIntervalForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const hours = parseInt(checkStatusIntervalInput.value, 10);
            const isEnabled = checkStatusEnabledCheckbox ? checkStatusEnabledCheckbox.checked : true;

            if (isNaN(hours) || hours < 1) {
                alert('Please enter a valid number of hours (minimum 1)');
                return;
            }

            try {
                showLoading();
                const response = await fetch('/api/config/checkstatus_interval', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        hours: hours,
                        enabled: isEnabled 
                    })
                });

                if (await handleApiResponse(response, 'Check status configuration updated successfully')) {
                    await loadConfigData();
                }
            } catch (error) {
                console.error('Error updating check status config:', error);
                alert('Network error while updating check status configuration');
            } finally {
                hideLoading();
            }
        });
    }

    // --- Control Automático del Checkbox de Check Status ---
	if (checkStatusEnabledCheckbox) {
		checkStatusEnabledCheckbox.addEventListener('change', async function() {
			const input = document.getElementById('checkStatusIntervalInput');
			const isEnabled = this.checked;
			
			// --- FIX AQUÍ: Asegurar que 'hours' tenga un valor numérico ---
			let hoursValue = input ? parseInt(input.value, 10) : 24;
			
			// Si el input existe pero está vacío (NaN), intentamos recuperar el valor previo o ponemos 24
			if (isNaN(hoursValue)) {
				hoursValue = 24; 
			}

			const payload = {
				enabled: Boolean(isEnabled),
				hours: hoursValue // Ahora siempre será un número (ej: 24)
			};

			try {
				showLoading();
				const response = await fetch('/api/config/checkstatus_interval', {
					method: 'PUT',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(payload)
				});

				if (await handleApiResponse(response, 'Status updated')) {
					// Actualizar UI localmente sin recargar inmediatamente para evitar el rebote
					if (input) input.disabled = !isEnabled;
					const taskBadge = document.getElementById('checkTaskStatusBadge');
					if (taskBadge) {
						taskBadge.className = isEnabled ? 'badge bg-success' : 'badge bg-secondary';
						taskBadge.textContent = isEnabled ? 'Enabled' : 'Disabled';
					}
				}
			} catch (error) {
				this.checked = !isEnabled;
				alert('Error updating status');
			} finally {
				hideLoading();
			}
		});
	}

    // Migration button
    const migrateConfigBtn = document.getElementById('migrateConfigBtn');
    if (migrateConfigBtn) {
        migrateConfigBtn.addEventListener('click', migrateConfigToDatabase);
    }
}

// Update Acexy check interval setting on server
async function updateAcexyCheckIntervalSetting(interval) {
    try {
        const response = await fetch('/api/config/acexy_check_interval', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ interval: interval })
        });
        
        await handleApiResponse(response, 'Acexy check interval saved');
    } catch (error) {
        console.error('Error updating Acexy check interval:', error);
        showAlert('error', 'Error saving Acexy check interval');
    }
}

// Update Acestream Engine check interval setting on server
async function updateAcestreamCheckIntervalSetting(interval) {
    try {
        const response = await fetch('/api/config/acestream_check_interval', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ interval: interval })
        });
        
        await handleApiResponse(response, 'Acestream Engine check interval saved');
    } catch (error) {
        console.error('Error updating Acestream Engine check interval:', error);
        showAlert('error', 'Error saving Acestream Engine check interval');
    }
}

// Initialize configuration page
document.addEventListener('DOMContentLoaded', function() {
    // Load configuration data
    loadConfigData();
    
    // Set up event handlers
    setupConfigEvents();
    
    // Refresh periodically
    setInterval(loadConfigData, 60000); // Every minute
});