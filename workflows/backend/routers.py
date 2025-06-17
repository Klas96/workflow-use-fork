import asyncio
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional

from .service import WorkflowService
from .views import (
	WorkflowCancelResponse,
	WorkflowExecuteRequest,
	WorkflowExecuteResponse,
	WorkflowListResponse,
	WorkflowLogsResponse,
	WorkflowMetadataUpdateRequest,
	WorkflowResponse,
	WorkflowStatusResponse,
	WorkflowUpdateRequest,
)

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/workflows')


def get_service() -> WorkflowService:
	logger.info("Initializing WorkflowService")
	return WorkflowService()


@router.get('/', response_model=List[str])
async def list_workflows(service: WorkflowService = Depends(get_service)):
	logger.info("GET /api/workflows/ - Listing all workflows")
	try:
		workflows = service.list_workflows()
		logger.info(f"Found workflows: {workflows}")
		return workflows
	except Exception as e:
		logger.error(f"Error listing workflows: {e}")
		raise HTTPException(status_code=500, detail=str(e))


@router.get('/{workflow_name}', response_model=str)
async def get_workflow(workflow_name: str, service: WorkflowService = Depends(get_service)):
	logger.info(f"GET /api/workflows/{workflow_name} - Retrieving workflow")
	try:
		return service.get_workflow(workflow_name)
	except Exception as e:
		logger.error(f"Error getting workflow {workflow_name}: {e}")
		raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_name}")


@router.post('/update', response_model=WorkflowResponse)
async def update_workflow(request: WorkflowUpdateRequest):
	service = get_service()
	return service.update_workflow(request)


@router.post('/update-metadata', response_model=WorkflowResponse)
async def update_workflow_metadata(request: WorkflowMetadataUpdateRequest):
	service = get_service()
	return service.update_workflow_metadata(request)


@router.post('/execute', response_model=WorkflowExecuteResponse)
async def execute_workflow(
	workflow_name: str,
	request: WorkflowExecuteRequest,
	service: WorkflowService = Depends(get_service)
):
	logger.info(f"POST /api/workflows/{workflow_name}/execute - Executing workflow")
	try:
		return await service.execute_workflow(workflow_name, request)
	except Exception as e:
		logger.error(f"Error executing workflow {workflow_name}: {e}")
		raise HTTPException(status_code=500, detail=str(e))


@router.get('/logs/{task_id}', response_model=WorkflowLogsResponse)
async def get_logs(task_id: str, position: int = 0):
	service = get_service()
	task_info = service.active_tasks.get(task_id)
	logs, new_pos = await service._read_logs_from_position(position)
	return WorkflowLogsResponse(
		logs=logs,
		position=new_pos,
		log_position=new_pos,
		status=task_info.status if task_info else 'unknown',
		result=task_info.result if task_info else None,
		error=task_info.error if task_info else None,
	)


@router.get('/tasks/{task_id}/status', response_model=WorkflowStatusResponse)
async def get_task_status(task_id: str):
	service = get_service()
	task_info = service.get_task_status(task_id)
	if not task_info:
		raise HTTPException(status_code=404, detail=f'Task {task_id} not found')
	return task_info


@router.post('/tasks/{task_id}/cancel', response_model=WorkflowCancelResponse)
async def cancel_workflow(
	workflow_name: str,
	task_id: str,
	service: WorkflowService = Depends(get_service)
):
	logger.info(f"POST /api/workflows/{workflow_name}/cancel/{task_id} - Cancelling workflow")
	try:
		return await service.cancel_workflow(task_id)
	except Exception as e:
		logger.error(f"Error cancelling workflow {workflow_name}, task {task_id}: {e}")
		raise HTTPException(status_code=404, detail="Task not found")


@router.put('/{workflow_name}/update', response_model=WorkflowResponse)
async def update_workflow(
	workflow_name: str,
	request: WorkflowUpdateRequest,
	service: WorkflowService = Depends(get_service)
):
	logger.info(f"PUT /api/workflows/{workflow_name}/update - Updating workflow")
	try:
		return service.update_workflow(workflow_name, request)
	except Exception as e:
		logger.error(f"Error updating workflow {workflow_name}: {e}")
		raise HTTPException(status_code=500, detail=str(e))
