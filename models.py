from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import resources, costs, recommendations, actions, simulate

app = FastAPI(
    title="Cloud Cost Optimizer & Remediation Engine",
    description="API-first engine for detecting cloud waste and remediating it.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(resources.router)
app.include_router(costs.router)
app.include_router(recommendations.router)
app.include_router(actions.router)
app.include_router(simulate.router)
