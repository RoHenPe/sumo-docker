FROM ghcr.io/eclipse-sumo/sumo:latest

USER root

# Instala Python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Venv
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Aponta para o alias 'socket_app'
CMD ["uvicorn", "main:socket_app", "--host", "0.0.0.0", "--port", "5000", "--reload"]