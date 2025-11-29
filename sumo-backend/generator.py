import os
import sys
import json
import subprocess
import shutil
import random
import urllib.request
import urllib.parse
import ssl
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import sumolib

# Tenta importar bibliotecas opcionais
try:
    from github import Github, Auth
    HAS_GITHUB = True
except ImportError: HAS_GITHUB = False

try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError: HAS_SUPABASE = False

# Logger simples para o Docker
def log(msg, level="INFO"):
    print(f"[{level}] {msg}", flush=True)

# Configurações de Diretório (Docker)
PROJECT_ROOT = Path("/app")
SCENARIO_DIR = PROJECT_ROOT / "scenarios" / "from_api"
OUTPUT_DIR = PROJECT_ROOT / "output" # Para validação/HTML

class ScenarioGeneratorAPI:
    def __init__(self):
        self.device_manifest = []
        self.traffic_lights_config = []
        self.generated_macs = set()
        
        # Credenciais
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")
        self.gh_token = os.getenv("GITHUB_TOKEN")
        
        # Repo Config
        self.repo_name = "RoHenPe/plataforma-trafego-web"
        self.repo_map_path = "public/maps" # Pasta base no Git

    def _gen_mac(self):
        while True:
            mac = ":".join([f"{random.randint(0, 255):02X}" for _ in range(6)])
            if mac not in self.generated_macs:
                self.generated_macs.add(mac)
                return mac

    def generate(self, city_name, num_vehicles, duration):
        log(f"=== INICIANDO GERAÇÃO: {city_name} ({num_vehicles} veic) ===")
        
        # 1. Preparar Pastas
        if SCENARIO_DIR.exists(): shutil.rmtree(SCENARIO_DIR)
        SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # 2. Localização (Nominatim)
        bbox, lat, lon = self._get_bbox_from_city(city_name)
        
        # Arquivos
        osm_file = SCENARIO_DIR / "map.osm.xml"
        net_file = SCENARIO_DIR / "api.net.xml"
        rou_file = SCENARIO_DIR / "api.rou.xml"
        cfg_file = SCENARIO_DIR / "api.sumocfg"
        
        # 3. Download e Conversão
        log("Baixando OSM...")
        self._download_map(bbox, osm_file)
        self._clean_xml(osm_file)
        
        log("Convertendo para Rede SUMO...")
        self._build_net(osm_file, net_file, bbox)
        
        # 4. Extração de Dados (Ruas e Dispositivos)
        log("Extraindo geometria das ruas...")
        roads_data = self._extract_sumo_geometry(net_file)
        
        log("Gerando dispositivos (Câmeras/Semáforos)...")
        self._generate_devices(net_file)
        
        # 5. Tráfego Aleatório
        log("Gerando rotas de veículos...")
        self._gen_trips(SCENARIO_DIR, net_file, duration, num_vehicles)

        # 6. HTML de Validação
        local_html = OUTPUT_DIR / "api_mapa_validacao.html"
        self._gen_web_map_fidelity(lat, lon, bbox, roads_data, local_html)

        # 7. Sincronização (Supabase)
        log("Sincronizando Banco de Dados...")
        self._clear_devices_db()
        self._sync_devices_db()
        self._sync_roads_to_supabase(roads_data)

        # 8. Backup no GitHub (Cenário Completo)
        log("Fazendo backup no GitHub...")
        self._upload_scenario_to_github(city_name, [
            (local_html, "api_mapa_validacao.html"),
            (net_file, f"{city_name}.net.xml"),
            (rou_file, f"{city_name}.rou.xml"),
            (cfg_file, f"{city_name}.sumocfg")
        ])

        return {"status": "success", "city": city_name, "bbox": bbox}

    # --- INTEGRAÇÃO GITHUB ---
    def _upload_scenario_to_github(self, city_slug, files_to_upload):
        """Salva HTML e arquivos do SUMO no Git"""
        if not HAS_GITHUB or not self.gh_token:
            log("GitHub Token não encontrado. Pulando backup.", "WARN")
            return

        try:
            g = Github(auth=Auth.Token(self.gh_token))
            repo = g.get_repo(self.repo_name)
            
            for local_path, remote_name in files_to_upload:
                if not local_path.exists(): continue
                
                # Salva na pasta public/maps/{cidade}/...
                remote_path = f"{self.repo_map_path}/{remote_name}"
                
                with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                try:
                    c = repo.get_contents(remote_path)
                    repo.update_file(c.path, f"Update {remote_name}", content, c.sha)
                    log(f"Git: Atualizado {remote_name}")
                except:
                    repo.create_file(remote_path, f"Create {remote_name}", content)
                    log(f"Git: Criado {remote_name}")
                    
        except Exception as e:
            log(f"Erro GitHub: {e}", "ERROR")

    # --- SUPABASE SYNC ---
    def _sync_roads_to_supabase(self, roads_data):
        if not HAS_SUPABASE or not self.sb_url: return
        try:
            client = create_client(self.sb_url, self.sb_key)
            # Limpa tabela (opcional, cuidado em prod)
            client.table("rede_viaria").delete().neq("id", "0").execute()
            
            # Batch Insert
            batch_size = 100
            for i in range(0, len(roads_data), batch_size):
                batch = roads_data[i:i+batch_size]
                payload = [{
                    "id": r['id'], "name": r['name'], "type": r['type'],
                    "points": r['points'], "style": r['style']
                } for r in batch]
                client.table("rede_viaria").upsert(payload).execute()
            log("Ruas sincronizadas com Supabase.")
        except Exception as e:
            log(f"Erro Supabase (Ruas): {e}", "ERROR")

    def _sync_devices_db(self):
        if not HAS_SUPABASE or not self.sb_url: return
        try:
            client = create_client(self.sb_url, self.sb_key)
            if not self.device_manifest: return
            
            payload = []
            for d in self.device_manifest:
                payload.append({
                    "mac_address": d['id'],
                    "tipo": d['type'],
                    "latitude": d['geo']['lat'],
                    "longitude": d['geo']['lon'],
                    "status": "active"
                })
            client.table("dispositivos").upsert(payload).execute()
            log(f"{len(payload)} dispositivos sincronizados.")
        except Exception as e:
            log(f"Erro Supabase (Devices): {e}", "ERROR")

    def _clear_devices_db(self):
        if not HAS_SUPABASE or not self.sb_url: return
        try:
            client = create_client(self.sb_url, self.sb_key)
            client.table("dispositivos").delete().neq("mac_address", "0").execute()
        except: pass

    # --- GEOMETRIA E SUMO ---
    def _extract_sumo_geometry(self, net_file):
        net = sumolib.net.readNet(str(net_file))
        roads = []
        for edge in net.getEdges():
            if edge.getFunction() == "internal": continue
            
            geo_shape = []
            for x, y in edge.getShape():
                lon, lat = net.convertXY2LonLat(x, y)
                geo_shape.append([lat, lon])
            
            speed = edge.getSpeed()
            rtype = 'rodovia' if speed > 20 else 'primaria' if speed > 13 else 'secundaria'
            color = '#22c55e' if rtype == 'primaria' else '#eab308'
            
            roads.append({
                'id': edge.getID(), 'name': edge.getName() or edge.getID(),
                'points': geo_shape, 'type': rtype,
                'style': {'c': color, 'w': 3}
            })
        return roads

    def _generate_devices(self, net_file):
        net = sumolib.net.readNet(str(net_file))
        for tls in net.getTrafficLights():
            # Cria lógica simples para semáforos
            conns = tls.getConnections()
            if not conns: continue
            
            lane = conns[0][0]
            sx, sy = lane.getShape()[-1]
            lon, lat = net.convertXY2LonLat(sx, sy)
            
            mac = self._gen_mac()
            self.device_manifest.append({
                "id": mac, "type": "SEMAFARO",
                "geo": {"lat": lat, "lon": lon}
            })
            
            # Adiciona Câmera próxima
            self.device_manifest.append({
                "id": self._gen_mac(), "type": "CAMERA",
                "geo": {"lat": lat + 0.0001, "lon": lon + 0.0001}
            })

    # --- HELPERS DE ARQUIVO E REDE ---
    def _get_bbox_from_city(self, city, radius_km=1.0):
        try:
            q = urllib.parse.quote(city)
            url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
            req = urllib.request.Request(url, headers={'User-Agent': 'Fluxus/1.0'})
            ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
                data = json.loads(r.read())
                lat, lon = float(data[0]['lat']), float(data[0]['lon'])
                offset = radius_km / 111.0
                return (lat - offset, lon - offset, lat + offset, lon + offset), lat, lon
        except:
            return (-23.5-0.01, -46.6-0.01, -23.5+0.01, -46.6+0.01), -23.5, -46.6

    def _download_map(self, bbox, target):
        s, w, n, e = bbox
        url = f"https://overpass-api.de/api/map?bbox={w},{s},{e},{n}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=60) as r, open(target, 'wb') as f:
                shutil.copyfileobj(r, f)
        except Exception as e:
            log(f"Erro download: {e}", "ERROR")

    def _clean_xml(self, fp):
        try:
            with open(fp, 'r', encoding='utf-8') as f: c = f.read()
            c = re.sub(r'\sxmlns="[^"]+"', '', c, count=1)
            with open(fp, 'w', encoding='utf-8') as f: f.write(c)
        except: pass

    def _build_net(self, osm, net, bbox):
        s, w, n, e = bbox
        # Usa netconvert do sistema
        cmd = ["netconvert", "--osm-files", str(osm), "-o", str(net), 
               "--keep-edges.in-geo-boundary", f"{w},{s},{e},{n}",
               "--geometry.remove", "true", "--tls.guess", "true", "--output.street-names"]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _gen_trips(self, out_dir, net_file, duration, vehicles):
        rou_file = out_dir / "api.rou.xml"
        trips_script = os.path.join(os.environ['SUMO_HOME'], 'tools', 'randomTrips.py')
        
        # Gera viagens
        period = float(duration) / float(vehicles)
        subprocess.run([
            "python3", trips_script, "-n", str(net_file), "-r", str(rou_file),
            "-e", str(duration), "-p", str(period), "--validate"
        ], check=True, stdout=subprocess.DEVNULL)
        
        # Gera Config
        with open(out_dir / "api.sumocfg", 'w') as f:
            f.write(f"""<configuration>
    <input><net-file value="api.net.xml"/><route-files value="api.rou.xml"/></input>
    <time><begin value="0"/><end value="{duration}"/></time>
</configuration>""")

    def _gen_web_map_fidelity(self, lat, lon, bbox, roads, fp):
        # Gera HTML simplificado para debug
        with open(fp, 'w') as f:
            f.write(f"<html><body><h1>Mapa Gerado: {lat}, {lon}</h1><p>Ruas: {len(roads)}</p></body></html>")