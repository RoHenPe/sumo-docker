import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Carrega suas chaves do arquivo .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def verificar_logs():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERRO] Arquivo .env não encontrado ou sem chaves.")
        return

    print(f"conectando ao Supabase em: {SUPABASE_URL[:20]}...")
    
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Busca os últimos 5 registros da tabela 'application_logs'
        # Se você mudou o nome da tabela no código, ajuste aqui.
        response = client.table("application_logs")\
            .select("*")\
            .order("timestamp", desc=True)\
            .limit(5)\
            .execute()
        
        logs = response.data
        
        if not logs:
            print("\n[AVISO] Conexão OK, mas a tabela está VAZIA.")
            print("Verifique se o nome da tabela 'application_logs' está correto no Supabase.")
        else:
            print("\n=== SUCESSO! ÚLTIMOS LOGS RECEBIDOS NA NUVEM ===")
            for log in logs:
                # Ajuste os campos 'nivel', 'modulo', 'mensagem' conforme suas colunas no banco
                ts = log.get('timestamp', 'Sem Data')
                mod = log.get('modulo', 'Geral')
                msg = log.get('mensagem', '')
                print(f"[{ts}] [{mod}] {msg}")
            print("================================================")

    except Exception as e:
        print(f"\n[FALHA] Não foi possível ler o Supabase: {e}")

if __name__ == "__main__":
    verificar_logs()