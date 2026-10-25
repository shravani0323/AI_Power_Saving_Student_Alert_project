# ==========================================================
# AI-Based Power Saving and Student Alert System
# ==========================================================

from ultralytics import YOLO
import cv2
import time
import serial
import csv
import os
from datetime import datetime
from flask import Flask, render_template, Response
import threading
import numpy as np

# Create Flask app
app = Flask(__name__)

# Variables for dashboard
dashboard_data = {
    "students": 0,
    "status": "Occupied",
    "alarm": "OFF",
    "energy": 0,
    "cost": 0
}

# Latest processed frame
output_frame = None

@app.route("/")
def dashboard():

    return render_template(
        "dashboard.html",
        students=dashboard_data["students"],
        status=dashboard_data["status"],
        alarm=dashboard_data["alarm"],
        energy=round(dashboard_data["energy"],4),
        cost=round(dashboard_data["cost"],2)
    )
@app.route("/video")
def video():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )
   
# Connect to Arduino
try:
    arduino = serial.Serial('COM3', 9600)
    time.sleep(2)
    print("Arduino Connected")
except Exception as e:
    print("Arduino Error:", e)
    arduino = None

# Load YOLOv8 model
model = YOLO("yolov8n.pt")

# Open mobile camera
cap = cv2.VideoCapture(1)

# Check camera connection
if not cap.isOpened():
    print("Cannot open camera")
    exit()
# Create attendance log file with header
log_file = "attendance_log.csv"

if (not os.path.exists(log_file)) or os.path.getsize(log_file) == 0:
    with open(log_file, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            "Date",
            "Time",
            "Students",
            "Room Status",
            "Alarm Status"
        ])


# Initialize variables
empty_start_time = None
room_status = "Occupied"
alarm_status = "OFF"
alert_count = 0

# Energy calculation variables
total_empty_seconds = 0
energy_saved = 0
cost_saved = 0

# Prevent duplicate log entries
last_status = ""

# Store previous frame time (used for FPS calculation)
previous_time = time.time()
# ==========================================================
# Start the main program loop
# ==========================================================
def generate_frames():

    global output_frame

    while True:

        if output_frame is None:
            continue

        ret, buffer = cv2.imencode('.jpg', output_frame)

        if not ret:
            continue

        frame = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame +
            b'\r\n'
        )

# Start Flask server
threading.Thread(
    target=lambda: app.run(host="0.0.0.0", port=5000),
    daemon=True
).start()

