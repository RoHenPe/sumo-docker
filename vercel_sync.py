import os
import time
import requests
import json
import sys

# --- SUAS CONFIGURAÇÕES ---
VERCEL_TOKEN = "m0tFEuTAoWFulOsHkGdWozCw"  # Seu token atual
VERCEL_PROJECT_NAME = "web"                 # Nome do projeto identificado
TARGET_ENV = "NEXT_PUBLIC_API_URL"

def get_ngrok_url():
    print("⏳ Procurando túnel Ngrok...")
    # Tenta conectar na API local do Ngrok (porta 4040 é padrão do Docker/Ngrok)
    for i in range(10):
        try:
            res = requests.get("http://localhost:4040/api/tunnels", timeout=2)
            data = res.json()
            # Pega o primeiro túnel público HTTPS
            for tunnel in data.get('tunnels', []):
                if tunnel.get('public_url', '').startswith('https'):
                    public_url = tunnel['public_url']
                    print(f"✅ Ngrok encontrado: {public_url}")
                    return public_url
        except:
            pass
        time.sleep(2)
        print(f"   (Tentativa {i+1}/10) Aguardando Ngrok subir...")
    return None

def update_vercel_env(new_value):
    headers = {
        "Authorization": f"Bearer {VERCEL_TOKEN}", 
        "Content-Type": "application/json"
    }
    
    # 1. Pegar ID do Projeto
    print(f"🔍 Buscando ID do projeto '{VERCEL_PROJECT_NAME}'...")
    r = requests.get(f"https://api.vercel.com/v9/projects/{VERCEL_PROJECT_NAME}", headers=headers)
    
    if r.status_code != 200:
        print(f"❌ Erro ao achar projeto. Verifique o nome '{VERCEL_PROJECT_NAME}'.")
        print(f"   Detalhe: {r.text}")
        return

    project_data = r.json()
    project_id = project_data.get('id')
    print(f"   ID encontrado: {project_id}")

    # 2. Listar Variáveis para achar o ID da NEXT_PUBLIC_API_URL
    print(f"🔍 Buscando variável '{TARGET_ENV}'...")
    r = requests.get(f"https://api.vercel.com/v9/projects/{project_id}/env", headers=headers)
    env_id = None
    
    # Procura a variável na lista
    for env in r.json().get('envs', []):
        if env['key'] == TARGET_ENV:
            env_id = env['id']
            break
    
    # Se não existir, avisa
    if not env_id:
        print(f"❌ Variável '{TARGET_ENV}' não encontrada no projeto Vercel.")
        print("   Crie ela manualmente no painel da Vercel primeiro com um valor qualquer.")
        return

    # 3. Atualizar a variável
    print(f"🚀 Atualizando Vercel para: {new_value}")
    body = {
        "value": new_value, 
        "type": "encrypted", 
        "target": ["production", "preview", "development"]
    }
    r = requests.patch(
        f"https://api.vercel.com/v9/projects/{project_id}/env/{env_id}", 
        headers=headers, 
        json=body
    )
    
    if r.status_code == 200:
        print("✅ SUCESSO! Variável atualizada na Vercel.")
        print("⚠️  ATENÇÃO: Para o site pegar o novo link, pode ser necessário um REDEPLOY no painel da Vercel.")
    else:
        print(f"❌ Falha ao atualizar: {r.text}")

if __name__ == "__main__":
    url = get_ngrok_url()
    if url:
        update_vercel_env(url)
    else:
        print("❌ Não foi possível pegar a URL do Ngrok. Verifique se o Docker está rodando.")