# 🛒 Apex Retail - Store Intelligence Platform

A complete, containerized computer vision and API pipeline for real-time offline retail analytics. This system processes raw CCTV footage, tracks shopper behavior, filters out staff, and serves real-time actionable metrics through a polymorphic FastAPI backend.

---

## 🚀 1. Quick Start (Acceptance Gate)

The Intelligence API and Database are fully containerized. No local dependencies are required beyond Docker. 

To launch the backend, run the following commands from the root directory:

```bash
# 1. Start the containerized API and Database
docker compose up --build