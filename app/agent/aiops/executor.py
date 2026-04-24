"""Executor node for running one AIOps plan step."""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_qwq import ChatQwen
from loguru import logger
from pydantic import SecretStr

from app.agent.tool_registry import tool_registry
from app.config import config

from .state import PlanExecuteState


async def executor(state: PlanExecuteState) -> dict[str, Any]:
    """Execute the next plan step and append the result to state."""
    logger.info("=== Executor: executing plan step ===")

    plan = state.get("plan", [])
    if not plan:
        logger.info("Plan is empty; skipping executor")
        return {}

    task = plan[0]
    logger.info(f"Current task: {task}")

    try:
        all_tools = await tool_registry.get_diagnosis_tools()
        llm = ChatQwen(
            model=config.rag_model,
            api_key=SecretStr(config.dashscope_api_key),
            temperature=0,
        )
        llm_with_tools = llm.bind_tools(all_tools)

        messages = [
            SystemMessage(
                content=(
                    "You execute one concrete AIOps investigation step. "
                    "Use available tools when needed. Do not invent data. "
                    "If a tool fails, report the failure clearly and continue with the evidence you have."
                )
            ),
            HumanMessage(content=f"Execute this task: {task}"),
        ]

        llm_response = await llm_with_tools.ainvoke(messages)
        logger.info(f"Executor LLM response type: {type(llm_response)}")

        if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
            logger.info(f"Detected {len(llm_response.tool_calls)} tool call(s)")
            tool_results = await _execute_tool_calls(llm_response.tool_calls, all_tools)
            final_response = await llm.ainvoke(
                [
                    *messages,
                    HumanMessage(content="Tool execution results:\n" + "\n\n".join(tool_results)),
                ]
            )
            result = (
                final_response.content
                if hasattr(final_response, "content")
                else str(final_response)
            )
        else:
            logger.info("Executor LLM did not call tools; using direct response")
            result = llm_response.content if hasattr(llm_response, "content") else str(llm_response)

        logger.info(f"Plan step completed; result length={len(result)}")
        return {
            "plan": plan[1:],
            "past_steps": [(task, result)],
        }

    except Exception as exc:
        logger.exception(f"Plan step failed: {exc}")
        return {
            "plan": plan[1:],
            "past_steps": [(task, f"execution failed: {exc}")],
        }


async def _execute_tool_calls(tool_calls: list[Any], tools: list[Any]) -> list[str]:
    """Execute selected tools directly and keep failures scoped to the current step."""
    tool_by_name = {str(getattr(tool, "name", "")): tool for tool in tools}
    results: list[str] = []

    for tool_call in tool_calls:
        tool_name = str(tool_call.get("name", "unknown"))
        tool_args = tool_call.get("args", {})
        tool = tool_by_name.get(tool_name)
        if tool is None:
            results.append(f"{tool_name}: tool not found")
            continue

        try:
            raw_result = await tool.ainvoke(tool_args)
            results.append(f"{tool_name}({tool_args}) => {raw_result}")
        except Exception as exc:
            logger.warning(f"Tool {tool_name} execution failed: {exc}")
            results.append(f"{tool_name}({tool_args}) => failed: {exc}")

    return results
