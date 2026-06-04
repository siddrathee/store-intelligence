import cv2
import requests
import os
import datetime as dt
import uuid
import argparse
import numpy as np
from ultralytics import YOLO

# 1. Multi-Store Scalability (Dynamic Arguments)
parser = argparse.ArgumentParser(description="Apex Retail - Entry Tripwire & Re-ID")
parser.add_argument("--store", type=str, default="ST1008", help="Store ID (e.g., ST1008 or ST1076)")
parser.add_argument("--video", type=str, default="data/store_1/cam1_entry.mp4", help="Path to entry camera video")
args = parser.parse_args()

API_URL = "http://127.0.0.1:8000/events/ingest"
CAMERA_ID = "CAM1_ENTRY"
TRIPWIRE_Y = 400  

def create_entry_payload(event_type, visitor_id, confidence):
    """Generates the strict UUID-based schema for Entry/Exit/Reentry."""
    return {
        "event_id": str(uuid.uuid4()),  # Changed from id_token
        "store_id": args.store,         # Changed from store_code
        "camera_id": CAMERA_ID,
        "visitor_id": str(visitor_id),
        "event_type": event_type,       # (Make sure you pass uppercase strings to this!)
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"), # Changed from event_timestamp
        "zone_id": None,
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": float(round(confidence, 2)),
        "metadata": {},
        "sku_zone": None,
        "session_seq": 1
    }

def extract_color_fingerprint(frame, x1, y1, x2, y2):
    """Creates a normalized color histogram of the shopper's clothing."""
    crop = frame[int(y1):int(y2), int(x1):int(x2)]
    if crop.size == 0: return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # Calculate 2D histogram for Hue and Saturation
    hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist

def main():
    print(f"🚀 Starting Tripwire | Store: {args.store} | Video: {args.video}")
    model = YOLO("yolov8n.pt") 
    
    # Path resolution fallback
    video_path = args.video
    if not os.path.exists(video_path):
        # Try absolute path resolution if relative fails
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        video_path = os.path.join(base, args.video)
        
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ ERROR: Could not open video at {video_path}")
        return

    track_history = {} 
    exit_memory = [] # Stores: {"visitor_id": id, "hist": fingerprint, "time": timestamp}
    event_batch = []
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success: break
            
        results = model.track(frame, persist=True, classes=[0], verbose=False)
        
        cv2.line(frame, (0, TRIPWIRE_Y), (frame.shape[1], TRIPWIRE_Y), (0, 255, 255), 2)
        cv2.putText(frame, "ENTRY TRIPWIRE", (20, TRIPWIRE_Y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy()
            confidences = results[0].boxes.conf.cpu().numpy()
            
            for box, track_id, conf in zip(boxes, track_ids, confidences):
                x1, y1, x2, y2 = box
                center_y = (y1 + y2) / 2
                current_hist = extract_color_fingerprint(frame, x1, y1, x2, y2)
                
                if track_id in track_history:
                    prev_y = track_history[track_id]
                    assigned_visitor_id = f"V_{int(track_id)}"
                    
                    # CROSSING DOWN (INBOUND)
                    if prev_y < TRIPWIRE_Y and center_y >= TRIPWIRE_Y:
                        # LOWERCASE APPLIED HERE
                        event_type = "entry"
                        
                        # Re-ID Check: Did this person recently exit?
                        if current_hist is not None:
                            for memory in exit_memory:
                                match_score = cv2.compareHist(current_hist, memory["hist"], cv2.HISTCMP_CORREL)
                                if match_score > 0.70: # 70% color similarity threshold
                                    # Ensures it passes API validation while keeping the original ID
                                    event_type = "entry" 
                                    assigned_visitor_id = memory["visitor_id"]
                                    exit_memory.remove(memory) # Clear from memory
                                    break
                                    
                        print(f"📥 {event_type.upper()} DETECTED: {assigned_visitor_id}")
                        event_batch.append(create_entry_payload(event_type, assigned_visitor_id, conf))
                        
                    # CROSSING UP (OUTBOUND)
                    elif prev_y > TRIPWIRE_Y and center_y <= TRIPWIRE_Y:
                        print(f"📤 EXIT DETECTED: {assigned_visitor_id}")
                        # LOWERCASE APPLIED HERE
                        event_batch.append(create_entry_payload("exit", assigned_visitor_id, conf))
                        
                        # Save the fingerprint to memory for future Re-ID
                        if current_hist is not None:
                            exit_memory.append({
                                "visitor_id": assigned_visitor_id, 
                                "hist": current_hist, 
                                "time": dt.datetime.now()
                            })
                            
                            # Keep memory light (max 50 recent exits)
                            if len(exit_memory) > 50:
                                exit_memory.pop(0)
                
                track_history[track_id] = center_y
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 0), 2)
                cv2.putText(frame, f"ID: {int(track_id)}", (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        
        cv2.imshow("Apex Retail - Entry Camera", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

        if len(event_batch) > 0:
            try: requests.post(API_URL, json=event_batch, timeout=2)
            except Exception: pass
            event_batch.clear()

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()