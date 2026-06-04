import cv2
import numpy as np
import requests
import json
import os
import datetime as dt
import uuid
import argparse
from ultralytics import YOLO

# 1. Multi-Store Scalability (Dynamic Arguments)
parser = argparse.ArgumentParser(description="Apex Retail - Zone Detection")
parser.add_argument("--store", type=str, default="ST1008", help="Store ID (e.g., ST1008 or ST1076)")
parser.add_argument("--video", type=str, default="data/store_1/cam1_zone.mp4", help="Path to zone camera video")
args = parser.parse_args()

# Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIX_PATH = os.path.join(BASE_DIR, "homography_matrix.npy")
ZONES_CONFIG_PATH = os.path.join(BASE_DIR, "zones_config.json")
API_URL = "http://127.0.0.1:8000/events/ingest"
STORE_ID = args.store
CAMERA_ID = "CAM1"

def apply_homography(matrix, x, y):
    point = np.array([[[float(x), float(y)]]])
    transformed_point = cv2.perspectiveTransform(point, matrix)
    return transformed_point[0][0][0], transformed_point[0][0][1]

def get_active_zone(map_x, map_y, store_id, zones_config):
    if store_id not in zones_config:
        return {"zone_id": "TRANSIT_01", "zone_name": "Main Walkway", "zone_type": "TRANSIT", "is_revenue_zone": "No"}
        
    store_zones = zones_config.get(store_id, {})
    for zone_id, zone_data in store_zones.items():
        poly_pts = np.array(zone_data["polygon"], np.int32).reshape((-1, 1, 2))
        if cv2.pointPolygonTest(poly_pts, (map_x, map_y), False) >= 0:
            return {
                "zone_id": zone_id,
                "zone_name": zone_data["zone_name"],
                "zone_type": zone_data["zone_type"],
                "is_revenue_zone": zone_data["is_revenue_zone"]
            }
    return {"zone_id": "TRANSIT_01", "zone_name": "Main Walkway", "zone_type": "TRANSIT", "is_revenue_zone": "No"}

def create_api_payload(event_type, track_id, zone_data, confidence, dwell_ms=0, queue_depth=None, is_staff=False):
    """Generates the strict UUID-based schema expected by the FastAPI backend."""
    payload = {
        "event_id": str(uuid.uuid4()),  # Changed from id_token
        "store_id": STORE_ID,           # Changed from store_code
        "camera_id": CAMERA_ID,
        "visitor_id": f"V_{int(track_id)}",
        "event_type": event_type,       # (Make sure you pass uppercase strings to this!)
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"), # Changed from event_timestamp
        "zone_id": str(zone_data["zone_id"]),
        "dwell_ms": int(dwell_ms),
        "is_staff": is_staff,  
        "confidence": float(round(confidence, 2)),
        "metadata": {},
        "sku_zone": None,
        "session_seq": 1
    }
    
    if queue_depth is not None:
        payload["metadata"]["queue_depth"] = queue_depth
        
    return payload

def is_staff_member(frame, x1, y1, x2, y2):
    """Detects if a tracked person is a staff member based on uniform color (HSV)."""
    try:
        crop = frame[int(y1):int(y2), int(x1):int(x2)]
        if crop.size == 0: return False

        hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lower_purple = np.array([125, 50, 50])
        upper_purple = np.array([150, 255, 255])
        mask = cv2.inRange(hsv_crop, lower_purple, upper_purple)

        matching_pixels = cv2.countNonZero(mask)
        total_pixels = crop.shape[0] * crop.shape[1]
        
        if total_pixels == 0: return False
        if (matching_pixels / total_pixels) * 100 > 5.0: return True
        return False
    except Exception:
        return False

