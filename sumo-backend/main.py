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

app = FastAPI()

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

# --- GERENCIADOR DE CONEXÕES (FILA) ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.queue: list[WebSocket] = []
        self.MAX_SIMULATIONS = 2  # Limite Rígido de 2 usuários

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        if len(self.active_connections) < self.MAX_SIMULATIONS:
            self.active_connections.append(websocket)
            return True # Entrou
        else:
            self.queue.append(websocket)
            pos = len(self.queue)
            await websocket.send_json({"status": "queue", "position": pos, "message": "Servidor cheio. Aguarde na fila."})
            return False # Fila

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        elif websocket in self.queue:
            self.queue.remove(websocket)

    def is_active(self, websocket: WebSocket):
        return websocket in self.active_connections

    def try_promote(self):
        if len(self.active_connections) < self.MAX_SIMULATIONS and len(self.queue) > 0:
            next_ws = self.queue.pop(0)
            self.active_connections.append(next_ws)
            return next_ws
        return None

manager = ConnectionManager()

class CityRequest(BaseModel):
    city_name: str
    ai_enabled: bool = False

class ControlRequest(BaseModel):
    action: str 

# --- ROTAS HTTP ---
@app.get("/")
def health_check():
    if sys_logger: sys_logger.info("Health Check OK.")
    return {"status": "online", "active": len(manager.active_connections), "queue": len(manager.queue)}

@app.post("/generate")
def generate_and_save(req: CityRequest):
    global current_scenario_id
    if sys_logger: sys_logger.info(f"Gerando: {req.city_name}")
    try:
        data = generate_scenario(req.city_name, max_vehicles=300)
    except Exception as e:
        if sys_logger: sys_logger.error(f"Erro Generator: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    # Lógica simplificada de salvar cenário no DB
    if supabase:
        try:
            res = supabase.table("scenarios").insert({
                "city_name": req.city_name,
                "node_count": data.get("nodes", 0),
                "edge_count": data.get("edges", 0)
            }).execute()
            if res.data: current_scenario_id = res.data[0]['id']
        except: pass
    return {"status": "success", "scenario_id": current_scenario_id}

@app.post("/toggle-ai")
def toggle_ai(enabled: bool):
    traffic_ai.set_ai_status(enabled)
    return {"ai_active": enabled}

@app.post("/control-simulation")
def control_simulation(req: ControlRequest):
    global simulation_running
    if req.action == "stop":
        simulation_running = False
        return {"status": "success"}
    elif req.action == "start":
        return {"status": "success"}
    raise HTTPException(status_code=400)

# --- WEBSOCKET ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # 1. Tenta conectar (Ativo ou Fila)
    is_authorized = await manager.connect(websocket)
    
    # 2. Loop de Espera na Fila
    if not is_authorized:
        try:
            while websocket in manager.queue:
                promoted = manager.try_promote()
                if promoted == websocket:
                    is_authorized = True
                    await websocket.send_json({"status": "started", "message": "Sua vez chegou!"})
                    break
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            manager.disconnect(websocket)
            return

    # 3. Inicia Simulação
    global simulation_running
    simulation_running = True
    if sys_logger: sys_logger.info("Simulacao Iniciada.")

    sumo_cmd = ["sumo", "-c", "/app/scenarios/simulacao.sumocfg", "--step-length", "0.5", "--no-warnings"]
    if not os.path.exists("/app/scenarios/simulacao.sumocfg"):
        with open("/app/scenarios/simulacao.sumocfg", "w") as f:
            f.write("""<configuration><input><net-file value="simulacao.net.xml"/><route-files value="simulacao.rou.xml"/></input></configuration>""")

    try:
        try: traci.start(sumo_cmd)
        except: 
            try: traci.close()
            except: pass
            traci.start(sumo_cmd)
    except Exception:
        await websocket.close()
        return

    step_count = 0
    try:
        while traci.simulation.getMinExpectedNumber() > 0 and simulation_running:
            if not manager.is_active(websocket): break

            traci.simulationStep()
            ai_logs = traffic_ai.step()
            
            vehicles = []
            for veh_id in traci.vehicle.getIDList():
                x, y = traci.vehicle.getPosition(veh_id)
                lon, lat = traci.simulation.convertGeo(x, y)
                # DADOS CRÍTICOS PARA O FRONTEND
                vehicles.append({
                    "id": veh_id, 
                    "lat": lat, 
                    "lon": lon, 
                    "angle": traci.vehicle.getAngle(veh_id),
                    "speed": traci.vehicle.getSpeed(veh_id),      # m/s
                    "distance": traci.vehicle.getDistance(veh_id) # metros
                })

            tls_states = {tls: traci.trafficlight.getRedYellowGreenState(tls) for tls in traci.trafficlight.getIDList()}
            
            await websocket.send_json({
                "time": traci.simulation.getTime(),
                "vehicles": vehicles,
                "traffic_lights": tls_states,
                "status": "running"
            })

            # Salva logs no Supabase a cada 10 steps
            if step_count % 10 == 0 and ai_logs and current_scenario_id and supabase:
                for log in ai_logs:
                    log['scenario_id'] = current_scenario_id
                    log['timestamp'] = traci.simulation.getTime()
                asyncio.create_task(save_logs_async(ai_logs))

            step_count += 1
            await asyncio.sleep(0.05)
        
        if not simulation_running:
             await websocket.send_json({"status": "stopped"})

    except Exception as e:
        print(f"Erro Loop: {e}")
    finally:
        manager.disconnect(websocket)
        try: traci.close()
        except: pass
        simulation_running = False

async def save_logs_async(logs):
    try:
        if supabase: supabase.table("simulation_logs").insert(logs).execute()
    except: pass