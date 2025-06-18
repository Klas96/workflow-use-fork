import asyncio
import json
import time
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import uuid

import aiofiles
from browser_use.browser.browser import Browser
from langchain_openai import ChatOpenAI

from workflow_use.controller.service import WorkflowController
from workflow_use.workflow.service import Workflow

from .views import (
	TaskInfo,
	WorkflowCancelResponse,
	WorkflowExecuteRequest,
	WorkflowMetadataUpdateRequest,
	WorkflowResponse,
	WorkflowStatusResponse,
	WorkflowUpdateRequest,
	WorkflowExecuteResponse,
)

class WorkflowService:
	"""Workflow execution service."""

	def __init__(self) -> None:
		self._setup_logging()
		
		self.tmp_dir = Path(os.path.dirname(os.path.dirname(__file__))) / "tmp"
		self.tmp_dir.mkdir(exist_ok=True)
		self.log_dir = self.tmp_dir / "logs"
		self.log_dir.mkdir(exist_ok=True)
		
		# Initialize LLM
		try:
			self.llm_instance = ChatOpenAI(model='gpt-4.1-mini')
			self.logger.info("LLM initialized successfully")
		except Exception as exc:
			self.logger.error(f'Error initializing LLM: {exc}. Ensure OPENAI_API_KEY is set.')
			self.llm_instance = None

		# Configure browser to use the X display
		os.environ['DISPLAY'] = ':99'
		os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '0'  # Use system browser
		os.environ['PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD'] = '1'
		
		self.browser_instance = Browser(
			headless=False,
			args=[
				'--no-sandbox',  # Required for running as root
				'--disable-setuid-sandbox',  # Required for running as root
				'--disable-dev-shm-usage',
				'--disable-accelerated-2d-canvas',
				'--disable-gpu',
				'--window-size=1920,1080',
				'--start-maximized',
				'--disable-extensions',
				'--disable-default-apps',
				'--disable-popup-blocking',
				'--disable-notifications',
				'--disable-infobars',
				'--disable-web-security',
				'--allow-running-insecure-content',
				'--disable-features=IsolateOrigins,site-per-process'
			],
			chromiumSandbox=False,
			channel="chrome",  # Use Chrome instead of Chromium
			executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH', '/opt/google/chrome/google-chrome'),
			launch_options={
				"args": ["--no-sandbox", "--disable-setuid-sandbox"],
				"chromiumSandbox": False,
				"executablePath": os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH', '/opt/google/chrome/google-chrome')
			}
		)
		self.controller_instance = WorkflowController()
		self.logger.info("Browser and controller instances initialized")

		# In‑memory task tracking
		self.active_tasks: Dict[str, TaskInfo] = {}
		self.workflow_tasks: Dict[str, asyncio.Task] = {}
		self.cancel_events: Dict[str, asyncio.Event] = {}

	def _setup_logging(self):
		"""Set up logging configuration."""
		log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tmp", "logs")
		os.makedirs(log_dir, exist_ok=True)
		
		log_file = os.path.join(log_dir, "backend.log")
		
		# Configure logging to write to both file and console
		logging.basicConfig(
			level=logging.INFO,
			format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
			handlers=[
				logging.FileHandler(log_file),
				logging.StreamHandler()  # This will write to stdout/stderr
			]
		)
		
		# Create logger for this module
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(logging.INFO)
		
		# Add file handler
		file_handler = logging.FileHandler(log_file)
		file_handler.setLevel(logging.INFO)
		formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
		file_handler.setFormatter(formatter)
		self.logger.addHandler(file_handler)
		
		# Add console handler
		console_handler = logging.StreamHandler()
		console_handler.setLevel(logging.INFO)
		console_handler.setFormatter(formatter)
		self.logger.addHandler(console_handler)

	async def _log_file_position(self) -> int:
		log_file = self.log_dir / 'backend.log'
		if not log_file.exists():
			async with aiofiles.open(log_file, 'w') as f:
				await f.write('')
			return 0
		return log_file.stat().st_size

	async def _read_logs_from_position(self, position: int) -> Tuple[List[str], int]:
		log_file = self.log_dir / 'backend.log'
		if not log_file.exists():
			return [], 0

		current_size = log_file.stat().st_size
		if position >= current_size:
			return [], position

		async with aiofiles.open(log_file, 'r') as f:
			await f.seek(position)
			all_logs = await f.readlines()
			# Include all log levels
			new_logs = [line for line in all_logs]
		return new_logs, current_size

	async def _write_log(self, log_file: Path, message: str) -> None:
		async with aiofiles.open(log_file, 'a') as f:
			await f.write(message)
		self.logger.info(message.strip())  # Also log to console

	def list_workflows(self) -> List[str]:
		workflows = [f.name for f in self.tmp_dir.iterdir() if f.is_file() and not f.name.startswith('temp_recording')]
		self.logger.info(f"Listing workflows: {workflows}")
		return workflows

	def get_workflow(self, name: str) -> str:
		wf_file = self.tmp_dir / name
		content = wf_file.read_text()
		self.logger.info(f"Retrieved workflow: {name}")
		return content

	def update_workflow(self, request: WorkflowUpdateRequest) -> WorkflowResponse:
		workflow_filename = request.filename
		node_id = request.nodeId
		updated_step_data = request.stepData

		if not (workflow_filename and node_id is not None and updated_step_data):
			self.logger.warning("Missing required fields in workflow update request")
			return WorkflowResponse(success=False, error='Missing required fields')

		wf_file = self.tmp_dir / workflow_filename
		if not wf_file.exists():
			self.logger.warning(f"Workflow file not found: {workflow_filename}")
			return WorkflowResponse(success=False, error=f"Workflow file '{workflow_filename}' not found")

		workflow_content = json.loads(wf_file.read_text())
		steps = workflow_content.get('steps', [])

		if 0 <= int(node_id) < len(steps):
			steps[int(node_id)] = updated_step_data
			wf_file.write_text(json.dumps(workflow_content, indent=2))
			self.logger.info(f"Updated workflow {workflow_filename}, node {node_id}")
			return WorkflowResponse(success=True)

		self.logger.warning(f"Node {node_id} not found in workflow {workflow_filename}")
		return WorkflowResponse(success=False, error='Node not found in workflow')

	def update_workflow_metadata(self, request: WorkflowMetadataUpdateRequest) -> WorkflowResponse:
		workflow_name = request.name
		updated_metadata = request.metadata

		if not (workflow_name and updated_metadata):
			return WorkflowResponse(success=False, error='Missing required fields')

		wf_file = self.tmp_dir / workflow_name
		if not wf_file.exists():
			return WorkflowResponse(success=False, error='Workflow not found')

		workflow_content = json.loads(wf_file.read_text())
		workflow_content['name'] = updated_metadata.get('name', workflow_content.get('name', ''))
		workflow_content['description'] = updated_metadata.get('description', workflow_content.get('description', ''))
		workflow_content['version'] = updated_metadata.get('version', workflow_content.get('version', ''))

		if 'input_schema' in updated_metadata:
			workflow_content['input_schema'] = updated_metadata['input_schema']

		wf_file.write_text(json.dumps(workflow_content, indent=2))
		return WorkflowResponse(success=True)

	async def run_workflow_in_background(
		self,
		task_id: str,
		request: WorkflowExecuteRequest,
		cancel_event: asyncio.Event,
	) -> None:
		workflow_name = request.name
		inputs = request.inputs
		log_file = self.log_dir / 'backend.log'
		try:
			self.active_tasks[task_id] = TaskInfo(status='running', workflow=workflow_name)
			ts = time.strftime('%Y-%m-%d %H:%M:%S')
			await self._write_log(log_file, f"[{ts}] Starting workflow '{workflow_name}'\n")
			await self._write_log(log_file, f'[{ts}] Input parameters: {json.dumps(inputs)}\n')

			if cancel_event.is_set():
				await self._write_log(log_file, f'[{ts}] Workflow cancelled before execution\n')
				self.active_tasks[task_id].status = 'cancelled'
				return

			workflow_path = self.tmp_dir / workflow_name
			try:
				self.logger.info(f"Loading workflow from {workflow_path}")
				self.workflow_obj = Workflow.load_from_file(
					str(workflow_path), llm=self.llm_instance, browser=self.browser_instance, controller=self.controller_instance
				)
			except Exception as e:
				self.logger.error(f'Error loading workflow: {e}')
				return

			await self._write_log(log_file, f'[{ts}] Executing workflow...\n')

			if cancel_event.is_set():
				await self._write_log(log_file, f'[{ts}] Workflow cancelled before execution\n')
				self.active_tasks[task_id].status = 'cancelled'
				return

			result = await self.workflow_obj.run(inputs, close_browser_at_end=True, cancel_event=cancel_event)

			if cancel_event.is_set():
				await self._write_log(log_file, f'[{ts}] Workflow execution was cancelled\n')
				self.active_tasks[task_id].status = 'cancelled'
				return

			formatted_result = [
				{
					'step_id': i,
					'extracted_content': s.extracted_content,
					'status': 'completed',
				}
				for i, s in enumerate(result.step_results)
			]
			for step in formatted_result:
				await self._write_log(log_file, f'[{ts}] Completed step {step["step_id"]}: {step["extracted_content"]}\n')

			self.active_tasks[task_id].status = 'completed'
			self.active_tasks[task_id].result = formatted_result
			await self._write_log(log_file, f'[{ts}] Workflow completed successfully with {len(result.step_results)} steps\n')

		except asyncio.CancelledError:
			await self._write_log(log_file, f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] Workflow force‑cancelled\n')
			self.active_tasks[task_id].status = 'cancelled'
			raise
		except Exception as exc:
			await self._write_log(log_file, f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] Error: {exc}\n')
			self.active_tasks[task_id].status = 'failed'
			self.active_tasks[task_id].error = str(exc)

	def get_task_status(self, task_id: str) -> Optional[WorkflowStatusResponse]:
		task_info = self.active_tasks.get(task_id)
		if not task_info:
			self.logger.warning(f"Task {task_id} not found")
			return None

		self.logger.info(f"Task {task_id} status: {task_info.status}")
		return WorkflowStatusResponse(
			task_id=task_id,
			status=task_info.status,
			workflow=task_info.workflow,
			result=task_info.result,
			error=task_info.error,
		)

	async def cancel_workflow(self, task_id: str) -> WorkflowCancelResponse:
		task_info = self.active_tasks.get(task_id)
		if not task_info:
			self.logger.warning(f"Task {task_id} not found for cancellation")
			return WorkflowCancelResponse(success=False, message='Task not found')
		if task_info.status != 'running':
			self.logger.warning(f"Task {task_id} is already {task_info.status}")
			return WorkflowCancelResponse(success=False, message=f'Task is already {task_info.status}')

		task = self.workflow_tasks.get(task_id)
		cancel_event = self.cancel_events.get(task_id)

		if cancel_event:
			cancel_event.set()
		if task and not task.done():
			task.cancel()

		await self._write_log(
			self.log_dir / 'backend.log',
			f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] Workflow execution for task {task_id} cancelled by user\n',
		)

		self.active_tasks[task_id].status = 'cancelling'
		self.logger.info(f"Task {task_id} cancellation requested")
		return WorkflowCancelResponse(success=True, message='Workflow cancellation requested')

	async def execute_workflow(self, workflow_name: str, request: WorkflowExecuteRequest) -> WorkflowExecuteResponse:
		"""Execute a workflow with the given name and inputs."""
		self.logger.info(f"Executing workflow: {workflow_name}")
		
		if not workflow_name:
			self.logger.error("Missing workflow name")
			raise ValueError('Missing workflow name')

		workflow_path = self.tmp_dir / workflow_name
		if not workflow_path.exists():
			self.logger.error(f"Workflow {workflow_name} not found")
			raise FileNotFoundError(f'Workflow {workflow_name} not found')

		try:
			task_id = str(uuid.uuid4())
			cancel_event = asyncio.Event()
			self.cancel_events[task_id] = cancel_event
			log_pos = await self._log_file_position()

			task = asyncio.create_task(self.run_workflow_in_background(task_id, request, cancel_event))
			self.workflow_tasks[task_id] = task
			task.add_done_callback(
				lambda _: (
					self.workflow_tasks.pop(task_id, None),
					self.cancel_events.pop(task_id, None),
				)
			)
			
			self.logger.info(f"Workflow execution started with task ID: {task_id}")
			return WorkflowExecuteResponse(
				success=True,
				task_id=task_id,
				workflow=workflow_name,
				log_position=log_pos,
				message=f"Workflow '{workflow_name}' execution started with task ID: {task_id}",
			)
		except Exception as exc:
			self.logger.error(f"Error starting workflow: {exc}")
			raise RuntimeError(f'Error starting workflow: {exc}')
