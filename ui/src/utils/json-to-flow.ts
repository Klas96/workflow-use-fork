import { Edge } from '@xyflow/react';
import { Workflow, WorkflowStep, WorkflowMetadata, PositionLoggerNode } from '../types/workflow-layout.types';

export function jsonToFlow(workflow: string): { 
  nodes: PositionLoggerNode[]; 
  edges: Edge[];
  metadata: WorkflowMetadata;
} {
  const parsedWorkflow = JSON.parse(workflow) as Workflow;
  const nodes: PositionLoggerNode[] = parsedWorkflow.steps.map((step: WorkflowStep, idx: number) => ({
    id: String(idx),
    data: { label: `${step.description}` },
    position: { x: 0, y: idx * 100 },
    type: 'position-logger'
  }));

  const edges: Edge[] = parsedWorkflow.steps.slice(1).map((_: WorkflowStep, idx: number) => ({
    id: `e${idx}-${idx + 1}`,
    source: String(idx),
    target: String(idx + 1),
    animated: true,
  }));

  const metadata: WorkflowMetadata = {
    name: parsedWorkflow.name,
    description: parsedWorkflow.description,
    version: parsedWorkflow.version,
    input_schema: parsedWorkflow.input_schema,
    workflow_analysis: parsedWorkflow.workflow_analysis
  };

  return { nodes, edges, metadata };
}