from fastapi import FastAPI, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
import sqlalchemy.exc
import datetime as dt
import time
import uuid
import logging

from app.database import SessionLocal, EventRecord

app = FastAPI(
    title="Apex Retail - Store Intelligence API",
    description="Multi-camera, strict PDF-compliant event ingestion engine",
    version="2.0.0"
)

# Configure terminal logger
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("apex_logger")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    trace_id = str(uuid.uuid4())[:8]
    store_id = "N/A"
    if "stores/" in request.url.path:
        parts = request.url.path.split("/")
        try:
            store_idx = parts.index("stores")
            store_id = parts[store_idx + 1]
        except ValueError:
            pass
            
    response = await call_next(request)
    latency_ms = round((time.time() - start_time) * 1000, 2)
    logger.info(f"📊 [TRACE: {trace_id}] | Store: {store_id} | {request.method} {request.url.path} | Status: {response.status_code} | Latency: {latency_ms}ms")
    return response

@app.exception_handler(sqlalchemy.exc.OperationalError)
async def database_unavailable_handler(request: Request, exc: sqlalchemy.exc.OperationalError):
    """Graceful degradation: Catches DB locks/crashes and returns a clean 503."""
    return JSONResponse(
        status_code=503,
        content={
            "error": "Service Unavailable",
            "detail": "The store intelligence database is currently unreachable or locked.",
            "action": "Please retry the request in a few moments."
        }
    )

# ---------------------------------------------------------
# 1. STRICT API SCHEMA (PDF COMPLIANT)
# ---------------------------------------------------------
class EventPayload(BaseModel):
    event_id: str
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str  # e.g., ENTRY, ZONE_ENTER
    timestamp: str
    zone_id: Optional[str] = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float
    metadata: Optional[Dict[str, Any]] = {}
    sku_zone: Optional[str] = None
    session_seq: int = 1

# ---------------------------------------------------------
# 2. DATABASE DEPENDENCY
# ---------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------
# 3. ENDPOINTS
# ---------------------------------------------------------
@app.get("/health")
def read_health(db: Session = Depends(get_db)):
    latest_event = db.query(EventRecord).order_by(EventRecord.id.desc()).first()
    health_status = "healthy"
    warnings = []
    last_timestamp = None

    if latest_event and latest_event.timestamp:
        last_timestamp = latest_event.timestamp
        try:
            last_ts = dt.datetime.fromisoformat(last_timestamp.replace("Z", "+00:00"))
            now = dt.datetime.now(dt.timezone.utc)
            if (now - last_ts).total_seconds() > 600:
                health_status = "degraded"
                warnings.append("STALE_FEED: No events received in > 10 minutes.")
        except Exception:
            pass

    return {
        "status": health_status, 
        "service": "Store Intelligence API",
        "last_event_timestamp": last_timestamp,
        "warnings": warnings
    }

@app.post("/events/ingest", status_code=status.HTTP_201_CREATED)
def ingest_events(payloads: List[EventPayload], db: Session = Depends(get_db)):
    if len(payloads) > 500:
        raise HTTPException(status_code=400, detail="Batch size exceeds maximum limit of 500.")
    
    accepted_count = 0
    
    for event in payloads:
        # Idempotency mapping
        existing = db.query(EventRecord).filter(EventRecord.id_token == event.event_id).first()
        if existing:
            continue
            
        # Safely map string token to numeric track_id fallback
        extracted_track = ''.join(filter(str.isdigit, event.visitor_id))
        track_num = int(extracted_track) if extracted_track else 0

        db_event = EventRecord(
            event_type=event.event_type,
            id_token=event.event_id,
            store_code=event.store_id,
            store_id=event.store_id,
            camera_id=event.camera_id,
            track_id=track_num,
            timestamp=event.timestamp,
            zone_id=event.zone_id,
            dwell_ms=event.dwell_ms,
            is_staff=event.is_staff
        )
        db.add(db_event)
        accepted_count += 1

    db.commit()
    return {"success": True, "events_processed": accepted_count}

