# 🛒 Apex Retail - Store Intelligence Platform

A production-ready, containerized computer vision and API pipeline for real-time offline retail analytics. This system processes raw CCTV footage, tracks shopper behavior, filters out staff via uniform detection, and serves real-time actionable metrics through a polymorphic FastAPI backend.

---

## 🚀 1. Quick Start (Acceptance Gate)

The Intelligence API and Database are fully containerized. No local dependencies are required beyond Docker. 

To launch the backend, the following command must be executed from the root directory:

```bash
docker compose up --build
The API will immediately be available at: http://localhost:8000

📹 2. Running the Detection Pipeline
The edge vision layer processes the video clips, handles bounding-box tracking and Re-ID, and emits structured JSON payloads directly to the API ingestion endpoint. With the Docker container running, new terminal windows must be opened to execute the vision scripts.

To track Entry/Exit Footfall (Camera 1):

Bash
# Store 1 (Main Test)
python pipeline/entry_detect.py --store ST1008 --video data/store_1/cam1_entry.mp4

# Store 2 (Scale Test)
python pipeline/entry_detect.py --store ST1076 --video data/store_2/cam1.mp4
To track Interior Zones & Queues (Camera 2):

Bash
# Store 1 (Main Test)
python pipeline/detect.py --store ST1008 --video data/store_1/cam1_zone.mp4

# Store 2 (Scale Test)
python pipeline/detect.py --store ST1076 --video data/store_2/cam1_zone.mp4
📊 3. Live UI Dashboard (Part E Bonus)
This system includes a real-time, responsive tracking dashboard to visualize the conversion funnel, queue anomalies, and footfall metrics as the CV scripts process frames.

Access the Live Dashboard: http://localhost:8000/dashboard

💡 REVIEWER NOTE - MULTI-STORE SCALING:
The dashboard includes a live configuration target selector in the top right corner. By clicking the text "ST1008" and changing it to "ST1076", the API polling will instantly switch to view horizontal scaling data across different retail locations in real-time.

🧪 4. Testing & Edge Cases
The project includes a comprehensive pytest suite ensuring idempotency, schema compliance, and zero-traffic math safety. Tests can be run locally via:

Bash
python -m pytest tests/

🤖 5. Architecture & Documentation
The following Markdown documents in the repository contain detailed architectural rationale:

DESIGN.md: System architecture overview and AI-Assisted Decisions.

CHOICES.md: Technical rationale for models, schemas, and API constraints.