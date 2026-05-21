"""
AegisFlow Orchestration Layer — v2.

Replaces mock sub-agents with real LLM-powered execution.
Supports OpenAI-compatible endpoints and OpenClaw session spawning.
"""

import uuid
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional

from aegisflow.memory import MemoryVault
from aegisflow.sandbox import LocalSandbox, SandboxResult
from aegisflow.llm import (
    AgenticLLM,
    AgenticResponse,
    SubAgentResult,
    OpenAICompatibleLLM,
    OpenClawSession,
)

logger = logging.getLogger(__name__)


class SubAgent:
    """
    An LLM-powered sub-agent that executes a discrete task.
    Can use either OpenAI-compatible API or OpenClaw session.
    """

    def __init__(
        self,
        task_id: str,
        prompt: str,
        sandbox: Optional[LocalSandbox] = None,
        llm: Optional[AgenticLLM] = None,
        backend: str = "openai",
    ):
        self.agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        self.task_id = task_id
        self.prompt = prompt
        self.sandbox = sandbox
        self.backend = backend

        # Initialize LLM
        if llm:
            self.llm = llm
        elif backend == "openclaw":
            self.llm = AgenticLLM(backend="openclaw")
        else:
            self.llm = AgenticLLM(backend="openai")

        self.status = "initialized"
        self.result: Optional[AgenticResponse] = None
        self.sandbox_output: Optional[str] = None

    def execute(self) -> Dict[str, Any]:
        """
        Execute the sub-agent task via LLM.
        If sandbox is provided, write results to sandbox workspace.
        """
        self.status = "running"
        logger.info(f"[{self.agent_id}] Executing task: {self.prompt[:80]}...")

        start = time.time()

        try:
            # Run LLM
            if self.backend == "openclaw" and isinstance(self.llm._impl, OpenClawSession):
                sub_result: SubAgentResult = self.llm._impl.spawn_subagent(
                    task=self.prompt,
                    agent_id=self.agent_id,
                    run_timeout=180,
                )
                if sub_result.status == "success" and sub_result.response:
                    self.result = sub_result.response
                else:
                    self.status = "error"
                    self.result = AgenticResponse(content=f"Agent error: {sub_result.error}")
            else:
                # OpenAI-compatible path
                messages = [
                    {"role": "system", "content": "You are a helpful research and analysis assistant. Be thorough and concise."},
                    {"role": "user", "content": self.prompt},
                ]
                self.result = self.llm.chat(messages, temperature=0.7, max_tokens=2048)

            self.status = "completed"

            # Write result to sandbox if available
            if self.sandbox:
                output_filename = f"{self.agent_id}_output.txt"
                self.sandbox.write_file(f"workspace/{output_filename}", self.result.content)
                self.sandbox_output = output_filename

            duration_ms = int((time.time() - start) * 1000)

            return {
                "agent_id": self.agent_id,
                "status": self.status,
                "result": self.result.content[:500] if self.result else "",
                "tokens_used": self.result.tokens_used if self.result else 0,
                "sandbox_file": self.sandbox_output,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            self.status = "error"
            logger.error(f"[{self.agent_id}] Error: {e}")
            return {
                "agent_id": self.agent_id,
                "status": "error",
                "error": str(e),
                "duration_ms": int((time.time() - start) * 1000),
            }

    async def execute_async(self) -> Dict[str, Any]:
        """Async wrapper — runs execute() in a thread so LLM I/O doesn't block."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute)


class LeadOrchestrator:
    """
    Main swarm coordinator. Decomposes tasks and manages sub-agents.
    Uses LLM-driven task decomposition when configured.
    """

    def __init__(
        self,
        memory: Optional[MemoryVault] = None,
        sandbox: Optional[LocalSandbox] = None,
        llm_backend: str = "openai",
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        self.memory = memory or MemoryVault(path="./vault")
        self.sandbox = sandbox or LocalSandbox(workspace_path="./sandbox_workspace")
        self.llm = AgenticLLM(
            backend=llm_backend,
            openai_config=llm_config if llm_backend == "openai" else None,
            openclaw_config=llm_config if llm_backend == "openclaw" else None,
        )
        self.sub_agents: List[SubAgent] = []
        self.session_id = str(uuid.uuid4())
        self.fallback_count: int = 0

    def _decompose_with_llm(self, task: str) -> List[str]:
        """
        Use the LLM to decompose a complex task into discrete sub-tasks.
        Falls back to rule-based decomposition if LLM call fails.
        """
        try:
            messages = [
                {"role": "system", "content": (
                    "You are a task decomposition assistant. Given a complex task, break it into "
                    "3-5 specific, actionable sub-tasks that can be executed independently. "
                    "Return ONLY a numbered list of sub-tasks, nothing else."
                )},
                {"role": "user", "content": f"Decompose this task: {task}"},
            ]
            response = self.llm.chat(messages, temperature=0.3, max_tokens=512)
            lines = response.content.strip().split("\n")
            sub_tasks = [l.lstrip("1234567890. )").strip() for l in lines if l.strip()]
            if len(sub_tasks) >= 2:
                logger.info(f"LLM decomposed into {len(sub_tasks)} sub-tasks")
                return sub_tasks
        except Exception as e:
            logger.warning(f"LLM decomposition failed, using fallback: {e}")
            self.fallback_count += 1

        # Fallback rule-based decomposition
        return [
            f"Research and gather information for: {task}",
            f"Analyze and process findings for: {task}",
            f"Synthesize and produce final result for: {task}",
        ]

    def delegate_and_run(self, task: str, max_agents: int = 5) -> Dict[str, Any]:
        """
        Main entry point for executing a complex workflow.
        1. Decompose the task (LLM-driven)
        2. Spawn isolated sub-agents
        3. Execute in parallel (sequential here, can be async)
        4. Synthesize results and store in memory
        """
        sub_tasks = self._decompose_with_llm(task)
        results = []

        for st in sub_tasks[:max_agents]:
            agent = SubAgent(
                task_id=self.session_id,
                prompt=st,
                sandbox=self.sandbox,
                llm=self.llm,
                backend=self.llm.backend,
            )
            self.sub_agents.append(agent)
            res = agent.execute()
            results.append(res)

        # Synthesis
        synthesis_prompt = (
            f"Synthesize the following sub-task results into a single coherent answer:\n"
            + "\n".join(f"[{i+1}] {r.get('result', r.get('error', ''))}" for i, r in enumerate(results))
        )
        try:
            synthesis_response = self.llm.chat(
                [{"role": "user", "content": synthesis_prompt}],
                temperature=0.5,
                max_tokens=1024,
            )
            synthesis = synthesis_response.content
        except Exception as e:
            synthesis = f"Synthesis completed for {len(results)} sub-tasks (LLM synthesis failed: {e})"

        # Store to persistent memory
        self.memory.store_verbatim(
            content=f"## Task: {task}\n\n## Synthesis\n{synthesis}\n\n## Sub-agent Results\n"
                    + "\n".join(f"### Agent {r['agent_id']}: {r['status']}\n{r.get('result', r.get('error', ''))}" for r in results),
            category="work",
            filename=f"session_{self.session_id}.md",
        )

        return {
            "session_id": self.session_id,
            "status": "success",
            "task": task,
            "sub_tasks": sub_tasks,
            "sub_agents": [{"agent_id": r["agent_id"], "status": r["status"]} for r in results],
            "synthesis": synthesis,
            "details": results,
        }

    def run_research(self, topic: str, depth: str = "quick") -> Dict[str, Any]:
        """
        Specialized research workflow.
        depth: "quick" (1 agent) | "standard" (3 agents) | "deep" (5 agents)
        """
        depth_map = {"quick": 1, "standard": 3, "deep": 5}
        max_agents = depth_map.get(depth, 1)

        return self.delegate_and_run(
            f"Research the following topic thoroughly: {topic}. Provide key findings, "
            f"sources, and actionable insights.",
            max_agents=max_agents,
        )

    async def delegate_and_run_async(self, task: str, max_agents: int = 5) -> Dict[str, Any]:
        """
        Async version — runs sub-agents concurrently via asyncio.gather.
        This is a 3-5× speedup on real LLM workloads (§5.5).
        """
        sub_tasks = self._decompose_with_llm(task)
        agents = []

        for st in sub_tasks[:max_agents]:
            agent = SubAgent(
                task_id=self.session_id,
                prompt=st,
                sandbox=self.sandbox,
                llm=self.llm,
                backend=self.llm.backend,
            )
            self.sub_agents.append(agent)
            agents.append(agent)

        # Run all sub-agents concurrently
        results = await asyncio.gather(*(a.execute_async() for a in agents))
        results = list(results)

        # Synthesis
        synthesis_prompt = (
            f"Synthesize the following sub-task results into a single coherent answer:\n"
            + "\n".join(f"[{i+1}] {r.get('result', r.get('error', ''))}" for i, r in enumerate(results))
        )
        try:
            synthesis_response = self.llm.chat(
                [{"role": "user", "content": synthesis_prompt}],
                temperature=0.5,
                max_tokens=1024,
            )
            synthesis = synthesis_response.content
        except Exception as e:
            synthesis = f"Synthesis completed for {len(results)} sub-tasks (LLM synthesis failed: {e})"

        # Store to persistent memory
        self.memory.store_verbatim(
            content=f"## Task: {task}\n\n## Synthesis\n{synthesis}\n\n## Sub-agent Results\n"
                    + "\n".join(f"### Agent {r['agent_id']}: {r['status']}\n{r.get('result', r.get('error', ''))}" for r in results),
            category="work",
            filename=f"session_{self.session_id}.md",
        )

        return {
            "session_id": self.session_id,
            "status": "success",
            "task": task,
            "sub_tasks": sub_tasks,
            "sub_agents": [{"agent_id": r["agent_id"], "status": r["status"]} for r in results],
            "synthesis": synthesis,
            "details": results,
        }