@app.get("/stores/{store_id}/metrics")
def get_store_metrics(store_id: str, db: Session = Depends(get_db)):
    norm_id = store_id.lower().replace("st", "store_")
    alt_id = store_id.upper().replace("STORE_", "ST")

    # Metric extraction filters out staff seamlessly
    total_visitors = db.query(EventRecord.id_token).filter(
        EventRecord.event_type == "ENTRY",
        EventRecord.is_staff == False,
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).distinct().count()

    total_purchases = db.query(EventRecord.track_id).filter(
        EventRecord.event_type == "BILLING_QUEUE_JOIN",
        EventRecord.is_staff == False,
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).distinct().count()

    conversion_rate = 0.0
    if total_visitors > 0:
        conversion_rate = round((total_purchases / total_visitors) * 100, 2)

    queue_dwells = db.query(
        EventRecord.zone_name,
        func.avg(EventRecord.dwell_ms / 1000.0)
    ).filter(
        EventRecord.event_type == "ZONE_DWELL",
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).group_by(EventRecord.zone_name).all()

    return {
        "store_id": store_id,
        "total_entry_footfall": total_visitors,
        "total_completed_purchases": total_purchases,
        "conversion_rate_percentage": f"{conversion_rate}%",
        "queue_analytics": [
            {"zone": row[0] if row[0] else "Billing Line", "avg_wait_seconds": round(row[1], 1) if row[1] else 0.0} 
            for row in queue_dwells
        ]
    }

@app.get("/stores/{store_id}/funnel")
def get_store_funnel(store_id: str, db: Session = Depends(get_db)):
    norm_id = store_id.lower().replace("st", "store_")
    alt_id = store_id.upper().replace("STORE_", "ST")

    entries = db.query(EventRecord.id_token).filter(
        EventRecord.event_type == "ENTRY",
        EventRecord.is_staff == False,
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).distinct().count()

    zone_browsers = db.query(EventRecord.track_id).filter(
        EventRecord.event_type.in_(["ZONE_ENTER", "ZONE_DWELL"]),
        EventRecord.is_staff == False,
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).distinct().count()

    queue_joiners = db.query(EventRecord.track_id).filter(
        EventRecord.event_type == "BILLING_QUEUE_JOIN",
        EventRecord.is_staff == False,
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).distinct().count()

    purchasers = queue_joiners 

    return {
        "store_id": store_id,
        "funnel_stages": {
            "1_total_entry": entries,
            "2_zone_interactions": zone_browsers,
            "3_billing_queue_entered": queue_joiners,
            "4_completed_purchases": purchasers
        },
        "dropoff_percentages": {
            "zone_dropoff": round(((entries - zone_browsers) / entries * 100), 1) if entries > 0 else 0,
            "queue_abandonment": round(((queue_joiners - purchasers) / queue_joiners * 100), 1) if queue_joiners > 0 else 0
        }
    }

@app.get("/stores/{store_id}/heatmap")
def get_store_heatmap(store_id: str, db: Session = Depends(get_db)):
    norm_id = store_id.lower().replace("st", "store_")
    alt_id = store_id.upper().replace("STORE_", "ST")

    total_sessions = db.query(EventRecord.id_token).filter(
        EventRecord.event_type == "ENTRY",
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).distinct().count()

    zone_stats = db.query(
        EventRecord.zone_name,
        func.count(EventRecord.track_id),
        func.avg(EventRecord.dwell_ms)
    ).filter(
        EventRecord.event_type.in_(["ZONE_ENTER", "ZONE_DWELL"]),
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id)),
        EventRecord.zone_name != None
    ).group_by(EventRecord.zone_name).all()

    max_visits = max([stat[1] for stat in zone_stats]) if zone_stats else 1
    max_dwell = max([stat[2] for stat in zone_stats]) if zone_stats and zone_stats[0][2] else 1

    heatmap_data = []
    for zone, visits, dwell in zone_stats:
        dwell_val = dwell if dwell else 0
        heatmap_data.append({
            "zone_name": zone,
            "visit_intensity": round((visits / max_visits) * 100, 1),
            "dwell_intensity": round((dwell_val / max_dwell) * 100, 1)
        })

    return {
        "store_id": store_id,
        "data_confidence": "HIGH" if total_sessions >= 20 else "LOW - Under 20 Sessions",
        "heatmap": heatmap_data
    }

