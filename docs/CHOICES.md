# Technical Rationale & Architecture Choices

This document outlines the core technical decisions made regarding model selection, schema design, and API resilience, fulfilling the requirements for Part D of the evaluation rubric.

## 1. Detection Model Selection: YOLOv8 Nano
* **Options Considered:** YOLOv8 (Ultralytics), YOLOv9, RT-DETR, and MediaPipe.
* **AI Suggestion:** The AI suggested utilizing YOLOv8 due to its extensive documentation, ease of deployment without complex PyTorch tensor setups, and built-in ByteTrack integration for maintaining object identity across frames. 
* **Final Choice & Rationale:** I chose **YOLOv8 Nano (yolov8n.pt)**. In a production retail environment processing multiple 1080p, 15fps CCTV feeds, computational speed on edge devices is prioritized over absolute bounding-box perfection. YOLOv8n is lightweight enough to run highly efficiently on standard CPUs. When paired with OpenCV HSV color-histogram extraction for Re-ID and staff uniform detection, the pipeline achieves robust tracking without requiring expensive, dedicated GPU hardware in every physical retail location.

## 2. Event Schema Design: Flattened Time-Series
* **Options Considered:** A heavily normalized relational database (separate tables for Visitors, Sessions, Zones, and Events) versus a flattened, polymorphic time-series table.
* **AI Suggestion:** The AI recommended a purely NoSQL approach (like MongoDB) to handle the varying payload structures of different event types (e.g., a `BILLING_QUEUE_JOIN` has a `queue_depth` parameter, while an `ENTRY` event does not).
* **Final Choice & Rationale:** I compromised between the two. I utilized **SQLite** for container portability but designed a **Flattened Polymorphic Schema**. All events are written to a single `events` table with an `event_type` discriminator. This flattens the data structure, natively aligning with the strict JSON payload schema required by the grading script. Crucially, a flat schema allows for rapid, sequential time-series querying (which is necessary for building conversion funnels) without requiring expensive SQL `JOIN` operations across millions of rows.

## 3. API Architecture Choice: Graceful DB Degradation
* **Options Considered:** Utilizing PostgreSQL for heavy concurrent writes vs. SQLite for zero-dependency container deployment.
* **AI Suggestion:** The AI strongly recommended PostgreSQL to handle the simultaneous database reads from the live dashboard and heavy batch writes from the computer vision ingestion endpoints.
* **Final Choice & Rationale:** I chose **SQLite** to ensure the project passes the "docker compose up" acceptance gate seamlessly, but I engineered around its limitations. SQLite is notorious for locking the database file during write operations. To prevent the API from throwing raw stack traces when the dashboard attempts to read locked data, I implemented a global exception handler in FastAPI. If a `sqlalchemy.exc.OperationalError` occurs, the API gracefully degrades, returning a structured `503 Service Unavailable` JSON payload. This fulfills the production-readiness constraint, ensuring the system fails safely and remains informative to monitoring tools.