while True:

    # Read a frame from the camera
    ret, frame = cap.read()

    if not ret:
        break
    # Create Sidebar
    sidebar = np.zeros((frame.shape[0], 350, 3), dtype=np.uint8)

    # Calculate FPS
    current_time = time.time()
    fps = 1 / (current_time - previous_time)
    previous_time = current_time

    # Run YOLO detection
    results = model(frame, conf=0.70, verbose=False)

    # Initialize student count
    student_count = 0

    # Process all detected objects
    for result in results:

        for box in result.boxes:

            # Get detected object class
            cls = int(box.cls[0])

            # Ignore everything except person
            if cls != 0:
                continue

            # Confidence score
            confidence = float(box.conf[0])

            # Ignore weak detections
            if confidence < 0.70:
                continue

            # Bounding box coordinates
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            width = x2 - x1
            height = y2 - y1

            # Ignore tiny detections
            if width < 80 or height < 120:
                continue

            student_count += 1

            # Draw green box around detected student
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            # Display confidence score
            cv2.putText(
                frame,
                f"Student {confidence:.2f}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )
    # Check classroom occupancy
    if student_count == 0:
        room_status = "Empty"

        # Start timer when room becomes empty
        if empty_start_time is None:
            empty_start_time = time.time()

        # Calculate elapsed time
        elapsed = int(time.time() - empty_start_time)
        remaining = max(0, 30 - elapsed)

        # Show countdown timer
        cv2.putText(
            frame,
            f"Empty Timer : {remaining}s",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )
    
    if student_count == 0:
        room_status = "Empty"

        # Start timer when room becomes empty
        if empty_start_time is None:
            empty_start_time = time.time()

        # Calculate elapsed time
        elapsed = int(time.time() - empty_start_time)
        remaining = max(0, 30 - elapsed)

        # Show countdown timer
        cv2.putText(
            frame,
        
            f"Empty Timer : {remaining}s",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )

        if elapsed >= 30:
            alarm_status = "ON"

            # Turn ON Arduino buzzer
            if arduino and arduino.is_open:
                arduino.write(b'1')

            # Count only one alert per empty event
            if last_status != "ALARM":
                alert_count += 1

                with open(log_file, "a", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow([
                        datetime.now().strftime("%d-%m-%Y"),
                        datetime.now().strftime("%H:%M:%S"),
                        student_count,
                        room_status,
                        alarm_status
                    ])

                last_status = "ALARM"

            # Calculate energy saved
            total_empty_seconds += 1
            energy_saved = (120 * total_empty_seconds) / 3600000
            cost_saved = energy_saved * 8.5

    else:
        # Reset timer when students enter
        empty_start_time = None

        room_status = "Occupied"
        alarm_status = "OFF"

        # Turn OFF Arduino buzzer
        if arduino and arduino.is_open:
            arduino.write(b'0')

        # Save log only when status changes
        if last_status != "OCCUPIED":
            with open(log_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    datetime.now().strftime("%d-%m-%Y"),
                    datetime.now().strftime("%H:%M:%S"),
                    student_count,
                    room_status,
                    alarm_status
                ])

            last_status = "OCCUPIED"
    # Project Title
    cv2.putText(sidebar, "AI-Based Power Saving", (15,40),
            cv2.FONT_HERSHEY_SIMPLEX,0.8,(255,255,0),2)

    cv2.putText(sidebar, "Student Alert System", (15,75),
            cv2.FONT_HERSHEY_SIMPLEX,0.8,(255,255,0),2)

    # Student Count
    cv2.putText(sidebar, f"Students : {student_count}", (15,130),
            cv2.FONT_HERSHEY_SIMPLEX,0.75,(0,255,0),2)

    # Timer
    cv2.putText(sidebar, f"Empty Timer : {remaining}s", (15,175),
            cv2.FONT_HERSHEY_SIMPLEX,0.75,(0,255,255),2)

    # Room Status
    cv2.putText(sidebar, f"Room Status : {room_status}", (15,220),
            cv2.FONT_HERSHEY_SIMPLEX,0.75,(255,255,255),2)

    # Alarm
    cv2.putText(sidebar, f"Alarm : {alarm_status}", (15,265),
            cv2.FONT_HERSHEY_SIMPLEX,0.75,(0,0,255),2)
    cv2.putText(sidebar, "Alert:", (15,320),
            cv2.FONT_HERSHEY_SIMPLEX,0.75,(0,255,255),2)

    if room_status == "Empty":

        cv2.putText(sidebar,
                "Classroom is empty.",
                (15,360),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0,0,255),
                2)

        cv2.putText(sidebar,
                "Please switch OFF",
                (15,395),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0,0,255),
                2)

        cv2.putText(sidebar,
                "lights and fans.",
                (15,430),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0,0,255),
                2)

    else:

        cv2.putText(sidebar,
                "Classroom Occupied.",
                (15,360),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0,255,0),
                2)

        cv2.putText(sidebar,
                "No action required.",
                (15,395),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0,255,0),
                2)
        cv2.putText(sidebar,
            "Press Q to Exit",
            (15,470),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255,255,0),
            2)
    # Draw border based on room status
    if room_status == "Occupied":
        cv2.rectangle(
            frame,
            (0, 0),
            (frame.shape[1]-1, frame.shape[0]-1),
            (0, 255, 0),
            5
        )
    else:
        cv2.rectangle(
            frame,
            (0, 0),
            (frame.shape[1]-1, frame.shape[0]-1),
            (0, 0, 255),
            5
        )
    
    # Save current frame for website
    dashboard_data["students"] = student_count
    dashboard_data["status"] = room_status
    dashboard_data["alarm"] = alarm_status
    dashboard_data["energy"] = energy_saved
    dashboard_data["cost"] = cost_saved
    output_frame = frame.copy()

    combined = np.hstack((sidebar, frame))
    #show dashboard on window
    cv2.imshow("Smart Classroom Dashboard", combined)

    # Exit when Q is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release camera
cap.release()

# Close Arduino connection
if arduino and arduino.is_open:
    arduino.close()

# Close all OpenCV windows
cv2.destroyAllWindows()

# Project ended successfully
print("Project Closed Successfully!")


