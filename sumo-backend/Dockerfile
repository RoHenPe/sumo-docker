FROM ghcr.io/eclipse-sumo/sumo:main

# Instala Python e Pip
USER root
RUN apt-get update && apt-get install -y python3 python3-pip

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o código do backend
COPY . .

# A porta 5000 será usada para o Socket.IO/FastAPI
EXPOSE 5000

# Inicia o servidor
CMD ["uvicorn", "main:socket_app", "--host", "0.0.0.0", "--port", "5000", "--reload"]