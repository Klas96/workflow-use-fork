from __future__ import annotations

import asyncio
import json
import json as _json
import logging
from pathlib import Path
from typing import Any, Dict, List, TypeVar
import os

from browser_use import Agent, Browser
from browser_use.agent.views import ActionResult, AgentHistoryList
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from workflow_use.controller.service import WorkflowController
from workflow_use.controller.utils import get_best_element_handle
from workflow_use.schema.views import (
    AgenticWorkflowStep,
    ClickStep,
    DeterministicWorkflowStep,
    InputStep,
    KeyPressStep,
    NavigationStep,
    ScrollStep,
    SelectChangeStep,
    WorkflowDefinitionSchema,
    WorkflowInputSchemaDefinition,
    WorkflowStep,
)
from workflow_use.workflow.prompts import STRUCTURED_OUTPUT_PROMPT, WORKFLOW_FALLBACK_PROMPT_TEMPLATE
from workflow_use.workflow.views import WorkflowRunOutput

logger = logging.getLogger(__name__)

WAIT_FOR_ELEMENT_TIMEOUT = 2500

T = TypeVar('T', bound=BaseModel)


class Workflow:
    """Simple orchestrator that executes a list of workflow *steps* defined in a WorkflowDefinitionSchema."""

    def __init__(
        self,
        workflow_schema: WorkflowDefinitionSchema,
        *,
        controller: WorkflowController | None = None,
        browser: Browser | None = None,
        llm: BaseChatModel | None = None,
        page_extraction_llm: BaseChatModel | None = None,
        fallback_to_agent: bool = True,
    ) -> None:
        """Initialize a new Workflow instance from a schema object.

        Args:
            workflow_schema: The parsed workflow definition schema.
            controller: Optional WorkflowController instance to handle action execution
            browser: Optional Browser instance to use for browser automation
            llm: Optional language model for fallback agent functionality
            fallback_to_agent: Whether to fall back to agent-based execution on step failure

        Raises:
            ValueError: If the workflow schema is invalid (though Pydantic handles most).
        """
        self.schema = workflow_schema  # Store the schema object

        self.name = self.schema.name
        self.description = self.schema.description
        self.version = self.schema.version
        self.steps = self.schema.steps

        self.controller = controller or WorkflowController()

        # Get browser arguments from environment variable or use defaults
        browser_args = os.environ.get('PLAYWRIGHT_BROWSER_ARGS', '').split() or [
            '--no-sandbox',  # Required for running as root
            '--disable-setuid-sandbox',  # Required for running as root
            '--disable-dev-shm-usage',  # Handle limited shared memory in Docker
            '--disable-gpu',  # Disable GPU hardware acceleration
            '--disable-software-rasterizer',  # Disable software rasterizer
            '--disable-accelerated-2d-canvas',
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
        ]

        self.browser = browser or Browser(
            headless=False,
            args=browser_args,
            keep_alive=True,
            chromiumSandbox=False,
            channel="chrome",  # Use Chrome instead of Chromium
            executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH', '/opt/google/chrome/google-chrome'),
            launch_options={
                "args": ["--no-sandbox", "--disable-setuid-sandbox"],
                "chromiumSandbox": False,
                "executablePath": os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH', '/opt/google/chrome/google-chrome')
            }
        )

        self.llm = llm
        self.page_extraction_llm = page_extraction_llm

        self.fallback_to_agent = fallback_to_agent

        self.context: dict[str, Any] = {}

        self.inputs_def: List[WorkflowInputSchemaDefinition] = self.schema.input_schema
        self._input_model: type[BaseModel] = self._build_input_model()

    # --- Loaders ---
    @classmethod
    def load_from_file(
        cls,
        file_path: str | Path,
        *,
        controller: WorkflowController | None = None,
        browser: Browser | None = None,
        llm: BaseChatModel | None = None,
        page_extraction_llm: BaseChatModel | None = None,
    ) -> Workflow:
        """Load a workflow from a file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = _json.load(f)
        workflow_schema = WorkflowDefinitionSchema(**data)
        return Workflow(
            workflow_schema=workflow_schema,
            controller=controller,
            browser=browser,
            llm=llm,
            page_extraction_llm=page_extraction_llm,
        )

    # --- Runners ---
    async def _run_deterministic_step(self, step: DeterministicWorkflowStep, step_index: int) -> ActionResult:
        """Execute a deterministic (controller) action based on step dictionary."""
        # Assumes WorkflowStep for deterministic type has 'action' and 'params' keys
        action_name: str = step.type  # Expect 'action' key for deterministic steps
        params: Dict[str, Any] = step.model_dump()  # Use params if present

        ActionModel = self.controller.registry.create_action_model(include_actions=[action_name])
        # Pass the params dictionary directly
        action_model = ActionModel(**{action_name: params})

        try:
            result = await self.controller.act(action_model, self.browser, page_extraction_llm=self.page_extraction_llm)
        except Exception as e:
            raise RuntimeError(f"Deterministic action '{action_name}' failed: {str(e)}")

        # Helper function to truncate long selectors in logs
        def truncate_selector(selector: str) -> str:
            return selector if len(selector) <= 45 else f'{selector[:45]}...'

        # Determine if this is not the last step, and extract next step's cssSelector if available
        current_index = step_index
        if current_index < len(self.steps) - 1:
            next_step = self.steps[current_index + 1]
            next_step_resolved = self._resolve_placeholders(next_step)
            css_selector = getattr(next_step_resolved, 'cssSelector', None)
            if css_selector:
                try:
                    await self.browser._wait_for_stable_network()
                    page = await self.browser.get_current_page()

                    logger.info(f'Waiting for element with selector: {truncate_selector(css_selector)}')
                    locator, selector_used = await get_best_element_handle(
                        page, css_selector, next_step_resolved, timeout_ms=WAIT_FOR_ELEMENT_TIMEOUT
                    )
                    logger.info(f'Element with selector found: {truncate_selector(selector_used)}')
                except Exception as e:
                    logger.error(f'Failed to wait for element with selector: {truncate_selector(css_selector)}. Error: {e}')
                    raise Exception(f'Failed to wait for element. Selector: {css_selector}') from e

        return result

    async def _run_agent_step(self, step: AgenticWorkflowStep) -> AgentHistoryList:
        """Spin-up an Agent based on step dictionary."""
        if self.llm is None:
            raise ValueError("An 'llm' instance must be supplied for agent-based steps")

        task: str = step.task
        max_steps: int = step.max_steps or 5

        agent = Agent(
            task=task,
            llm=self.llm,
            browser_session=self.browser,
            use_vision=True,  # Consider making this configurable via WorkflowStep schema
        )
        return await agent.run(max_steps=max_steps)

    async def _fallback_to_agent(
        self,
        step_resolved: WorkflowStep,
        step_index: int,
    ) -> AgentHistoryList:
        """Fall back to agent-based execution if deterministic action fails."""
        if self.llm is None:
            raise ValueError("An 'llm' instance must be supplied for agent-based steps")

        # Create a task description based on the step
        task = f"Complete step {step_index + 1} of the workflow: {step_resolved.description or 'No description provided'}"

        agent = Agent(
            task=task,
            llm=self.llm,
            browser_session=self.browser,
            use_vision=True,
        )
        return await agent.run(max_steps=5)

    def _validate_inputs(self, inputs: dict[str, Any]) -> None:
        """Validate input values against the input schema."""
        if not inputs:
            return

        # Create an instance of the input model to validate
        try:
            self._input_model(**inputs)
        except Exception as e:
            raise ValueError(f"Invalid input values: {str(e)}")

    def _resolve_placeholders(self, data: Any) -> Any:
        """Resolve {context_var} placeholders in string values."""
        if isinstance(data, str):
            # Replace {context_var} with values from self.context
            for key, value in self.context.items():
                placeholder = f"{{{key}}}"
                if placeholder in data:
                    data = data.replace(placeholder, str(value))
            return data
        elif isinstance(data, dict):
            return {k: self._resolve_placeholders(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_placeholders(item) for item in data]
        else:
            return data

    def _store_output(self, step_cfg: WorkflowStep, result: Any) -> None:
        """Store step output in context if output key is specified."""
        if not hasattr(step_cfg, 'output') or not step_cfg.output:
            return

        output_key = step_cfg.output
        if isinstance(result, ActionResult):
            self.context[output_key] = result.extracted_content
        elif isinstance(result, AgentHistoryList):
            # For agent steps, store the final message
            if result.messages:
                self.context[output_key] = result.messages[-1].content
        else:
            self.context[output_key] = str(result)

    async def _execute_step(self, step_index: int, step_resolved: WorkflowStep) -> ActionResult | AgentHistoryList:
        """Execute a single workflow step."""
        try:
            if isinstance(step_resolved, DeterministicWorkflowStep):
                result = await self._run_deterministic_step(step_resolved, step_index)
            elif isinstance(step_resolved, AgenticWorkflowStep):
                result = await self._run_agent_step(step_resolved)
            else:
                raise ValueError(f"Unknown step type: {type(step_resolved)}")

            self._store_output(step_resolved, result)
            return result

        except Exception as e:
            if self.fallback_to_agent:
                logger.warning(f"Step {step_index + 1} failed, falling back to agent: {str(e)}")
                return await self._fallback_to_agent(step_resolved, step_index)
            else:
                raise

    async def _convert_results_to_output_model(
        self,
        results: List[ActionResult | AgentHistoryList],
        output_model: type[T],
    ) -> T:
        """Convert workflow results to the specified output model."""
        # Extract content from results
        content = []
        for result in results:
            if isinstance(result, ActionResult):
                content.append(result.extracted_content)
            elif isinstance(result, AgentHistoryList):
                if result.messages:
                    content.append(result.messages[-1].content)

        # Join all content
        full_content = "\n".join(str(c) for c in content if c)

        # Create a prompt for the LLM to extract structured data
        prompt = ChatPromptTemplate.from_messages([
            ("system", STRUCTURED_OUTPUT_PROMPT),
            ("human", full_content)
        ])

        # Get the output schema
        schema = output_model.model_json_schema()

        # Create a tool for structured output
        structured_tool = StructuredTool.from_function(
            func=lambda **kwargs: output_model(**kwargs),
            name="extract_structured_data",
            description="Extract structured data from the content",
            args_schema=output_model,
        )

        # Create an agent to extract structured data
        agent = create_tool_calling_agent(
            llm=self.llm,
            tools=[structured_tool],
            prompt=prompt,
        )

        # Run the agent
        agent_executor = AgentExecutor(
            agent=agent,
            tools=[structured_tool],
            verbose=True,
        )

        result = await agent_executor.ainvoke({"input": full_content})
        return output_model(**result["output"])

    async def run_step(self, step_index: int, inputs: dict[str, Any] | None = None):
        """Run a single step of the workflow."""
        if inputs:
            self._validate_inputs(inputs)
            self.context.update(inputs)

        if step_index < 0 or step_index >= len(self.steps):
            raise ValueError(f"Invalid step index: {step_index}")

        step = self.steps[step_index]
        step_resolved = self._resolve_placeholders(step)

        return await self._execute_step(step_index, step_resolved)

    async def run(
        self,
        inputs: dict[str, Any] | None = None,
        close_browser_at_end: bool = True,
        cancel_event: asyncio.Event | None = None,
        output_model: type[T] | None = None,
    ) -> WorkflowRunOutput[T]:
        """Run the workflow.

        Args:
            inputs: Optional input values to use in the workflow
            close_browser_at_end: Whether to close the browser when done
            cancel_event: Optional event to check for cancellation
            output_model: Optional Pydantic model to convert results to

        Returns:
            WorkflowRunOutput containing step results and optional output model
        """
        try:
            if inputs:
                self._validate_inputs(inputs)
                self.context.update(inputs)

            results: List[ActionResult | AgentHistoryList] = []

            for i, step in enumerate(self.steps):
                if cancel_event and cancel_event.is_set():
                    logger.info("Workflow execution cancelled")
                    break

                step_resolved = self._resolve_placeholders(step)
                result = await self._execute_step(i, step_resolved)
                results.append(result)

            output = None
            if output_model and results:
                output = await self._convert_results_to_output_model(results, output_model)

            return WorkflowRunOutput(step_results=results, output_model=output)

        finally:
            if close_browser_at_end:
                await self.browser.close()

    def _build_input_model(self) -> type[BaseModel]:
        """Build a Pydantic model for workflow inputs."""
        fields = {}
        for input_def in self.inputs_def:
            field_type = str if input_def.type == 'string' else (
                int if input_def.type == 'number' else bool
            )
            fields[input_def.name] = (
                field_type,
                ... if input_def.required else None
            )

        return create_model('WorkflowInputs', **fields)

    def as_tool(self, *, name: str | None = None, description: str | None = None):  # noqa: D401
        """Convert the workflow to a LangChain tool.

        Args:
            name: Optional name for the tool (defaults to workflow name)
            description: Optional description for the tool (defaults to workflow description)

        Returns:
            A LangChain tool that can be used in an agent
        """
        if not self.llm:
            raise ValueError("An 'llm' instance must be supplied to use the workflow as a tool")

        async def _invoke(**kwargs):  # type: ignore[override]
            result = await self.run(inputs=kwargs)
            if result.output_model:
                return result.output_model.model_dump_json()
            return str(result.step_results[-1])

        return StructuredTool.from_function(
            func=_invoke,
            name=name or self.name,
            description=description or self.description,
            args_schema=self._input_model,
        )

    async def run_as_tool(self, prompt: str) -> str:
        """Run the workflow as a tool with a natural language prompt.

        Args:
            prompt: Natural language description of what to do

        Returns:
            The result of the workflow execution
        """
        if not self.llm:
            raise ValueError("An 'llm' instance must be supplied to use the workflow as a tool")

        # Create a prompt for the LLM to extract inputs
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that extracts input values from natural language prompts."),
            ("human", f"Extract input values for the workflow '{self.name}' from this prompt: {prompt}")
        ])

        # Create a tool for structured output
        structured_tool = StructuredTool.from_function(
            func=lambda **kwargs: self._input_model(**kwargs),
            name="extract_inputs",
            description="Extract input values from the prompt",
            args_schema=self._input_model,
        )

        # Create an agent to extract inputs
        agent = create_tool_calling_agent(
            llm=self.llm,
            tools=[structured_tool],
            prompt=prompt_template,
        )

        # Run the agent
        agent_executor = AgentExecutor(
            agent=agent,
            tools=[structured_tool],
            verbose=True,
        )

        result = await agent_executor.ainvoke({"input": prompt})
        inputs = self._input_model(**result["output"])

        # Run the workflow with the extracted inputs
        workflow_result = await self.run(inputs=inputs.model_dump())
        if workflow_result.output_model:
            return workflow_result.output_model.model_dump_json()
        return str(workflow_result.step_results[-1]) 