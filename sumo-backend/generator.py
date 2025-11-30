import os
import shutil
import random
import urllib.request
import urllib.parse
import ssl
import subprocess
from pathlib import Path
import json

try:
    from github import Github, Auth
    HAS_GITHUB = True
except ImportError: HAS_GITHUB = False

try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError: HAS_SUPABASE = False

def log(msg, level="INFO"):
    print(f"[{level}] {msg}", flush=True)

PROJECT_ROOT = Path("/app")
SCENARIO_DIR = PROJECT_ROOT / "scenarios" 
SCENARIO_DIR.mkdir(parents=True, exist_ok=True)

class ScenarioGeneratorAPI:
    def __init__(self):
        self.device_manifest = []
        self.generated_macs = set()
        self.sb_url = os.getenv("SUPABASE_URL")
        self.sb_key = os.getenv("SUPABASE_KEY")
        self.gh_token = os.getenv("GITHUB_TOKEN")
        self.repo_name = "RoHenPe/sumo-docker" 
        self.repo_map_path = "scenarios" 

    def _gen_mac(self):
        while True:
            mac = ":".join([f"{random.randint(0, 255):02X}" for _ in range(6)])
            if mac not in self.generated_macs:
                self.generated_macs.add(mac)
                return mac

    def generate(self, city_name, num_vehicles=300, duration=1000):
        log(f"=== INICIANDO GERAÇÃO OSM: {city_name} ===")
        
        osm_file = SCENARIO_DIR / "map.osm.xml"
        net_file = SCENARIO_DIR / "simulacao.net.xml"
        rou_file = SCENARIO_DIR / "simulacao.rou.xml"
        cfg_file = SCENARIO_DIR / "simulacao.sumocfg"

        if osm_file.exists(): os.remove(osm_file)
        
        # 1. Download
        bbox, lat, lon = self._get_bbox_from_city(city_name)
        self._download_map(bbox, osm_file)
        
        # 2. Conversão
        log("Convertendo OSM para SUMO...")
        try:
            self._build_net(osm_file, net_file, bbox)
        except subprocess.CalledProcessError as e:
            log(f"ERRO NETCONVERT (Ignoravel se gerou arquivo): {e}", "WARN")
        
        # 3. Sync Supabase
        log("Sincronizando com Supabase...")
        try:
            roads_data = self._extract_sumo_geometry(net_file)
            self._sync_roads_to_supabase(roads_data)
            self._generate_devices(net_file)
            self._sync_devices_db()
        except Exception as e:
            log(f"Erro sync dados: {e}", "WARN")
        
        # 4. Tráfego
        log("Gerando tráfego...")
        self._gen_trips(net_file, rou_file, duration, num_vehicles)

        with open(cfg_file, 'w') as f:
            f.write(f"""<configuration><input><net-file value="simulacao.net.xml"/><route-files value="simulacao.rou.xml"/></input><time><begin value="0"/><end value="{duration}"/></time></configuration>""")

        # 5. GitHub
        log("Salvando no GitHub...")
        self._upload_scenario_to_github(city_name, [
            (net_file, f"{city_name}.net.xml"),
            (rou_file, f"{city_name}.rou.xml"),
            (cfg_file, f"{city_name}.sumocfg")
        ])

        return {"status": "success", "city": city_name}

    def _sync_roads_to_supabase(self, roads_data):
        if not HAS_SUPABASE or not self.sb_url: return
        try:
            client = create_client(self.sb_url, self.sb_key)
            # CORREÇÃO UUID: Deleta filtrando por nome, não por ID zero
            try: client.table("rede_viaria").delete().neq("name", "SYSTEM_INIT_CHECK").execute()
            except: pass 
            
            batch_size = 50
            for i in range(0, len(roads_data), batch_size):
                batch = roads_data[i:i+batch_size]
                client.table("rede_viaria").upsert(batch).execute()
            log("Tabela 'rede_viaria' atualizada.")
        except Exception as e:
            log(f"Erro Supabase (Ruas): {e}", "ERROR")

    def _sync_devices_db(self):
        if not HAS_SUPABASE or not self.sb_url: return
        try:
            client = create_client(self.sb_url, self.sb_key)
            if not self.device_manifest: return
            
            # CORREÇÃO UUID: Deleta filtrando por MAC, não por ID zero
            try: client.table("dispositivos").delete().neq("mac_address", "00:00:00:00:00:00").execute()
            except: pass

            client.table("dispositivos").upsert(self.device_manifest).execute()
            log(f"Inseridos {len(self.device_manifest)} dispositivos.")
        except Exception as e:
            log(f"Erro Supabase (Devices): {e}", "ERROR")

    def _upload_scenario_to_github(self, city_slug, files_to_upload):
        if not HAS_GITHUB or not self.gh_token: return
        try:
            g = Github(auth=Auth.Token(self.gh_token))
            try: repo = g.get_repo(self.repo_name)
            except: repo = g.get_user().get_repo(self.repo_name.split('/')[-1])
            
            for local_path, remote_name in files_to_upload:
                if not local_path.exists(): continue
                remote_path = f"{self.repo_map_path}/{city_slug}/{remote_name}"
                with open(local_path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
                try:
                    c = repo.get_contents(remote_path)
                    repo.update_file(c.path, f"Update {remote_name}", content, c.sha)
                except:
                    repo.create_file(remote_path, f"Create {remote_name}", content)
        except Exception as e:
            log(f"Erro GitHub: {e}", "ERROR")

    def _extract_sumo_geometry(self, net_file):
        import sumolib
        net = sumolib.net.readNet(str(net_file))
        roads = []
        for edge in net.getEdges():
            if edge.getFunction() == "internal": continue
            geo_shape = [[net.convertXY2LonLat(x,y)[1], net.convertXY2LonLat(x,y)[0]] for x,y in edge.getShape()]
            speed = edge.getSpeed()
            rtype = 'rodovia' if speed > 20 else 'primaria' if speed > 13 else 'secundaria'
            roads.append({
                'id': edge.getID(), 
                'name': edge.getName() or edge.getID(),
                'type': rtype,
                'points': geo_shape,
                'style': {'color': '#22c55e' if rtype == 'primaria' else '#eab308'}
            })
        return roads

    def _generate_devices(self, net_file):
        import sumolib
        net = sumolib.net.readNet(str(net_file))
        self.device_manifest = []
        for tls in net.getTrafficLights():
            conns = tls.getConnections()
            if not conns: continue
            lane = conns[0][0]
            sx, sy = lane.getShape()[-1]
            lon, lat = net.convertXY2LonLat(sx, sy)
            self.device_manifest.append({"mac_address": self._gen_mac(), "tipo": "SEMAFARO", "latitude": lat, "longitude": lon, "status": "active"})
            self.device_manifest.append({"mac_address": self._gen_mac(), "tipo": "CAMERA", "latitude": lat+0.0001, "longitude": lon+0.0001, "status": "active"})

    def _get_bbox_from_city(self, city, radius_km=1.5):
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
            return (-23.56-0.01, -46.65-0.01, -23.56+0.01, -46.65+0.01), -23.56, -46.65

    def _download_map(self, bbox, target):
        s, w, n, e = bbox
        url = f"https://overpass-api.de/api/map?bbox={w},{s},{e},{n}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as r, open(target, 'wb') as f: shutil.copyfileobj(r, f)

    def _build_net(self, osm, net, bbox):
        s, w, n, e = bbox
        cmd = ["netconvert", "--osm-files", str(osm), "-o", str(net), 
               "--keep-edges.in-geo-boundary", f"{w},{s},{e},{n}",
               "--geometry.remove", "true", "--tls.guess", "true", "--output.street-names", "true"]
        subprocess.run(cmd, check=True)

    def _gen_trips(self, net_file, rou_file, duration, vehicles):
        if "SUMO_HOME" not in os.environ: os.environ["SUMO_HOME"] = "/usr/share/sumo"
        trips_script = os.path.join(os.environ['SUMO_HOME'], 'tools', 'randomTrips.py')
        subprocess.run(["python3", trips_script, "-n", str(net_file), "-r", str(rou_file), "-e", str(duration), "-p", str(float(duration)/vehicles), "--validate"], check=True)

def generate_scenario(city_name, max_vehicles=300):
    gen = ScenarioGeneratorAPI()
    return gen.generate(city_name, max_vehicles)