from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal

# --- Типы ---

IntentType = Literal["BIOLOGY", "INFRASTRUCTURE", "KNOWLEDGE", "CHITCHAT"]

ResponseType = Literal[
    "text",
    "image",
    "file",
    "map",
    "clarification",
    "clarification_map",
    "debug",
]

# --- Входящий запрос ---

class UserRequest(BaseModel):
    user_id: str
    query: str
    context: List[Dict[str, str]] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)

# --- Ответ диалоговой системы (Telegram + HTTP API) ---

class SystemResponse(BaseModel):
    text: str
    intent: str
    response_type: str = "text"
    buttons: List[List[Dict[str, Any]]] = Field(default_factory=list)
    media_url: Optional[str] = None
    debug_info: Optional[Any] = None

# --- Состояние диалога (хранится в Redis между запросами) ---

class DialogueState(BaseModel):
    intent: Optional[str] = None
    object_name: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)
    last_action: Optional[str] = None
    timestamp: float = 0.0

# --- Ответ action handlers (граница между application и adapters/backend) ---

class CoreResponse(BaseModel):
    type: ResponseType
    content: str = ""
    buttons: List[List[Dict[str, Any]]] = Field(default_factory=list)
    static_map: Optional[str] = None
    interactive_map: Optional[str] = None
    used_objects: List[Dict[str, Any]] = Field(default_factory=list)
    debug_info: Optional[str] = None
