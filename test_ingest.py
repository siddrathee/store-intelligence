import json
import requests
import time
import os

# Configuration
API_URL = "http://127.0.0.1:8000/events/ingest"
# Update this path if your sample_events.jsonl is stored somewhere else
JSONL_FILE_PATH = "sample_events.jsonl" 
BATCH_SIZE = 50

def run_ingestion_simulation():
    if not os.path.exists(JSONL_FILE_PATH):
        print(f"❌ Error: Could not find {JSONL_FILE_PATH}. Make sure it is in the same folder.")
        return

    print(f"🚀 Starting Data Ingestion from {JSONL_FILE_PATH}...")
    
    events_batch = []
    total_sent = 0

    # Read the file line by line
    with open(JSONL_FILE_PATH, 'r') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
                
            try:
                # Parse the JSON string into a Python dictionary
                event_data = json.loads(line)
                events_batch.append(event_data)
                
                # When we hit the batch limit, send it to the API
                if len(events_batch) >= BATCH_SIZE:
                    send_batch(events_batch)
                    total_sent += len(events_batch)
                    events_batch.clear()
                    time.sleep(0.1) # Small delay to simulate network travel
                    
            except json.JSONDecodeError:
                print("⚠️ Skipping invalid JSON line.")

    # Send any remaining events in the final batch
    if events_batch:
        send_batch(events_batch)
        total_sent += len(events_batch)

    print(f"\n✅ Simulation Complete! Successfully ingested {total_sent} events.")

def send_batch(batch):
    try:
        response = requests.post(API_URL, json=batch)
        if response.status_code == 201:
            print(f"✅ Batch of {len(batch)} events accepted.")
        else:
            print(f"❌ API Error {response.status_code}: {response.text}")
    except requests.exceptions.ConnectionError:
        print("🛑 Connection refused. Is your FastAPI server running?")

if __name__ == "__main__":
    run_ingestion_simulation()