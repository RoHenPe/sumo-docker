import os
import sys
import traci
import libsumo
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import socketio
from supabase import create_client, Client
import asyncio
import json

# --- CONFIGURAÇÃO ---
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)

# Chaves de Segurança
API_SECRET = os.getenv("API_SECRET", "fluxus-secret-key-2025")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Conexão com Banco
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase Conectado")
    except:
        print("❌ Erro Supabase")

# App Server
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO com Autenticação
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
socket_app = socketio.ASGIApp(sio, app)

# Estado Global
SIMULATION_STATE = {
    "running": False,
    "mode": "static",
    "city": "Indefinida",
    "step": 0,
    "vehicles_count": 0,
    "avg_speed": 0.0
}

# --- SEGURANÇA ---
async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_SECRET:
        raise HTTPException(status_code=403, detail="Chave de API Inválida ou Ausente")

# --- ROTAS ---
class ScenarioRequest(BaseModel):
    city: str
    vehicles: int = 1000

@app.post("/generate", dependencies=[Depends(verify_api_key)])
async def generate_scenario(req: ScenarioRequest):
    # Aqui entraria a chamada ao script generator.py real
    # Por enquanto, simulamos o sucesso para o frontend não travar se o script faltar
    SIMULATION_STATE["city"] = req.city
    return {"status": "success", "message": f"Cenário {req.city} gerado com {req.vehicles} veículos."}

@app.post("/control", dependencies=[Depends(verify_api_key)])
async def control_sim(action: str):
    if action == "start":
        if not SIMULATION_STATE["running"]:
            sio.start_background_task(run_simulation_loop)
        return {"status": "started"}
    elif action == "stop":
        SIMULATION_STATE["running"] = False
        return {"status": "stopped"}
    return {"status": "invalid"}

# --- LOOP DE SIMULAÇÃO ---
async def run_simulation_loop():
    # Tenta encontrar o arquivo gerado. Se não achar, usa um dummy para não quebrar o loop visual
    cfg_file = "/app/scenarios/from_api/api.sumocfg"
    
    # Comando de inicialização (Headless)
    sumo_cmd = ["sumo", "-c", cfg_file, "--step-length", "0.5", "--no-warnings"]
    
    try:
        if os.path.exists(cfg_file):
            traci.start(sumo_cmd)
        else:
            print("⚠️ Configuração não encontrada. Aguardando geração...")
            return

        SIMULATION_STATE["running"] = True
        print(f"🚀 Simulação iniciada: {SIMULATION_STATE['city']}")

        while SIMULATION_STATE["running"]:
            traci.simulationStep()
            SIMULATION_STATE["step"] += 1
            
            # Extração de Dados Reais
            vehicle_ids = traci.vehicle.getIDList()
            vehicles_data = []
            total_speed = 0
            
            for vid in vehicle_ids:
                x, y = traci.vehicle.getPosition(vid)
                lon, lat = traci.simulation.convertGeo(x, y)
                angle = traci.vehicle.getAngle(vid)
                v_type = traci.vehicle.getTypeID(vid)
                speed = traci.vehicle.getSpeed(vid)
                
                total_speed += speed
                vehicles_data.append({
                    "id": vid, "lat": lat, "lon": lon,
                    "angle": angle, "type": v_type, "speed": speed
                })

            # Atualiza Estatísticas Globais
            count = len(vehicles_data)
            SIMULATION_STATE["vehicles_count"] = count
            SIMULATION_STATE["avg_speed"] = (total_speed / count) if count > 0 else 0

            # Envia para o Frontend (React)
            await sio.emit('simulation_update', {
                "vehicles": vehicles_data,
                "stats": {
                    "count": SIMULATION_STATE["vehicles_count"],
                    "speed": SIMULATION_STATE["avg_speed"] * 3.6 # Converter m/s para km/h
                }
            })
            
            # Reinicia se acabar os carros
            if traci.simulation.getMinExpectedNumber() <= 0:
                traci.load(sumo_cmd[1:])

            await asyncio.sleep(0.1) # Controla FPS do servidor

    except Exception as e:
        print(f"Erro Crítico: {e}")
        SIMULATION_STATE["running"] = False
        try: traci.close()
        except: pass

# --- SOCKET.IO AUTH ---
@sio.on('connect')
async def connect(sid, environ, auth):
    # Verifica a chave também no WebSocket
    if not auth or auth.get('token') != API_SECRET:
        print(f"Cliente rejeitado (Chave inválida): {sid}")
        return False # Rejeita conexão
    print(f"Cliente autenticado conectado: {sid}")

@sio.on('disconnect')
def disconnect(sid):
    print(f"Cliente desconectado: {sid}")