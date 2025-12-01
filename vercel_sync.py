import os
import time
import sys
from dotenv import load_dotenv
from supabase import create_client
from pyngrok import ngrok, conf

# Carrega variáveis
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN") # Adicione isso no seu .env

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERRO] Supabase Credentials missing.")
    sys.exit(1)

def update_config(url_http, url_ws):
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Atualiza HTTP
        supabase.table("system_config").update({"value": url_http, "updated_at": "now()"}).eq("key", "backend_url").execute()
        
        # Atualiza WebSocket
        supabase.table("system_config").update({"value": url_ws, "updated_at": "now()"}).eq("key", "backend_ws").execute()
        
        print(f"[SYNC] URLs atualizadas no Supabase:\nHTTP: {url_http}\nWS: {url_ws}")
    except Exception as e:
        print(f"[ERRO] Falha ao atualizar Supabase: {e}")

def main():
    # Configura Ngrok
    if NGROK_AUTH_TOKEN:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN
    
    print("[TUNNEL] Iniciando Ngrok na porta 5000...")
    
    # Abre o túnel
    try:
        # Fecha túneis anteriores se houver
        ngrok.kill()
        
        # Cria novo túnel HTTP
        tunnel = ngrok.connect(5000, "http")
        public_url = tunnel.public_url
        
        # Converte para WSS (WebSocket Seguro)
        wss_url = public_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        
        # Atualiza o banco de dados
        update_config(public_url, wss_url)
        
        print("[INFO] Pressione Ctrl+C para encerrar o túnel.")
        
        # MANTÉM O SCRIPT RODANDO (Loop Infinito)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Encerrando túnel...")
            ngrok.kill()

    except Exception as e:
        print(f"[CRITICAL] Erro no Ngrok: {e}")

if __name__ == "__main__":
    main()