import sys
import threading
import datetime
import traceback
from supabase import Client

class SupabaseLogger:
    def __init__(self, supabase_client: Client, module_name="SUMO_DOCKER"):
        self.supabase = supabase_client
        self.module = module_name
        self.terminal = sys.stdout # Guarda o print original

    def log(self, level, message):
        """Envia o log para o Supabase e imprime no terminal do Docker"""
        # 1. Imprime no console do Docker (para debug via 'docker logs')
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        colored_level = f"[{level}]"
        print(f"{timestamp} {colored_level} {message}", file=self.terminal)

        # 2. Envia para o Supabase (em uma thread separada para não travar a simulação)
        def _send():
            try:
                self.supabase.table("simulation_logs").insert({
                    "nivel": level,
                    "modulo": self.module,
                    "mensagem": str(message),
                    "timestamp": datetime.datetime.now().isoformat()
                }).execute()
            except Exception as e:
                print(f"Erro ao salvar log no Supabase: {e}", file=self.terminal)
        
        threading.Thread(target=_send).start()

    def info(self, msg): self.log("INFO", msg)
    def warning(self, msg): self.log("WARNING", msg)
    def error(self, msg): self.log("ERROR", msg)
    def critical(self, msg): self.log("CRITICAL", msg)

class StreamInterceptor:
    """Redireciona stdout e stderr para o nosso Logger"""
    def __init__(self, logger, level="INFO"):
        self.logger = logger
        self.level = level
        self.buffer = ""

    def write(self, message):
        # Ignora quebras de linha sozinhas
        if message.strip() == "": return
        self.logger.log(self.level, message.strip())

    def flush(self):
        pass

def setup_global_logging(supabase_client):
    """Ativa a interceptação global"""
    logger = SupabaseLogger(supabase_client)
    
    # Redireciona prints normais -> INFO
    sys.stdout = StreamInterceptor(logger, "INFO")
    
    # Redireciona erros (ex: exceções do Python) -> ERROR
    sys.stderr = StreamInterceptor(logger, "ERROR")
    
    return logger