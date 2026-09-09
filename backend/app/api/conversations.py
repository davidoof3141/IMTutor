from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Repos, authorize_learner, get_current_user, get_repos
from app.store.conversations import Conversation, Message
from app.store.users import User

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _load_owned(learner_id: str, conversation_id: str, repos: Repos) -> Conversation:
    conversation = repos.conversations.get(conversation_id)
    if conversation is None or conversation.learner_id != learner_id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.get("/{learner_id}", response_model=list[Conversation])
def list_conversations(
    learner_id: str,
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> list[Conversation]:
    authorize_learner(learner_id, user, repos)
    return repos.conversations.for_learner(learner_id)


@router.post("/{learner_id}", response_model=Conversation, status_code=201)
def create_conversation(
    learner_id: str,
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> Conversation:
    authorize_learner(learner_id, user, repos)
    study_mode = repos.study_mode.get(learner_id)
    return repos.conversations.create(learner_id, study_mode)


@router.get("/{learner_id}/{conversation_id}/messages", response_model=list[Message])
def conversation_messages(
    learner_id: str,
    conversation_id: str,
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> list[Message]:
    authorize_learner(learner_id, user, repos)
    _load_owned(learner_id, conversation_id, repos)
    return repos.conversations.messages(conversation_id)
