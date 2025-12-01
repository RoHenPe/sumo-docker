import os
import time
import sys
from dotenv import load_dotenv
from supabase import create_client
from pyngrok import ngrok, conf

# Carrega .env local
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN") # Opcional, mas recomendado

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERRO] Faltam credenciais do Supabase no .env")
    sys.exit(1)

def update_config(url_http, url_ws):
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Atualiza HTTP
        supabase.table("system_config").upsert({"key": "backend_url", "value": url_http}, on_conflict="key").execute()
        # Atualiza WebSocket
        supabase.table("system_config").upsert({"key": "backend_ws", "value": url_ws}, on_conflict="key").execute()
        print(f"[SYNC] URLs atualizadas:\nHTTP: {url_http}\nWS: {url_ws}")
    except Exception as e:
        print(f"[ERRO] Falha Supabase: {e}")

def main():
    if NGROK_AUTH_TOKEN:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN
    
    print("[TUNNEL] Iniciando Ngrok na porta 5000...")
    try:
        ngrok.kill()
        tunnel = ngrok.connect(5000, "http")
        public_url = tunnel.public_url
        wss_url = public_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        
        update_config(public_url, wss_url)
        
        print("[INFO] Túnel Ativo. Não feche esta janela.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ngrok.kill()
    except Exception as e:
        print(f"[CRITICAL] Erro: {e}")

if __name__ == "__main__":
    main()