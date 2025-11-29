import os
import traci
import sumolib
import requests
import json

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://rumhqljidmwkctjojqdw.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_secret_n9XxV9u5_4SUzn-yXf71bw_bV2c0oR3")

# Caminho deve coincidir com o gerado pelo generator.py
SUMO_CMD = ["sumo", "-c", "/app/scenarios/from_api/api.sumocfg"]

def sync_traffic_lights():
    print("--- Iniciando Sincronização de Semáforos ---")
    try:
        traci.start(SUMO_CMD)
    except Exception as e:
        print(f"Erro ao iniciar SUMO (Cenário existe?): {e}")
        return

    tls_list = []
    for tls_id in traci.trafficlight.getIDList():
        lanes = traci.trafficlight.getControlledLanes(tls_id)
        if not lanes: continue
        
        lane_shape = traci.lane.getShape(lanes[0])
        if not lane_shape: continue
            
        x, y = lane_shape[-1]
        lon, lat = traci.simulation.convertGeo(x, y)
        
        tls_list.append({"id": tls_id, "lat": lat, "lon": lon})

    traci.close()

    if tls_list:
        print(f"Enviando {len(tls_list)} semáforos para o Supabase...")
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        res = requests.post(f"{SUPABASE_URL}/rest/v1/traffic_lights", headers=headers, data=json.dumps(tls_list))
        print("Status envio:", res.status_code)

if __name__ == "__main__":
    sync_traffic_lights()