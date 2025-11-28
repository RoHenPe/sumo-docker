import os
import sys
import json
import subprocess
import random
import urllib.request
import urllib.parse
import ssl
import xml.etree.ElementTree as ET
import sumolib

# Configuração de Pastas no Docker
BASE_DIR = "/app"
SCENARIO_DIR = os.path.join(BASE_DIR, "scenarios/from_api")

def ensure_directories():
    if not os.path.exists(SCENARIO_DIR):
        os.makedirs(SCENARIO_DIR)

def get_bbox(city_name, radius_km=1.0):
    """Busca coordenadas da cidade no Nominatim (OSM)"""
    try:
        q = urllib.parse.quote(city_name)
        url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'FluxusDocker/1.0'})
        ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
        
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            data = json.loads(r.read())
            if not data: return None
            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
            
            # Calcula BBOX simples
            offset = radius_km / 111.0
            return (lat - offset, lon - offset, lat + offset, lon + offset), lat, lon
    except Exception as e:
        print(f"Erro Geocoding: {e}")
        return None

def generate_scenario(city_name, vehicles=500):
    ensure_directories()
    
    print(f"📍 Gerando cenário para: {city_name}")
    
    # 1. Obter Coordenadas
    geo_data = get_bbox(city_name)
    if not geo_data:
        raise Exception("Cidade não encontrada")
    
    bbox, lat, lon = geo_data
    s, w, n, e = bbox
    
    osm_file = os.path.join(SCENARIO_DIR, "map.osm.xml")
    net_file = os.path.join(SCENARIO_DIR, "api.net.xml")
    rou_file = os.path.join(SCENARIO_DIR, "api.rou.xml")
    cfg_file = os.path.join(SCENARIO_DIR, "api.sumocfg")
    
    # 2. Baixar OSM
    print("📥 Baixando mapa do OpenStreetMap...")
    osm_url = f"https://overpass-api.de/api/map?bbox={w},{s},{e},{n}"
    try:
        req = urllib.request.Request(osm_url)
        with urllib.request.urlopen(req, timeout=60) as r, open(osm_file, 'wb') as f:
            f.write(r.read())
    except Exception as e:
        raise Exception(f"Erro download OSM: {e}")

    # 3. Converter para SUMO (.net.xml)
    print("🔄 Convertendo para Rede SUMO (netconvert)...")
    subprocess.run([
        "netconvert",
        "--osm-files", osm_file,
        "-o", net_file,
        "--geometry.remove", "true",
        "--tls.guess", "true",
        "--tls.join", "true",
        "--output.street-names", "true"
    ], check=True)

    # 4. Gerar Rotas Aleatórias (randomTrips.py)
    print(f"🚗 Gerando {vehicles} viagens aleatórias...")
    random_trips_script = os.path.join(os.environ['SUMO_HOME'], 'tools', 'randomTrips.py')
    subprocess.run([
        "python3", random_trips_script,
        "-n", net_file,
        "-r", rou_file,
        "-e", "3600", # 1 hora de geração
        "-p", str(3600 / vehicles), # Periodo de inserção
        "--validate"
    ], check=True)

    # 5. Criar Configuração SUMO (.sumocfg)
    with open(cfg_file, "w") as f:
        f.write(f"""<configuration>
    <input>
        <net-file value="api.net.xml"/>
        <route-files value="api.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="90000"/>
    </time>
</configuration>""")

    # Retorna dados para o frontend atualizar o mapa
    return {
        "status": "success",
        "center": {"lat": lat, "lon": lon},
        "bbox": bbox
    }