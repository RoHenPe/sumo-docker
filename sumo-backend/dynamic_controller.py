import traci

class TrafficAI:
    def __init__(self, ai_enabled=False):
        self.ai_enabled = ai_enabled
        self.tls_timers = {} # Para evitar troca frenética de luzes

    def set_ai_status(self, status: bool):
        self.ai_enabled = status
        print(f"🧠 IA Status: {'ATIVADA' if status else 'DESATIVADA'}")

    def step(self):
        # Se IA desligada, deixa o SUMO controlar (tempo fixo)
        if not self.ai_enabled:
            return {}

        logs = []
        tls_ids = traci.trafficlight.getIDList()

        for tls_id in tls_ids:
            # Lógica Simples de IA Adaptativa:
            # Verifica todas as faixas controladas por esse semáforo
            controlled_lanes = traci.trafficlight.getControlledLanes(tls_id)
            
            max_queue = 0
            total_wait = 0
            
            for lane in controlled_lanes:
                # Pega numero de carros parados na faixa
                queue = traci.lane.getLastStepHaltingNumber(lane)
                # Pega tempo de espera acumulado
                wait = traci.lane.getWaitingTime(lane)
                
                if queue > max_queue:
                    max_queue = queue
                total_wait += wait

            # DECISÃO DA IA:
            # Se a fila estiver grande (> 5 carros) e o sinal não trocou recentemente
            # Força o verde para a via mais congestionada (Simplificação)
            # No SUMO real, mudamos a "Phase" do programa
            
            current_phase = traci.trafficlight.getPhase(tls_id)
            
            # Log para salvar no banco
            logs.append({
                "traffic_light_id": tls_id,
                "queue_length": max_queue,
                "avg_wait_time": total_wait / (len(controlled_lanes) or 1),
                "is_ai_active": True
            })

            # Exemplo de ação: Se fila > 10, estende o tempo da fase atual
            if max_queue > 10:
                traci.trafficlight.setPhaseDuration(tls_id, 60) # Dá mais tempo verde

        return logs