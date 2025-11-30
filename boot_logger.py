import os, sys, datetime 
from dotenv import load_dotenv 
from supabase import create_client 
try: load_dotenv() 
except: pass 
url = os.getenv("SUPABASE_URL") 
key = os.getenv("SUPABASE_KEY") 
def log(lvl, msg): 
    if not url or not key: return 
    try: 
        sb = create_client(url, key) 
        data = {"nivel": lvl, "modulo": "CONTROLLER", "mensagem": msg, "timestamp": datetime.datetime.now().isoformat()} 
        sb.table("simulation_logs").insert(data).execute() 
    except: pass 
if name == "main": 
    if len(sys.argv) > 2: log(sys.argv[1], sys.argv[2]) 
