.import re
import serial
import serial.tools.list_ports
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
import time
import csv
from datetime import datetime
from collections import deque

# Matplotlib embedding
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

### ===== CONFIG =====
CSV_FILENAME = "sensor_log.csv"
MAX_HISTORY = 100
DISEASE_ALERT_THRESHOLD = 0.8
### ==================

# Regex
temp_hum_pattern = re.compile(r"T:\s*([\d.]+)\s*C\s*H:\s*([\d.]+)")
class_value_pattern = re.compile(r"^\s*([^:]+):\s*([\d.]+)")
rssi_pattern = re.compile(r"RSSI\s*(-?\d+)")
received_packet_pattern = re.compile(r"Received packet '(.+)' with RSSI\s*(-?\d+)")
event_q = queue.Queue()

serial_running = False
serial_thread = None

last_temp = None
last_hum = None

def init_csv():
    try:
        with open(CSV_FILENAME, "r"): return
    except:
        with open(CSV_FILENAME, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp","temp","hum","diseased","healthy","soil","rssi"])

init_csv()

### SERIAL READER THREAD
def serial_reader(port, baud):
    global last_temp, last_hum, serial_running

    try:
        ser = serial.Serial(port, baud, timeout=1)
        event_q.put(("status", f"Connected to {port}"))
    except Exception as e:
        event_q.put(("error", str(e)))
        return

    prediction_block = False
    prediction_lines = []

    while serial_running:
        try:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()

            # ---- PRINT RAW SERIAL OUTPUT ----
            print(f"[SERIAL] {line}")

            # Temperature/humidity parsing
            m = temp_hum_pattern.search(line)
            if m:
                t, h = float(m.group(1)), float(m.group(2))
                last_temp, last_hum = t, h
                event_q.put(("temp_hum", {"temp": t, "hum": h}))
                continue

            # Start of prediction block
            if "Pred(" in line or "Predictions:" in line or "Received packet" in line:
                prediction_block = True
                prediction_lines = [line]
                continue

            # Collect prediction block lines
            if prediction_block:
                prediction_lines.append(line)

                # End of block: RSSI found
                if "RSSI" in line:
                    block_text = " ".join(prediction_lines)

                    md = re.search(r"Diseased:\s*([\d.]+)", block_text)
                    mh = re.search(r"Healthy:\s*([\d.]+)", block_text)
                    ms = re.search(r"Soil.*State:\s*([\d.]+)", block_text)
                    mrssi = re.search(r"RSSI\s*(-?\d+)", block_text)

                    event_q.put(("prediction", {
                        "diseased": float(md.group(1)) if md else None,
                        "healthy": float(mh.group(1)) if mh else None,
                        "soil": float(ms.group(1)) if ms else None,
                        "rssi": int(mrssi.group(1)) if mrssi else None,
                        "temp": last_temp,
                        "hum": last_hum,
                    }))

                    prediction_block = False
                    prediction_lines = []

        except Exception as e:
            event_q.put(("error", str(e)))
            break

    ser.close()
    event_q.put(("status", "Serial stopped"))




### MAIN GUI APP
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ESP32 LoRa Sensor Monitor")
        self.geometry("820x560")
        self.protocol("WM_DELETE_WINDOW", self.exit_app)

        # Tk Variables
        self.temp_var = tk.StringVar(value="--- °C")
        self.hum_var = tk.StringVar(value="--- %")
        self.rssi_var = tk.StringVar(value="--- dBm")
        self.status_var = tk.StringVar(value="Idle")

        # For alert flashing
        self.alert_active = False
        self.flash_state = False

        # History for graph
        self.hist = {
            "diseased": deque(maxlen=MAX_HISTORY),
            "healthy": deque(maxlen=MAX_HISTORY),
            "soil": deque(maxlen=MAX_HISTORY)
        }

        self.build_ui()
        self.after(100, self.process_events)



    ### UI CREATION
    ### UI CREATION (update build_ui)
    def build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=6)

        # Port selector
        ttk.Label(top, text="Port:").grid(row=0, column=0)
        self.port_var = tk.StringVar()
        self.port_menu = ttk.OptionMenu(top, self.port_var, "")
        self.port_menu.grid(row=0, column=1)
        self.refresh_ports()
        ttk.Button(top, text="Refresh", command=self.refresh_ports).grid(row=0, column=2)

        # Baud
        ttk.Label(top, text="Baud:").grid(row=0, column=3)
        self.baud_var = tk.StringVar(value="115200")
        ttk.Entry(top, textvariable=self.baud_var, width=10).grid(row=0, column=4)

        # Start/Stop Buttons
        ttk.Button(top, text="START", command=self.start_serial).grid(row=0, column=5, padx=10)
        ttk.Button(top, text="STOP", command=self.stop_serial).grid(row=0, column=6)

        # Labels section
        label_frame = ttk.Frame(self)
        label_frame.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(label_frame, text="Temperature:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(label_frame, textvariable=self.temp_var).grid(row=1, column=0, sticky="w")

        ttk.Label(label_frame, text="Humidity:", font=("Arial", 10, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(label_frame, textvariable=self.hum_var).grid(row=1, column=1, sticky="w")

        ttk.Label(label_frame, text="RSSI:", font=("Arial", 10, "bold")).grid(row=0, column=2, sticky="w")
        ttk.Label(label_frame, textvariable=self.rssi_var).grid(row=1, column=2, sticky="w")

        ttk.Label(label_frame, text="Status:", font=("Arial", 10, "bold")).grid(row=0, column=3, sticky="w")
        ttk.Label(label_frame, textvariable=self.status_var).grid(row=1, column=3, sticky="w")

        # Alert box
        self.alert_box = ttk.Label(self, text="OK", background="lightgreen", anchor="center", font=("Arial", 14, "bold"))
        self.alert_box.pack(fill=tk.X, padx=10, pady=6)

        # Matplotlib Graph (time-series)
        fig = Figure(figsize=(7,3), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_ylim(0, 1)
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Probability")
        self.ax.set_title("Plant Health Over Time")

        self.line_diseased, = self.ax.plot([], [], color='red', label="Diseased")
        self.line_healthy,  = self.ax.plot([], [], color='green', label="Healthy")
        self.ax.legend(loc="upper right")

        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Plant state label
        self.plant_state_label = ttk.Label(self, text="Plant State: ---", font=("Arial", 12, "bold"))
        self.plant_state_label.pack(pady=4)

        # Soil state label
        self.soil_state_label = ttk.Label(self, text="Soil State: ---", font=("Arial", 12, "bold"))
        self.soil_state_label.pack(pady=4)

        # History for graph
        self.time_history = deque(maxlen=MAX_HISTORY)
        self.hist = {
            "diseased": deque(maxlen=MAX_HISTORY),
            "healthy": deque(maxlen=MAX_HISTORY),
        }



    ### PORT REFRESH
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        menu = self.port_menu["menu"]
        menu.delete(0, "end")

        if ports:
            for p in ports:
                menu.add_command(label=p, command=lambda x=p: self.port_var.set(x))
            self.port_var.set(ports[0])
        else:
            self.port_var.set("None")



    ### START SERIAL
    def start_serial(self):
        global serial_running, serial_thread
        if serial_running:
            return

        port = self.port_var.get()
        baud = int(self.baud_var.get())

        serial_running = True
        serial_thread = threading.Thread(target=serial_reader, args=(port, baud), daemon=True)
        serial_thread.start()
        self.status_var.set("Serial running")



    ### STOP SERIAL
    def stop_serial(self):
        global serial_running
        serial_running = False
        self.status_var.set("Stopped")



    ### PROCESS EVENTS
    def process_events(self):
        while not event_q.empty():
            ev, data = event_q.get()

            if ev == "error":
                messagebox.showerror("Serial Error", data)
                self.status_var.set("Error")

            elif ev == "status":
                self.status_var.set(data)

            elif ev == "temp_hum":
                t, h = data["temp"], data["hum"]
                self.temp_var.set(f"{t:.1f} °C")
                self.hum_var.set(f"{h:.1f} %")
                self.log_csv(t, h, None, None, None, None)

            elif ev == "prediction":
                self.update_prediction(data)

        self.after(100, self.process_events)



    ### UPDATE PREDICTION UI
    def update_prediction(self, cur):
        diseased = cur["diseased"] or 0
        healthy  = cur["healthy"] or 0
        soil     = cur["soil"] or 0
        rssi     = cur["rssi"]

        self.rssi_var.set(f"{rssi} dBm")

        # Append to history
        timestamp = datetime.now()
        self.time_history.append(timestamp)
        self.hist["diseased"].append(diseased)
        self.hist["healthy"].append(healthy)

        # Update time-series lines
        self.line_diseased.set_data(self.time_history, self.hist["diseased"])
        self.line_healthy.set_data(self.time_history, self.hist["healthy"])
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()

        # Update plant state text
        if diseased > DISEASE_ALERT_THRESHOLD:
            self.plant_state_label.config(text=f"Plant State: Diseased", foreground="red")
            self.activate_alert(diseased)
        else:
            self.plant_state_label.config(text=f"Plant State: Healthy", foreground="green")
            self.deactivate_alert()

        # Update soil state text
        soil_text = "Wet" if soil == 1 else "Dry"
        self.soil_state_label.config(text=f"Soil State: {soil_text}", foreground="blue")

        # Log CSV
        self.log_csv(cur["temp"], cur["hum"], diseased, healthy, soil, rssi)



    ### ALERTS
    def activate_alert(self, val):
        if not self.alert_active:
            self.alert_active = True
            self.flash_alert()

        self.alert_box.config(text=f"ALERT! Diseased {val:.2f}")

    def deactivate_alert(self):
        self.alert_active = False
        self.alert_box.config(text="OK", background="lightgreen")

    def flash_alert(self):
        if not self.alert_active:
            self.alert_box.config(background="lightgreen")
            return
        self.flash_state = not self.flash_state
        self.alert_box.config(background="red" if self.flash_state else "#8b0000")
        self.after(400, self.flash_alert)



    ### CSV LOGGING
    def log_csv(self, temp, hum, diseased, healthy, soil, rssi):
        with open(CSV_FILENAME, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                datetime.utcnow().isoformat(),
                temp if temp is not None else "",
                hum if hum is not None else "",
                diseased if diseased is not None else "",
                healthy if healthy is not None else "",
                soil if soil is not None else "",
                rssi if rssi is not None else "",
            ])



    ### EXIT APP
    def exit_app(self):
        global serial_running
        serial_running = False
        self.destroy()



if __name__ == "__main__":
    App().mainloop()
