"""Model wrapper for ChatOllama and streaming helper."""

from __future__ import annotations

import httpx
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from .constants import C, AGENT_FLYING_ON
from .utils import cprint


class ModelUnavailableError(RuntimeError):
    """Raised when the Ollama backend cannot be reached."""


model = ChatOllama(model=AGENT_FLYING_ON, reasoning=True, temperature=0)


def stream_model(
    system_prompt: str,
    user_content: str,
    label: str = "",
    color: str = C.AMBER,
    show_thinking: bool = True,
) -> str:
    msgs = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

    output_parts: list[str] = []
    thinking_open = False
    output_open = False

    try:
        for chunk in model.stream(msgs):
            thinking = ""
            if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
                thinking = (
                    chunk.additional_kwargs.get("reasoning_content")
                    or chunk.additional_kwargs.get("thinking")
                    or ""
                )
            if thinking:
                if not thinking_open:
                    cprint(
                        f"\n  {C.DIM}{C.ITAL}∴ {label} · thinking{C.RESET}",
                        "",
                        kind="thinking",
                        emit=show_thinking,
                    )
                    thinking_open = True
                cprint(
                    thinking,
                    C.GREY + C.DIM,
                    end="",
                    flush=True,
                    kind="thinking",
                    emit=show_thinking,
                )

            text = chunk.content if hasattr(chunk, "content") else ""
            if not isinstance(text, str):
                text = str(text)
            if text:
                if thinking_open and not output_open:
                    cprint("")
                    cprint(f"  {color}▶ {label}{C.RESET}", "")
                    output_open = True
                elif not output_open:
                    output_open = True
                    if label:
                        cprint(f"  {color}▶ {label}{C.RESET}", "")
                cprint(text, C.BONE, end="", flush=True)
                output_parts.append(text)
    except httpx.ConnectError as exc:
        raise ModelUnavailableError(
            "Ollama is not reachable. Start the Ollama server and retry."
        ) from exc

    if output_open or thinking_open:
        cprint("")
    return "".join(output_parts)
