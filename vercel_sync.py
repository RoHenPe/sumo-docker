import os
import time
import sys
from dotenv import load_dotenv
from supabase import create_client
from pyngrok import ngrok, conf

# --- CORREÇÃO DE CAMINHOS (INFALÍVEL) ---
# Pega a pasta onde ESTE script está (sumo-backend)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Sobe um nível para a pasta raiz (sumo-docker)
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Define os caminhos absolutos
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
URL_FILE = os.path.join(PROJECT_ROOT, "ngrok_url.txt")

# Carrega .env
load_dotenv(ENV_PATH)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTHTOKEN")

# Se não tiver chave principal, tenta a anônima (fallback)
if not SUPABASE_KEY:
    SUPABASE_KEY = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

if not SUPABASE_URL:
    # Cria arquivo de erro para o BAT avisar você
    try:
        with open(URL_FILE, "w") as f: f.write("ERRO_ENV_MISSING")
    except: pass
    sys.exit(1)

def update_config(url_http, url_ws):
    print(f"[INFO] Link Gerado: {url_http}")
    
    # 1. SALVA ARQUIVO NA RAIZ (PARA O BAT DESTRAVAR)
    try:
        with open(URL_FILE, "w") as f:
            f.write(url_http)
        print(f"[SUCESSO] Arquivo salvo em: {URL_FILE}")
    except Exception as e:
        print(f"[ERRO] Falha ao criar arquivo local: {e}")

    # 2. SALVA NO SUPABASE (PARA O CELULAR FUNCIONAR)
    try:
        if SUPABASE_KEY:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            supabase.table("system_config").upsert({"key": "backend_url", "value": url_http}, on_conflict="key").execute()
            supabase.table("system_config").upsert({"key": "backend_ws", "value": url_ws}, on_conflict="key").execute()
            print("[NUVEM] Supabase Sincronizado.")
    except Exception as e:
        print(f"[AVISO] Erro ao salvar na nuvem (o link local ainda funciona): {e}")

def main():
    if NGROK_AUTH_TOKEN:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN
    
    print("[TUNNEL] Iniciando Ngrok...")
    
    while True:
        try:
            ngrok.kill()
            tunnel = ngrok.connect(5000, "http")
            public_url = tunnel.public_url
            wss_url = public_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
            
            update_config(public_url, wss_url)
            
            print("------------------------------------------------")
            print(" TÚNEL ATIVO. NÃO FECHE ESTA JANELA.")
            print("------------------------------------------------")
            
            while True:
                time.sleep(5)
                
        except KeyboardInterrupt:
            ngrok.kill()
            if os.path.exists(URL_FILE): os.remove(URL_FILE)
            sys.exit(0)
        except Exception as e:
            print(f"[RETRY] Erro no túnel: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()