@app.get("/stores/{store_id}/anomalies")
def get_store_anomalies(store_id: str, db: Session = Depends(get_db)):
    norm_id = store_id.lower().replace("st", "store_")
    alt_id = store_id.upper().replace("STORE_", "ST")
    anomalies = []

    avg_queue_wait = db.query(func.avg(EventRecord.dwell_ms / 1000.0)).filter(
        EventRecord.event_type == "ZONE_DWELL",
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).scalar() or 0

    if avg_queue_wait > 60:
        anomalies.append({
            "type": "QUEUE_SPIKE",
            "severity": "CRITICAL",
            "description": f"Average billing wait time is dangerously high ({round(avg_queue_wait)}s).",
            "suggested_action": "Open additional billing counter immediately."
        })

    all_known_zones = db.query(EventRecord.zone_name).filter(
        EventRecord.zone_name != None,
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).distinct().all()

    active_zones_today = db.query(EventRecord.zone_name).filter(
        EventRecord.event_type == "ZONE_ENTER",
        ((EventRecord.store_code == norm_id) | (EventRecord.store_id == alt_id))
    ).distinct().all()

    dead_zones = set([z[0] for z in all_known_zones]) - set([z[0] for z in active_zones_today])
    
    for dz in dead_zones:
        anomalies.append({
            "type": "DEAD_ZONE",
            "severity": "WARN",
            "description": f"No foot traffic detected in '{dz}' for over 30 minutes.",
            "suggested_action": "Check camera feed for occlusion or send staff to inspect aisle."
        })

    return {
        "store_id": store_id,
        "active_anomalies": anomalies
    }
