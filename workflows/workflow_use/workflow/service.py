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
from workflow_use.workflow.workflow import Workflow

logger = logging.getLogger(__name__)

WAIT_FOR_ELEMENT_TIMEOUT = 2500

T = TypeVar('T', bound=BaseModel)
