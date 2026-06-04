# PROMPT: "Write a pytest suite for a FastAPI retail intelligence application. Ensure it tests the /health endpoint, the /events/ingest endpoint with idempotency, and metric endpoints handling edge cases like empty stores with zero purchases. Use TestClient and reach >70% statement coverage."
# AI MODIFICATIONS: The AI suggested using standard assert statements with FastAPI's TestClient. I manually added the specific JSON payload structure to ensure it matches our strict UUID-based schema.

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine
import uuid

# Initialize the test client
client = TestClient(app)

# Ensure the database tables are created for tests
Base.metadata.create_all(bind=engine)

def test_health_check():
    """Test 1: Ensures the health endpoint is active and returns correct schema."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "service" in data

def test_ingest_events_and_idempotency():
    """Test 2: Ensures the API accepts events and safely ignores duplicates (Idempotency)."""
    event_id = str(uuid.uuid4())
    payload = [{
        "event_id": event_id,           # Changed from id_token
        "store_id": "TEST_STORE",       # Changed from store_code
        "camera_id": "TEST_CAM",
        "visitor_id": "V_999",
        "event_type": "ENTRY",          # Changed from "entry" (MUST BE UPPERCASE)
        "timestamp": "2026-06-04T12:00:00Z", # Changed from event_timestamp
        "zone_id": None,            
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.95,
        "metadata": {},             
        "sku_zone": None,           
        "session_seq": 1
    }]
    
    # First ingestion should succeed
    response1 = client.post("/events/ingest", json=payload)
    
    assert response1.status_code == 201, f"Failed: {response1.json()}"
    
    # Second ingestion of the same exact payload should be safely processed
    response2 = client.post("/events/ingest", json=payload)
    assert response2.status_code == 201

def test_empty_store_edge_case():
    """Test 3: Evaluates math safety when requesting metrics for a store with 0 traffic."""
    response = client.get("/stores/GHOST_STORE/metrics")
    assert response.status_code == 200
    data = response.json()
    
    # Should safely return 0s instead of throwing divide-by-zero Internal Server Errors
    assert data["total_entry_footfall"] == 0
    assert data["total_completed_purchases"] == 0
    assert data["conversion_rate_percentage"] == "0.0%"

def test_funnel_initialization():
    """Test 4: Verifies the funnel endpoint structure."""
    response = client.get("/stores/TEST_STORE/funnel")
    assert response.status_code == 200
    assert "funnel_stages" in response.json()