import serial
import matplotlib.pyplot as plt
import numpy as np
from collections import deque
import serial.tools.list_ports
import time

# ---------------- AUTO PORT ----------------
ports = serial.tools.list_ports.comports()
if len(ports) == 0:
    print("No COM port found")
    exit()

port = ports[0].device
print("Using:", port)

time.sleep(2)
ser = serial.Serial(port, 115200, timeout=1)

plt.style.use('dark_background')
plt.ion()

fig = plt.figure(figsize=(10,5))

ax_radar = fig.add_subplot(121, polar=True)
ax_graph = fig.add_subplot(122)

# ---------------- DATA ----------------
data = deque([-60]*64)
prev = -60

ROWS = 40
COLS = 60
spec_buffer = np.zeros((ROWS, COLS))

angle = 0
rotation_speed = 0.06

value = -60

plt.show(block=False)

while True:
    try:
        # ---------------- SERIAL ----------------
        if ser.in_waiting:
            line = ser.readline().decode(errors='ignore').strip()
            if "RSSI" in line:
                try:
                    value = int(line.split(":")[1])
                except:
                    pass

        # ---------------- SIGNAL ----------------
        delta = value - prev
        prev = value

        # keep signal alive (avoid flat line)
        if abs(delta) < 1:
            delta += np.random.uniform(-0.5, 0.5)

        data.append(delta)
        data.popleft()

        arr = np.array(data)

        # ---------------- FFT ----------------
        fft = np.fft.fft(arr)
        mag = np.abs(fft[:len(fft)//2])
        mag = mag / (np.max(mag) + 1e-6)

        # resize to fit spectrogram height
        mag_resized = np.interp(
            np.linspace(0, len(mag)-1, ROWS),
            np.arange(len(mag)),
            mag
        )

        # scroll buffer
        spec_buffer = np.roll(spec_buffer, -1, axis=1)
        spec_buffer[:, -1] = mag_resized

        energy = np.mean(mag)

        # ---------------- RADAR ----------------
        ax_radar.clear()

        ax_radar.set_xticks([])
        ax_radar.set_yticks([])
        ax_radar.set_theta_zero_location('N')
        ax_radar.set_theta_direction(-1)
        ax_radar.set_ylim(0, 1)

        theta = np.linspace(0, 2*np.pi, 400)
        ax_radar.fill(theta, np.ones_like(theta), color='#020202')

        if energy < 0.2:
            base_color = 'cyan'
            title = "No Movement"
        elif energy < 0.5:
            base_color = 'orange'
            title = "Movement ⚠️"
        else:
            base_color = 'red'
            title = "High Movement 🚨"

        for alpha in [0.05, 0.1, 0.2]:
            ax_radar.fill(theta, np.ones_like(theta), color=base_color, alpha=alpha)

        for r in [0.4, 0.7]:
            ax_radar.plot(theta, [r]*len(theta), linewidth=1)

        ax_radar.plot([0,0],[0,1])
        ax_radar.plot([np.pi,np.pi],[0,1])
        ax_radar.plot([np.pi/2,np.pi/2],[0,1])
        ax_radar.plot([3*np.pi/2,3*np.pi/2],[0,1])

        sweep_theta = np.linspace(angle, angle+0.3, 200)
        ax_radar.fill_between(sweep_theta, 0, 1, color=base_color, alpha=0.4)

        ax_radar.set_title(title)

        # ---------------- CLEAN SPECTRUM GRAPH ----------------
        ax_graph.clear()

        # 🔥 reduce height (clean band)
        display_spec = spec_buffer[8:22, :]

        # 🔥 improve contrast
        display_spec = np.clip(display_spec, 0, 1)
        display_spec = np.power(display_spec, 0.5)

        im = ax_graph.imshow(
            display_spec,
            aspect='auto',
            cmap='plasma',
            origin='lower',
            interpolation='bilinear'
        )

        ax_graph.set_title("Real-Time Motion Spectrum", fontsize=10)
        ax_graph.set_xlabel("Time →", fontsize=8)
        ax_graph.set_ylabel("Freq Band", fontsize=8)

        ax_graph.set_xticks([])
        ax_graph.set_yticks([])

        # colorbar (only once)
        if not hasattr(ax_graph, "cbar"):
            ax_graph.cbar = plt.colorbar(im, ax=ax_graph, fraction=0.03, pad=0.02)
        else:
            ax_graph.cbar.update_normal(im)

        # ---------------- UPDATE ----------------
        angle += rotation_speed

        plt.pause(0.03)

    except KeyboardInterrupt:
        break

    except Exception as e:
        print("Error:", e)