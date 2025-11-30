import os
import json
import asyncio
import traci
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

try:
    from generator import generate_scenario
except ImportError:
    print("ERRO: generator.py não encontrado!")
    def generate_scenario(city, max_vehicles): return {"status": "error"}

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = FastAPI()
socket_app = app 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase conectado.")
    except Exception as e:
        print(f"Erro conexão Supabase: {e}")

class CityRequest(BaseModel):
    city_name: str
    ai_enabled: bool = False

@app.get("/")
def health_check():
    return {"status": "online", "service": "Fluxus Backend v2"}

@app.post("/generate")
def generate_endpoint(req: CityRequest):
    print(f"Recebido pedido de geração para: {req.city_name}")
    try:
        # 1. Gera o cenário (OSM -> SUMO -> Git -> Supa)
        result = generate_scenario(req.city_name, max_vehicles=200)
        
        # 2. Tenta avisar o Frontend via Banco (Tratamento de erro adicionado)
        if supabase:
            try:
                supabase.table("simulation_config").upsert({
                    "id": 1, 
                    "status": "MAP_READY", 
                    "city_name": req.city_name,
                    "command": "STOP" 
                }).execute()
            except Exception as e:
                print(f"Aviso: Erro ao atualizar simulation_config (Tabela existe?): {e}")
            
        return result
    except Exception as e:
        print(f"Erro na geração: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/toggle-ai")
def toggle_ai(enabled: bool):
    if supabase:
        try:
            supabase.table("simulation_config").update({"adaptive_mode": enabled}).eq("id", 1).execute()
        except: pass
    return {"status": "ok", "ai": enabled}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Cliente WebSocket conectado.")
    
    sumo_cfg = "/app/scenarios/simulacao.sumocfg"
    
    if not os.path.exists(sumo_cfg):
        await websocket.send_json({"error": "Cenário não encontrado. Gere primeiro."})
        await websocket.close()
        return

    # Inicia o SUMO
    sumo_cmd = ["sumo", "-c", sumo_cfg, "--step-length", "0.5", "--no-warnings"]
    
    try:
        traci.start(sumo_cmd)
        print("Simulação SUMO iniciada.")
    except Exception as e:
        print(f"Erro start SUMO: {e}")
        try: traci.close() 
        except: pass
        try: traci.start(sumo_cmd)
        except: 
            await websocket.close()
            return

    try:
        step = 0
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            
            vehicles = []
            for veh_id in traci.vehicle.getIDList():
                x, y = traci.vehicle.getPosition(veh_id)
                lon, lat = traci.simulation.convertGeo(x, y)
                angle = traci.vehicle.getAngle(veh_id)
                vehicles.append({"id": veh_id, "lat": lat, "lon": lon, "angle": angle})
            
            tls = {}
            for tls_id in traci.trafficlight.getIDList():
                tls[tls_id] = traci.trafficlight.getRedYellowGreenState(tls_id)

            await websocket.send_json({
                "time": traci.simulation.getTime(),
                "vehicles": vehicles,
                "traffic_lights": tls
            })
            
            # Grava Log no Banco (simulation_logs)
            if step % 20 == 0 and supabase:
                try:
                    supabase.table("simulation_logs").insert({
                        "step": step,
                        "vehicle_count": len(vehicles),
                        "traffic_status": "active",
                        "nivel": "INFO",
                        "modulo": "SUMO",
                        "mensagem": f"Simulacao rodando - Passo {step}"
                    }).execute()
                except: pass

            step += 1
            await asyncio.sleep(0.1)

    except Exception as e:
        print(f"Erro loop simulação: {e}")
    finally:
        try: traci.close()
        except: pass
        print("Simulação finalizada.")