import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from .routers import router

app = FastAPI(title='Workflow Execution Service')

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
	uvicorn.run('api:app', host='127.0.0.1', port=8002, log_level='info')
