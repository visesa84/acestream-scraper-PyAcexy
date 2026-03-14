#!/bin/bash
# filepath: /app/warp-setup.sh

CONFIG_DIR="/app/config"
WG_CONF="$CONFIG_DIR/wg0.conf"
LOG_FILE="/app/logs/warp.log"

if [ "${ENABLE_WARP}" = "true" ]; then
    mkdir -p "$CONFIG_DIR" /app/logs
    cd "$CONFIG_DIR" || exit

    # 1. GENERAR CONFIGURACIÓN SI NO EXISTE
    if [ ! -f "$WG_CONF" ]; then
        echo "$(date): wg0.conf was not found. Registering a new Warp account..." >> "$LOG_FILE"
        
        # Aceptar términos y registrar (crea wgcf-account.json)
        wgcf register --accept-tos
        
        # Si tienes una clave de WARP+, aplícala aquí antes de generar
        if [ -n "$WARP_LICENSE_KEY" ]; then
            sed -i "s/\"license_key\": \".*\"/\"license_key\": \"$WARP_LICENSE_KEY\"/" wgcf-account.json
            wgcf update
        fi

        # Generar el perfil (crea wgcf-profile.conf)
        wgcf generate
        
        # Renombrar para que wg-quick lo reconozca
        mv wgcf-profile.conf "$WG_CONF"
    fi

    # 2. LEVANTAR EL TÚNEL CON BORINGTUN
    export WG_QUICK_USERSPACE_IMPLEMENTATION=boringtun
    export WG_THREADS=4

	# Limpiar por si acaso
	ip link delete wg0 2>/dev/null || true
	
	# Limpiar Address: Deja solo la primera IP (IPv4)
	sed -i 's/Address = \([^,]*\),.*/Address = \1/' "$WG_CONF"

	# Limpiar DNS: Deja solo las dos primeras (IPv4)
	sed -i 's/DNS = \([^,]*\), \([^,]*\),.*/DNS = \1, \2/' "$WG_CONF"

	# Limpiar AllowedIPs: Quita el rango ::/0
	sed -i 's/, ::\/0//' "$WG_CONF"

	# Asegurar MTU bajo
	sed -i 's/MTU = .*/MTU = 1280/' "$WG_CONF"
	
	# ELIMINAR SIEMPRE RUTAS EXISTENTES
    sed -i '/PostUp = .*/d' "$WG_CONF"
    sed -i '/PostDown = .*/d' "$WG_CONF"

    # AÑADIR RUTAS SOLO SI CONTAINER_NETWORK_MODE=bridge
    if [ "$CONTAINER_NETWORK_MODE" = "bridge" ]; then
        echo "$(date): CONTAINER_NETWORK_MODE=bridge → Adding PostUp/PostDown routes." >> "$LOG_FILE"

        GATEWAY_IP=$(ip route | grep default | awk '{print $3}')

        if [ -n "$GATEWAY_IP" ]; then
            sed -i "/\[Interface\]/a PostUp = ip route replace 162.159.192.1 via $GATEWAY_IP dev eth0 && ip route replace 0.0.0.0/0 dev wg0" "$WG_CONF"
            sed -i "/\[Interface\]/a PostDown = ip route replace 0.0.0.0/0 via $GATEWAY_IP dev eth0" "$WG_CONF"
        else
            echo "$(date): WARNING: Gateway not detected. Skipping route injection." >> "$LOG_FILE"
        fi
    else
        echo "$(date): CONTAINER_NETWORK_MODE != bridge → Running in safe mode (no routes)." >> "$LOG_FILE"
    fi

	# Eliminar cualquier FwMark si existiera
	sed -i '/FwMark/d' "$WG_CONF"
	
	# Creamos un nft falso para que no falle
	ln -sf /bin/true /usr/sbin/nft
	
	# Crear un comando sysctl falso que no haga nada pero devuelva "éxito"
	echo '#!/bin/bash' > /usr/local/bin/sysctl
	echo 'exit 0' >> /usr/local/bin/sysctl
	chmod +x /usr/local/bin/sysctl

    echo "$(date): Building a tunnel with BoringTun..." >> "$LOG_FILE"
    if wg-quick up "$WG_CONF" >> "$LOG_FILE" 2>&1; then
        echo "$(date): WARP connected." >> "$LOG_FILE"
    else
        echo "$(date): ERROR when starting wg-quick." >> "$LOG_FILE"
    fi
fi
