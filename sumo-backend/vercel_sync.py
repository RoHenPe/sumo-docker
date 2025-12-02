import os
import time
import sys
from dotenv import load_dotenv
from supabase import create_client
from pyngrok import ngrok, conf

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# CORREÇÃO: Nome exato conforme seu .env
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTHTOKEN") 

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERRO] Supabase Credentials missing.")
    sys.exit(1)

def update_config(url_http, url_ws):
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Atualiza HTTP e Websocket no banco para a Vercel ler
        supabase.table("system_config").upsert({"key": "backend_url", "value": url_http}, on_conflict="key").execute()
        supabase.table("system_config").upsert({"key": "backend_ws", "value": url_ws}, on_conflict="key").execute()
        print(f"[SYNC] URLs atualizadas no Supabase:\nHTTP: {url_http}\nWS: {url_ws}")
    except Exception as e:
        print(f"[ERRO] Falha ao atualizar Supabase: {e}")

def main():
    if NGROK_AUTH_TOKEN:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN
    else:
        print("[AVISO] Token do Ngrok não encontrado no .env!")
    
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
        print(f"[CRITICAL] Erro no Ngrok: {e}")

if __name__ == "__main__":
    main()