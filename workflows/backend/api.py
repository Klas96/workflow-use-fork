import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from .routers import router

app = FastAPI(title='Workflow Execution Service')

# Add CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=['http://localhost:5173'],
	allow_credentials=True,
	allow_methods=['*'],
	allow_headers=['*'],
)

# Serve static files (frontend)
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ui/dist'))
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")

# Include routers
app.include_router(router)

# Optional standalone runner
if __name__ == '__main__':
	uvicorn.run('api:app', host='127.0.0.1', port=8000, log_level='info')
