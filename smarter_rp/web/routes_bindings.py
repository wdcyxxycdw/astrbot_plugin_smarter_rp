from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Request, Response, status

from smarter_rp.tavern_bindings import AccountBinding, ChatBinding
from smarter_rp.web.auth import require_token

router = APIRouter(prefix="/api/bindings", dependencies=[Depends(require_token)])


class AccountBindingBody(BaseModel):
    character_id: str = Field(alias="characterId")


def account_binding_to_json(binding: AccountBinding) -> dict[str, object]:
    return {
        "adapter": binding.adapter,
        "platform": binding.platform,
        "accountId": binding.account_id,
        "characterId": binding.character_id,
        "createdAt": binding.created_at,
        "updatedAt": binding.updated_at,
    }


def chat_binding_to_json(binding: ChatBinding) -> dict[str, object]:
    return {
        "adapter": binding.adapter,
        "platform": binding.platform,
        "accountId": binding.account_id,
        "sessionId": binding.session_id,
        "characterId": binding.character_id,
        "chatId": binding.chat_id,
        "createdAt": binding.created_at,
        "updatedAt": binding.updated_at,
    }


@router.get("/accounts")
def list_account_bindings(request: Request) -> dict[str, object]:
    bindings = request.app.state.bindings.list_account_bindings()
    return {"bindings": [account_binding_to_json(binding) for binding in bindings]}


@router.put("/accounts/{adapter}/{platform}/{account_id}")
def put_account_binding(
    request: Request,
    adapter: str,
    platform: str,
    account_id: str,
    body: AccountBindingBody,
) -> dict[str, object]:
    binding = request.app.state.bindings.set_account_binding(adapter, platform, account_id, body.character_id)
    return {"binding": account_binding_to_json(binding)}


@router.delete("/accounts/{adapter}/{platform}/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account_binding(request: Request, adapter: str, platform: str, account_id: str) -> Response:
    request.app.state.bindings.delete_account_binding(adapter, platform, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/chats")
def list_chat_bindings(request: Request) -> dict[str, object]:
    bindings = request.app.state.bindings.list_chat_bindings()
    return {"bindings": [chat_binding_to_json(binding) for binding in bindings]}


@router.delete("/chats/{adapter}/{platform}/{account_id}/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_binding(
    request: Request,
    adapter: str,
    platform: str,
    account_id: str,
    session_id: str,
) -> Response:
    request.app.state.bindings.delete_chat_binding(adapter, platform, account_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
