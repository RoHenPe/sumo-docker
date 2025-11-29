import os
import json
import asyncio
import traci
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from github import Github
from generator import generate_scenario
from dynamic_controller import TrafficAI

# --- Configurações ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") # Token enviado pelo frontend ou .env
SCENARIO_DIR = "/app/scenarios"
REPO_NAME = "rohenpe/sumo-scenarios-data" # Crie esse repo ou use o seu

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Clientes
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
traffic_ai = TrafficAI(ai_enabled=False)
simulation_running = False
current_scenario_id = None

# Modelos de Dados
class CityRequest(BaseModel):
    city_name: str
    ai_enabled: bool = False

# --- ROTAS DA API (Controle do Site) ---

@app.get("/validate-city")
def validate_city(city: str):
    """Verifica se a cidade existe no OpenStreetMap (via OSMnx/Nominatim)"""
    try:
        import osmnx as ox
        # Tenta pegar apenas as coordenadas para validar rápido
        gdf = ox.geocode_to_gdf(city)
        return {"exists": True, "lat": gdf.geometry.y[0], "lon": gdf.geometry.x[0]}
    except:
        return {"exists": False}

@app.post("/generate")
def generate_and_save(req: CityRequest):
    """
    1. Gera Malha
    2. Salva Metadados no Git
    3. Salva Arquivos no Supabase
    """
    global current_scenario_id
    
    # 1. Gerar Arquivos Locais
    try:
        data = generate_scenario(req.city_name, max_vehicles=300) # 300 carros base
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Upload para Supabase Storage
    bucket = "scenarios"
    files = ["simulacao.net.xml", "simulacao.rou.xml"]
    
    for f_name in files:
        path = os.path.join(SCENARIO_DIR, f_name)
        with open(path, "rb") as f:
            supabase.storage.from_(bucket).upload(f"{req.city_name}/{f_name}", f, {"upsert": "true"})

    # 3. Salvar Metadados no Git (GitHub)
    commit_url = "Git Disabled"
    if GITHUB_TOKEN:
        try:
            g = Github(GITHUB_TOKEN)
            # Ajuste para seu usuário/repo correto
            repo = g.get_user().get_repo("sumo-docker") 
            # Cria um arquivo JSON de metadata no repo
            metadata_content = json.dumps(data, indent=2)
            repo.create_file(
                path=f"scenarios/{req.city_name}_meta.json",
                message=f"Gerado cenário para {req.city_name}",
                content=metadata_content
            )
            commit_url = f"https://github.com/{repo.full_name}/tree/main/scenarios"
        except Exception as e:
            print(f"⚠️ Erro Git: {e}")

    # 4. Registrar no Banco SQL
    res = supabase.table("scenarios").insert({
        "city_name": req.city_name,
        "node_count": data["nodes"],
        "edge_count": data["edges"],
        "github_commit_url": commit_url
    }).execute()
    
    if res.data:
        current_scenario_id = res.data[0]['id']

    return {"status": "success", "scenario_id": current_scenario_id}

@app.post("/toggle-ai")
def toggle_ai(enabled: bool):
    """Ativa ou Desativa a IA em tempo real"""
    traffic_ai.set_ai_status(enabled)
    return {"ai_active": enabled}

# --- WEBSOCKET (Simulação em Tempo Real) ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global simulation_running
    
    simulation_running = True
    print("🚦 Simulação Iniciada via WebSocket")

    sumo_cmd = ["sumo", "-c", "/app/scenarios/simulacao.sumocfg", "--step-length", "0.5"]
    
    # Se não tiver .sumocfg, cria um temporário rápido
    if not os.path.exists("/app/scenarios/simulacao.sumocfg"):
        with open("/app/scenarios/simulacao.sumocfg", "w") as f:
            f.write("""<configuration><input><net-file value="simulacao.net.xml"/><route-files value="simulacao.rou.xml"/></input></configuration>""")

    try:
        traci.start(sumo_cmd)
    except:
        traci.close()
        traci.start(sumo_cmd)

    step_count = 0
    
    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            
            # 1. Executa IA
            ai_logs = traffic_ai.step()
            
            # 2. Envia dados para o Frontend (Visualização)
            vehicles = []
            for veh_id in traci.vehicle.getIDList():
                x, y = traci.vehicle.getPosition(veh_id)
                lon, lat = traci.simulation.convertGeo(x, y)
                vehicles.append({"id": veh_id, "lat": lat, "lon": lon, "angle": traci.vehicle.getAngle(veh_id)})

            tls_states = {tls: traci.trafficlight.getRedYellowGreenState(tls) for tls in traci.trafficlight.getIDList()}
            
            await websocket.send_json({
                "time": traci.simulation.getTime(),
                "vehicles": vehicles,
                "traffic_lights": tls_states
            })

            # 3. Salva Logs no Supabase (Batch a cada 10 passos para não travar)
            if step_count % 10 == 0 and ai_logs and current_scenario_id:
                # Adiciona o ID do cenário aos logs
                for log in ai_logs:
                    log['scenario_id'] = current_scenario_id
                    log['timestamp'] = traci.simulation.getTime()
                
                # Envia para o banco de forma assíncrona (fire and forget)
                asyncio.create_task(save_logs_async(ai_logs))

            step_count += 1
            await asyncio.sleep(0.1)

    except Exception as e:
        print(f"Erro simulação: {e}")
    finally:
        try: traci.close()
        except: pass
        simulation_running = False

async def save_logs_async(logs):
    try:
        supabase.table("simulation_logs").insert(logs).execute()
    except Exception as e:
        print(f"Erro ao salvar logs: {e}")