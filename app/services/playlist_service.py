import os
import base64
import time
import html
from datetime import datetime
from flask import request
from urllib.parse import urlparse, quote
from typing import List, Dict, Optional
from ..repositories import ChannelRepository
from app.utils.config import Config
from app.repositories.tv_channel_repository import TVChannelRepository
from app.services.tv_channel_service import TVChannelService
from app.models.acestream_channel import AcestreamChannel

class PlaylistService:
    def __init__(self):
        self.channel_repository = ChannelRepository()
        self.config = Config()
        self.tv_channel_repository = TVChannelRepository()
        self.tv_channel_service = TVChannelService()
    
    def get_basic_auth_credentials(self):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Basic "):
            return None, None

        encoded = auth.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        user, password = decoded.split(":", 1)
        return user, password

    def _format_stream_url(self, channel_id: str, local_id: int, base_url: str = None) -> str:

        def is_ip_address(h):
            parts = h.split(".")
            return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

        if base_url:
            base_url = base_url.strip().rstrip("/")

            # Si no tiene protocolo, decidir según si es IP o dominio
            if not base_url.startswith("http://") and not base_url.startswith("https://"):
                if is_ip_address(base_url):
                    base_url = "http://" + base_url
                else:
                    base_url = "https://" + base_url

        # Si no hay base_url, usar config o localhost
        host = (base_url or getattr(self.config, 'base_url', 'http://localhost:8080')).rstrip('/')
        parsed = urlparse(host)

        # -----------------------------
        # 2. Obtener credenciales BasicAuth
        # -----------------------------
        rp_user, rp_pass = self.get_basic_auth_credentials()

        auth_str = ""
        if rp_user and rp_pass:
            safe_user = quote(rp_user, safe='')
            safe_pass = quote(rp_pass, safe='')
            auth_str = f"{safe_user}:{safe_pass}@"

        # -----------------------------
        # 3. Detectar si es IP o dominio
        # -----------------------------
        hostname = parsed.hostname or ""
        is_ip = is_ip_address(hostname)

        # -----------------------------
        # 4. Construir host final
        # -----------------------------
        if not is_ip and hostname:
            # Dominio → siempre HTTPS
            host = f"https://{auth_str}{hostname}"
        else:
            # IP local → siempre HTTP
            host = f"http://{hostname}"

            # Ajustar puerto: si viene de Flask (8040), cambiar a 8080
            flask_port = os.environ.get('FLASK_PORT', '8040')
            if parsed.port == int(flask_port):
                host = f"http://{hostname}:8080"
            elif parsed.port:
                host = f"http://{hostname}:{parsed.port}"

        # -----------------------------
        # 5. Construir query final
        # -----------------------------
        query = f"id={channel_id}"
        if getattr(self.config, 'addpid', False):
            query += f"&pid={local_id}"

        return f"{host}/ace/getstream?{query}"

    def _get_channels(self, search_term: str = None):
        """Retrieve channels from the repository with optional search term."""
        if search_term:
            return self.channel_repository.model.query.filter(
                (self.channel_repository.model.status == 'active') &
                (self.channel_repository.model.name.ilike(f'%{search_term}%'))
            ).all()
        return self.channel_repository.get_active()

    def generate_playlist(self, search_term=None, base_url=None):
        """Generate M3U playlist with channels."""
        playlist_lines = ['#EXTM3U']
        
        # Query channels from the database
        channels = self._get_channels(search_term)
        # Ordenamos por nombre ignorando mayúsculas/minúsculas
        channels = sorted(channels, key=lambda c: (c.name or "").lower())
        
        # Track used names and their counts
        name_counts = {}
        
        # Add each channel to the playlist
        for local_id, channel in enumerate(channels, start=0):
            #if not channel.is_online:
            #    continue
            # Use _format_stream_url to get the correct URL format
            stream_url = self._format_stream_url(channel.id, local_id, base_url=base_url)
            
            # Handle duplicate names
            base_name = (channel.name or "").strip()
            if base_name in name_counts:
                # Increment the counter for this name
                name_counts[base_name] += 1
                # For duplicates, append the counter value (2, 3, etc.)
                display_name = f"{base_name} #{name_counts[base_name]}"
            else:
                # First occurrence - use original name and initialize counter
                name_counts[base_name] = 1
                display_name = base_name
            
            # Add metadata if available
            metadata = []
            if channel.tvg_name:
                metadata.append(f'tvg-name="{channel.tvg_name}"')
            if channel.tvg_id:
                metadata.append(f'tvg-id="{channel.tvg_id}"')
            if channel.logo:
                metadata.append(f'tvg-logo="{channel.logo}"')
            if channel.group:
                metadata.append(f'group-title="{channel.group}"')
            
            # Create EXTINF line with metadata
            extinf = '#EXTINF:-1'
            if metadata:
                extinf += f' {" ".join(metadata)}'
            extinf += f',{display_name}'
            
            playlist_lines.append(extinf)
            playlist_lines.append(stream_url)
            
        return '\n'.join(playlist_lines)
    
    def generate_tv_channels_playlist(self, search_term=None, favorites_only=False, base_url=None):
        """Generate M3U playlist with TV channels using all their acestreams.
        
        Args:
            search_term: Optional search term to filter channels by name
            favorites_only: If True, only include favorite channels
            
        Returns:
            String containing the M3U playlist content
        """
        playlist_lines = ['#EXTM3U']
        
        # Query TV channels with filters
        channels, total, _ = self.tv_channel_repository.filter_channels(
            search_term=search_term,
            favorites_only=favorites_only,
            per_page=1000  # Large value to avoid pagination
        )
        
        # Sort channels by channel_number if available
        sorted_channels = sorted(
            channels, 
            key=lambda c: (c.channel_number is None, c.channel_number or 0, c.name.lower())
        )
        
        # Track used names and their counts
        name_counts = {}
        local_id = 0
        
        # Process each TV channel
        for tv_channel in sorted_channels:
            # Get all acestreams for this TV channel, prioritize online and best quality
            acestreams = AcestreamChannel.query.filter(
                AcestreamChannel.tv_channel_id == tv_channel.id,
                AcestreamChannel.status == 'active'
            ).all()
            
            # Skip channels without acestreams
            if not acestreams:
                continue
                
            # Sort acestreams by quality (online first, then by metadata completeness)
            def score_acestream(acestream):
                score = 0
                if acestream.is_online:
                    score += 10
                if acestream.logo:
                    score += 3
                if acestream.tvg_id:
                    score += 2
                if acestream.tvg_name:
                    score += 1
                return score
                
            sorted_acestreams = sorted(acestreams, key=score_acestream, reverse=True)
            
            # Process each acestream for this TV channel
            for stream_index, acestream in enumerate(sorted_acestreams):
                stream_url = self._format_stream_url(acestream.id, local_id, base_url=base_url)
                local_id += 1
                
                # --- AQUÍ LA SOLUCIÓN: Nombre y EPG siempre limpios ---
                display_name = tv_channel.name
                epg_id = tv_channel.epg_id if tv_channel.epg_id else acestream.tvg_id
                
                # Add metadata if available
                metadata = []
                
                # Channel numbering: Siempre el original, sin decimales
                if tv_channel.channel_number is not None:
                    metadata.append(f'tvg-chno="{tv_channel.channel_number}"')
                
                if epg_id:
                    metadata.append(f'tvg-id="{epg_id}"')
                    
                metadata.append(f'tvg-name="{display_name}"')
                
                # Logos y Categoría
                if tv_channel.logo_url:
                    metadata.append(f'tvg-logo="{tv_channel.logo_url}"')
                elif acestream.logo:
                    metadata.append(f'tvg-logo="{acestream.logo}"')
                    
                if tv_channel.category:
                    metadata.append(f'group-title="{tv_channel.category}"')
                
                # Create EXTINF line
                extinf = '#EXTINF:-1'
                if metadata:
                    extinf += f' {" ".join(metadata)}'
                extinf += f',{display_name}'
                
                playlist_lines.append(extinf)
                playlist_lines.append(stream_url)
            
        return '\n'.join(playlist_lines)

    def generate_epg_xml(self, search_term=None, favorites_only=False, base_url=None):
        """Generate XML EPG guide for channels with EPG data and associated acestreams.
        
        Args:
            search_term: Optional search term to filter channels by name
            favorites_only: If True, only include favorite channels
            
        Returns:
            String containing the XML EPG guide content
        """
        from datetime import datetime, timedelta
        from app.repositories.epg_channel_repository import EPGChannelRepository
        from app.repositories.epg_program_repository import EPGProgramRepository
        import html
        
        # Start with XML header and root element
        xml_lines = [
            '<?xml version="1.0" encoding="utf-8" ?>',
            '<!DOCTYPE tv SYSTEM "xmltv.dtd">',
            '<tv generator-info-name="Acestream Scraper EPG Generator" generator-info-url="https://github.com/visesa84/acestream-scraper-PyAcexy">'
        ]
        
        # Get TV channels with filters
        channels, _, _ = self.tv_channel_repository.filter_channels(
            search_term=search_term,
            favorites_only=favorites_only,
            is_active=True,
            per_page=1000  # Large value to avoid pagination
        )
        
        # Sort channels by channel_number if available (consistent with playlist generation)
        sorted_channels = sorted(
            channels, 
            key=lambda c: (c.channel_number is None, c.channel_number or 0, c.name.lower())
        )
        
        # Initialize repositories for EPG data
        epg_channel_repo = EPGChannelRepository()
        epg_program_repo = EPGProgramRepository()
        
        # Track channels and their EPG mappings
        channel_epg_mappings = []
        # Initialize name_counts for tracking duplicates
        name_counts = {} # Simple counter for duplicate channel names
        
        # Process each TV channel
        for tv_channel in sorted_channels:
            # Skip channels without EPG ID or acestreams
            if not tv_channel.epg_id or tv_channel.acestream_channels.count() == 0:
                continue
                
            # Get all acestreams for this TV channel
            acestreams = AcestreamChannel.query.filter(
                AcestreamChannel.tv_channel_id == tv_channel.id,
                AcestreamChannel.status == 'active'
            ).all()
            if not acestreams:
                continue
                
            # Sort acestreams by quality (same logic as playlist generation)
            def score_acestream(acestream):
                score = 0
                if acestream.is_online:
                    score += 10
                if acestream.logo:
                    score += 3
                if acestream.tvg_id:
                    score += 2
                if acestream.tvg_name:
                    score += 1
                return score
                
            sorted_acestreams = sorted(acestreams, key=score_acestream, reverse=True)
              # Find the EPG channels corresponding to this TV channel's EPG ID
            epg_channels = epg_channel_repo.get_by_channel_xml_id(tv_channel.epg_id)
            
            # Use the first channel if available, otherwise None
            epg_channel = epg_channels[0] if epg_channels else None
            
            # Create channel definitions for each acestream (handle duplicates like playlist)
            base_name = tv_channel.name
            
            # Process each acestream to create channel entries
            for stream_index, acestream in enumerate(sorted_acestreams):
                # Handle duplicate names and multiple streams per channel
                if len(sorted_acestreams) > 1:
                    # El nombre visual lleva #, pero el ID técnico es el ORIGINAL
                    display_name = f"{tv_channel.name} #{stream_index + 1}"
                    epg_id = tv_channel.epg_id  # <--- ID limpio sin sufijos
                else:
                    # Single stream: check for global name duplicates
                    if base_name in name_counts:
                        name_counts[base_name] += 1
                        display_name = f"{base_name} #{name_counts[base_name]}"
                        epg_id = tv_channel.epg_id # <--- ID limpio sin sufijos
                    else:
                        name_counts[base_name] = 1
                        display_name = base_name
                        epg_id = tv_channel.epg_id
                
                # Store mapping for program generation
                channel_epg_mappings.append({
                    'epg_id': epg_id,
                    'display_name': display_name,
                    'tv_channel': tv_channel,
                    'epg_channel': epg_channel,
                    'stream_index': stream_index,
                    'original_epg_id': tv_channel.epg_id
                })
        
        # Generate channel definitions
        for mapping in channel_epg_mappings:
            epg_id = mapping['epg_id']
            display_name = mapping['display_name']
            tv_channel = mapping['tv_channel']
            xml_lines.append(f'  <channel id="{html.escape(epg_id)}">')
            xml_lines.append(f'    <display-name>{html.escape(display_name)}</display-name>')
            
            if tv_channel.logo_url:
                xml_lines.append(f'    <icon src="{html.escape(tv_channel.logo_url)}" />')
                
            if tv_channel.website:
                xml_lines.append(f'    <url>{html.escape(tv_channel.website)}</url>')
                
            xml_lines.append('  </channel>')
        
        # Initialize the programs section - add an empty line to separate channels from programs
        xml_lines.append('')
        
        # Get program data for each channel mapping
        processed_epg_ids = set()
        
        # Get program data for each channel mapping
        for mapping in channel_epg_mappings:
            epg_id = mapping['epg_id']
            epg_channel = mapping['epg_channel']
            
            # SI YA PROCESAMOS ESTE ID, SALTAMOS AL SIGUIENTE
            if not epg_channel or epg_id in processed_epg_ids:
                continue
            
            # Marcar este ID como procesado
            processed_epg_ids.add(epg_id)
            
            # Get programs for this channel
            now = datetime.now()
            start_time = now - timedelta(hours=12)
            end_time = now + timedelta(days=7)
            
            programs = epg_program_repo.get_programs_for_channel(epg_channel.id, start_time, end_time)
            
            # Detectar el offset real del contenedor (usa la variable TZ)
            is_dst = time.localtime().tm_isdst
            offset_seconds = -(time.altzone if is_dst else time.timezone)
            
            # Convertir segundos a formato XMLTV (+HHMM)
            h, m = divmod(abs(offset_seconds) // 60, 60)
            sign = '+' if offset_seconds >= 0 else '-'
            local_offset = f"{sign}{h:02d}{m:02d}"

            # Aplicar a los programas
            for program in programs:
                start_dt = datetime.fromisoformat(program['start_time'])
                end_dt = datetime.fromisoformat(program['end_time'])
                
                # Construir el string final con el offset detectado del sistema
                start_time_str = f"{start_dt.strftime('%Y%m%d%H%M%S')} {local_offset}"
                stop_time_str = f"{end_dt.strftime('%Y%m%d%H%M%S')} {local_offset}"
                
                xml_lines.append(f'  <programme start="{start_time_str}" stop="{stop_time_str}" channel="{html.escape(epg_id)}">')
                
                title = program.get('title', 'Untitled')
                xml_lines.append(f'    <title>{html.escape(str(title))}</title>')
                
                desc = program.get('description')
                if desc:
                    xml_lines.append(f'    <desc>{html.escape(str(desc))}</desc>')
                
                cat = program.get('category')
                if cat:
                    xml_lines.append(f'    <category>{html.escape(str(cat))}</category>')
                
                xml_lines.append('  </programme>')

        xml_lines.append('</tv>')
        return '\n'.join(xml_lines)
    
    def generate_all_streams_playlist(self, search_term=None, include_unassigned=True, base_url=None):
        """Generate M3U playlist with all acestreams, including both TV channels and unassigned streams.
        
        Args:
            search_term: Optional search term to filter channels by name
            include_unassigned: If True, include acestreams not assigned to TV channels
            
        Returns:
            String containing the M3U playlist content
        """
        playlist_lines = ['#EXTM3U']
        local_id = 0
        name_counts = {}
        
        # First, get all TV channels and their acestreams
        channels, _, _ = self.tv_channel_repository.filter_channels(
            search_term=search_term,
            per_page=1000  # Large value to avoid pagination
        )
        
        # Sort channels by channel_number if available
        sorted_channels = sorted(
            channels, 
            key=lambda c: (c.channel_number is None, c.channel_number or 0, c.name.lower())
        )
        
        processed_acestreams = set()
        
        # Process TV channels and their acestreams first
        for tv_channel in sorted_channels:
            acestreams = AcestreamChannel.query.filter(
                AcestreamChannel.tv_channel_id == tv_channel.id,
                AcestreamChannel.status == 'active'
            ).all()
            if not acestreams:
                continue
                
            # Sort acestreams by quality
            def score_acestream(acestream):
                score = 0
                if acestream.is_online:
                    score += 10
                if acestream.logo:
                    score += 3
                if acestream.tvg_id:
                    score += 2
                if acestream.tvg_name:
                    score += 1
                return score
                
            sorted_acestreams = sorted(acestreams, key=score_acestream, reverse=True)
            
            # Process each acestream for this TV channel
            for stream_index, acestream in enumerate(sorted_acestreams):
                processed_acestreams.add(acestream.id)
                
                stream_url = self._format_stream_url(acestream.id, local_id, base_url=base_url)
                local_id += 1
                
                # Channel numbering and naming
                base_name = tv_channel.name
                if len(sorted_acestreams) > 1:
                    display_name = f"{base_name} ({stream_index + 1})"
                else:
                    if base_name in name_counts:
                        name_counts[base_name] += 1
                        display_name = f"{base_name} #{name_counts[base_name]}"
                    else:
                        name_counts[base_name] = 1
                        display_name = base_name
                
                metadata = []
                
                # Channel numbering with sub-numbering
                if tv_channel.channel_number is not None:
                    if len(sorted_acestreams) > 1:
                        channel_number = f"{tv_channel.channel_number}.{stream_index + 1}"
                    else:
                        channel_number = str(tv_channel.channel_number)
                    metadata.append(f'tvg-chno="{channel_number}"')
                
                # EPG and metadata
                if tv_channel.epg_id:
                    metadata.append(f'tvg-id="{tv_channel.epg_id}"')
                elif acestream.tvg_id:
                    metadata.append(f'tvg-id="{acestream.tvg_id}"')
                    
                metadata.append(f'tvg-name="{display_name}"')
                
                if tv_channel.logo_url:
                    metadata.append(f'tvg-logo="{tv_channel.logo_url}"')
                elif acestream.logo:
                    metadata.append(f'tvg-logo="{acestream.logo}"')
                    
                if tv_channel.category:
                    metadata.append(f'group-title="{tv_channel.category}"')
                
                extinf = '#EXTINF:-1'
                if metadata:
                    extinf += f' {" ".join(metadata)}'
                extinf += f',{display_name}'
                
                playlist_lines.append(extinf)
                playlist_lines.append(stream_url)
        
        # Now process unassigned acestreams if requested
        if include_unassigned:
            unassigned_query = AcestreamChannel.query.filter(
                AcestreamChannel.tv_channel_id == None,
                AcestreamChannel.status == 'active'
            )
            if search_term:
                unassigned_query = unassigned_query.filter(
                    AcestreamChannel.name.ilike(f'%{search_term}%')
                )
                
            unassigned_acestreams = unassigned_query.all()
            
            # Find the next available channel number
            next_channel_number = 1  # Start unassigned streams
            if sorted_channels:
                max_channel_number = max((c.channel_number or 0) for c in sorted_channels)
                next_channel_number = max(next_channel_number, max_channel_number + 1)
            
            for acestream in unassigned_acestreams:
                if acestream.id in processed_acestreams:
                    continue
                    
                stream_url = self._format_stream_url(acestream.id, local_id, base_url=base_url)
                local_id += 1
                
                # Use acestream name or fallback
                display_name = acestream.name or f"Stream {acestream.id[:8]}"
                
                # Handle duplicate names
                if display_name in name_counts:
                    name_counts[display_name] += 1
                    display_name = f"{display_name} #{name_counts[display_name]}"
                else:
                    name_counts[display_name] = 1
                
                metadata = []
                
                # Assign channel number to unassigned streams
                metadata.append(f'tvg-chno="{next_channel_number}"')
                next_channel_number += 1
                
                if acestream.tvg_id:
                    metadata.append(f'tvg-id="{acestream.tvg_id}"')
                    
                metadata.append(f'tvg-name="{display_name}"')
                
                if acestream.logo:
                    metadata.append(f'tvg-logo="{acestream.logo}"')
                    
                # Group unassigned streams
                if acestream.group:
                    metadata.append(f'group-title="{acestream.group}"')
                else:
                    metadata.append(f'group-title="Unassigned Streams"')
                
                extinf = '#EXTINF:-1'
                if metadata:
                    extinf += f' {" ".join(metadata)}'
                extinf += f',{display_name}'
                
                playlist_lines.append(extinf)
                playlist_lines.append(stream_url)
            
        return '\n'.join(playlist_lines)
        
    def generate_online_only_playlist(self, search_term=None, base_url=None):
        """Generate M3U playlist with ONLY active and online acestreams."""
        playlist_lines = ['#EXTM3U']
        
        query = AcestreamChannel.query.filter(
            AcestreamChannel.status == 'active',
            AcestreamChannel.is_online.is_(True)
        )

        # 2. Si hay término de búsqueda, filtramos por nombre en la DB
        if search_term:
            query = query.filter(AcestreamChannel.name.ilike(f'%{search_term}%'))

        # Ejecutamos la consulta
        online_acestreams = query.all()

        # 3. Ordenamos por nombre (insensible a mayúsculas)
        online_acestreams = sorted(online_acestreams, key=lambda x: (x.name or "").lower())
        
        name_counts = {}
        local_id = 0
        
        for acestream in online_acestreams:
            
            stream_url = self._format_stream_url(acestream.id, local_id, base_url=base_url)
            local_id += 1

            base_name = (acestream.name or "").strip()
            
            # Manejo de nombres duplicados
            if base_name in name_counts:
                name_counts[base_name] += 1
                display_name = f"{base_name} #{name_counts[base_name]}"
            else:
                name_counts[base_name] = 1
                display_name = base_name
            
            # Construcción de Metadatos EPG
            metadata = []            
            if acestream.tvg_name:
                metadata.append(f'tvg-name="{acestream.tvg_name}"')
            if acestream.tvg_id:
                metadata.append(f'tvg-id="{acestream.tvg_id}"')
            if acestream.logo:
                metadata.append(f'tvg-logo="{acestream.logo}"')
            if acestream.group:
                metadata.append(f'group-title="{acestream.group}"')
            
            # Formato EXTINF con metadatos unidos por espacios
            metadata_str = f" {' '.join(metadata)}" if metadata else ""
            extinf = f'#EXTINF:-1{metadata_str},{display_name}'
            
            playlist_lines.append(extinf)
            playlist_lines.append(stream_url)
                    
        return '\n'.join(playlist_lines)
        
    def generate_m3u_with_epg(self, base_url=None, search_term=None, favorites_only=False):
        
        # 1. Cabecera con URL del EPG
        user, password = self.get_basic_auth_credentials()

        if user and password and base_url:
            # Inyectamos las credenciales en la URL del EPG que va dentro del M3U
            parsed = urlparse(base_url)
            epg_url = f"{parsed.scheme}://{user}:{password}@{parsed.netloc}/api/playlists/epg.xml"
        else:
            epg_url = f"{base_url}/api/playlists/epg.xml" if base_url else ""

        m3u_lines = [f'#EXTM3U x-tvg-url="{epg_url}"']

        # 2. Obtener canales
        channels, _, _ = self.tv_channel_repository.filter_channels(
            search_term=search_term, 
            favorites_only=favorites_only, 
            is_active=True, 
            per_page=1000
        )
        
        name_counts = {}
        local_id = 0 # Inicializamos el contador
        
        # Ordenar por número de canal o nombre
        sorted_channels = sorted(channels, key=lambda c: (c.channel_number is None, c.channel_number or 0, c.name.lower()))

        for tv_channel in sorted_channels:
            # Solo acestreams activos para este canal de TV
            acestreams = AcestreamChannel.query.filter(
                AcestreamChannel.tv_channel_id == tv_channel.id, 
                AcestreamChannel.status == 'active'
            ).all()
            
            if not acestreams: continue

            for i, stream in enumerate(acestreams):
                # 3. Generar URL del stream usando el formateador interno
                stream_url = self._format_stream_url(stream.id, local_id, base_url=base_url)
                local_id += 1 # Incrementar para el siguiente stream

                # 4. Lógica de nombres con #
                if len(acestreams) > 1:
                    display_name = f"{tv_channel.name} #{i + 1}"
                elif tv_channel.name in name_counts:
                    name_counts[tv_channel.name] += 1
                    display_name = f"{tv_channel.name} #{name_counts[tv_channel.name]}"
                else:
                    name_counts[tv_channel.name] = 1
                    display_name = tv_channel.name

                # 5. Metadatos (Priorizamos los del canal de TV para que coincidan con el EPG)
                tvg_id = tv_channel.epg_id or ""
                logo = tv_channel.logo_url or ""
                group = tv_channel.category or "General"
                
                # Construcción de la línea #EXTINF
                m3u_lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group}",{display_name}')
                m3u_lines.append(stream_url)

        return "\n".join(m3u_lines)
