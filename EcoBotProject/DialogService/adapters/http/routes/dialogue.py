import os
import logging
from fastapi import APIRouter, Body, HTTPException, Request

from application.dialogue.orchestrator import DialogueSystem
from domain.entities import UserRequest
from infrastructure.storage.redis_storage import RedisContextManager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/test_query")
async def test_query(request: Request, data: dict = Body(...)):
    query = data.get("query")
    user_id = data.get("user_id", "test_user")
    request_settings = data.get("settings", {})

    session = request.app.state.session
    cm = RedisContextManager(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)

    history_data = await cm.get_context(user_id)
    history = history_data.get("history", [])

    formatted_context = []
    for entry in reversed(history[:3]):
        formatted_context.append({"role": "user", "content": entry.get("query", "")})
        resp_text = entry.get("response_content", "") or entry.get("text", "")
        formatted_context.append({"role": "assistant", "content": str(resp_text)})

    ds = DialogueSystem(provider="qwen", session=session, context_manager=cm)
    request = UserRequest(
        user_id=user_id,
        query=query,
        context=formatted_context,
        settings=request_settings,
    )

    responses = await ds.process_request(request)

    final_text = responses[0].text if responses else ""
    new_entry = {"query": query, "response_content": final_text}
    history_data["history"] = [new_entry] + history[:10]
    await cm.set_context(user_id, history_data)

    output = []
    for r in responses:
        item = {"type": r.response_type, "buttons": r.buttons, "debug_info": r.debug_info}
        if r.response_type == "image":
            item["content"] = r.media_url
        else:
            item["content"] = r.text
            if r.media_url:
                item["static_map"] = r.media_url
        output.append(item)
    return output


@router.post("/clear_context")
async def clear_context(data: dict = Body(...)):
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="No user_id")

    cm = RedisContextManager()
    await cm.delete_context(user_id)
    if cm.redis_client:
        await cm.redis_client.delete(f"clarify_options:{user_id}")
        await cm.redis_client.delete(f"fallback_attributes:{user_id}")

    return {"status": "cleared"}