@app.get("/dashboard", response_class=HTMLResponse)
def get_live_dashboard():
    """Serves a real-time, premium single-page application metrics cockpit."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Apex Retail | Store Intelligence Cockpit</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: 'Inter', sans-serif; }
            .metric-card { transition: all 0.2s ease-in-out; }
            .metric-card:hover { transform: translateY(-2px); }
        </style>
    </head>
    <body class="bg-slate-900 text-slate-100 min-h-screen flex flex-col">

        <header class="border-b border-slate-800 bg-slate-950/50 backdrop-blur sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="bg-indigo-600 p-2 rounded-lg text-white">
                    <i class="fa-solid fa-chart-line text-xl"></i>
                </div>
                <div>
                    <h1 class="text-lg font-bold tracking-tight">APEX RETAIL</h1>
                    <p class="text-xs text-slate-400 font-medium">Store Intelligence & Vision Analytics Platform</p>
                </div>
            </div>
            
            <div class="flex items-center space-x-6">
                <div class="flex items-center space-x-2 bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800">
                    <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Target Store:</span>
                    <input type="text" id="storeSelector" value="ST1008" class="bg-transparent border-none text-indigo-400 font-bold focus:outline-none w-20 text-center">
                </div>
                
                <div class="flex items-center space-x-2 bg-emerald-950/40 border border-emerald-800 px-3 py-1.5 rounded-full">
                    <span class="relative flex h-2 w-2">
                        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                    </span>
                    <span class="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Pipeline Connected</span>
                </div>
            </div>
        </header>

        <main class="flex-1 p-6 space-y-6 max-w-[1600px] w-full mx-auto">
            
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="metric-card bg-slate-950 p-5 rounded-xl border border-slate-800 flex items-center justify-between">
                    <div class="space-y-1">
                        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Total Entry Footfall</p>
                        <h3 class="text-3xl font-bold tracking-tight" id="kpiFootfall">0</h3>
                    </div>
                    <div class="bg-blue-500/10 p-3 rounded-xl text-blue-400"><i class="fa-solid fa-users text-2xl"></i></div>
                </div>

                <div class="metric-card bg-slate-950 p-5 rounded-xl border border-slate-800 flex items-center justify-between">
                    <div class="space-y-1">
                        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Completed Purchases</p>
                        <h3 class="text-3xl font-bold tracking-tight" id="kpiPurchases">0</h3>
                    </div>
                    <div class="bg-emerald-500/10 p-3 rounded-xl text-emerald-400"><i class="fa-solid fa-bag-shopping text-2xl"></i></div>
                </div>

                <div class="metric-card bg-slate-950 p-5 rounded-xl border border-slate-800 flex items-center justify-between">
                    <div class="space-y-1">
                        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Conversion Rate</p>
                        <h3 class="text-3xl font-bold tracking-tight text-indigo-400" id="kpiConversion">0.0%</h3>
                    </div>
                    <div class="bg-indigo-500/10 p-3 rounded-xl text-indigo-400"><i class="fa-solid fa-percentage text-2xl"></i></div>
                </div>

                <div class="metric-card bg-slate-950 p-5 rounded-xl border border-slate-800 flex items-center justify-between">
                    <div class="space-y-1">
                        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Active Alerts</p>
                        <h3 class="text-3xl font-bold tracking-tight" id="kpiAnomalies">0</h3>
                    </div>
                    <div class="bg-rose-500/10 p-3 rounded-xl text-rose-400" id="anomalyBell"><i class="fa-solid fa-bell text-2xl"></i></div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="bg-slate-950 p-5 rounded-xl border border-slate-800 lg:col-span-2">
                    <div class="flex items-center justify-between mb-4">
                        <h4 class="text-sm font-semibold text-slate-200 uppercase tracking-wider"><i class="fa-solid fa-filter text-indigo-400 mr-2"></i>Conversion Funnel Stages</h4>
                        <span class="text-xs text-slate-500">Auto-refreshing stream</span>
                    </div>
                    <div class="h-[300px] flex items-center justify-center">
                        <canvas id="funnelChart"></canvas>
                    </div>
                </div>

                <div class="bg-slate-950 p-5 rounded-xl border border-slate-800">
                    <div class="flex items-center justify-between mb-4">
                        <h4 class="text-sm font-semibold text-slate-200 uppercase tracking-wider"><i class="fa-solid fa-clock text-amber-400 mr-2"></i>Queue Bottleneck Monitor</h4>
                        <span class="text-xs text-slate-500">Avg Wait Times</span>
                    </div>
                    <div class="h-[300px] flex items-center justify-center">
                        <canvas id="queueChart"></canvas>
                    </div>
                </div>
            </div>

            <div class="bg-slate-950 p-5 rounded-xl border border-slate-800">
                <div class="flex items-center justify-between mb-4">
                    <h4 class="text-sm font-semibold text-slate-200 uppercase tracking-wider"><i class="fa-solid fa-triangle-exclamation text-rose-400 mr-2"></i>Real-time Edge Anomaly Feed</h4>
                    <span class="px-2 py-0.5 text-xs font-bold rounded bg-slate-900 text-slate-400 border border-slate-800" id="anomalyCountLabel">0 Active Issues</span>
                </div>
                <div class="space-y-3" id="anomalyContainer">
                    <div class="p-4 rounded-lg bg-slate-900 border border-slate-800 text-center text-slate-500 text-sm">
                        <i class="fa-solid fa-shield-cat text-lg mb-2 block"></i> No systemic anomalies detected in the active window.
                    </div>
                </div>
            </div>
        </main>

        <script>
            let funnelChartInstance = null;
            let queueChartInstance = null;

            async function refreshTelemetry() {
                const storeId = document.getElementById('storeSelector').value.trim();
                if (!storeId) return;

                try {
                    // Parallel endpoint execution framework 
                    const [metricsRes, funnelRes, anomalyRes] = await Promise.all([
                        fetch(`/stores/${storeId}/metrics`),
                        fetch(`/stores/${storeId}/funnel`),
                        fetch(`/stores/${storeId}/anomalies`)
                    ]);

                    if (metricsRes.status === 200 && funnelRes.status === 200 && anomalyRes.status === 200) {
                        const metrics = await metricsRes.json();
                        const funnel = await funnelRes.json();
                        const anomalies = await anomalyRes.json();

                        // 1. Update Core Metric Fields Safely
                        document.getElementById('kpiFootfall').textContent = metrics.total_entry_footfall || 0;
                        document.getElementById('kpiPurchases').textContent = metrics.total_completed_purchases || 0;
                        document.getElementById('kpiConversion').textContent = metrics.conversion_rate_percentage || "0.0%";
                        
                        const activeAlertsCount = anomalies.active_anomalies ? anomalies.active_anomalies.length : 0;
                        document.getElementById('kpiAnomalies').textContent = activeAlertsCount;
                        document.getElementById('anomalyCountLabel').textContent = `${activeAlertsCount} Active Issues`;

                        if (activeAlertsCount > 0) {
                            document.getElementById('anomalyBell').className = "bg-rose-500/20 p-3 rounded-xl text-rose-400 animate-bounce";
                        } else {
                            document.getElementById('anomalyBell').className = "bg-rose-500/10 p-3 rounded-xl text-rose-500";
                        }

                        // 2. Render Conversion Funnel Graph Layout Elements Dynamically
                        const stages = funnel.funnel_stages || {};
                        const funnelData = [
                            stages["1_total_entry"] || 0,
                            stages["2_zone_interactions"] || 0,
                            stages["3_billing_queue_entered"] || 0,
                            stages["4_completed_purchases"] || 0
                        ];

                        if (funnelChartInstance) {
                            funnelChartInstance.data.datasets[0].data = funnelData;
                            funnelChartInstance.update();
                        } else {
                            const ctx = document.getElementById('funnelChart').getContext('2d');
                            funnelChartInstance = new Chart(ctx, {
                                type: 'bar',
                                data: {
                                    labels: ['Total Entries', 'Zone Browsers', 'Queue Joiners', 'Conversions'],
                                    datasets: [{
                                        label: 'Total Shoppers',
                                        data: funnelData,
                                        backgroundColor: ['rgba(59, 130, 246, 0.6)', 'rgba(168, 85, 247, 0.6)', 'rgba(245, 158, 11, 0.6)', 'rgba(16, 185, 129, 0.6)'],
                                        borderColor: ['#3b82f6', '#a855f7', '#f59e0b', '#10b981'],
                                        borderWidth: 1,
                                        borderRadius: 6
                                    }]
                                },
                                options: {
                                    responsive: true,
                                    maintainAspectRatio: false,
                                    plugins: { legend: { display: false } },
                                    scales: {
                                        y: { grid: { color: '#1e293b' }, ticks: { color: '#94a3b8' } },
                                        x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
                                    }
                                }
                            });
                        }

                        // 3. Render Bottleneck Dwell Chart Metrics
                        const queueAnalytics = metrics.queue_analytics || [];
                        const queueLabels = queueAnalytics.length ? queueAnalytics.map(q => q.zone) : ['Billing Line'];
                        const queueData = queueAnalytics.length ? queueAnalytics.map(q => q.avg_wait_seconds) : [0];

                        if (queueChartInstance) {
                            queueChartInstance.data.labels = queueLabels;
                            queueChartInstance.data.datasets[0].data = queueData;
                            queueChartInstance.update();
                        } else {
                            const ctxQ = document.getElementById('queueChart').getContext('2d');
                            queueChartInstance = new Chart(ctxQ, {
                                type: 'doughnut',
                                data: {
                                    labels: queueLabels,
                                    datasets: [{
                                        data: queueData,
                                        backgroundColor: ['rgba(249, 115, 22, 0.6)', 'rgba(239, 68, 68, 0.6)'],
                                        borderColor: ['#f97316', '#ef4444'],
                                        borderWidth: 1
                                    }]
                                },
                                options: {
                                    responsive: true,
                                    maintainAspectRatio: false,
                                    plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8' } } }
                                }
                            });
                        }

                        // 4. Update Anomaly Feed Elements Dynamically
                        const container = document.getElementById('anomalyContainer');
                        if (activeAlertsCount === 0) {
                            container.innerHTML = `
                                <div class="p-4 rounded-lg bg-slate-900 border border-slate-800 text-center text-slate-500 text-sm">
                                    <i class="fa-solid fa-shield-cat text-lg mb-2 block"></i> No systemic anomalies detected in the active window.
                                </div>`;
                        } else {
                            container.innerHTML = anomalies.active_anomalies.map(anomaly => `
                                <div class="p-4 rounded-xl bg-slate-950 border border-rose-900/50 flex items-start space-x-4 border-l-4 border-l-rose-500">
                                    <div class="bg-rose-500/10 p-2 rounded text-rose-400"><i class="fa-solid fa-circle-exclamation text-lg"></i></div>
                                    <div class="space-y-1 flex-1">
                                        <div class="flex items-center justify-between">
                                            <h5 class="text-sm font-bold text-slate-200">${anomaly.type}</h5>
                                            <span class="px-2 py-0.5 text-[10px] font-black uppercase tracking-wider rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">${anomaly.severity}</span>
                                        </div>
                                        <p class="text-xs text-slate-400">${anomaly.description}</p>
                                        <p class="text-xs text-indigo-400 font-medium pt-1"><i class="fa-solid fa-lightbulb mr-1.5"></i>Action: ${anomaly.suggested_action}</p>
                                    </div>
                                </div>
                            `).join('');
                        }
                    }
                } catch (err) {
                    console.error("Dashboard tracking sync error: ", err);
                }
            }

            // Real-time synchronization interval loop (Every 1000 milliseconds)
            setInterval(refreshTelemetry, 1000);
            window.onload = refreshTelemetry;
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)