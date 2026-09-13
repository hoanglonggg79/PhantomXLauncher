from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from sidecar.services import instances as svc
from sidecar.services.instances import InstanceError

router = APIRouter(tags=["instances"])

NOT_FOUND_MARKERS = ("not found", "unreadable")
CONFLICT_MARKERS = ("already exists", "is running")


class CreateInstanceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    version_id: str = Field(min_length=1, max_length=64)
    loader: str = Field(default="vanilla")
    loader_version: str = Field(default="", max_length=64)


class LaunchRequest(BaseModel):
    username: Optional[str] = Field(default=None, max_length=32)
    ram: Optional[int] = Field(default=None, ge=512, le=65536)


class CloneInstanceRequest(BaseModel):
    """Mirrors the Clone dialog: name plus the three opt-out groups."""

    new_name: str = Field(min_length=1, max_length=64)
    copy_saves: bool = True
    copy_configs: bool = True
    copy_mods: bool = True


class UpdateInstanceRequest(BaseModel):
    """Both fields optional: omit one to leave it untouched."""

    name: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=4000)


class OpenFolderRequest(BaseModel):
    subdir: str = Field(default="", max_length=32)


def _fail(e: InstanceError) -> HTTPException:
    pinned = getattr(e, "status", None)
    if pinned:
        return HTTPException(status_code=pinned, detail=str(e))

    message = str(e)
    lowered = message.lower()
    if any(m in lowered for m in NOT_FOUND_MARKERS):
        status = 404
    elif any(m in lowered for m in CONFLICT_MARKERS):
        status = 409
    else:
        status = 400
    return HTTPException(status_code=status, detail=message)


@router.get("")
def list_instances() -> Dict[str, Any]:
    items = svc.list_instances()
    return {"instances": items, "count": len(items)}


@router.post("/create", status_code=202)
def create_instance(body: CreateInstanceRequest) -> Dict[str, Any]:
    """Create instance.json and start installing. Returns {instance, task_id}."""
    try:
        return svc.create_instance(
            body.name, body.version_id, body.loader, body.loader_version
        )
    except InstanceError as e:
        raise _fail(e) from e


@router.get("/{name}")
def get_instance(name: str) -> Dict[str, Any]:
    try:
        return {"instance": svc.serialize(svc.get_instance(name))}
    except InstanceError as e:
        raise _fail(e) from e


@router.post("/{name}/install", status_code=202)
def install_instance(name: str) -> Dict[str, Any]:
    try:
        return svc.install_instance(name)
    except InstanceError as e:
        raise _fail(e) from e


@router.post("/{name}/launch", status_code=202)
def launch_instance(name: str, body: Optional[LaunchRequest] = None) -> Dict[str, Any]:
    """Start the game. Returns {instance, task_id, username}."""
    payload = body or LaunchRequest()
    try:
        return svc.launch_instance(name, payload.username, payload.ram)
    except InstanceError as e:
        raise _fail(e) from e


@router.post("/{name}/stop")
def stop_instance(name: str) -> Dict[str, Any]:
    try:
        return svc.stop_instance(name)
    except InstanceError as e:
        raise _fail(e) from e


@router.delete("/{name}")
def delete_instance(
    name: str,
    response: Response,
    delete_files: bool = Query(
        default=False,
        description="False removes the instance from the list only; True wipes the folder.",
    ),
) -> Dict[str, Any]:
    """
    Delete an instance. Wiping the files is task-based (202 + task_id) because it
    can be gigabytes; removing it from the list only is immediate (200).
    """
    try:
        result = svc.delete_instance(name, delete_files=delete_files)
    except InstanceError as e:
        raise _fail(e) from e

    if result.get("task_id"):
        response.status_code = 202
    return result


@router.post("/{name}/clone", status_code=202)
def clone_instance(name: str, body: CloneInstanceRequest) -> Dict[str, Any]:
    """Physical copy onto a worker thread. Returns {source, name, path, task_id}."""
    try:
        return svc.clone_instance(
            name,
            body.new_name,
            copy_saves=body.copy_saves,
            copy_configs=body.copy_configs,
            copy_mods=body.copy_mods,
        )
    except InstanceError as e:
        raise _fail(e) from e


@router.patch("/{name}")
def update_instance(name: str, body: UpdateInstanceRequest) -> Dict[str, Any]:
    """Rename (moves the folder) and/or edit notes. Returns {instance, changed}."""
    try:
        return svc.update_instance(name, new_name=body.name, notes=body.notes)
    except InstanceError as e:
        raise _fail(e) from e


@router.post("/{name}/open-folder")
def open_instance_folder(
    name: str, body: Optional[OpenFolderRequest] = None
) -> Dict[str, Any]:
    """Reveal the instance folder (or a whitelisted subfolder) in the file manager."""
    payload = body or OpenFolderRequest()
    try:
        return svc.open_instance_folder(name, payload.subdir)
    except InstanceError as e:
        raise _fail(e) from e
