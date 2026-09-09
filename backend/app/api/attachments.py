from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import Repos, authorize_learner, get_current_user, get_repos
from app.store.attachments import (
    ALLOWED_MIME,
    MAX_IMAGE_BYTES,
    MAX_UPLOAD_BYTES,
    AttachmentMeta,
    extract_text,
)
from app.store.users import User

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


@router.post("/{learner_id}", response_model=AttachmentMeta, status_code=201)
async def upload_attachment(
    learner_id: str,
    file: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> AttachmentMeta:
    authorize_learner(learner_id, user, repos)

    kind = ALLOWED_MIME.get(file.content_type or "")
    if kind is None:
        raise HTTPException(status_code=415, detail="unsupported file type")

    data = await file.read()
    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_UPLOAD_BYTES
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file too large")

    if conversation_id is not None:
        conversation = repos.conversations.get(conversation_id)
        if conversation is None or conversation.learner_id != learner_id:
            raise HTTPException(status_code=404, detail="conversation not found")

    assert file.content_type is not None
    extracted_text = extract_text(data, file.content_type)

    return repos.attachments.create(
        learner_id=learner_id,
        conversation_id=conversation_id,
        filename=file.filename or "attachment",
        mime_type=file.content_type,
        kind=kind,
        size_bytes=len(data),
        data=data,
        extracted_text=extracted_text,
    )


@router.get("/{learner_id}/{attachment_id}")
def download_attachment(
    learner_id: str,
    attachment_id: str,
    repos: Repos = Depends(get_repos),
    user: User = Depends(get_current_user),
) -> Response:
    authorize_learner(learner_id, user, repos)
    attachment = repos.attachments.get_with_data(attachment_id, learner_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    return Response(
        content=attachment.data,
        media_type=attachment.mime_type,
        headers={"Content-Disposition": f'inline; filename="{attachment.filename}"'},
    )
