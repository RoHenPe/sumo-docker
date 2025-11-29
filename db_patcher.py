import os 
def patch_file(fp, old, new): 
    if not os.path.exists(fp): return 
    with open(fp, 'r', encoding='utf-8') as f: c = f.read() 
    if old in c: 
        with open(fp, 'w', encoding='utf-8') as f: f.write(c.replace(old, new)) 
if __name__ == "__main__": 
    patch_file(r"C:\UNIP\sumo-docker\sumo-backend\logger_utils.py", "application_logs", "simulation_logs") 
