/**
 * Stream Player Options Modal Implementation
 */
// Carga dinámica de mpegts.js
if (typeof mpegts === 'undefined') {
    const script = document.createElement('script');
    script.src = "https://cdn.jsdelivr.net/npm/mpegts.js@1.8.0/dist/mpegts.min.js";
    script.onload = () => console.log("mpegts.js loaded successfully");
    document.head.appendChild(script);
}

// Hacer el videoPlayer mas grande
const style = document.createElement('style');
style.innerHTML = `
    .player-options-modal .modal-content {
        max-width: 1000px !important; /* Permitir que sea casi tan ancho como la pantalla */
        width: 90% !important;
        padding: 20px;
        border-radius: 8px;
    }
    #videoPlayer {
        outline: none;
    }
`;
document.head.appendChild(style);

// Function to get the base URL from config
async function getAceEngineUrl() {
    try {
        const response = await fetch('/api/config/ace_engine_url');
        const data = await response.json();
        return data.ace_engine_url || 'http://127.0.0.1:6878'; // Default to localhost if not set
    } catch (error) {
        console.error('Error fetching Ace Engine URL:', error);
        return 'http://127.0.0.1:6878'; // Default to localhost on error
    }
}

async function getBaseUrl() {
    try {
        const response = await fetch('/api/config/base_url');
        const data = await response.json();
        
        const currentHost = window.location.hostname;
        const isIp = (h) => {
            const parts = h.split(".");
            return parts.length === 4 && parts.every(p => !isNaN(p));
        };

        // Si entramos por DOMINIO
        if (!isIp(currentHost) && currentHost !== 'localhost') {
            // IMPORTANTE: No ponemos :8080
            return `${window.location.protocol}//${currentHost}/ace/getstream?id=`;
        } 
        
        // Si entramos por IP LOCAL
        else {
            // Aquí sí necesitamos el puerto 8080
            return `http://${currentHost}:8080/ace/getstream?id=`;
        }
    } catch (error) {
        console.error('Error fetching base URL:', error);
        return `${window.location.protocol}//${window.location.hostname}/ace/getstream?id=`;
    }
}

// Open the player options modal for a stream
async function showPlayerOptions(streamId) {
    if (!streamId) {
        console.error('No stream ID provided to showPlayerOptions');
        return;
    }
    
    // 1. Obtener la URL del motor
    const aceEngineUrl = await getAceEngineUrl();
    const baseUrl = await getBaseUrl();
    const fullStreamUrl = `${baseUrl}${streamId}`;
    
    // Create the modal HTML
    const modalHTML = `
    <div class="player-options-modal" id="playerOptionsModal">
        <div class="modal-content" style="max-width: 900px; width: 95%;">
            <h3 style="margin-top: 0; text-align: center;">Stream Options</h3>
            <div id="acePlayerWeb" style="display:none; width:100%; min-height:300px; background:#000; margin-bottom:15px; position:relative;"></div>
            <div style="margin-bottom: 20px;">
                <div class="input-group mb-2">
                    <input type="text" class="form-control" id="streamUrlInput" value="${fullStreamUrl}" readonly>
                    <button class="button modal-button" onclick="copyStreamUrl()" style="border-radius: 0 4px 4px 0;">
                        Copy URL
                    </button>
                </div>
            </div>
            <div style="display: flex; flex-direction: column; gap: 10px;">
                <div id="modalButtons" style="display: flex; flex-direction: column; gap: 10px;">
                    <button class="button modal-button" onclick="window.open('acestream://${streamId}', '_blank')">
                        Open in Acestream (PC/Android)
                    </button>
                    <button class="button modal-button" style="background-color: #28a745; color: white;" 
                        onclick="startAceJSPlayer('${fullStreamUrl}')">
                        Play on Web
                    </button>
                    <button class="button modal-button cancel-button" onclick="document.getElementById('playerOptionsModal').remove()">
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Add escape key listener to close modal
    document.addEventListener('keydown', function closeOnEscape(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('playerOptionsModal');
            if (modal) {
                modal.remove();
                document.removeEventListener('keydown', closeOnEscape);
            }
        }
    });
    
    // Add click outside to close
    document.getElementById('playerOptionsModal').addEventListener('click', function(event) {
        if (event.target === this) {
            this.remove();
        }
    });
}

function startAceJSPlayer(fullStreamUrl) {
    // 1. Limpiar la interfaz
    document.getElementById('modalButtons').style.display = 'none';
    const container = document.getElementById('acePlayerWeb');
    container.style.display = 'block';
    container.innerHTML = ''; // Limpiar cualquier error previo
	
    // 2. CREAR EL ELEMENTO VIDEO
    container.innerHTML = `<video id="videoPlayer" controls autoplay style="width:100%; height:auto; max-height:80vh; background:#000; display:block;"></video>`;
    const video = document.getElementById('videoPlayer');
	
    // Función para iniciar la reproducción con mpegts.js
    const playStream = () => {
        // Verificamos si el navegador soporta MSE para MPEG-TS
        if (mpegts.getFeatureList().mseLivePlayback) {
            const player = mpegts.createPlayer({
                type: 'mse', // Requerido para el flujo directo del proxy
                isLive: true,
                url: fullStreamUrl
            }, {
                enableWorker: true,
                stashInitialSize: 128, // Reduce latencia inicial
                lazyLoadMaxDuration: 3,
                seekType: 'range'
            });

            player.attachMediaElement(video);
            player.load();
            player.play();

            // Manejo de errores de mpegts.js
            player.on(mpegts.Events.ERROR, (type, detail, info) => {
                console.error("Mpegts error:", type, detail, info);
                container.innerHTML = `<div style="color:white; text-align:center; padding:20px;">
                    PyAceXY error: The stream is unavailable or CORS is blocked.
                </div>`;
                player.destroy();
            });

            // Limpieza: Si cierras el modal, hay que destruir el player
            // Puedes disparar este evento al cerrar el modal de Flask
            const observer = new MutationObserver((mutations) => {
                if (!document.body.contains(container) || container.style.display === 'none') {
                    player.pause();
                    player.unload();
                    player.detachMediaElement();
                    player.destroy();
                    observer.disconnect();
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });

        } 
        else if (video.canPlayType('video/mp2t')) {
            // Caso para algunos dispositivos que soportan TS nativo (raro en web)
            video.src = fullStreamUrl;
        }
        else {
            container.innerHTML = `<div style="color:white; text-align:center; padding:20px;">
                Your browser does not support MPEG-TS playback.
            </div>`;
        }
    };

    // Si la librería aún no ha cargado, esperamos un poco
    if (typeof mpegts === 'undefined') {
        setTimeout(playStream, 800);
    } else {
        playStream();
    }
}

// Function to copy the stream URL to clipboard
function copyStreamUrl() {
    const input = document.getElementById('streamUrlInput');
    input.select();
    document.execCommand('copy');
    
    // Show feedback
    const originalValue = input.value;
    input.value = 'Copied!';
    setTimeout(() => {
        input.value = originalValue;
    }, 1000);
}
