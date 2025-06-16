import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
import time

from .routers import router

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s',
	handlers=[
		logging.StreamHandler(),  # Log to console
		logging.FileHandler('tmp/logs/api.log')  # Log to file
	]
)

logger = logging.getLogger(__name__)

app = FastAPI(title='Workflow Execution Service')

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
	start_time = time.time()
	response = await call_next(request)
	duration = time.time() - start_time
	
	logger.info(
		f"Method: {request.method} Path: {request.url.path} "
		f"Status: {response.status_code} Duration: {duration:.2f}s"
	)
	
	return response

# Add CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=[
		'http://localhost:5173',
		'http://localhost:8000',
		'http://192.168.1.17:8000',
		'http://192.168.1.17:8002',
		'http://192.168.1.17:8004'
	],
	allow_credentials=True,
	allow_methods=['*'],
	allow_headers=['*'],
)

# Include routers
app.include_router(router)

# Optional standalone runner
if __name__ == '__main__':
	uvicorn.run('api:app', host='127.0.0.1', port=8002, log_level='info', access_log=True)
