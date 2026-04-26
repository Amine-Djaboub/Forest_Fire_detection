import subprocess
import sys
import os
import time

def main():
    print(">>> Starting Drone Simulation System <<<")
    
    # Dynamically find the app directory so paths are always correct
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.join(base_dir, "app")
    
    # List of your sub-modules
    scripts = [
        os.path.join(app_dir, "drone_translator.py"),
        os.path.join(app_dir, "model_cam.py"),
        os.path.join(app_dir, "gcs.py"),
        os.path.join(app_dir, "movement_logic.py"),
        os.path.join(app_dir, "image_receiver.py")
    ]
    
    processes = []
    
    try:
        # Launch each script as a background process
        for script in scripts:
            print(f"Launching {os.path.basename(script)}...")
            process = subprocess.Popen([sys.executable, script])
            processes.append(process)
            
            # Give each script a second to spin up its MQTT connection/Camera
            time.sleep(1) 
            
        print("\n[+] All modules are running! Press Ctrl+C in this terminal to shut down the entire system.")
        
        # Keep the main script alive so we can catch Ctrl+C
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[!] Ctrl+C detected. Shutting down all modules...")
        for p in processes:
            p.terminate() # Kill the background processes cleanly
        print("System shutdown complete.")

if __name__ == "__main__":
    main()