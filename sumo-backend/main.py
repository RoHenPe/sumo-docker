import os
import json
import asyncio
import traci
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from github import Github

# Logger
from logger_utils import setup_global_logging

# Imports Opcionais
try:
    import osmnx as ox
except ImportError:
    ox = None
    print("AVISO: osmnx não instalado.")

try:
    from generator import generate_scenario
    from dynamic_controller import TrafficAI
except ImportError:
    def generate_scenario(*args, **kwargs): return {"nodes": 0, "edges": 0}
    class TrafficAI:
        def __init__(self, ai_enabled): pass
        def set_ai_status(self, enabled): pass
        def step(self): return []

# Configurações
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SCENARIO_DIR = "/app/scenarios"

os.makedirs(SCENARIO_DIR, exist_ok=True)

# --- CORREÇÃO DO NOME DO APP ---
app = FastAPI()
socket_app = app  # O Dockerfile busca 'socket_app'

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Inicializa Logs
sys_logger = None
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        sys_logger = setup_global_logging(supabase)
        sys_logger.info("Backend iniciado com sucesso.")
    else:
        supabase = None
except Exception as e:
    print(f"ERRO SUPABASE: {e}")
    supabase = None

traffic_ai = TrafficAI(ai_enabled=False)
simulation_running = False
current_scenario_id = None

class CityRequest(BaseModel):
    city_name: str
    ai_enabled: bool = False

# --- ROTAS ---

@app.get("/")
def health_check():
    if sys_logger: sys_logger.info("Health Check OK.")
    return {"status": "online", "service": "SUMO Backend"}

@app.get("/validate-city")
def validate_city(city: str):
    if not ox: return {"exists": False, "error": "OSMnx ausente"}
    try:
        gdf = ox.geocode_to_gdf(city)
        return {"exists": True, "lat": gdf.geometry.y[0], "lon": gdf.geometry.x[0]}
    except Exception as e:
        if sys_logger: sys_logger.warning(f"Erro cidade: {e}")
        return {"exists": False}

@app.post("/generate")
def generate_and_save(req: CityRequest):
    global current_scenario_id
    if sys_logger: sys_logger.info(f"Gerando: {req.city_name}")

    try:
        data = generate_scenario(req.city_name, max_vehicles=300)
    except Exception as e:
        if sys_logger: sys_logger.error(f"Erro Generator: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    commit_url = "Git Disabled"
    if supabase:
        try:
            bucket = "scenarios"
            files = ["simulacao.net.xml", "simulacao.rou.xml"]
            for f_name in files:
                path = os.path.join(SCENARIO_DIR, f_name)
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        supabase.storage.from_(bucket).upload(f"{req.city_name}/{f_name}", f, {"upsert": "true"})
        except Exception as e:
            if sys_logger: sys_logger.error(f"Erro Storage: {e}")

        if GITHUB_TOKEN:
            try:
                g = Github(GITHUB_TOKEN)
                repo = g.get_user().get_repo("sumo-docker") 
                metadata_content = json.dumps(data, indent=2)
                try:
                    repo.create_file(path=f"scenarios/{req.city_name}_meta.json", message=f"Cenario {req.city_name}", content=metadata_content)
                except: pass
                commit_url = f"https://github.com/{repo.full_name}/tree/main/scenarios"
            except Exception as e:
                if sys_logger: sys_logger.warning(f"Erro Git: {e}")

        try:
            res = supabase.table("scenarios").insert({
                "city_name": req.city_name,
                "node_count": data.get("nodes", 0),
                "edge_count": data.get("edges", 0),
                "github_commit_url": commit_url
            }).execute()
            if res.data:
                current_scenario_id = res.data[0]['id']
        except Exception as e:
            if sys_logger: sys_logger.error(f"Erro SQL: {e}")

    return {"status": "success", "scenario_id": current_scenario_id}

@app.post("/toggle-ai")
def toggle_ai(enabled: bool):
    traffic_ai.set_ai_status(enabled)
    return {"ai_active": enabled}

# --- WEBSOCKET ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global simulation_running
    
    simulation_running = True
    if sys_logger: sys_logger.info("Simulacao Iniciada (WS).")

    sumo_cmd = ["sumo", "-c", "/app/scenarios/simulacao.sumocfg", "--step-length", "0.5", "--no-warnings"]
    
    if not os.path.exists("/app/scenarios/simulacao.sumocfg"):
        with open("/app/scenarios/simulacao.sumocfg", "w") as f:
            f.write("""<configuration><input><net-file value="simulacao.net.xml"/><route-files value="simulacao.rou.xml"/></input></configuration>""")

    try:
        traci.start(sumo_cmd)
    except traci.TraCIException:
        try: traci.close()
        except: pass
        traci.start(sumo_cmd)

    step_count = 0
    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            ai_logs = traffic_ai.step()
            
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

            if step_count % 10 == 0 and ai_logs and current_scenario_id and supabase:
                for log in ai_logs:
                    log['scenario_id'] = current_scenario_id
                    log['timestamp'] = traci.simulation.getTime()
                asyncio.create_task(save_logs_async(ai_logs))

            step_count += 1
            await asyncio.sleep(0.05)

    except Exception as e:
        print(f"Erro Simulacao: {e}")
    finally:
        try: traci.close()
        except: pass
        simulation_running = False

async def save_logs_async(logs):
    try:
        if supabase:
            supabase.table("simulation_logs").insert(logs).execute()
    except Exception as e:
        print(f"Erro logs async: {e}")