def main():
    video_path = args.video
    if not os.path.exists(video_path):
        video_path = os.path.join(BASE_DIR, args.video)

    print(f"🚀 Initializing Engine | Store: {STORE_ID} | Video: {video_path}")
    
    model = YOLO("yolov8n.pt") 
    
    with open(ZONES_CONFIG_PATH, "r") as f:
        zones_config = json.load(f)
    
    matrix = np.load(MATRIX_PATH)
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"❌ CRITICAL ERROR: Could not open video at {video_path}")
        return

    track_states = {} 
    event_batch = []
    frame_count = 0
    fps = 15.0
    current_queue_display = 0
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success: break
            
        frame_count += 1
        simulated_time_sec = frame_count / fps 
            
        results = model.track(frame, persist=True, classes=[0], verbose=False)
        
        # CORRECTED: Safely tucked inside the None check
        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy()
            confidences = results[0].boxes.conf.cpu().numpy()
            
            for box, track_id, conf in zip(boxes, track_ids, confidences):
                x1, y1, x2, y2 = box
                map_x, map_y = apply_homography(matrix, (x1 + x2) / 2, y2)
                current_zone = get_active_zone(map_x, map_y, STORE_ID, zones_config)
                z_id = current_zone["zone_id"]
                
                # Check for staff uniform
                staff_flag = is_staff_member(frame, x1, y1, x2, y2)
                
                # --- STATE MACHINE LOGIC ---
                if track_id not in track_states:
                    track_states[track_id] = {
                        "zone_id": z_id, 
                        "zone_entry_time": simulated_time_sec,
                        "last_dwell_emit": simulated_time_sec, 
                        "zone_data": current_zone,
                        "is_staff": staff_flag
                    }
                    if current_zone["zone_type"] != "TRANSIT":
                        # CHANGED TO LOWERCASE
                        event_batch.append(create_api_payload("zone_entered", track_id, current_zone, conf, is_staff=staff_flag))
                else:
                    state = track_states[track_id]
                    
                    # If we missed the uniform at first, but see it now, update their state
                    if not state["is_staff"] and staff_flag:
                        state["is_staff"] = True
                        
                    if state["zone_id"] != z_id:
                        dwell_ms = int((simulated_time_sec - state["zone_entry_time"]) * 1000)
                        
                        if state["zone_data"]["zone_type"] != "TRANSIT":
                            # CHANGED TO LOWERCASE & ADDED STAFF FLAG
                            event_batch.append(create_api_payload("zone_exited", track_id, state["zone_data"], conf, dwell_ms=dwell_ms, is_staff=state["is_staff"]))
                        if current_zone["zone_type"] != "TRANSIT":
                            event_batch.append(create_api_payload("zone_entered", track_id, current_zone, conf, is_staff=state["is_staff"]))
                        
                        track_states[track_id].update({
                            "zone_id": z_id, 
                            "zone_entry_time": simulated_time_sec,
                            "last_dwell_emit": simulated_time_sec, 
                            "zone_data": current_zone
                        })
                    elif current_zone["zone_type"] != "TRANSIT" and (simulated_time_sec - state["last_dwell_emit"]) >= 30.0:
                        dwell_ms = int((simulated_time_sec - state["zone_entry_time"]) * 1000)
                        # CHANGED TO LOWERCASE
                        event_batch.append(create_api_payload("zone_dwell", track_id, current_zone, conf, dwell_ms=dwell_ms, is_staff=state["is_staff"]))
                        state["last_dwell_emit"] = simulated_time_sec

                p_state = track_states[track_id]
                dwell_sec = int(simulated_time_sec - p_state["zone_entry_time"])
                
                # Visual Indicator for Staff
                role_label = "STAFF" if p_state["is_staff"] else "ID"
                box_color = (0, 165, 255) if p_state["is_staff"] else (0, 255, 0) # Orange for staff
                
                label = f"{role_label}: {int(track_id)} | {current_zone['zone_name']} | {dwell_sec}s"
                cv2.putText(frame, label, (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), box_color, 2)
        
        if frame_count % 15 == 0:
            current_queue = 0
            for t_id, state in track_states.items():
                if state["zone_data"]["zone_type"] == "BILLING":
                    current_queue += 1
            current_queue_display = current_queue

        cv2.putText(frame, f"LIVE QUEUE: {current_queue_display} Shoppers", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

        cv2.imshow("Apex Retail - Intelligence", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

        if len(event_batch) >= 10:
            try:
                response = requests.post(API_URL, json=event_batch, timeout=2)
                if response.status_code == 201:
                    pass # Silenced for clean terminal output
                else:
                    print(f"❌ API Error {response.status_code}: {response.text}")
            except Exception:
                pass
            event_batch.clear()

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()