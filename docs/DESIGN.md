# System Architecture Design

## 1. High-Level Overview
The Apex Retail Intelligence Platform is engineered to bridge the data gap between online analytics and offline physical stores. The architecture is decoupled into two primary layers to ensure scalability and fault tolerance:

* **The Edge Vision Layer:** A suite of Python scripts utilizing OpenCV and Ultralytics YOLOv8. This layer operates locally at the store level (simulated via terminal execution). It ingests raw MP4 frames, applies homography matrices to map pixels to physical floor zones, extracts HSV color histograms for staff uniform filtering and Re-ID, and translates raw physical movement into structured semantic JSON payloads.
* **The Intelligence API:** A centralized FastAPI microservice backed by a SQLite database. It serves as the ingestion engine, handling batch processing, `event_id` idempotency checks, and polymorphic schema validation. It computes high-level business intelligence metrics (conversion funnels, heatmap densities, and queue anomalies) on demand.

## 2. AI-Assisted Decisions
Throughout the development of this architecture, large language models (LLMs) were utilized as pair-programming assistants to rapidly prototype, debug, and validate design patterns. Below are three specific instances where AI significantly shaped the system design:

**A. Polymorphic Event Schema vs. Strict Payload Schemas**
* **The Situation:** Initial designs included highly specific, separate Pydantic models for `EntryEvent`, `ZoneEvent`, and `QueueEvent`. 
* **The AI Suggestion:** The AI pointed out that the automated grading script would strictly enforce a single, flat schema structure requiring specific keys (`event_id`, `store_id`, `timestamp`, and uppercase event types like `ENTRY`). 
* **The Decision:** The AI's suggestion was accepted, and the initial modular design was overridden. The API was refactored to utilize a single, flattened `EventPayload` model. This guaranteed compliance with the evaluation harness while allowing the database layer to remain flexible enough to handle disparate event types securely.

**B. Live Dashboard Implementation (Part E)**
* **The Situation:** A live dashboard was required to visualize the data stream. The initial approach was to scaffold a separate React.js application.
* **The AI Suggestion:** The AI advised against a decoupled frontend, suggesting that it would overly complicate the `docker-compose.yml` requirements and risk failing the single-command "Acceptance Gate." It suggested serving a raw HTML/JS template directly via FastAPI's `HTMLResponse`.
* **The Decision:** The AI's suggestion was implemented. By utilizing embedded Tailwind CSS and Chart.js within a single endpoint, the dashboard achieves real-time polling without requiring node modules, build steps, or risking cross-origin resource sharing (CORS) failures inside the container.

**C. Staff Filtering Logic Placement**
* **The Situation:** Staff needed to be excluded from customer metrics to prevent skewed conversion rates. 
* **The AI Suggestion:** The AI initially recommended filtering out staff events *at the database ingestion level*, meaning staff data would be permanently dropped and never saved to SQLite.
* **The Decision:** This AI suggestion was overridden. The decision was made to save staff tracking data with a boolean flag (`is_staff: True`) and implement the filtering during the API aggregation layer (`EventRecord.is_staff == False`). Retaining staff movement data is crucial for future operational analytics, such as analyzing employee-to-customer ratios or staff zone-coverage efficiency.