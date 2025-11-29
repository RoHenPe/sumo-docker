FROM ghcr.io/eclipse-sumo/sumo:latest

USER root
# Instala Python, Pip e bibliotecas espaciais necessárias para o OSMNX
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Atualiza pip e instala dependências
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["uvicorn", "main:socket_app", "--host", "0.0.0.0", "--port", "5000", "--reload"]